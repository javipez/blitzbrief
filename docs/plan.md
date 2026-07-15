# Plan: mejorar los titulares y el "Por qué importa" del briefing diario

> **Nota de ejecución**: este plan lo ejecutará una sesión con **Sonnet 5**.
> Es autocontenido: no hace falta contexto de la conversación original.
> El usuario ya ha decidido: se despliega al VPS y se observa en producción
> ~1 semana (es un bot personal, no pasa nada por probar en real).
> **El push y el despliegue de ESTE cambio ya están autorizados por el
> usuario**; no hace falta volver a pedir permiso para ese paso concreto.

> **Reversibilidad**: hay una copia literal del prompt actual en
> `docs/prompt-briefing-anterior.md` (creada el 15/07/2026 sobre el commit
> `05ebfe7`). Si la nueva versión funciona peor, se puede restaurar a mano
> desde ahí o con `git revert` del commit del cambio.

## Problema

El briefing matutino que genera Gemini tiene dos defectos:

1. **Titulares poco ilustrativos**: frases vagas que no dicen qué pasó
   concretamente.
2. **"Por qué importa" redundante**: muchas veces repite la noticia o solo
   añade un detalle más, en vez de explicar la relevancia. Ejemplos reales:
   - "OpenAI lanza recomendaciones para gestionar inversiones empresariales —
     Por qué importa: El objetivo es optimizar la eficiencia y el valor del
     trabajo por dólar" (redunda).
   - "Apple lanza la beta pública de iOS 27 — Por qué importa: La
     actualización incluye Apple Intelligence y mejoras en Siri" (solo
     detalla, no explica relevancia).

## Diagnóstico (verificado en el código)

Todo está en `blitzbrief_bot.py`:

1. **El prompt no define qué es un buen "Por qué importa"** (líneas
   2251-2292, en `generate_news_briefing()`). Solo pide "[frase muy breve]"
   con máximo 14 palabras. Sin definición ni ejemplos, el modelo rellena
   parafraseando el titular.

2. **Se inyecta una señal de plantilla que empuja a lo genérico**. La función
   `_why_headline_matters()` (línea ~797) genera frases de plantilla
   ("Conecta con tus intereses: X", "La cubren N fuentes...", "Es una noticia
   relevante dentro de su sección") que `curate_news_headlines()` (línea
   ~897) guarda en `why_it_matters` y el prompt incluye como
   `| por qué importa: ...` (línea ~2244). Además, el propio prompt dice
   "frase muy breve basada en el titular o en la señal 'por qué importa'"
   (línea 2270), es decir, invita al modelo a copiar esa plantilla genérica.

3. **Tensión con las reglas anti-alucinación**. El prompt prohíbe usar
   conocimiento previo y casi toda inferencia ("USA EXCLUSIVAMENTE los
   titulares..."). Pero explicar relevancia exige inferir consecuencias.
   Con temperature 0.2 y esas reglas, lo más "seguro" para el modelo es
   parafrasear el titular. Hay que permitir explícitamente inferir
   RELEVANCIA sin permitir inventar HECHOS.

4. **Titulares**: el prompt pide "UNA frase de máximo 15 palabras" pero no
   exige que contenga el hecho concreto (qué pasó, quién, resultado).

## Opciones consideradas

### Opción A — Mejorar el prompt (definición + ejemplos + regla de omisión)

Añadir al prompt: qué es un buen "Por qué importa" (consecuencia, a quién
afecta, qué cambia), 2-3 ejemplos buenos y malos (few-shot), la regla "si no
puedes decir nada que no esté ya en el titular, omite la línea", y un
carve-out explícito: se permite inferir relevancia, no hechos nuevos.

- **A favor**: ataca la causa raíz, coste cero de infraestructura, una sola
  llamada a Gemini como ahora, fácil de revertir.
- **En contra**: prompt más largo; hay que redactar los ejemplos con cuidado
  para que el modelo no los copie como noticias.

### Opción B — Quitar/reetiquetar la señal `why_it_matters` de plantilla

La plantilla ("Conecta con tus intereses...") es una señal de *selección*,
no contenido editorial. Reetiquetarla en el prompt como
`criterio de selección (uso interno, NO copiar)` y dejar de sugerir que el
"Por qué importa" se base en ella.

- **A favor**: elimina la fuente directa de texto genérico; cambio mínimo.
- **En contra**: por sí sola no enseña al modelo a escribir un buen
  "Por qué importa".

### Opción C — Ajustar límites de palabras y exigir titular concreto

Mantener 15 palabras para el titular pero exigir que incluya el hecho
concreto; subir "Por qué importa" de 14 a 18 palabras para dar espacio a
explicar una consecuencia.

- **A favor**: 14 palabras es tan poco que fomenta la paráfrasis; barato.
- **En contra**: mensajes algo más largos.

### Opción D — Segunda pasada de crítica (otra llamada a Gemini que revise)

- **A favor**: podría cazar redundancias que la primera pasada deje pasar.
- **En contra**: duplica llamadas a la API, más latencia, más puntos de
  fallo, y más superficie para alucinar en la reescritura. **Descartada por
  ahora**; solo si A+B+C no bastan tras una semana de observación.

### Opción E — Post-filtro determinista de redundancia en Python

Función que compare tokens del titular con los del "Por qué importa" (ya
existe `_briefing_tokens` y `_briefing_text_matches_headline` como base) y
borre la línea si el solape es casi total.

- **A favor**: determinista, testeable, red de seguridad si el modelo falla.
- **En contra**: heurística delicada (puede borrar líneas buenas); mejor
  como fase 2 si hace falta.

## Recomendación

**Fase 1: A + B + C juntas** (todo es cambio de prompt y de una etiqueta) más
un **modo preview** para probar en local sin enviar a Telegram (hoy no
existe: `main()` en línea ~3193 solo tiene `--serve`, `--evening`,
`--morning` y digest completo; `send_news_briefing()` siempre envía).

**Fase 2 (solo si tras ~1 semana siguen saliendo redundancias): E.**
**D queda descartada salvo fracaso de lo anterior.**

---

## Pasos de ejecución (Fase 1)

### Paso 1 — Añadir modo preview (para poder probar sin enviar)

En `blitzbrief_bot.py`:

1. Crear una función `preview_news_briefing()` que replique el principio de
   `send_news_briefing()` (línea ~2335) pero SIN enviar nada: llama a
   `fetch_news_headlines()`, `curate_news_headlines()`,
   `generate_news_briefing()` y hace `print()` del resultado (y del fallback
   de titulares en bruto si Gemini falla). No debe llamar a
   `_send_rich_html_message` ni a nada de Telegram.
2. En `main()` (línea ~3193) añadir la rama:

   ```python
   elif "--preview-briefing" in sys.argv:
       preview_news_briefing()
   ```

   Colocarla ANTES del `else` final para que no caiga en `run_digest`.
3. Probar en local: `python blitzbrief_bot.py --preview-briefing`
   (necesita `GEMINI_API_KEY` del `.env`, pero no toca Telegram).

Commit sugerido: `Añade modo --preview-briefing para probar el briefing sin enviarlo`

### Paso 2 — Reetiquetar la señal de plantilla en el prompt (Opción B)

En `generate_news_briefing()`:

1. Línea ~2243-2244: cambiar la etiqueta que se inyecta por titular de
   `| por qué importa: {why}` a
   `| criterio de selección (uso interno, NO copiar): {why}`.
2. Línea ~2265: cambiar
   `Usa las señales de prioridad y "por qué importa" como ayuda editorial...`
   por algo como
   `Usa las señales de prioridad y "criterio de selección" solo para ELEGIR titulares; nunca las copies en el texto.`
3. Línea 2270: quitar `o en la señal "por qué importa"` del formato de la
   línea Por qué importa.

NO tocar `_why_headline_matters()` ni `curate_news_headlines()`: la señal
sigue siendo útil para elegir, solo cambia cómo se presenta al modelo.

### Paso 3 — Enseñar al modelo qué es un buen "Por qué importa" (Opción A)

Añadir al prompt (entre SELECCIÓN y FORMATO) un bloque nuevo, aproximadamente
así (redacción orientativa, ajustable):

```
POR QUÉ IMPORTA (regla de oro):
- La línea "Por qué importa" debe responder a UNA de estas preguntas:
  ¿qué consecuencia tiene?, ¿a quién afecta y cómo?, ¿qué cambia respecto
  a antes? NUNCA debe repetir ni parafrasear el titular.
- PROHIBIDO: repetir el titular con otras palabras, añadir solo un detalle
  más del mismo hecho, o generalidades vacías ("es relevante", "es
  importante para el sector").
- Puedes INFERIR la relevancia con sentido común (consecuencias plausibles,
  a quién afecta), pero SIN añadir hechos nuevos: nada de nombres, cifras,
  fechas ni sucesos que no estén en el titular.
- Si no puedes decir nada útil que NO esté ya en el titular, OMITE la línea
  "Por qué importa" de esa sección (la noticia sola es válida).

EJEMPLOS DE ESTILO (solo ilustran el formato; JAMÁS los incluyas como noticias):
- MAL:  "El banco central sube los tipos — Por qué importa: Los tipos de
  interés suben." (repite el titular)
- BIEN: "El banco central sube los tipos — Por qué importa: Encarece
  hipotecas y préstamos para las familias."
- MAL:  "Sale la beta de un sistema operativo — Por qué importa: La beta
  incluye nuevas funciones." (solo añade detalle)
- BIEN: "Sale la beta de un sistema operativo — Por qué importa: Cualquiera
  puede probarla ya antes del lanzamiento oficial."
```

Detalles importantes al integrarlo:

- Los ejemplos deben ser **genéricos e inventados a propósito** (no noticias
  reales de hoy) y estar marcados como "solo estilo", para que las reglas
  anti-alucinación no entren en conflicto y el modelo no los copie.
- Añadir también en el bloque ANTI-ALUCINACIÓN una aclaración de una línea:
  la prohibición de inventar aplica a HECHOS; inferir la relevancia de un
  titular real sí está permitido.
- En FORMATO, indicar que la línea `Por qué importa:` es opcional por
  sección (se omite si sería redundante). Verificado: el código lo tolera —
  `_filter_ungrounded_tech_section()` (línea ~847) y los formateadores HTML
  (líneas ~2398 y ~2441) tratan esa línea como opcional.

### Paso 4 — Titulares concretos y límite de palabras (Opción C)

En ESTILO (líneas ~2283-2284):

- Cambiar la regla del titular a: una frase de máximo 15 palabras que
  contenga el HECHO concreto (qué pasó y quién), no vaguedades tipo
  "novedades en X" o "polémica por Y" si el titular original da el dato.
- Subir el límite de "Por qué importa" de 14 a 18 palabras.

Commit sugerido para pasos 2-4 (pueden ir en un solo commit, es todo el
mismo prompt): `Mejora el prompt del briefing: define un buen "Por qué importa" y evita redundancias`

### Paso 5 — Tests

Correr siempre con: `python -m pytest tests/ -q`

Ajustar en `tests/test_blitzbrief_bot.py`:

- `test_generate_news_briefing_includes_importance_context` (línea ~628):
  la aserción `assertIn("por qué importa", captured["prompt"])` (línea 661)
  se romperá al reetiquetar. Cambiarla por
  `assertIn("criterio de selección", captured["prompt"])`.

Añadir tests nuevos (mismo patrón de `fake_post` capturando el prompt):

1. El prompt contiene el bloque nuevo: p. ej.
   `assertIn("NUNCA debe repetir ni parafrasear el titular", prompt)` y
   `assertIn("OMITE la línea", prompt)`.
2. El prompt marca la señal de plantilla como no copiable:
   `assertIn("uso interno, NO copiar", prompt)` y
   `assertNotIn("| por qué importa:", prompt)`.
3. Los formateadores HTML (`_format_news_briefing_rich_html` y
   `_format_news_briefing_html`) renderizan bien un bloque de sección SIN
   línea "Por qué importa" (ahora es opcional).
4. `--preview-briefing`: test de que `preview_news_briefing()` NO llama a
   funciones de envío (patch de `_send_rich_html_message` /
   `send_telegram_message` y assert de que no se invocan), mockeando
   `fetch_news_headlines` y `generate_news_briefing`.

Commit sugerido: incluir los tests en los mismos commits de los pasos 1 y 2-4.

### Paso 6 — Prueba rápida en local

En local: `python blitzbrief_bot.py --preview-briefing` 1-2 veces y revisar
a ojo: ¿los titulares dicen el hecho concreto?, ¿algún "Por qué importa"
repite el titular?, ¿se omite la línea cuando toca? Es solo una comprobación
de humo — la prueba de verdad será en el VPS durante la semana.

### Paso 7 — Desplegar al VPS (ya autorizado por el usuario)

Con los commits hechos y los tests en verde:

1. `git push` (autorizado para este cambio).
2. Desplegar en el VPS — el push solo NO basta, el VPS tiene su propio
   checkout:

   ```bash
   ssh bots
   cd /home/javi/apps/blitzbrief
   git pull
   sudo systemctl restart blitzbrief
   sudo systemctl status blitzbrief --no-pager
   ```

3. Comprobar que el servicio queda `active (running)`.

### Paso 8 — Observación en producción

Observar los briefings reales de las mañanas durante ~1 semana. Si siguen
saliendo "Por qué importa" redundantes, activar la Fase 2. Si la nueva
versión fuera peor, revertir con `docs/prompt-briefing-anterior.md` o
`git revert` y volver a desplegar.

---

## Fase 2 (opcional, solo si la Fase 1 no basta)

Post-filtro determinista `_strip_redundant_why_lines(briefing)`:

- Para cada línea `Por qué importa:` del briefing, comparar sus tokens
  (reutilizando `_briefing_tokens`, línea ~821) con los del titular de su
  misma sección (la línea anterior).
- Si el solape es casi total (p. ej. ≥ 80 % de los tokens del "por qué"
  ya están en el titular, con mínimo de 3 tokens), eliminar la línea y
  loguear un warning, igual que hace `_filter_ungrounded_tech_section`.
- Aplicarlo en `generate_news_briefing()` justo después de
  `_filter_ungrounded_tech_section` (línea ~2323).
- Tests: caso redundante (se borra), caso legítimo (se conserva), caso sin
  línea (no rompe nada).

## Restricciones a respetar

- No tocar `.env` ni claves.
- Commits en español tras cada cambio que funcione. El push y el despliegue
  de este cambio ya están autorizados (ver nota de ejecución arriba); para
  cualquier otro push distinto de este, pedir permiso.
- No borrar archivos sin preguntar.
- Ejecutar los tests después de cada cambio antes de darlo por terminado.
- Explicar al usuario en lenguaje sencillo qué se cambió y por qué
  (está aprendiendo a programar).
