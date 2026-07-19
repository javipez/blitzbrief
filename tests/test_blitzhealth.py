import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import blitzhealth as health


class BlitzHealthWeekendTests(unittest.TestCase):
    def test_fetch_rss_articles_uses_published_when_no_pubdate(self):
        # Sin <pubDate> mezclado con etiquetas al estilo Atom sueltas
        # (<published>/<updated>) sin espacio de nombres: reproduce el
        # bug de truthiness de ElementTree sin depender de la resolución
        # de namespace de <entry>/<title> en feeds Atom reales, que es un
        # problema aparte y no forma parte de este fix.
        xml = """<?xml version="1.0"?>
        <rss><channel>
          <title>Blog</title>
          <item>
            <title>Entrada</title>
            <link>https://example.com/entrada</link>
            <published>2026-06-10T09:00:00Z</published>
          </item>
        </channel></rss>
        """

        with patch.object(health, "_fetch_page", return_value=(xml, None)):
            articles = health.fetch_rss_articles(
                "Autor", "https://example.com/feed",
                datetime(2026, 6, 9, tzinfo=timezone.utc),
            )

        self.assertEqual(len(articles), 1)
        self.assertEqual(
            articles[0]["date"], datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
        )

    def test_fetch_rss_articles_prefers_published_over_updated(self):
        xml = """<?xml version="1.0"?>
        <rss><channel>
          <title>Blog</title>
          <item>
            <title>Entrada</title>
            <link>https://example.com/entrada</link>
            <published>2026-06-10T09:00:00Z</published>
            <updated>2026-06-12T09:00:00Z</updated>
          </item>
        </channel></rss>
        """

        with patch.object(health, "_fetch_page", return_value=(xml, None)):
            articles = health.fetch_rss_articles(
                "Autor", "https://example.com/feed",
                datetime(2026, 6, 9, tzinfo=timezone.utc),
            )

        self.assertEqual(len(articles), 1)
        self.assertEqual(
            articles[0]["date"], datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
        )

    def test_generate_weekend_digest_prompt_includes_all_sections(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": "📚 PANORAMA SEMANAL\nTest"}]}}
                    ]
                }

        def fake_post(url, headers, json, timeout):
            captured["prompt"] = json["contents"][0]["parts"][0]["text"]
            return FakeResponse()

        health_data = {
            "Marcos Vázquez": [
                {
                    "title": "Proteína y fuerza",
                    "url": "https://example.com/proteina",
                    "date": datetime(2026, 6, 14, tzinfo=timezone.utc),
                    "subtitle": "Resumen salud",
                    "content": "",
                }
            ]
        }
        author_articles = [
            {
                "title": "Columna de la semana",
                "url": "https://example.com/columna",
                "author": "Autor",
                "source": "El País",
                "date": datetime(2026, 6, 14, tzinfo=timezone.utc),
                "subtitle": "Resumen columna",
            }
        ]
        longform_articles = [
            {
                "title": "Análisis internacional",
                "url": "https://example.com/contexto",
                "author": "El Orden Mundial",
                "source": "El Orden Mundial",
                "date": datetime(2026, 6, 14, tzinfo=timezone.utc),
                "subtitle": "Resumen largo",
            }
        ]

        with patch.object(health, "GEMINI_API_KEY", "key"), \
             patch.object(health.requests, "post", side_effect=fake_post):
            digest = health.generate_weekend_digest(
                health_data,
                author_articles,
                longform_articles,
            )

        self.assertEqual(digest, "📚 PANORAMA SEMANAL\nTest")
        self.assertIn("SALUD / FITNESS / LONGEVIDAD", captured["prompt"])
        self.assertIn("COLUMNAS Y AUTORES", captured["prompt"])
        self.assertIn("LECTURAS LARGAS / CONTEXTO", captured["prompt"])
        self.assertIn("Proteína y fuerza", captured["prompt"])
        self.assertIn("Columna de la semana", captured["prompt"])
        self.assertIn("Análisis internacional", captured["prompt"])

    def test_generate_weekend_digest_sends_api_key_as_header_not_query_string(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": "📚 PANORAMA SEMANAL\nTest"}]}}
                    ]
                }

        def fake_post(url, headers, json, timeout):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse()

        author_articles = [
            {
                "title": "Columna de la semana",
                "url": "https://example.com/columna",
                "author": "Autor",
                "source": "El País",
                "date": datetime(2026, 6, 14, tzinfo=timezone.utc),
                "subtitle": "Resumen columna",
            }
        ]

        with patch.object(health, "GEMINI_API_KEY", "key"), \
             patch.object(health.requests, "post", side_effect=fake_post):
            health.generate_weekend_digest({}, author_articles, [])

        self.assertNotIn("key=", captured["url"])
        self.assertEqual(captured["headers"]["x-goog-api-key"], "key")

    def test_digest_rich_html_formats_sections_lists_and_links(self):
        html = health._format_digest_rich_html(
            "📚 BLITZ WEEKEND",
            "📚 PANORAMA SEMANAL\n"
            "Una idea con <detalle>.\n\n"
            "🎯 IDEAS PARA QUEDARSE\n"
            "1. Primera idea\n"
            "- Segunda idea\n"
            "URL: https://example.com/a?x=1&y=2",
        )

        self.assertIn("<h1>📚 BLITZ WEEKEND</h1>", html)
        self.assertIn("<h2>📚 PANORAMA SEMANAL</h2>", html)
        self.assertIn("<p>Una idea con &lt;detalle&gt;.</p>", html)
        self.assertIn("<li>Primera idea</li>", html)
        self.assertIn("<li>Segunda idea</li>", html)
        self.assertIn('href="https://example.com/a?x=1&amp;y=2"', html)

    def test_send_telegram_digest_uses_rich_message(self):
        captured = {}

        with patch.object(health, "TELEGRAM_BOT_TOKEN", "token"), \
             patch.object(health, "TELEGRAM_CHAT_ID", "123"), \
             patch.object(health, "_send_rich_html_message", return_value=True) as send_rich:
            sent = health.send_telegram_digest("📚 PANORAMA SEMANAL\nTest")

        self.assertTrue(sent)
        args, kwargs = send_rich.call_args
        captured["rich_html"] = args[0]
        self.assertIn("<h1>📚 BLITZ WEEKEND", captured["rich_html"])
        self.assertIn("fallback_html", kwargs)
        self.assertIn("fallback_text", kwargs)
        self.assertIn("📚 BLITZ WEEKEND", kwargs["fallback_text"])

    def test_send_html_message_second_chunk_failure_only_resends_failed_chunk(self):
        text = ("A" * 2000) + "\n\n" + ("B" * 2000)
        plain_calls = []
        responses = iter([{"ok": True}, {"ok": False}])

        class FakeResponse:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                return None

            def json(self):
                return self._data

        with patch.object(health, "TELEGRAM_BOT_TOKEN", "token"), \
             patch.object(health, "TELEGRAM_CHAT_ID", "123"), \
             patch.object(
                 health.requests, "post",
                 side_effect=lambda *a, **k: FakeResponse(next(responses)),
             ), \
             patch.object(
                 health, "send_telegram_text",
                 side_effect=lambda t: plain_calls.append(t) or True,
             ):
            sent = health._send_html_message(text, fallback_text="FALLBACK TEXT")

        self.assertTrue(sent)
        self.assertEqual(len(plain_calls), 1)
        self.assertIn("B" * 2000, plain_calls[0])
        self.assertNotIn("A" * 2000, plain_calls[0])
        self.assertNotIn("FALLBACK TEXT", plain_calls[0])

    def test_cluster_weekend_articles_groups_shared_theme_across_authors(self):
        article_a = {
            "title": "La inflación golpea a las familias españolas",
            "author": "Autor X",
        }
        article_b = {
            "title": "Familias españolas sufren la inflación disparada",
            "author": "Autor Y",
        }
        article_c = {
            "title": "El nuevo iPhone sorprende por su batería",
            "author": "Autor Z",
        }

        clusters = health._cluster_weekend_articles([article_a, article_b, article_c])

        sizes = sorted(len(group) for group in clusters)
        self.assertEqual(sizes, [1, 2])
        themed_cluster = next(group for group in clusters if len(group) == 2)
        self.assertIn(article_a, themed_cluster)
        self.assertIn(article_b, themed_cluster)

    def test_curate_weekend_articles_prioritizes_cross_author_theme_over_recency(self):
        now = datetime.now(timezone.utc)
        older_a = {
            "title": "La inflación golpea a las familias españolas",
            "author": "Autor X",
            "url": "https://example.com/a",
            "date": now - timedelta(days=6),
            "content": "",
        }
        older_b = {
            "title": "Familias españolas sufren la inflación disparada",
            "author": "Autor Y",
            "url": "https://example.com/b",
            "date": now - timedelta(days=6) + timedelta(hours=1),
            "content": "",
        }
        newer_isolated = {
            "title": "El nuevo iPhone sorprende por su batería",
            "author": "Autor Z",
            "url": "https://example.com/c",
            "date": now - timedelta(hours=2),
            "content": "",
        }

        curated = health.curate_weekend_articles(
            [older_a, older_b, newer_isolated], max_items=2
        )

        self.assertEqual(len(curated), 2)
        # El artículo más viejo pero corroborado por otro autor gana al
        # artículo más reciente pero aislado: la señal de tema compartido
        # pesa más que la pura recencia.
        self.assertEqual(curated[0]["cluster_size"], 2)
        self.assertGreater(curated[0]["relevance_score"], curated[1]["relevance_score"])

    def test_curate_weekend_articles_respects_max_items(self):
        now = datetime.now(timezone.utc)
        titles = [
            "El aumento del precio de la vivienda preocupa a los jóvenes",
            "Un nuevo estudio sobre el sueño y la longevidad",
            "La final de baloncesto deja polémica arbitral",
            "Una novela histórica ambientada en el Mediterráneo",
            "El auge de los coches eléctricos en Noruega",
        ]
        articles = [
            {
                "title": title,
                "author": f"Autor {i}",
                "url": f"https://example.com/{i}",
                "date": now - timedelta(days=i),
                "content": "",
            }
            for i, title in enumerate(titles)
        ]

        curated = health.curate_weekend_articles(articles, max_items=2)

        self.assertEqual(len(curated), 2)

    def test_why_weekend_article_matters_labels_cluster_signal(self):
        reason = health._why_weekend_article_matters(
            {"title": "Cualquiera", "content": ""}, cluster_size=2
        )
        self.assertIn("Coincide con", reason)

    def test_why_weekend_article_matters_labels_matched_interest(self):
        reason = health._why_weekend_article_matters(
            {"title": "Reflexión sobre la IA generativa", "content": ""},
            cluster_size=1,
        )
        self.assertIn("Conecta con tus intereses", reason)

    def test_generate_weekend_digest_labels_selection_criteria_as_internal(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": "📚 PANORAMA SEMANAL\nTest"}]}}
                    ]
                }

        def fake_post(url, headers, json, timeout):
            captured["prompt"] = json["contents"][0]["parts"][0]["text"]
            return FakeResponse()

        author_articles = [
            {
                "title": "Columna de la semana",
                "url": "https://example.com/columna",
                "author": "Autor",
                "source": "El País",
                "date": datetime(2026, 6, 14, tzinfo=timezone.utc),
                "subtitle": "Resumen columna",
                "why_relevant": "Coincide con otro 1 autor tratando un tema similar esta semana.",
            }
        ]

        with patch.object(health, "GEMINI_API_KEY", "key"), \
             patch.object(health.requests, "post", side_effect=fake_post):
            health.generate_weekend_digest({}, author_articles, [])

        self.assertIn("criterio de selección (uso interno, NO copiar)", captured["prompt"])
        self.assertIn("Nunca copies la etiqueta", captured["prompt"])
        self.assertIn(
            "Coincide con otro 1 autor tratando un tema similar esta semana.",
            captured["prompt"],
        )

    def test_generate_weekend_digest_prompt_defines_panorama_golden_rule(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": "📚 PANORAMA SEMANAL\nTest"}]}}
                    ]
                }

        def fake_post(url, headers, json, timeout):
            captured["prompt"] = json["contents"][0]["parts"][0]["text"]
            return FakeResponse()

        author_articles = [
            {
                "title": "Columna de la semana",
                "url": "https://example.com/columna",
                "author": "Autor",
                "source": "El País",
                "date": datetime(2026, 6, 14, tzinfo=timezone.utc),
                "subtitle": "Resumen columna",
            }
        ]

        with patch.object(health, "GEMINI_API_KEY", "key"), \
             patch.object(health.requests, "post", side_effect=fake_post):
            health.generate_weekend_digest({}, author_articles, [])

        prompt = captured["prompt"]
        self.assertIn("PROHIBIDO inventar un hilo conductor artificial", prompt)
        self.assertIn("SÍ puedes mencionar una conexión", prompt)
        self.assertIn("El Mundial se analiza esta semana desde la estadística avanzada", prompt)

    def test_preview_weekend_digest_does_not_send_to_telegram(self):
        send_calls = []

        with patch.object(health, "fetch_all_sources", return_value={}), \
             patch.object(health, "fetch_weekend_author_articles", return_value=[]), \
             patch.object(health, "fetch_weekend_longform_articles", return_value=[]), \
             patch.object(
                 health, "generate_weekend_digest", return_value="📚 PANORAMA SEMANAL\nTest"
             ), \
             patch.object(
                 health, "send_telegram_text",
                 side_effect=lambda *a, **k: send_calls.append("text"),
             ), \
             patch.object(
                 health, "send_telegram_digest",
                 side_effect=lambda *a, **k: send_calls.append("digest"),
             ), \
             patch.object(
                 health, "_send_rich_html_message",
                 side_effect=lambda *a, **k: send_calls.append("rich"),
             ):
            health.preview_weekend_digest()

        self.assertEqual(send_calls, [])

    def test_send_html_message_first_chunk_failure_resends_whole_fallback(self):
        text = ("A" * 2000) + "\n\n" + ("B" * 2000)
        plain_calls = []

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": False}

        with patch.object(health, "TELEGRAM_BOT_TOKEN", "token"), \
             patch.object(health, "TELEGRAM_CHAT_ID", "123"), \
             patch.object(health.requests, "post", return_value=FakeResponse()), \
             patch.object(
                 health, "send_telegram_text",
                 side_effect=lambda t: plain_calls.append(t) or True,
             ):
            sent = health._send_html_message(text, fallback_text="FALLBACK TEXT")

        self.assertTrue(sent)
        self.assertEqual(plain_calls, ["FALLBACK TEXT"])


if __name__ == "__main__":
    unittest.main()
