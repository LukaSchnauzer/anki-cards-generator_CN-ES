# ChinoSRS — cheat sheet de `main.py`

Pipeline nuevo (SQLite + LangGraph + ElevenLabs + AnkiConnect). Todos los comandos van precedidos de `python main.py`.

## Cómo correrlo (PowerShell + venv)

Sin activar el venv (un comando cada vez):
```powershell
.\anki-venv\Scripts\python.exe main.py generate
```

Activando el venv (varios comandos seguidos):
```powershell
.\anki-venv\Scripts\Activate.ps1
python main.py generate
```
Si PowerShell bloquea `Activate.ps1` por política de ejecución, usa la primera forma.

## Flujo normal

```
load     --input resources/complete.json [--hsk-level 3] [--db outputs/chinosrs.db]
generate [--limit N]
export   --hsk-level 3 [--limit N]
```

- **`load`**: siembra palabras del JSON fuente en SQLite (idempotente). `--hsk-level 0` carga todo el diccionario sin filtrar (rara vez se quiere esto).
- **`generate`**: corre el pipeline (word_prep → sentence/pattern/audio en paralelo → audio de cada una). Deja quietas las tarjetas en `guardrail_failed` a propósito — no las reintenta sola. Barra de progreso + costo LLM/ElevenLabs en vivo. Interrumpible (Ctrl+C) y resumible.
- **`export`**: empuja tarjetas `ready` de ese nivel al mazo `ChinoSRS - HSK{X}` (modelos `ChinoSRS_{Tipo}_HSK{X}`). Idempotente — actualiza en vez de duplicar.

## Revisión manual (flags de Anki)

```
flag-batch  --flag 1 [--notes "por qué"]
regenerate  --flagged [--hsk-level 3]
export      --hsk-level 3      <- necesario para que se vea el arreglo en Anki
```

- Flaguea en Anki con **Ctrl+1** (rojo = convención de este flujo; otros colores no se tocan nunca).
- `flag-batch` solo LEE de Anki — nunca escribe ahí. Marca `review_status='flagged_bad'` en SQLite.
- `regenerate --flagged` solo toca SQLite (no habla con Anki). Regenera esa tarjeta puntual (no `word_prep`, no las otras 2 del mismo tipo).
- Tras 2 rondas fallidas seguidas, la tarjeta escala a `needs_human` y deja de reintentarse sola.
- `export` es el que sincroniza el contenido nuevo Y limpia el flag rojo — sin este paso, la tarjeta se ve igual en Anki aunque ya esté arreglada en la DB.

Regenerar una tarjeta puntual sin pasar por flags:
```
regenerate --word <hanzi> --type <sentence|pattern|audio> [--hsk-level 3]
```

## Diagnóstico

```
dashboard    [--hsk-level N]
clean-audio  [--yes]
```

- **`dashboard`**: tarjetas por estado/`review_status`, quién falla guardrails y por qué, quién está flaggeado/escalado, palabras atascadas en `word_prep`, resumen de audio huérfano.
- **`clean-audio`**: borra archivos de audio en `resources/audios/` que ya nadie referencia (por defecto solo muestra qué borraría — hace falta `--yes` para borrar de verdad).

## Legacy

```
dump --deck "Chino SRS" --output archivo.json
```
Vuelca el mazo viejo (pipeline CSV anterior) a JSON. No toca la DB de ChinoSRS.
