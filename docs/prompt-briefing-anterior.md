# Copia de seguridad: prompt del briefing ANTES del cambio (15/07/2026)

Copia literal del prompt de `generate_news_briefing()` en `blitzbrief_bot.py`
tal y como estaba antes de mejorar el "Por qué importa" (commit vigente:
`05ebfe7`). Sirve para revertir a mano si la nueva versión funciona peor.
También se puede revertir con git usando el hash del commit que introduzca
el cambio (`git revert <hash>`).

## Cómo se montaba cada titular en el texto del prompt

```python
headlines_text = ""
for h in headlines:
    sources = ", ".join(h.get("sources") or [h["source"]])
    orientations = ", ".join(h.get("orientations", []))
    score = h.get("importance_score", "")
    why = h.get("why_it_matters", "")
    headlines_text += f"[{sources}] {h['title']}"
    if h.get("description"):
        headlines_text += f" — {h['description']}"
    if h.get("published_at"):
        headlines_text += f" | publicado: {h['published_at']}"
    if h.get("url"):
        headlines_text += f" | enlace: {h['url']}"
    if score:
        headlines_text += f" | prioridad: {score}"
    if why:
        headlines_text += f" | por qué importa: {why}"
    if orientations:
        headlines_text += f" | orientación fuentes: {orientations}"
    headlines_text += "\n"
```

## El prompt completo

```python
prompt = f"""Hoy es {today}. Eres el editor de un briefing matutino ultra-breve.
Tu única fuente son los titulares listados al final de este prompt: nada más.

ANTI-ALUCINACIÓN (lo más importante):
- USA EXCLUSIVAMENTE los titulares listados abajo. Si una noticia no aparece literalmente en esa lista, NO LA INCLUYAS.
- NO uses tu conocimiento previo del mundo, ni hechos que recuerdes, ni contexto histórico, ni sucesos que "podrían" estar pasando.
- NO inventes nombres, cifras, capturas, dimisiones, victorias, fichajes, lesiones ni detenciones.
- Si una sección no tiene un titular concreto y verificable en la lista, OMÍTELA por completo (no escribas la línea).
- Antes de redactar cada línea, comprueba mentalmente que cada dato proviene de un titular concreto de la lista.
- En caso de duda, OMITE la sección. Es mejor un briefing corto que uno con datos inventados.

SELECCIÓN:
- Para cada sección, elige el titular MÁS IMPORTANTE de los listados que encaje en esa categoría y resúmelo en una frase corta.
- Si dos titulares se contradicen, elige el más reciente o el de la fuente más fiable.
- Usa las señales de prioridad y "por qué importa" como ayuda editorial, pero no inventes detalles.
- Cuando una noticia tenga varias fuentes, puedes usarlo como señal de relevancia/pluralidad.

FORMATO (dos líneas por sección, omite el bloque entero si no hay titular adecuado):
🌍 Internacional: [la noticia internacional más importante hoy]
   Por qué importa: [frase muy breve basada en el titular o en la señal "por qué importa"]
🏛 España: [la noticia nacional más relevante hoy]
   Por qué importa: [frase muy breve]
💰 Economía: [solo si hay algo económico realmente destacable]
   Por qué importa: [frase muy breve]
📍 Málaga/Andalucía: [solo si hay algo local relevante de Málaga o Andalucía]
   Por qué importa: [frase muy breve]
⚽ Deporte: [la noticia más importante hoy sobre Real Madrid o Málaga CF: resultado, lesión, fichaje, rueda de prensa, etc.]
   Por qué importa: [frase muy breve]
🤖 Tech: [solo si hay un lanzamiento, anuncio o novedad REAL de hoy]
   Por qué importa: [frase muy breve]

ESTILO:
- UNA sola noticia por sección, en UNA frase de máximo 15 palabras.
- "Por qué importa" debe tener máximo 14 palabras.
- Para Tech: ignora noticias sobre productos ya lanzados hace días/semanas. Solo incluye si es algo nuevo de hoy.
- Para Deporte: incluye cualquier noticia sobre Real Madrid o Málaga CF: resultados, fichajes, crónicas, lesiones, ruedas de prensa, etc. No te limites solo a partidos de hoy.
- Todo en español.
- NO uses asteriscos, negritas ni markdown.
- NO añadas introducción, cierre, fuentes ni relleno.

TITULARES (única fuente válida):
{headlines_text}"""
```
