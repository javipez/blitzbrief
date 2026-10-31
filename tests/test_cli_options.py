import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

import blitzbrief_bot as bot
import blitzhealth as health
from cli_options import reject_unknown_options


class RejectUnknownOptionsTests(unittest.TestCase):
    def _rechaza(self, valid, argv):
        """Ejecuta la comprobación esperando que falle; devuelve lo que avisa."""
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as salida:
            reject_unknown_options(valid, argv)
        self.assertEqual(salida.exception.code, 2)
        return stderr.getvalue()

    def test_opciones_validas_o_ninguna_pasan_sin_mas(self):
        reject_unknown_options(["--serve", "--morning"], [])
        reject_unknown_options(["--serve", "--morning"], ["--morning"])
        reject_unknown_options(["--serve", "--morning"], ["--serve", "--morning"])

    def test_opcion_mal_escrita_sugiere_la_buena(self):
        aviso = self._rechaza(["--preview-partidos", "--serve"], ["--preview-partido"])
        self.assertIn("Opción desconocida: --preview-partido", aviso)
        self.assertIn("¿Querías decir --preview-partidos?", aviso)
        self.assertIn("Opciones válidas: --preview-partidos, --serve", aviso)

    def test_opcion_que_no_se_parece_a_nada_no_inventa_sugerencias(self):
        aviso = self._rechaza(["--serve"], ["--xyz"])
        self.assertIn("Opción desconocida: --xyz", aviso)
        self.assertNotIn("Querías decir", aviso)

    def test_basta_una_mala_entre_varias_buenas(self):
        aviso = self._rechaza(["--serve", "--morning"], ["--morning", "--evenig"])
        self.assertIn("--evenig", aviso)


class BotMainTests(unittest.TestCase):
    """El main del bot: qué se ejecuta según las opciones."""

    def _main(self, *argv):
        with patch.object(bot.sys, "argv", ["blitzbrief_bot.py", *argv]), \
             patch.object(bot, "load_authors"), \
             patch.object(bot, "run_digest") as digest, \
             patch.object(bot, "preview_fixtures") as preview, \
             patch.object(bot, "serve") as serve:
            bot.main()
        return digest, preview, serve

    def test_opcion_mal_escrita_no_lanza_el_digest(self):
        with patch.object(bot.sys, "argv", ["blitzbrief_bot.py", "--preview-partido"]), \
             patch.object(bot, "load_authors") as load_authors, \
             patch.object(bot, "run_digest") as digest, \
             redirect_stderr(io.StringIO()), \
             self.assertRaises(SystemExit):
            bot.main()
        # Si hubiese llegado a llamarlo, el envío habría sido real
        digest.assert_not_called()
        load_authors.assert_not_called()

    def test_sin_opciones_lanza_el_digest_completo(self):
        digest, preview, serve = self._main()
        digest.assert_called_once_with(notify_empty=True, mode="full")
        preview.assert_not_called()
        serve.assert_not_called()

    def test_cada_opcion_lanza_su_modo(self):
        digest, _, _ = self._main("--morning")
        digest.assert_called_once_with(mode="morning")

        digest, _, _ = self._main("--evening")
        digest.assert_called_once_with(notify_empty=True, mode="evening")

        digest, preview, _ = self._main("--preview-partidos")
        preview.assert_called_once_with()
        digest.assert_not_called()

    def test_con_varias_opciones_gana_la_de_siempre(self):
        # Se conserva el orden de antes: --serve va por delante de --morning
        digest, _, serve = self._main("--morning", "--serve")
        serve.assert_called_once_with()
        digest.assert_not_called()


class HealthMainTests(unittest.TestCase):
    def test_opcion_mal_escrita_no_envia_el_weekend(self):
        with patch.object(health.sys, "argv", ["blitzhealth.py", "--preview-weeknd"]), \
             patch.object(health, "fetch_all_sources") as fetch, \
             patch.object(health, "preview_weekend_digest") as preview, \
             redirect_stderr(io.StringIO()) as stderr, \
             self.assertRaises(SystemExit):
            health.main()
        fetch.assert_not_called()
        preview.assert_not_called()
        self.assertIn("¿Querías decir --preview-weekend?", stderr.getvalue())

    def test_weekend_desde_telegram_no_lee_las_opciones_del_bot(self):
        # /weekend llama a blitzhealth.main() dentro del proceso del bot,
        # que se arrancó con --serve. Esa opción no es del Weekend y no
        # debe hacer que se rechace: el digest tiene que llegar a generarse.
        parada = RuntimeError("basta con saber que llegó hasta aquí")
        with patch.object(bot.sys, "argv", ["blitzbrief_bot.py", "--serve"]), \
             patch.object(health, "fetch_all_sources", side_effect=parada) as fetch, \
             patch.object(bot, "send_telegram_message"), \
             redirect_stderr(io.StringIO()) as stderr:
            bot.run_weekend_digest()

        fetch.assert_called_once()
        self.assertNotIn("Opción desconocida", stderr.getvalue())

    def test_preview_weekend_sigue_funcionando(self):
        with patch.object(health.sys, "argv", ["blitzhealth.py", "--preview-weekend"]), \
             patch.object(health, "fetch_all_sources") as fetch, \
             patch.object(health, "preview_weekend_digest") as preview:
            health.main()
        preview.assert_called_once_with()
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
