# ChinoSRS — cheat sheet de `main.py`

Referencia rápida de sintaxis. Para explicaciones, criterios de "cuándo usar cada herramienta" y ejemplos completos, ver **[WORKFLOWS.md](WORKFLOWS.md)**.

Todos los comandos van precedidos de `python main.py`.

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

## Revisión manual (flags de Anki)

```
flag-batch  --flag 1 [--notes "por qué"]
regenerate  --flagged [--hsk-level 3]
regenerate  --word <hanzi> --type <sentence|pattern|audio> [--hsk-level 3]
export      --hsk-level 3      <- necesario para que se vea el arreglo en Anki
```

## Casos difíciles (`needs_human`)

```
swap-primary      --word <hanzi> --meaning "<texto parcial>" [--regenerate] [--hsk-level 3]
add-reading       --word <hanzi> --pinyin <pinyin> --meaning-es "<significado>" [--meaning-zh "<def>"] [--secondary] [--regenerate] [--hsk-level 3]
edit-reading      --word <hanzi> --meaning-query "<texto parcial>" [--new-meaning-es "<texto>"] [--new-meaning-zh "<texto>"] [--new-pinyin <pinyin>] [--hsk-level 3]
manual-card       --word <hanzi> --type <sentence|pattern|audio> --zh "<oración>" --es "<traducción>" [--hsk-level 3]
manual-card-batch --file <ruta.json> [--hsk-level 3]
```

## Auditoría proactiva de naturalidad

```
audit-naturalness [--hsk-level N] [--batch-size 15]
unflag             --word <hanzi> --type <sentence|pattern|audio> [--hsk-level 3]
```

## Diagnóstico

```
inspect-word     --word <hanzi> [--hsk-level 3]
resync-due-order [--hsk-level 3] [--apply]
dashboard        [--hsk-level N]
clean-audio      [--yes]
```

## Legacy

```
dump --deck "Chino SRS" --output archivo.json
```
