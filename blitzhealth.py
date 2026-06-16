"""
📚 Blitz Weekend — Digest semanal de lecturas → Telegram
========================================================

Scrapea fuentes RSS de salud/fitness, autores y lecturas largas cada
domingo, filtra contenido de los últimos 7 días, genera un resumen con
Gemini y lo envía por Telegram.

Mismo patrón que elpais_telegram_bot.py: requests + ElementTree + Gemini REST.

Uso:
  pip install -r requirements.txt
  export TELEGRAM_BOT_TOKEN="..." TELEGRAM_CHAT_ID="..." GEMINI_API_KEY="..."
  python blitzhealth.py
"""

import os
import sys
import time
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape as html_escape, unescape
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

LOOKBACK_DAYS = 7
TELEGRAM_RICH_MAX_LEN = 32000

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

BASE_DIR = Path(__file__).parent
AUTHORS_FILE = BASE_DIR / "authors.json"

# ── Fuentes RSS ───────────────────────────────────────────────────
HEALTH_SOURCES: dict[str, str] = {
    "Marcos Vázquez": "https://www.fitnessrevolucionario.com/feed/",
    "Peter Attia": "https://peterattiamd.com/feed/",
    "Layne Norton": "https://feeds.captivate.fm/the-dr-layne-norton-podcast/",
    "Steve Magness": "https://stevemagness.substack.com/feed",
}

WEEKEND_LONGFORM_SOURCES: dict[str, str] = {
    "El Orden Mundial": "https://elordenmundial.com/feed/",
}


def _ensure_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Devuelve una fecha comparable con `datetime.now(timezone.utc)`."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("blitzhealth")


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _fetch_page(url: str) -> tuple[Optional[str], Optional[str]]:
    """Descarga una URL y devuelve (contenido, error)."""
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return _decoded_response_text(resp), None
    except requests.RequestException as e:
        log.warning(f"Error al descargar {url}: {e}")
        return None, str(e)


def _decoded_response_text(resp) -> str:
    """Decodifica respuestas RSS/HTML evitando mojibake en feeds UTF-8."""
    encoding = resp.encoding
    if not encoding or encoding.lower() == "iso-8859-1":
        encoding = resp.apparent_encoding or "utf-8"
    return resp.content.decode(encoding, errors="replace")


# ---------------------------------------------------------------------------
# Scraper RSS
# ---------------------------------------------------------------------------

def fetch_rss_articles(
    author_name: str, feed_url: str, cutoff: datetime,
    errors: Optional[list] = None,
) -> list[dict]:
    """Extrae artículos/episodios recientes de un feed RSS/Atom."""
    xml_text, err = _fetch_page(feed_url)
    if not xml_text:
        log.error(f"RSS — {author_name}: {err}")
        if errors is not None and err:
            errors.append(f"{author_name}: {err}")
        return []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning(f"Error al parsear RSS de {feed_url}: {e}")
        return []

    articles: list[dict] = []

    # Nombre de la fuente desde el feed
    channel = root.find("channel")
    source_name = "Blog"
    if channel is not None:
        title_el = channel.find("title")
        if title_el is not None and title_el.text:
            source_name = title_el.text.strip()

    # Buscar items (RSS) o entry (Atom)
    items = root.findall(".//item")
    if not items:
        # Intentar Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//atom:entry", ns)

    for item in items:
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        desc_el = item.find("description")

        # Atom fallbacks
        if link_el is None:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            link_el = item.find("atom:link", ns)
        if pub_el is None:
            pub_el = item.find("published") or item.find(
                "{http://www.w3.org/2005/Atom}published"
            ) or item.find("updated") or item.find(
                "{http://www.w3.org/2005/Atom}updated"
            )

        if title_el is None:
            continue

        title = (title_el.text or "").strip()

        # Extraer URL
        href = ""
        if link_el is not None:
            href = link_el.text or link_el.get("href", "") or ""
        href = href.strip()

        if not href:
            continue

        # Parsear fecha
        pub_date = None
        if pub_el is not None and pub_el.text:
            try:
                pub_date = _ensure_aware_utc(parsedate_to_datetime(pub_el.text))
            except (ValueError, TypeError):
                try:
                    pub_date = _ensure_aware_utc(
                        datetime.fromisoformat(
                            pub_el.text.replace("Z", "+00:00")
                        )
                    )
                except (ValueError, TypeError):
                    pass

        if pub_date and pub_date < cutoff:
            continue

        # Descripción
        subtitle = ""
        if desc_el is not None and desc_el.text:
            subtitle = unescape(desc_el.text)
            subtitle = BeautifulSoup(subtitle, "html.parser").get_text(strip=True)

        # Content:encoded (algunos feeds ponen el contenido completo aquí)
        content_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        full_content = ""
        if content_el is not None and content_el.text:
            full_content = BeautifulSoup(
                unescape(content_el.text), "html.parser"
            ).get_text(strip=True)

        articles.append({
            "title": title,
            "url": href,
            "author": author_name,
            "source": source_name,
            "date": pub_date,
            "subtitle": subtitle[:300],
            "content": full_content[:2000],
        })

    return articles


# ---------------------------------------------------------------------------
# Recopilar todas las fuentes
# ---------------------------------------------------------------------------

def fetch_all_sources(
    errors: Optional[list] = None,
) -> dict[str, list[dict]]:
    """Scrapea las fuentes configuradas y devuelve {autor: [artículos]}.

    Si se pasa `errors`, acumula ahí los fallos de fetch por fuente.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    result: dict[str, list[dict]] = {}

    for author, feed_url in HEALTH_SOURCES.items():
        log.info(f"Scrapeando: {author}")
        articles = fetch_rss_articles(author, feed_url, cutoff, errors)
        result[author] = articles
        if articles:
            log.info(f"  → {len(articles)} artículos/episodios encontrados")
        else:
            log.info(f"  → Sin contenido nuevo esta semana")

    return result


def _load_weekend_authors() -> dict[str, dict[str, str]]:
    """Carga los autores configurados para incluir lecturas del fin de semana."""
    if not AUTHORS_FILE.exists():
        log.warning("No se encontró authors.json; se omiten autores del weekend.")
        return {"elpais": {}, "elplural": {}, "rss": {}}
    try:
        data = json.loads(AUTHORS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning(f"No se pudo leer authors.json: {e}")
        return {"elpais": {}, "elplural": {}, "rss": {}}
    return {
        "elpais": data.get("elpais", {}) or {},
        "elplural": data.get("elplural", {}) or {},
        "rss": data.get("rss", {}) or {},
    }


def fetch_weekend_author_articles(errors: Optional[list] = None) -> list[dict]:
    """Recopila artículos semanales de autores del digest diario."""
    import elpais_telegram_bot as press_bot

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    config = _load_weekend_authors()
    articles: list[dict] = []

    for author, slug in config["elpais"].items():
        log.info(f"[Weekend autores] El País — {author}")
        articles.extend(press_bot.fetch_elpais_articles(author, slug, cutoff, errors))

    for author, slug in config["elplural"].items():
        log.info(f"[Weekend autores] El Plural — {author}")
        articles.extend(press_bot.fetch_elplural_articles(author, slug, cutoff, errors))

    for author, feed_url in config["rss"].items():
        log.info(f"[Weekend autores] RSS — {author}")
        articles.extend(press_bot.fetch_rss_articles(author, feed_url, cutoff, errors))

    articles.sort(
        key=lambda art: art.get("date") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return articles[:12]


def fetch_weekend_longform_articles(errors: Optional[list] = None) -> list[dict]:
    """Recopila lecturas largas/análisis de la semana."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    articles: list[dict] = []
    for source, feed_url in WEEKEND_LONGFORM_SOURCES.items():
        log.info(f"[Weekend lecturas largas] {source}")
        source_articles = fetch_rss_articles(source, feed_url, cutoff, errors)
        for article in source_articles:
            article["author"] = source
            article["source"] = source
        articles.extend(source_articles)

    articles.sort(
        key=lambda art: art.get("date") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return articles[:6]


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def _format_articles_for_prompt(articles: list[dict]) -> str:
    """Convierte una lista de artículos en bloque compacto para Gemini."""
    if not articles:
        return "Sin publicaciones detectadas esta semana.\n"

    content = ""
    for art in articles:
        date_str = art["date"].strftime("%d/%m") if art.get("date") else "?"
        content += f"\n[{date_str}] {art.get('author', art.get('source', 'Fuente'))}: {art['title']}\n"
        content += f"Fuente: {art.get('source', '')}\n"
        content += f"URL: {art['url']}\n"
        if art.get("content"):
            content += f"{art['content'][:1200]}\n"
        elif art.get("subtitle"):
            content += f"{art['subtitle'][:500]}\n"
    return content


def generate_weekend_digest(
    health_data: dict[str, list[dict]],
    author_articles: list[dict],
    longform_articles: list[dict],
) -> Optional[str]:
    """Envía el contenido semanal a Gemini para generar Blitz Weekend."""
    if not GEMINI_API_KEY:
        log.error("Falta GEMINI_API_KEY.")
        return None

    if not health_data and not author_articles and not longform_articles:
        log.info("Sin contenido nuevo esta semana, nada que resumir.")
        return None

    # Construir el bloque de contenido para el prompt
    health_block = ""
    for author, articles in health_data.items():
        health_block += f"\n== {author} ==\n"
        if not articles:
            health_block += "Sin publicaciones detectadas esta semana.\n"
            continue
        for art in articles:
            date_str = art["date"].strftime("%d/%m") if art["date"] else "?"
            health_block += f"\n[{date_str}] {art['title']}\n"
            health_block += f"URL: {art['url']}\n"
            if art.get("content"):
                health_block += f"{art['content'][:1500]}\n"
            elif art.get("subtitle"):
                health_block += f"{art['subtitle']}\n"

    today = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%d/%m/%Y")

    prompt = f"""Hoy es {today}. Eres el editor de Blitz Weekend, un digest dominical de lecturas para una persona que sigue actualidad, columnas, salud, longevidad, deporte, tecnología y análisis internacional.

A partir del contenido publicado esta semana, genera un digest en español con esta estructura exacta:

📚 PANORAMA SEMANAL
3-5 líneas con los temas o lecturas que mejor resumen la semana. Nada genérico.

🧠 SALUD / LONGEVIDAD
Resume lo más importante de salud, fitness y longevidad. Incluye enlaces.

🗞️ COLUMNAS Y AUTORES
Selecciona las mejores lecturas de autores de la semana. No listes todo: prioriza 4-8 piezas. Incluye enlaces.

🌍 LECTURAS LARGAS / CONTEXTO
Resume análisis o textos largos relevantes. Incluye enlaces.

🎯 IDEAS PARA QUEDARSE
5 ideas prácticas o intelectuales para recordar esta semana.

REGLAS:
- Todo en español
- Conciso pero con criterio editorial
- No uses asteriscos ni formato markdown con ** (usa texto plano con los emojis de sección)
- No añadas introducción genérica ni cierre motivacional
- Si una sección no tiene material suficiente, déjala breve en vez de inventar.
- Cada enlace debe ir en una línea URL: ...

SALUD / FITNESS / LONGEVIDAD:
{health_block}

COLUMNAS Y AUTORES:
{_format_articles_for_prompt(author_articles)}

LECTURAS LARGAS / CONTEXTO:
{_format_articles_for_prompt(longform_articles)}"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
        f"?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 8192},
    }

    # Hasta 3 intentos con espera entre ellos: Gemini 2.5 Flash devuelve
    # 503/overload con frecuencia y un solo fallo no debe tirar el digest.
    for attempt in range(3):
        try:
            resp = requests.post(
                url,
                headers={"content-type": "application/json"},
                json=payload,
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts and parts[0].get("text"):
                    return parts[0]["text"]
            log.error(
                f"Respuesta inesperada de Gemini (intento {attempt + 1}): {data}"
            )
        except requests.RequestException as e:
            log.error(
                f"Error al llamar a Gemini API (intento {attempt + 1}): {e}"
            )

        if attempt < 2:
            log.info("Reintentando en 10 segundos...")
            time.sleep(10)

    return None


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _split_message(text: str, max_len: int = 4096) -> list[str]:
    """Parte un mensaje largo en trozos respetando saltos de línea."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        cut = text.rfind("\n\n", 0, max_len)
        if cut == -1:
            cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


def send_telegram_text(text: str) -> bool:
    """Envía un mensaje de texto plano por Telegram (un único chunk)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text[:4000]},
            timeout=15,
        )
        resp.raise_for_status()
        return bool(resp.json().get("ok"))
    except requests.RequestException as e:
        log.error(f"Error al enviar a Telegram: {e}")
        return False


def _format_digest_rich_html(title: str, digest: str) -> str:
    """Convierte el digest de texto en HTML para Rich Messages."""
    blocks = [f"<h1>{html_escape(title)}</h1>"]
    list_open = False

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            blocks.append("</ul>")
            list_open = False

    for raw_line in digest.splitlines():
        line = raw_line.strip()
        if not line:
            close_list()
            continue

        is_section = (
            any(line.startswith(prefix) for prefix in ("📚", "🧠", "🗞️", "🌍", "🎯"))
            and len(line) <= 80
        )
        if is_section:
            close_list()
            blocks.append(f"<h2>{html_escape(line)}</h2>")
            continue

        if line.startswith(("URL: http://", "URL: https://")):
            close_list()
            url = line.removeprefix("URL:").strip()
            safe_url = html_escape(url, quote=True)
            blocks.append(f'<p><a href="{safe_url}">Leer fuente</a></p>')
            continue

        is_bullet = line.startswith(("- ", "• ")) or (
            len(line) > 3 and line[0].isdigit() and line[1:3] in (". ", ") ")
        )
        if is_bullet:
            if not list_open:
                blocks.append("<ul>")
                list_open = True
            item = line[2:].strip() if line[:2] in ("- ", "• ") else line[3:].strip()
            blocks.append(f"<li>{html_escape(item)}</li>")
            continue

        close_list()
        blocks.append(f"<p>{html_escape(line)}</p>")

    close_list()
    return "\n".join(blocks)


def _format_digest_html(title: str, digest: str) -> str:
    """Convierte el digest a HTML compatible con sendMessage."""
    lines = [f"<b>{html_escape(title)}</b>", ""]
    for raw_line in digest.splitlines():
        line = raw_line.strip()
        if line.startswith(("URL: http://", "URL: https://")):
            url = line.removeprefix("URL:").strip()
            safe_url = html_escape(url, quote=True)
            lines.append(f'<a href="{safe_url}">Leer fuente</a>')
        else:
            lines.append(html_escape(raw_line))
    return "\n".join(lines)


def _send_html_message(text: str, fallback_text: str = "") -> bool:
    """Envía HTML clásico por Telegram y cae a texto plano si falla."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chunk in _split_message(text, max_len=3000):
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                log.error(f"Error HTML de Telegram: {data}")
                return send_telegram_text(fallback_text or text)
        except requests.RequestException as e:
            log.error(f"Error al enviar HTML a Telegram: {e}")
            return send_telegram_text(fallback_text or text)
    return True


def _send_rich_html_message(
    rich_html: str,
    fallback_html: str = "",
    fallback_text: str = "",
) -> bool:
    """Envía Rich Message y cae al HTML clásico si Telegram lo rechaza."""
    if len(rich_html) > TELEGRAM_RICH_MAX_LEN:
        log.warning("Rich Message demasiado largo; usando HTML clásico.")
        return _send_html_message(fallback_html or rich_html, fallback_text)

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendRichMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "rich_message": {
            "html": rich_html,
            "skip_entity_detection": True,
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            log.info("Digest enviado correctamente como Rich Message.")
            return True
        log.error(f"Error Rich Message de Telegram: {data}")
    except requests.RequestException as e:
        log.error(f"Error al enviar Rich Message a Telegram: {e}")

    return _send_html_message(fallback_html or rich_html, fallback_text)


def send_telegram_digest(digest: str) -> bool:
    """Envía el digest por Telegram como Rich Message con fallback."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
        return False

    now = datetime.now(ZoneInfo("Europe/Madrid"))
    date_str = now.strftime("%d/%m/%Y")
    title = f"📚 BLITZ WEEKEND — Semana del {date_str}"
    message = f"{title}\n\n{digest}"
    return _send_rich_html_message(
        _format_digest_rich_html(title, digest),
        fallback_html=_format_digest_html(title, digest),
        fallback_text=message,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== Blitz Weekend — Digest semanal ===")

    # 1. Scrapear fuentes
    fetch_errors: list[str] = []
    health_data = fetch_all_sources(fetch_errors)
    author_articles = fetch_weekend_author_articles(fetch_errors)
    longform_articles = fetch_weekend_longform_articles(fetch_errors)

    health_total = sum(len(arts) for arts in health_data.values())
    authors_with_content = sum(1 for arts in health_data.values() if arts)
    log.info(
        f"Salud: {health_total} artículos/episodios de "
        f"{authors_with_content}/{len(health_data)} autores."
    )
    log.info(f"Autores: {len(author_articles)} artículos semanales.")
    log.info(f"Lecturas largas: {len(longform_articles)} artículos semanales.")

    # Si TODAS las fuentes fallaron / vinieron vacías, mejor avisar a
    # Telegram que quedarse callado un domingo entero.
    if not any(health_data.values()) and not author_articles and not longform_articles:
        msg = "⚠️ Blitz Weekend: ninguna fuente devolvió contenido esta semana."
        if fetch_errors:
            msg += "\n\nFuentes con error:\n" + "\n".join(
                f"• {e}" for e in fetch_errors
            )
        else:
            msg += "\nLos feeds responden bien pero ninguno tiene artículos en los últimos 7 días."
        send_telegram_text(msg)
        log.warning("Sin contenido — notificado a Telegram. Abortando.")
        sys.exit(1)

    # 2. Generar digest con Gemini
    log.info("Generando digest con Gemini...")
    digest = generate_weekend_digest(
        health_data,
        author_articles,
        longform_articles,
    )

    if not digest:
        log.warning("No se pudo generar el digest. Abortando.")
        send_telegram_text(
            "⚠️ Blitz Weekend: Gemini no respondió tras 3 intentos. "
            "Sin digest esta semana."
        )
        sys.exit(1)

    # 3. Enviar por Telegram
    success = send_telegram_digest(digest)
    if not success:
        log.error("Fallo al enviar por Telegram.")
        sys.exit(1)

    log.info("=== Blitz Weekend completado ===")


if __name__ == "__main__":
    main()
