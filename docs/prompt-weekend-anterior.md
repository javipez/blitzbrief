# Copia de seguridad: prompt de Blitz Weekend ANTES del cambio (19/07/2026)

Copia literal del prompt de `generate_weekend_digest()` en `blitzhealth.py`
tal y como estaba antes de: (1) añadir puntuación de relevancia real a los
artículos de autores/lecturas largas y (2) arreglar la instrucción de
PANORAMA SEMANAL para que no invente hilos narrativos falsos entre temas
sin relación. Commit vigente antes del cambio: `6c3cc6a`. Sirve para
revertir a mano si la nueva versión funciona peor, o con
`git revert <hash>` del commit que introduzca el cambio.

## Cómo se formateaban los artículos de autores/lecturas largas (sin señal de relevancia)

```python
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
```

## Cómo se seleccionaban los artículos antes de llegar al prompt (solo por fecha)

```python
def fetch_weekend_author_articles(errors: Optional[list] = None) -> list[dict]:
    """Recopila artículos semanales de autores del digest diario."""
    import blitzbrief_bot as press_bot

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    config = _load_weekend_authors()
    articles: list[dict] = []

    for author, slug in config["elpais"].items():
        articles.extend(press_bot.fetch_elpais_articles(author, slug, cutoff, errors))

    for author, slug in config["elplural"].items():
        articles.extend(press_bot.fetch_elplural_articles(author, slug, cutoff, errors))

    for author, feed_url in config["rss"].items():
        articles.extend(press_bot.fetch_rss_articles(author, feed_url, cutoff, errors))

    articles.sort(
        key=lambda art: art.get("date") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return articles[:12]
```

`fetch_weekend_longform_articles()` seguía el mismo patrón: orden por
fecha descendente y corte a `[:6]`, sin ninguna señal de relevancia.

## Prompt completo de `generate_weekend_digest()`

```python
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
```

## Diagnóstico que motivó el cambio

1. **Selección arbitraria de columnas**: `fetch_weekend_author_articles`/
   `fetch_weekend_longform_articles` solo ordenaban por fecha y cortaban a
   12/6 artículos. Sin ninguna señal de relevancia, Gemini elegía "las
   mejores lecturas" de una lista sin ranking real — la instrucción
   "Selecciona las mejores lecturas... prioriza 4-8 piezas" no tenía nada
   objetivo en qué apoyarse.
2. **PANORAMA SEMANAL genérico/con hilos falsos**: la instrucción "3-5
   líneas... Nada genérico" no definía qué es genérico ni daba ejemplos, y
   pedía un párrafo fluido — eso empujaba al modelo a inventar una
   narrativa única conectando temas sin relación real (ej: unir el
   Mundial, un debate sobre el calor, el fin de un programa de radio y una
   reflexión sobre IA como si fueran parte de la misma reflexión).

Ver `docs/plan.md` para el diagnóstico y la solución equivalente ya
aplicada al briefing diario, de donde se reutilizan las lecciones.
