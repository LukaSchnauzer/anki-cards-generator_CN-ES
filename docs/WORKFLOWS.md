# ChinoSRS — guía de flujos de trabajo

Explicaciones detalladas, criterios de "cuándo usar cada herramienta" y ejemplos completos. Para la sintaxis rápida de cada comando, ver **[CLI_CHEATSHEET.md](CLI_CHEATSHEET.md)**.

## Flujo normal

- **`load`**: siembra palabras del JSON fuente en SQLite (idempotente). `--hsk-level 0` carga todo el diccionario sin filtrar (rara vez se quiere esto).
- **`generate`**: corre el pipeline (word_prep → sentence/pattern/audio en paralelo → audio de cada una). Deja quietas las tarjetas en `guardrail_failed` a propósito — no las reintenta sola. Barra de progreso + costo LLM/ElevenLabs en vivo. Interrumpible (Ctrl+C) y resumible.
- **`export`**: empuja tarjetas `ready` de ese nivel al mazo `ChinoSRS - HSK{X}` (modelos `ChinoSRS_{Tipo}_HSK{X}`). Idempotente — actualiza en vez de duplicar.

## Revisión manual (flags de Anki)

- Flaguea en Anki con **Ctrl+1** (rojo = convención de este flujo; otros colores no se tocan nunca).
- `flag-batch` solo LEE de Anki — nunca escribe ahí. Marca `review_status='flagged_bad'` en SQLite.
- `regenerate --flagged` solo toca SQLite (no habla con Anki). Regenera esa tarjeta puntual (no `word_prep`, no las otras 2 del mismo tipo).
- Tras 2 rondas fallidas seguidas, la tarjeta escala a `needs_human` y deja de reintentarse sola.
- `export` es el que sincroniza el contenido nuevo Y limpia el flag rojo — sin este paso, la tarjeta se ve igual en Anki aunque ya esté arreglada en la DB.
- `regenerate --word <hanzi> --type <tipo>` regenera una tarjeta puntual sin pasar por flags.

## Casos difíciles (`needs_human`)

Cuando una tarjeta agota el tope de reintentos (`regenerate --flagged` no puede arreglarla sola), hay cuatro herramientas según la causa real — revisa primero qué generaron las otras 2 tarjetas de la misma palabra para diagnosticar cuál aplica:

- **`swap-primary`**: para cuando `word_prep` le asignó como significado primario una acepción que no es como la palabra realmente se usa, PERO el sentido correcto YA existe registrado como lectura secundaria (ej. 把 = "agarrar" cuando el uso real dominante es la partícula gramatical del 把字句, ya presente como secundaria). Busca la lectura cuyo `meaning_es` contiene el texto dado y la promueve a primaria.
- **`add-reading`**: para cuando el sentido que realmente domina el uso **no está registrado en absoluto** — ni como primaria ni como secundaria (ej. 系: solo tenía "sistema" y "atar", pero el uso común de 系 solo es "departamento académico", un sentido que ninguna lectura cubría; "sistema" no estaba mal, solo era demasiado abstracto para que saliera una oración natural). Inserta una lectura nueva y, por defecto, la vuelve primaria (degradando a secundaria la que lo era) — usa `--secondary` si solo quieres agregarla sin tocar cuál es primaria.
- **`edit-reading`**: para cuando la lectura correcta ya existe pero está mal descrita, y por eso nunca se elige (ej. 所: tenía una secundaria "clasificador para casas o edificios pequeños" — la descripción estaba mal, 所 es clasificador de INSTITUCIONES: 一所学校, 一所医院, 一所大学; con esa descripción nunca se usaba, y todo forzaba "所" como sustantivo libre). Corrige el texto (`--new-meaning-es`/`--new-meaning-zh`/`--new-pinyin`) sin agregar ni cambiar cuál es primaria — normalmente se sigue de `swap-primary` si, ya corregida, debería serlo.
- **`manual-card`**: para cuando la palabra genuinamente no tiene una forma natural e independiente de aparecer (morfemas casi siempre atados a un compuesto, ej. 乐, 冬, 报, 保, 亲 — ningún significado la salva, agregar/corregir/cambiar lecturas no ayuda). Tú escribes la oración china + traducción ya aprobadas; el LLM SOLO hace el desglose palabra por palabra (no toca la oración), sin pasar por ningún guardrail. Para PatternCard, si el LLM no logra aislar la palabra objetivo como su propio token del desglose (necesario para ubicar el hueco), lo separa a mano automáticamente — nunca falla en silencio.
- **`manual-card-batch`**: cuando se acumulan varias correcciones (ej. tras revisar una lista larga de marcadas por `audit-naturalness`), en vez de un `manual-card` a la vez, se junta todo en un JSON (fuera del repo — ej. en el scratchpad de la sesión) y se corre de una.

  Formato del JSON — una lista de objetos `{"word", "type", "zh", "es"}` (mismo `word`/`type` puede repetirse para las 3 tarjetas de una palabra; cualquier campo extra como `"nota"` se ignora, útil para dejarte contexto mientras decides):
  ```json
  [
    {
      "word": "亲",
      "type": "sentence",
      "zh": "每年春节我都会去看望亲戚。",
      "es": "Cada Año Nuevo chino voy a visitar a mis parientes."
    },
    {
      "word": "亲",
      "type": "pattern",
      "zh": "过年的时候，我们全家都会去乡下看望亲戚。",
      "es": "Durante el Año Nuevo, toda mi familia va al campo a visitar a los parientes."
    },
    {
      "word": "亲",
      "type": "audio",
      "zh": "他和亲戚们一起吃了年夜饭。",
      "es": "Él cenó la cena de Fin de Año junto con sus parientes."
    },
    {
      "word": "破",
      "type": "sentence",
      "zh": "他一不小心，杯子就破了。",
      "es": "Se descuidó un momento y la taza se rompió.",
      "nota": "破 es intransitivo — no forzar 把+破, ni agregar 打 si no hace falta"
    }
  ]
  ```
  Barra de progreso + costo en vivo, igual que `generate`. Al final imprime cuántas se guardaron/fallaron (y por qué, si alguna falló).

- `swap-primary` y `add-reading` aceptan `--regenerate`, que corre el pipeline normal (LLM + guardrail, con reintentos) en las 3 tarjetas usando ya la lectura corregida — normalmente basta, sin necesitar más intervención. `edit-reading` no regenera nada por sí sola (solo corrige texto); si después de corregir hace falta promoverla, usa `swap-primary --regenerate` a continuación.
- Todas estas (menos `edit-reading`, que no llama al LLM) imprimen el costo desglosado (LLM/ElevenLabs) al final, igual que `generate`/`regenerate --flagged`.

## Auditoría proactiva de naturalidad

El guardrail normal evalúa gramática/traducción, pero no detecta cuando una oración es *técnicamente* correcta y aun así suena forzada a un hablante nativo — el patrón real encontrado en 报/保: la palabra usada como verbo/sustantivo genérico con un objeto libre ("报 + lo que sea"), cuando en el uso real casi siempre necesita un compuesto fijo (汇报, 报警, 保护...). Como esto puede colarse sin que nadie lo flaguee en Anki, existe una pasada aparte que lo busca a propósito: `audit-naturalness`.

- Revisa tarjetas `ready` con `content_source='llm'` de palabras de **1 solo carácter** (donde vimos el patrón) — no toca las que ya están flaggeadas o son manuales.
- Le manda las oraciones al LLM en lotes (15 por llamada por defecto, no 1 por 1) pidiéndole que juzgue si el uso suena natural o forzado.
- Las que salen mal quedan directo en `review_status='needs_human'` con el motivo en `review_notes` (prefijo `[audit-naturalness]`) — entran al mismo `dashboard` y al mismo flujo de siempre (`swap-primary` / `add-reading` / `edit-reading` / `manual-card`), sin cola aparte.
- Barra de progreso (lote actual, costo LLM en vivo, cuántas marcadas hasta el momento) + costo final, igual que `generate`/`regenerate --flagged`.
- Es de solo lectura sobre el contenido — no regenera nada por sí sola, solo marca para revisión humana.
- No es infalible — puede haber falsos positivos (dos tarjetas con la misma construcción gramatical, una marcada y la otra no). Si al revisar una resulta que en realidad estaba bien, usa `unflag` — limpia `review_status`/`review_notes` sin tocar el contenido, no regenera, no habla con Anki.

## Diagnóstico

- **`inspect-word`**: todo el estado de una palabra en un comando — lecturas (con cuál es primaria), las 3 tarjetas (status/review_status/content_source/oración/traducción), y los últimos intentos de generación con su motivo de fallo. Reemplaza tener que escribir un SELECT a mano contra SQLite para revisar un caso puntual (lo que se hacía antes de que existiera). `--hsk-level 0` no filtra por nivel.
- **`dashboard`**: tarjetas por estado/`review_status`/`content_source` (`llm` vs `manual`, solo se muestra si hay alguna manual), **cuántas ya se exportaron a Anki** (vía `anki_note_id`, se pone la primera vez que `export` crea la nota — no antes) con aviso de cuántas `ready` siguen esperando su primer `export`, quién falla guardrails y por qué, quién está flaggeado/escalado, palabras atascadas en `word_prep`, resumen de audio huérfano.
- **`clean-audio`**: borra archivos de audio en `resources/audios/` que ya nadie referencia (por defecto solo muestra qué borraría — hace falta `--yes` para borrar de verdad).

## Legacy

`dump --deck "Chino SRS" --output archivo.json` vuelca el mazo viejo (pipeline CSV anterior) a JSON. No toca la DB de ChinoSRS.
