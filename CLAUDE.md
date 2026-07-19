# BlitzBrief_bot

## Qué es
Bot de Telegram que cada mañana envía un briefing de noticias generado con IA
(Gemini) y un digest de artículos nuevos de columnistas favoritos (El País,
El Plural, RSS). También manda el resumen semanal "Blitz Weekend" los
domingos. Corre en producción como servicio systemd en el VPS `bots-01`.

## Comandos
- Arrancar en local (digest completo, una vez): `python blitzbrief_bot.py`
- Modo bot interactivo (escucha comandos de Telegram): `python blitzbrief_bot.py --serve`
- Otros modos: `--morning`, `--evening`, `--preview-briefing` (prueba el
  briefing de IA sin enviarlo a Telegram)
- Digest dominical (Blitz Weekend): `python blitzhealth.py`
  (modo `--preview-weekend`: prueba el digest semanal sin enviarlo a
  Telegram, mostrando la puntuación de relevancia de cada artículo)
- Tests: `pytest tests/ -v`
- Instalar dependencias: `pip install -r requirements.txt`

Variables de entorno necesarias en local: `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`.

## Particularidades de este repo
- En producción no se usa GitHub Actions para los digests (solo para tests
  en CI); el bot corre en el VPS bajo systemd. Un `git push` no actualiza el
  proceso en marcha — hace falta `git pull` + `sudo systemctl restart
  blitzbrief` en el VPS (ver memoria del proyecto para detalles de acceso).
- El script no usa `.env`/dotenv: las variables se leen directamente de
  `os.environ`, y en el VPS las inyecta systemd.
- `curl_cffi` imita el TLS fingerprint de un navegador real porque El País
  devuelve 403 a peticiones de `requests` normales en `/autor/<slug>/`. Es
  opcional (fallback a `requests` si no está instalado).
- Los autores a seguir se gestionan en `authors.json`, editable también por
  Telegram (`/add`, `/remove`) — no es solo config estática.
- `.blitzbrief_seen_articles.json` evita reenviar artículos y avisos
  duplicados (incluye el aviso de entrenos del box, que solo debe llegar una
  vez por semana).
- El scraping es de HTML, no de APIs oficiales: si un medio cambia su web,
  el parser correspondiente puede romperse y necesitar ajuste.
- El script hace una petición por autor sin concurrencia agresiva, a
  propósito, para ser respetuoso con los servidores.

## Lecciones aprendidas
(Cuando el usuario señale un error repetido en este repo, añadir aquí una
regla de una línea que lo evite. No añadir nada sin que lo pida. Máximo 10
líneas: si se llena, proponer cuál borrar.)
