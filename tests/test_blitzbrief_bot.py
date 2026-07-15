import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import blitzbrief_bot as bot


class FakeDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        base = cls(2026, 6, 1, 22, 30, tzinfo=timezone.utc)
        return base.astimezone(tz) if tz is not None else base.replace(tzinfo=None)


class BlitzBriefTests(unittest.TestCase):
    def test_elpais_feed_matches_dc_creator(self):
        xml = """<?xml version="1.0"?>
        <rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
          <item>
            <title>Yo estaba allí</title>
            <link>https://elpais.com/opinion/2026-06-01/yo-estaba-alli.html</link>
            <dc:creator>Juan José Millás García</dc:creator>
            <pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate>
            <category>Opinión</category>
            <description><![CDATA[Entradilla]]></description>
          </item>
          <item>
            <title>Riki Blanco: el que pueda hacer</title>
            <link>https://elpais.com/opinion/2026-06-01/riki-blanco.html</link>
            <dc:creator>Riki Blanco</dc:creator>
            <pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate>
          </item>
        </channel></rss>
        """

        with patch.object(bot, "_fetch_page", return_value=(xml, None)):
            articles = bot.fetch_elpais_articles(
                "Juan José Millás",
                "juan-jose-millas",
                datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Yo estaba allí")
        self.assertEqual(
            articles[0]["url"],
            "https://elpais.com/opinion/2026-06-01/yo-estaba-alli.html",
        )
        self.assertEqual(articles[0]["subtitle"], "Entradilla")
        self.assertEqual(articles[0]["tag"], "Opinión")

    def test_elpais_feed_supports_multiple_creators_and_latest_only(self):
        xml = """<?xml version="1.0"?>
        <rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
          <item>
            <title>Más reciente</title>
            <link>https://elpais.com/opinion/2026-06-01/reciente.html</link>
            <dc:creator>Otra Persona, Juan José Millás</dc:creator>
            <pubDate>Mon, 01 Jun 2026 11:00:00 +0000</pubDate>
          </item>
          <item>
            <title>Más antiguo</title>
            <link>https://elpais.com/opinion/2026-06-01/antiguo.html</link>
            <dc:creator>Juan José Millás</dc:creator>
            <pubDate>Mon, 01 Jun 2026 09:00:00 +0000</pubDate>
          </item>
        </channel></rss>
        """

        with patch.object(bot, "_fetch_page", return_value=(xml, None)):
            articles = bot.fetch_elpais_articles(
                "Juan José Millás",
                "juan-jose-millas",
                datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        self.assertEqual([article["title"] for article in articles], ["Más reciente"])

    def test_elplural_uses_google_news_for_benjamin_prado(self):
        xml = """<?xml version="1.0"?>
        <rss><channel><title>Google News</title>
          <item>
            <title>Una nueva columna - El Plural</title>
            <link>https://news.google.com/articles/ok</link>
            <description><![CDATA[<a href="https://www.elplural.com/opinion/benjamin-prado/columna.html">Ver</a>]]></description>
            <pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate>
          </item>
        </channel></rss>
        """

        with patch.object(bot, "_fetch_page", return_value=(xml, None)) as fetch_page:
            articles = bot.fetch_elplural_articles(
                "Benjamín Prado",
                "benjamin-prado",
                datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        self.assertEqual(len(articles), 1)
        self.assertEqual(
            articles[0]["title"],
            "Una nueva columna",
        )
        self.assertEqual(
            articles[0]["url"],
            "https://www.elplural.com/opinion/benjamin-prado/columna.html",
        )
        self.assertEqual(articles[0]["source"], "El Plural")
        self.assertIn("site%3Aelplural.com", fetch_page.call_args.args[0])

    def test_elplural_falls_back_to_tag_page_when_google_news_is_empty(self):
        empty_google_news_xml = """<?xml version="1.0"?>
        <rss><channel><title>Google News</title></channel></rss>
        """
        tag_html = """
        <html><body>
          <div class="item">
            <h3><a href="/opinion/benjamin-prado/directa.html">Columna directa</a></h3>
            <p class="excerpt">Entradilla</p>
          </div>
        </body></html>
        """
        article_html = """
        <html><head>
          <meta property="article:published_time" content="2026-06-01T10:00:00+00:00">
        </head></html>
        """

        with patch.object(
            bot,
            "_fetch_page",
            side_effect=[
                (empty_google_news_xml, None),
                (tag_html, None),
                (article_html, None),
            ],
        ):
            articles = bot.fetch_elplural_articles(
                "Benjamín Prado",
                "benjamin-prado",
                datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        self.assertEqual([article["title"] for article in articles], ["Columna directa"])
        self.assertEqual(
            articles[0]["url"],
            "https://www.elplural.com/opinion/benjamin-prado/directa.html",
        )

    def test_elplural_google_news_503_does_not_alert_when_direct_page_works(self):
        direct_html = "<html><body></body></html>"
        errors = []

        with patch.object(
            bot,
            "_fetch_page",
            side_effect=[
                (None, "503 Server Error: Service Unavailable"),
                (direct_html, None),
            ],
        ):
            articles = bot.fetch_elplural_articles(
                "Benjamín Prado",
                "benjamin-prado",
                datetime(2026, 6, 1, tzinfo=timezone.utc),
                errors,
            )

        self.assertEqual(articles, [])
        self.assertEqual(errors, [])

    def test_google_news_rss_filters_out_non_author_entries(self):
        xml = """<?xml version="1.0"?>
        <rss><channel><title>Google News</title>
          <item>
            <title>Manuel Jabois analiza la política española</title>
            <link>https://news.google.com/articles/ok</link>
            <pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate>
          </item>
          <item>
            <title>Última hora en España y economía</title>
            <link>https://news.google.com/articles/bad</link>
            <pubDate>Mon, 01 Jun 2026 11:00:00 +0000</pubDate>
          </item>
        </channel></rss>
        """

        with patch.object(bot, "_fetch_page", return_value=(xml, None)):
            articles = bot.fetch_rss_articles(
                "Manuel Jabois",
                "https://news.google.com/rss/search?q=Manuel+Jabois&hl=es&gl=ES&ceid=ES:es",
                datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Manuel Jabois analiza la política española")

    def test_google_news_rss_applies_site_filter_when_present(self):
        xml = """<?xml version="1.0"?>
        <rss><channel><title>Google News</title>
          <item>
            <title>Manuel Jabois firma su nueva columna</title>
            <link>https://news.google.com/articles/ok</link>
            <description><![CDATA[<a href="https://elpais.com/opinion/2026-06-01/columna.html">Ver</a>]]></description>
            <pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate>
          </item>
          <item>
            <title>Manuel Jabois comenta la actualidad</title>
            <link>https://news.google.com/articles/bad</link>
            <description><![CDATA[<a href="https://example.com/opinion/2026-06-01/ajeno.html">Ver</a>]]></description>
            <pubDate>Mon, 01 Jun 2026 11:00:00 +0000</pubDate>
          </item>
        </channel></rss>
        """

        with patch.object(bot, "_fetch_page", return_value=(xml, None)):
            articles = bot.fetch_rss_articles(
                "Manuel Jabois",
                "https://news.google.com/rss/search?q=Manuel+Jabois+site:elpais.com&hl=es&gl=ES&ceid=ES:es",
                datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Manuel Jabois firma su nueva columna")

    def test_fetch_page_retries_403_with_curl_cffi(self):
        class ForbiddenResponse:
            encoding = "utf-8"
            content = b""

            def raise_for_status(self):
                raise bot.requests.HTTPError("403 Client Error: Forbidden")

        class OkResponse:
            encoding = "utf-8"
            content = b"<rss></rss>"

            def raise_for_status(self):
                return None

        fake_cffi = type("FakeCffi", (), {"get": staticmethod(lambda *args, **kwargs: OkResponse())})

        with patch.object(bot, "HAS_CURL_CFFI", True), \
             patch.object(bot, "cffi_requests", fake_cffi), \
             patch.object(bot.requests, "get", return_value=ForbiddenResponse()):
            text, err = bot._fetch_page("https://example.com/feed")

        self.assertEqual(text, "<rss></rss>")
        self.assertIsNone(err)

    def test_fetch_page_uses_configured_rss_fallback(self):
        class Response:
            encoding = "utf-8"

            def __init__(self, url):
                self.url = url
                self.content = b"<rss></rss>" if url.endswith("feed.xml") else b""

            def raise_for_status(self):
                if not self.url.endswith("feed.xml"):
                    raise bot.requests.HTTPError("403 Client Error: Forbidden")

        with patch.object(bot, "HAS_CURL_CFFI", False), \
             patch.object(bot.requests, "get", side_effect=lambda url, **kwargs: Response(url)):
            text, err = bot._fetch_page("https://www.error500.net/feed")

        self.assertEqual(text, "<rss></rss>")
        self.assertIsNone(err)

    def test_articles_are_not_marked_seen_when_send_fails(self):
        article = {
            "title": "Titulo",
            "url": "https://example.com/a1",
            "author": "Autor",
            "source": "El Pais",
            "date": datetime(2026, 3, 27, tzinfo=timezone.utc),
            "subtitle": "",
            "tag": "",
        }
        saved_states = []

        with patch.dict(bot.ELPAIS_AUTHORS, {"Autor": "slug"}, clear=True), \
             patch.dict(bot.ELPLURAL_AUTHORS, {}, clear=True), \
             patch.dict(bot.RSS_AUTHORS, {}, clear=True), \
             patch.dict(bot.PODCAST_SOURCES, {}, clear=True), \
             patch.object(bot, "GEMINI_API_KEY", ""), \
             patch.object(bot, "load_sent_runs", return_value={}), \
             patch.object(bot, "save_sent_runs"), \
             patch.object(bot, "load_seen_articles", return_value=[]), \
             patch.object(bot, "fetch_elpais_articles", return_value=[article]), \
             patch.object(bot, "send_articles_digest", return_value=False), \
             patch.object(bot, "fetch_tomorrow_weather_block", return_value=""), \
             patch.object(bot, "fetch_bitcoin_block", return_value=""), \
             patch.object(bot, "fetch_box_workouts_notice", return_value=None), \
             patch.object(bot, "save_seen_articles", side_effect=lambda seen: saved_states.append(set(seen))):
            bot.run_digest(mode="evening")

        self.assertEqual(saved_states, [])

    def test_duplicate_article_urls_are_sent_once_per_run(self):
        article = {
            "title": "Misma columna",
            "url": "https://example.com/a1",
            "author": "Autor",
            "source": "El Pais",
            "date": datetime(2026, 3, 27, tzinfo=timezone.utc),
            "subtitle": "",
            "tag": "",
        }
        sent_digests = []
        saved_states = []

        with patch.dict(bot.ELPAIS_AUTHORS, {"Autor": "slug", "Autor 2": "slug2"}, clear=True), \
             patch.dict(bot.ELPLURAL_AUTHORS, {}, clear=True), \
             patch.dict(bot.RSS_AUTHORS, {}, clear=True), \
             patch.dict(bot.PODCAST_SOURCES, {}, clear=True), \
             patch.object(bot, "GEMINI_API_KEY", ""), \
             patch.object(bot, "load_sent_runs", return_value={}), \
             patch.object(bot, "save_sent_runs"), \
             patch.object(bot, "load_seen_articles", return_value=[]), \
             patch.object(bot, "fetch_elpais_articles", return_value=[article]), \
             patch.object(bot, "send_articles_digest", side_effect=lambda articles: sent_digests.append(articles) or True), \
             patch.object(bot, "fetch_tomorrow_weather_block", return_value=""), \
             patch.object(bot, "fetch_bitcoin_block", return_value=""), \
             patch.object(bot, "fetch_box_workouts_notice", return_value=None), \
             patch.object(bot, "save_seen_articles", side_effect=lambda seen: saved_states.append(list(seen))):
            bot.run_digest(mode="evening")

        self.assertEqual(len(sent_digests), 1)
        self.assertEqual(len(sent_digests[0]), 1)
        self.assertEqual(sent_digests[0][0]["title"], "Misma columna")
        self.assertEqual(saved_states, [[bot.article_hash(article["url"])]])

    def test_elplural_naive_article_date_is_comparable(self):
        tag_html = """
        <html><body>
          <div class="item">
            <h3><a href="/opinion/benjamin-prado/directa.html">Columna directa</a></h3>
          </div>
        </body></html>
        """
        article_html = """
        <html><head>
          <meta property="article:published_time" content="2026-06-01T10:00:00">
        </head></html>
        """

        with patch.object(bot, "_fetch_page", side_effect=[(tag_html, None), (article_html, None)]):
            articles = bot._fetch_elplural_tag_articles(
                "Benjamín Prado",
                "benjamin-prado",
                datetime(2026, 6, 1, tzinfo=timezone.utc),
            )

        self.assertEqual([article["title"] for article in articles], ["Columna directa"])
        self.assertEqual(articles[0]["date"].tzinfo, timezone.utc)

    def test_only_successful_podcast_sends_are_marked_seen(self):
        segments = [
            {
                "title": "Segmento 1",
                "audio_url": "https://example.com/audio1.mp3",
                "label": "Podcast",
                "date": datetime(2026, 3, 27, tzinfo=timezone.utc),
                "duration": "12:34",
            },
            {
                "title": "Segmento 2",
                "audio_url": "https://example.com/audio2.mp3",
                "label": "Podcast",
                "date": datetime(2026, 3, 27, tzinfo=timezone.utc),
                "duration": "10:00",
            },
        ]
        saved_states = []
        first_hash = bot.article_hash(segments[0]["audio_url"])
        second_hash = bot.article_hash(segments[1]["audio_url"])

        with patch.dict(bot.ELPAIS_AUTHORS, {}, clear=True), \
             patch.dict(bot.ELPLURAL_AUTHORS, {}, clear=True), \
             patch.dict(bot.RSS_AUTHORS, {}, clear=True), \
             patch.dict(bot.PODCAST_SOURCES, {"Podcast": {"feed": "feed", "filter": "x"}}, clear=True), \
             patch.object(bot, "GEMINI_API_KEY", ""), \
             patch.object(bot, "load_sent_runs", return_value={}), \
             patch.object(bot, "save_sent_runs"), \
             patch.object(bot, "load_seen_articles", return_value=[]), \
             patch.object(bot, "fetch_podcast_segments", return_value=segments), \
             patch.object(bot, "fetch_weather_block", return_value=""), \
             patch.object(bot, "send_telegram_audio", side_effect=[True, False]), \
             patch.object(bot, "fetch_box_workouts_notice", return_value=None), \
             patch.object(bot, "save_seen_articles", side_effect=lambda seen: saved_states.append(set(seen))):
            bot.run_digest(mode="morning")

        self.assertEqual(saved_states, [{first_hash}])
        self.assertNotIn(second_hash, saved_states[0])

    def test_scheduled_digest_skips_when_already_sent_today(self):
        key = bot.digest_run_key("morning")

        with patch.object(bot, "load_sent_runs", return_value={key: True}), \
             patch.object(bot, "send_news_briefing") as send_news:
            bot.run_digest(mode="morning")

        send_news.assert_not_called()

    def test_scheduled_digest_marks_run_after_successful_send(self):
        saved_runs = []

        with patch.object(bot, "GEMINI_API_KEY", "key"), \
             patch.object(bot, "load_sent_runs", return_value={}), \
             patch.object(bot, "save_sent_runs", side_effect=lambda runs: saved_runs.append(dict(runs))), \
             patch.object(bot, "send_news_briefing", return_value=True), \
             patch.object(bot, "fetch_weather_block", return_value=""), \
             patch.object(bot, "load_seen_articles", return_value=[]), \
             patch.object(bot, "fetch_podcast_segments", return_value=[]), \
             patch.object(bot, "fetch_box_workouts_notice", return_value=None):
            bot.run_digest(mode="morning")

        self.assertEqual(saved_runs, [{bot.digest_run_key("morning"): True}])

    def test_scheduled_digest_not_marked_when_morning_briefing_fails_but_weather_succeeds(self):
        save_calls = []

        with patch.dict(bot.PODCAST_SOURCES, {}, clear=True), \
             patch.object(bot, "GEMINI_API_KEY", "key"), \
             patch.object(bot, "load_sent_runs", return_value={}), \
             patch.object(bot, "save_sent_runs", side_effect=lambda runs: save_calls.append(dict(runs))), \
             patch.object(bot, "send_news_briefing", return_value=False), \
             patch.object(bot, "fetch_weather_block", return_value="☀️ Málaga: 20°C"), \
             patch.object(bot, "_send_plain_message", return_value=True), \
             patch.object(bot, "load_seen_articles", return_value=[]), \
             patch.object(bot, "fetch_box_workouts_notice", return_value=None):
            bot.run_digest(mode="morning")

        self.assertEqual(save_calls, [])

    def test_scheduled_digest_marked_when_evening_inbox_empty(self):
        save_calls = []

        with patch.dict(bot.ELPAIS_AUTHORS, {}, clear=True), \
             patch.dict(bot.ELPLURAL_AUTHORS, {}, clear=True), \
             patch.dict(bot.RSS_AUTHORS, {}, clear=True), \
             patch.object(bot, "load_sent_runs", return_value={}), \
             patch.object(bot, "save_sent_runs", side_effect=lambda runs: save_calls.append(dict(runs))), \
             patch.object(bot, "load_seen_articles", return_value=[]), \
             patch.object(bot, "fetch_tomorrow_weather_block", return_value=""), \
             patch.object(bot, "fetch_bitcoin_block", return_value=""), \
             patch.object(bot, "fetch_box_workouts_notice", return_value=None):
            bot.run_digest(mode="evening")

        self.assertEqual(save_calls, [{bot.digest_run_key("evening"): True}])

    def test_empty_digest_header_uses_madrid_timezone(self):
        with patch.object(bot, "datetime", FakeDateTime):
            message = bot.format_telegram_message([])

        self.assertIn(" 2 de ", message)
        self.assertNotIn(" 1 de ", message)

    def test_articles_digest_rich_html_groups_authors_and_escapes_content(self):
        articles = [
            {
                "title": "Titulo con <alerta>",
                "url": "https://example.com/a?x=1&y=2",
                "author": "Autor Uno",
                "source": "El Pais",
                "subtitle": "Entradilla con <detalle>",
                "tag": "Opinion",
            },
            {
                "title": "Segundo texto",
                "url": "https://example.com/b",
                "author": "Autor Uno",
                "source": "El Pais",
                "subtitle": "",
                "tag": "",
            },
        ]

        html = bot._format_articles_digest_rich_html(articles)

        self.assertIn("<h1>📰 Tu prensa del día</h1>", html)
        self.assertIn("<h2>✍️ Autor Uno (El Pais)</h2>", html)
        self.assertIn('href="https://example.com/a?x=1&amp;y=2"', html)
        self.assertIn("Titulo con &lt;alerta&gt;", html)
        self.assertIn("<i>Entradilla con &lt;detalle&gt;</i>", html)
        self.assertEqual(html.count("<li>"), 2)

    def test_send_articles_digest_uses_rich_message_with_html_fallback(self):
        article = {
            "title": "Titulo",
            "url": "https://example.com/a1",
            "author": "Autor",
            "source": "El Pais",
            "subtitle": "Entradilla",
            "tag": "Opinion",
        }

        with patch.object(bot, "_send_rich_html_message", return_value=True) as send_rich:
            sent = bot.send_articles_digest([article])

        self.assertTrue(sent)
        args, kwargs = send_rich.call_args
        self.assertIn("<h1>📰 Tu prensa del día</h1>", args[0])
        self.assertIn("<h2>✍️ Autor (El Pais)</h2>", args[0])
        self.assertIn("fallback_html", kwargs)
        self.assertIn("fallback_text", kwargs)
        self.assertIn("Titulo", kwargs["fallback_text"])

    def test_bitcoin_block_includes_price_and_change(self):
        class FakeResponse:
            ok = True
            text = ""

            def raise_for_status(self):
                return None

            def json(self):
                return {"bitcoin": {"eur": 61234.0, "eur_24h_change": 4.2}}

        with patch.object(bot.requests, "get", return_value=FakeResponse()):
            block = bot.fetch_bitcoin_block()

        self.assertEqual(block, "📈 Bitcoin: 61.234 € (+4.2%)")

    def test_all_briefing_sources_have_profiles(self):
        all_sources = {**bot.NEWS_SOURCES, **bot.SPORTS_SOURCES}

        missing = [
            name for name in all_sources
            if bot._source_profile(name)["orientation"] == "no clasificada"
        ]

        self.assertEqual(missing, [])

    def test_news_headlines_include_source_profile(self):
        xml = """<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Titular de prueba</title>
            <description>Descripción</description>
            <pubDate>Sun, 07 Jun 2026 00:30:00 +0000</pubDate>
          </item>
        </channel></rss>
        """

        with patch.dict(bot.NEWS_SOURCES, {"ABC": "feed"}, clear=True), \
             patch.dict(bot.SPORTS_SOURCES, {}, clear=True), \
             patch.object(bot, "datetime", FakeDateTime), \
             patch.object(bot, "_fetch_page", return_value=(xml, None)):
            headlines = bot.fetch_news_headlines()

        self.assertEqual(len(headlines), 1)
        self.assertEqual(headlines[0]["profile"]["orientation"], "conservador / centro-derecha")
        self.assertEqual(headlines[0]["profile"]["reliability"], "media-alta")
        self.assertEqual(headlines[0]["published_at"], "2026-06-07T00:30:00+00:00")

    def test_news_headlines_include_link(self):
        xml = """<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Titular de prueba</title>
            <link>https://example.com/noticia</link>
            <pubDate>Sun, 07 Jun 2026 00:30:00 +0000</pubDate>
          </item>
        </channel></rss>
        """

        with patch.dict(bot.NEWS_SOURCES, {"ABC": "feed"}, clear=True), \
             patch.dict(bot.SPORTS_SOURCES, {}, clear=True), \
             patch.object(bot, "datetime", FakeDateTime), \
             patch.object(bot, "_fetch_page", return_value=(xml, None)):
            headlines = bot.fetch_news_headlines()

        self.assertEqual(headlines[0]["url"], "https://example.com/noticia")

    def test_curate_news_headlines_groups_duplicate_titles(self):
        headlines = [
            {
                "source": "El País",
                "title": "El Gobierno aprueba una nueva ley de vivienda",
                "description": "",
                "profile": bot._source_profile("El País"),
            },
            {
                "source": "ABC",
                "title": "El Gobierno aprueba la nueva ley de vivienda",
                "description": "",
                "profile": bot._source_profile("ABC"),
            },
        ]

        curated = bot.curate_news_headlines(headlines)

        self.assertEqual(len(curated), 1)
        self.assertEqual(curated[0]["source_count"], 2)
        self.assertEqual(curated[0]["sources"], ["ABC", "El País"])

    def test_curate_news_headlines_prioritizes_interests(self):
        headlines = [
            {
                "source": "BBC Mundo",
                "title": "Una noticia internacional genérica",
                "description": "",
                "profile": bot._source_profile("BBC Mundo"),
            },
            {
                "source": "Google Gemini Blog",
                "title": "Google presenta novedades de Gemini para IA",
                "description": "",
                "profile": bot._source_profile("Google Gemini Blog"),
            },
        ]

        curated = bot.curate_news_headlines(headlines)

        self.assertEqual(curated[0]["source"], "Google Gemini Blog")
        self.assertIn("Gemini", curated[0]["why_it_matters"])

    def test_interest_matching_uses_word_boundaries(self):
        headline = {
            "title": "Los socios deciden hoy el futuro del club",
            "description": "Una crónica institucional sin tecnología.",
        }

        self.assertEqual(bot._matched_interests(headline), [])

    def test_generate_news_briefing_includes_importance_context(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": "🏛 España: Test"}]}}
                    ]
                }

        def fake_post(url, headers, json, timeout):
            captured["prompt"] = json["contents"][0]["parts"][0]["text"]
            return FakeResponse()

        headline = {
            "source": "ABC",
            "sources": ["ABC", "El País"],
            "orientations": ["conservador / centro-derecha", "centro-izquierda / progresista"],
            "title": "El Gobierno aprueba una nueva ley de vivienda",
            "description": "",
            "importance_score": 2.0,
            "why_it_matters": "Conecta con tus intereses: economía personal.",
        }

        with patch.object(bot, "GEMINI_API_KEY", "key"), \
             patch.object(bot.requests, "post", side_effect=fake_post):
            result = bot.generate_news_briefing([headline])

        self.assertEqual(result, "🏛 España: Test")
        self.assertIn("criterio de selección", captured["prompt"])
        self.assertIn("prioridad: 2.0", captured["prompt"])
        self.assertIn("ABC, El País", captured["prompt"])

    def test_generate_news_briefing_prompt_defines_por_que_importa(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": "🏛 España: Test"}]}}
                    ]
                }

        def fake_post(url, headers, json, timeout):
            captured["prompt"] = json["contents"][0]["parts"][0]["text"]
            return FakeResponse()

        headline = {
            "source": "ABC",
            "title": "El Gobierno aprueba una nueva ley",
            "description": "",
        }

        with patch.object(bot, "GEMINI_API_KEY", "key"), \
             patch.object(bot.requests, "post", side_effect=fake_post):
            bot.generate_news_briefing([headline])

        self.assertIn("NUNCA debe repetir ni parafrasear el titular", captured["prompt"])
        self.assertIn("OMITE la línea", captured["prompt"])

    def test_generate_news_briefing_prompt_marks_selection_signal_as_not_copyable(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": "🏛 España: Test"}]}}
                    ]
                }

        def fake_post(url, headers, json, timeout):
            captured["prompt"] = json["contents"][0]["parts"][0]["text"]
            return FakeResponse()

        headline = {
            "source": "ABC",
            "title": "El Gobierno aprueba una nueva ley",
            "description": "",
            "why_it_matters": "Conecta con tus intereses: economía personal.",
        }

        with patch.object(bot, "GEMINI_API_KEY", "key"), \
             patch.object(bot.requests, "post", side_effect=fake_post):
            bot.generate_news_briefing([headline])

        self.assertIn("uso interno, NO copiar", captured["prompt"])
        self.assertNotIn("| por qué importa:", captured["prompt"])

    def test_generate_news_briefing_filters_ungrounded_tech_block(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": (
                                            "🏛 España: El Gobierno aprueba una nueva ley.\n"
                                            "   Por qué importa: Afecta a la vivienda.\n"
                                            "🤖 Tech: Google lanza Gemma 4 12B para laptops.\n"
                                            "   Por qué importa: Lleva IA local a portátiles."
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }

        headlines = [
            {
                "source": "ABC",
                "title": "El Gobierno aprueba una nueva ley de vivienda",
                "description": "",
                "profile": bot._source_profile("ABC"),
            }
        ]

        with patch.object(bot, "GEMINI_API_KEY", "key"), \
             patch.object(bot.requests, "post", return_value=FakeResponse()):
            result = bot.generate_news_briefing(headlines)

        self.assertIn("🏛 España:", result)
        self.assertNotIn("🤖 Tech:", result)
        self.assertNotIn("Gemma 4 12B", result)

    def test_generate_news_briefing_keeps_grounded_tech_block(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": (
                                            "🤖 Tech: OpenAI presenta mejoras para ChatGPT.\n"
                                            "   Por qué importa: Cambia flujos de trabajo con IA."
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }

        headlines = [
            {
                "source": "OpenAI Blog",
                "title": "OpenAI presenta mejoras para ChatGPT",
                "description": "",
                "profile": bot._source_profile("OpenAI Blog"),
            }
        ]

        with patch.object(bot, "GEMINI_API_KEY", "key"), \
             patch.object(bot.requests, "post", return_value=FakeResponse()):
            result = bot.generate_news_briefing(headlines)

        self.assertIn("🤖 Tech: OpenAI presenta mejoras para ChatGPT.", result)

    def test_generate_news_briefing_sends_api_key_as_header_not_query_string(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": "🏛 España: Test"}]}}
                    ]
                }

        def fake_post(url, headers, json, timeout):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse()

        headline = {
            "source": "ABC",
            "title": "El Gobierno aprueba una nueva ley",
            "description": "",
        }

        with patch.object(bot, "GEMINI_API_KEY", "key"), \
             patch.object(bot.requests, "post", side_effect=fake_post):
            bot.generate_news_briefing([headline])

        self.assertNotIn("key=", captured["url"])
        self.assertEqual(captured["headers"]["x-goog-api-key"], "key")

    def test_news_briefing_html_highlights_why_it_matters(self):
        html = bot._format_news_briefing_html(
            "📰 BRIEFING",
            "🌍 Internacional: Test\n   Por qué importa: Afecta a <mercados>.",
        )

        self.assertIn("↳ <b>Por qué importa:</b> Afecta a", html)
        self.assertIn("&lt;mercados&gt;.", html)

    def test_news_briefing_rich_html_uses_structured_blocks(self):
        html = bot._format_news_briefing_rich_html(
            "📰 BRIEFING",
            "🌍 Internacional: Test\n   Por qué importa: Afecta a <mercados>.",
            "\n\n📅 PARTIDOS HOY:\nReal Madrid - Málaga",
        )

        self.assertIn("<h1>📰 BRIEFING</h1>", html)
        self.assertIn("<h2>🌍 Internacional</h2>", html)
        self.assertIn("<p>Test</p>", html)
        self.assertIn("<blockquote><b>Por qué importa:</b> Afecta a &lt;mercados&gt;.</blockquote>", html)
        self.assertIn("<details open><summary>Partidos de hoy</summary><ul>", html)
        self.assertIn("<li>Real Madrid - Málaga</li>", html)

    def test_news_briefing_html_renders_section_without_why_it_matters(self):
        html = bot._format_news_briefing_html(
            "📰 BRIEFING",
            "🌍 Internacional: Test sin línea de por qué importa",
        )

        self.assertIn("Test sin línea de por qué importa", html)
        self.assertNotIn("Por qué importa", html)

    def test_news_briefing_rich_html_renders_section_without_why_it_matters(self):
        html = bot._format_news_briefing_rich_html(
            "📰 BRIEFING",
            "🌍 Internacional: Test sin línea de por qué importa",
        )

        self.assertIn("<h2>🌍 Internacional</h2>", html)
        self.assertIn("<p>Test sin línea de por qué importa</p>", html)
        self.assertNotIn("<blockquote>", html)

    def test_preview_news_briefing_does_not_send_to_telegram(self):
        headline = {
            "source": "ABC",
            "title": "El Gobierno aprueba una nueva ley",
            "description": "",
        }

        with patch.object(bot, "fetch_news_headlines", return_value=[headline]), \
             patch.object(bot, "generate_news_briefing", return_value="🏛 España: Test") as gen, \
             patch.object(bot, "_send_rich_html_message") as send_rich, \
             patch.object(bot, "send_telegram_message") as send_plain:
            bot.preview_news_briefing()

        gen.assert_called_once()
        send_rich.assert_not_called()
        send_plain.assert_not_called()

    def test_send_rich_html_message_uses_send_rich_message_payload(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": True}

        def fake_post(url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return FakeResponse()

        with patch.object(bot, "TELEGRAM_BOT_TOKEN", "token"), \
             patch.object(bot, "TELEGRAM_CHAT_ID", "123"), \
             patch.object(bot.requests, "post", side_effect=fake_post):
            sent = bot._send_rich_html_message("<h1>Briefing</h1>")

        self.assertTrue(sent)
        self.assertTrue(captured["url"].endswith("/sendRichMessage"))
        self.assertEqual(captured["json"]["chat_id"], "123")
        self.assertEqual(
            captured["json"]["rich_message"],
            {"html": "<h1>Briefing</h1>", "skip_entity_detection": True},
        )
        self.assertEqual(captured["timeout"], 15)

    def test_send_rich_html_message_falls_back_to_html(self):
        calls = []

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": False, "description": "unsupported"}

        def fake_post(url, json, timeout):
            calls.append((url, json))
            return FakeResponse()

        with patch.object(bot, "TELEGRAM_BOT_TOKEN", "token"), \
             patch.object(bot, "TELEGRAM_CHAT_ID", "123"), \
             patch.object(bot.requests, "post", side_effect=fake_post), \
             patch.object(bot, "_send_html_message", return_value=True) as send_html:
            sent = bot._send_rich_html_message(
                "<h1>Rich</h1>",
                fallback_html="<b>HTML</b>",
                fallback_text="plain",
            )

        self.assertTrue(sent)
        self.assertEqual(len(calls), 1)
        send_html.assert_called_once_with("<b>HTML</b>", fallback_text="plain")

    def test_get_updates_sends_allowed_updates_as_json(self):
        captured = {}

        class FakeResponse:
            def json(self):
                return {"ok": True, "result": []}

        def fake_get(url, params, timeout):
            captured["params"] = params
            return FakeResponse()

        with patch.object(bot.requests, "get", side_effect=fake_get):
            bot._get_updates(offset=5)

        self.assertEqual(captured["params"]["allowed_updates"], '["message"]')
        self.assertEqual(captured["params"]["offset"], 5)

    def test_get_updates_logs_warning_when_not_ok(self):
        class FakeResponse:
            def json(self):
                return {"ok": False, "error_code": 400, "description": "Bad Request"}

        with patch.object(bot.requests, "get", return_value=FakeResponse()):
            with self.assertLogs(bot.log, level="WARNING") as logs:
                result = bot._get_updates()

        self.assertEqual(result, [])
        self.assertTrue(
            any("getUpdates devolvió error" in message for message in logs.output)
        )

    def test_get_updates_returns_result_when_ok(self):
        class FakeResponse:
            def json(self):
                return {"ok": True, "result": [{"update_id": 5}]}

        with patch.object(bot.requests, "get", return_value=FakeResponse()):
            result = bot._get_updates()

        self.assertEqual(result, [{"update_id": 5}])

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

        with patch.object(bot, "TELEGRAM_BOT_TOKEN", "token"), \
             patch.object(bot, "TELEGRAM_CHAT_ID", "123"), \
             patch.object(
                 bot.requests, "post",
                 side_effect=lambda *a, **k: FakeResponse(next(responses)),
             ), \
             patch.object(
                 bot, "_send_plain_message",
                 side_effect=lambda t: plain_calls.append(t) or True,
             ):
            sent = bot._send_html_message(text, fallback_text="FALLBACK TEXT")

        self.assertTrue(sent)
        self.assertEqual(len(plain_calls), 1)
        self.assertIn("B" * 2000, plain_calls[0])
        self.assertNotIn("A" * 2000, plain_calls[0])
        self.assertNotIn("FALLBACK TEXT", plain_calls[0])

    def test_send_html_message_first_chunk_failure_resends_whole_fallback(self):
        text = ("A" * 2000) + "\n\n" + ("B" * 2000)
        plain_calls = []

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": False}

        with patch.object(bot, "TELEGRAM_BOT_TOKEN", "token"), \
             patch.object(bot, "TELEGRAM_CHAT_ID", "123"), \
             patch.object(bot.requests, "post", return_value=FakeResponse()), \
             patch.object(
                 bot, "_send_plain_message",
                 side_effect=lambda t: plain_calls.append(t) or True,
             ):
            sent = bot._send_html_message(text, fallback_text="FALLBACK TEXT")

        self.assertTrue(sent)
        self.assertEqual(plain_calls, ["FALLBACK TEXT"])

    def test_upcoming_box_week_targets_next_monday_to_sunday(self):
        madrid = ZoneInfo("Europe/Madrid")

        # Miércoles: apunta a la semana que empieza el próximo lunes.
        url, start, end = bot._upcoming_box_week(
            datetime(2026, 7, 8, 9, 0, tzinfo=madrid)
        )
        self.assertEqual(start, date(2026, 7, 13))
        self.assertEqual(end, date(2026, 7, 19))
        self.assertEqual(
            url, "https://boxolimpo.com/entrenamientos-13-07-2026-al-19-07-2026"
        )

        # Domingo de esa misma semana: sigue apuntando a la siguiente.
        url_sun, start_sun, _ = bot._upcoming_box_week(
            datetime(2026, 7, 12, 20, 0, tzinfo=madrid)
        )
        self.assertEqual(start_sun, date(2026, 7, 13))
        self.assertEqual(
            url_sun, "https://boxolimpo.com/entrenamientos-13-07-2026-al-19-07-2026"
        )

        # Al pasar al lunes, avanza al siguiente bloque semanal.
        _, start_mon, end_mon = bot._upcoming_box_week(
            datetime(2026, 7, 13, 9, 0, tzinfo=madrid)
        )
        self.assertEqual(start_mon, date(2026, 7, 20))
        self.assertEqual(end_mon, date(2026, 7, 26))

    def test_fetch_box_workouts_notice_none_when_not_published(self):
        class FakeResp:
            status_code = 404
            ok = False

        with patch.object(bot.requests, "get", return_value=FakeResp()):
            notice = bot.fetch_box_workouts_notice(
                datetime(2026, 7, 8, 9, 0, tzinfo=ZoneInfo("Europe/Madrid"))
            )

        self.assertIsNone(notice)

    def test_fetch_box_workouts_notice_returns_dict_when_published(self):
        class FakeResp:
            status_code = 200
            ok = True

        with patch.object(bot.requests, "get", return_value=FakeResp()):
            notice = bot.fetch_box_workouts_notice(
                datetime(2026, 7, 8, 9, 0, tzinfo=ZoneInfo("Europe/Madrid"))
            )

        self.assertIsNotNone(notice)
        self.assertEqual(
            notice["url"],
            "https://boxolimpo.com/entrenamientos-13-07-2026-al-19-07-2026",
        )
        self.assertEqual(notice["start"], date(2026, 7, 13))

    def test_box_workouts_notice_sent_once_and_marked_seen(self):
        notice = {
            "url": "https://boxolimpo.com/entrenamientos-13-07-2026-al-19-07-2026",
            "start": date(2026, 7, 13),
            "end": date(2026, 7, 19),
        }
        notice_hash = bot.article_hash(notice["url"])
        saved_states = []

        with patch.dict(bot.ELPAIS_AUTHORS, {}, clear=True), \
             patch.dict(bot.ELPLURAL_AUTHORS, {}, clear=True), \
             patch.dict(bot.RSS_AUTHORS, {}, clear=True), \
             patch.dict(bot.PODCAST_SOURCES, {}, clear=True), \
             patch.object(bot, "GEMINI_API_KEY", ""), \
             patch.object(bot, "load_sent_runs", return_value={}), \
             patch.object(bot, "save_sent_runs"), \
             patch.object(bot, "load_seen_articles", return_value=[]), \
             patch.object(bot, "fetch_weather_block", return_value=""), \
             patch.object(bot, "fetch_box_workouts_notice", return_value=notice), \
             patch.object(bot, "send_box_workouts_notice", return_value=True) as send_box, \
             patch.object(bot, "save_seen_articles", side_effect=lambda seen: saved_states.append(list(seen))):
            bot.run_digest(mode="morning")

        send_box.assert_called_once_with(notice)
        self.assertEqual(saved_states, [[notice_hash]])

    def test_box_workouts_notice_not_resent_when_already_seen(self):
        notice = {
            "url": "https://boxolimpo.com/entrenamientos-13-07-2026-al-19-07-2026",
            "start": date(2026, 7, 13),
            "end": date(2026, 7, 19),
        }
        notice_hash = bot.article_hash(notice["url"])

        with patch.dict(bot.ELPAIS_AUTHORS, {}, clear=True), \
             patch.dict(bot.ELPLURAL_AUTHORS, {}, clear=True), \
             patch.dict(bot.RSS_AUTHORS, {}, clear=True), \
             patch.dict(bot.PODCAST_SOURCES, {}, clear=True), \
             patch.object(bot, "GEMINI_API_KEY", ""), \
             patch.object(bot, "load_sent_runs", return_value={}), \
             patch.object(bot, "save_sent_runs"), \
             patch.object(bot, "load_seen_articles", return_value=[notice_hash]), \
             patch.object(bot, "fetch_weather_block", return_value=""), \
             patch.object(bot, "fetch_box_workouts_notice", return_value=notice), \
             patch.object(bot, "send_box_workouts_notice", return_value=True) as send_box, \
             patch.object(bot, "save_seen_articles"):
            bot.run_digest(mode="morning")

        send_box.assert_not_called()


if __name__ == "__main__":
    unittest.main()
