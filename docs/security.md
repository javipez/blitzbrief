# Seguridad del contenido externo

Revisión del 8 de octubre de 2026, centrada en prompt injection.

## Qué puede hacer Gemini

Las tres llamadas (briefing, Bitcoin y Weekend) utilizan generateContent sin
herramientas, conectores de correo, ejecución de código ni búsqueda web. Solo se
consume texto de la respuesta. El programa no lo interpreta como comandos ni
visita URLs generadas. El destinatario de Telegram procede de la configuración,
no del modelo. La clave de Gemini se transmite como cabecera de autenticación,
no dentro del prompt. No se envían archivos del VPS ni variables de entorno como
material editorial. El bot sí envía a Google noticias y preferencias editoriales
incluidas en sus prompts.

## Defensas implementadas

- `content_security.py` elimina scripts, estilos, comentarios, formularios,
  contenido incrustado y nodos con ocultación HTML o CSS inline explícita.
  Se aplica antes de convertir HTML a texto y truncarlo; también se limpian
  campos editoriales al preparar los prompts. Se conserva el texto de enlaces,
  sin copiar sus atributos al texto del artículo.
- Las tres peticiones llevan una `systemInstruction` separada que declara las
  fuentes como datos no fiables y prohíbe obedecer instrucciones incrustadas,
  pedir secretos, reenviar correos o ejecutar órdenes.
- Se rechazan respuestas con URLs explícitas ajenas a las URLs de los artículos
  suministrados, incluso cambios de parámetros o fragmentos. Bitcoin no admite
  enlaces. Una respuesta rechazada usa la ruta existente de generación fallida:
  titulares para el briefing, sin explicación de Bitcoin, aviso para Weekend.
- Los logs propios del bot ocultan los valores de sus claves de Telegram y
  Gemini: los errores HTTP pueden incluir el token dentro de la URL.
- Pruebas con fuentes y respuestas hostiles simuladas verifican las tres rutas
  sin llamar a Google ni enviar mensajes a Telegram.

## Límites y trabajo separado

Esto reduce la superficie de ataque; no demuestra inmunidad a prompt injection.
Una instrucción puede estar en texto visible. BeautifulSoup no renderiza CSS
externo ni conoce qué ocultan las clases de una página. El filtro de enlaces no
verifica la reputación de las URLs originales ni detecta todas las direcciones
escritas sin esquema. Un resumen aún puede contener texto engañoso.

El 8 de octubre se verificó que `blitzbrief` corre como `javi`, con
`NoNewPrivileges=no`, `ProtectSystem=no` y `ProtectHome=no`. Gemini no hereda esos
permisos, pero una vulnerabilidad de Python o de una dependencia tendría el
alcance del usuario del proceso. El aislamiento de systemd necesita una revisión
propia de los servicios y sus directorios de escritura. Esta revisión no incluye
una auditoría integral del VPS, dependencias o redirecciones/SSRF del scraper.

No se inspeccionaron secretos ni correos. El filtro de logs no modifica
registros históricos ni los emitidos directamente por bibliotecas externas.
