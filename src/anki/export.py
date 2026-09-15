"""Exportador SQLite -> AnkiConnect.

Empuja las tarjetas con status='ready' de un nivel HSK al mazo real
"ChinoSRS - HSK{X}", usando los 3 modelos de ese nivel (ver
src/anki/models.py). Idempotente: guarda el noteId de AnkiConnect devuelto
por addNotes en cards.anki_note_id, así que volver a correrlo actualiza los
campos de las notas ya exportadas (updateNoteFields) en vez de duplicarlas.

No hay heurística de "quién manda" en un conflicto: la DB de ChinoSRS SIEMPRE
gana sobre lo que haya en Anki (updateNoteFields sobreescribe los campos).
La revisión manual del usuario vive en el flag/estado de Anki, no editando
campos de la nota a mano (ver memoria project-manual-review-workflow).
"""

import argparse
import json
import random
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from src.anki.api import (
    clear_note_flags_batch,
    ensure_deck,
    find_notes_batch,
    post,
    store_media_files_batch,
    update_note_fields_batch,
)
from src.anki.models import CARD_TYPE_LABELS, model_name_for, setup_models
from src.db.database import get_connection, init_db
from src.utils.frequency import get_freq_bucket

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DECK_PREFIX = "ChinoSRS"
EXPORT_BATCH_SIZE = 50  # mismo tamaño que usaba el pipeline viejo (csv_to_anki.py) para addNotes

# Bucket -> prioridad numérica para SortKey/ORDER BY. Igual que el pipeline
# viejo (src/csv_to_anki.py, ya borrado): agrupar por bucket ancho (~1000+
# palabras) y desordenar ADENTRO del bucket, no por rango exacto — si se
# ordenara por rango exacto, las 3 tarjetas de una misma palabra (que
# comparten el mismo frequency_rank) siempre quedarían consecutivas. Con un
# bucket de este tamaño, la chance de que las 3 hermanas caigan juntas es
# baja (igual que en el sistema viejo — no es una garantía dura, es la
# misma tolerancia que ya se aceptaba antes).
_FREQ_BUCKET_ORDER = {"top1k": 0, "top3k": 1, "top5k": 2, "top10k": 3, "rare": 4}
_FREQ_BUCKET_SQL_CASE = """
    CASE
        WHEN w.frequency_rank IS NULL THEN 9
        WHEN w.frequency_rank <= 1000 THEN 0
        WHEN w.frequency_rank <= 3000 THEN 1
        WHEN w.frequency_rank <= 5000 THEN 2
        WHEN w.frequency_rank <= 10000 THEN 3
        ELSE 4
    END
"""


def deck_name_for(hsk_level: int) -> str:
    return f"{DECK_PREFIX} - HSK{hsk_level}"


def _sort_key(hsk_level: int, frequency_rank: Optional[int]) -> str:
    """Primer campo del modelo -> Anki lo usa como Sort Field por defecto.
    nivel HSK real (2 dígitos) + bucket (2 dígitos) + aleatorio (4 dígitos) —
    mismo formato que el pipeline viejo (ej. "020100123"), para que el
    Browser ordene igual que como se crearon las notas (ver
    _FREQ_BUCKET_SQL_CASE). En el uso normal (un nivel por mazo) el prefijo
    de nivel es idéntico en toda la exportación, así que no cambia nada —
    solo importa cuando se mezclan niveles a propósito (ver export_level)."""
    bucket_code = _FREQ_BUCKET_ORDER.get(get_freq_bucket(frequency_rank), 9)
    return f"{hsk_level:02d}{bucket_code:02d}{random.randint(0, 9999):04d}"


def _fetch_word(conn, word_id: int) -> dict:
    return dict(conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone())


def _fetch_primary_reading(conn, word_id: int) -> dict:
    row = conn.execute("SELECT * FROM readings WHERE word_id = ? AND is_primary = 1", (word_id,)).fetchone()
    return dict(row) if row else None


def _fetch_secondary_readings(conn, word_id: int) -> list:
    rows = conn.execute("SELECT * FROM readings WHERE word_id = ? AND is_primary = 0", (word_id,)).fetchall()
    return [{"pinyin": r["pinyin"], "es": r["meaning_es"], "zh": r["meaning_zh"]} for r in rows]


def _fetch_collocations(conn, word_id: int) -> list:
    rows = conn.execute(
        "SELECT * FROM collocations WHERE word_id = ? ORDER BY sort_order", (word_id,)
    ).fetchall()
    return [{"p": r["pattern_zh"], "g": r["gloss_es"]} for r in rows]


def _fetch_example(conn, card_id: int) -> dict:
    row = conn.execute("SELECT * FROM card_examples WHERE card_id = ?", (card_id,)).fetchone()
    return dict(row) if row else None


def _fetch_audio(conn, *, reading_id: int = None, card_example_id: int = None, speed: str) -> dict:
    if reading_id is not None:
        row = conn.execute(
            "SELECT * FROM audio_files WHERE reading_id = ? AND speed = ?", (reading_id, speed)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM audio_files WHERE card_example_id = ? AND speed = ?", (card_example_id, speed)
        ).fetchone()
    return dict(row) if row else None


class ExportError(RuntimeError):
    pass


def _upload_audio(media_cache: dict, pending_uploads: list, file_path: str) -> str:
    """Devuelve el filename (determinístico, ver store_media_file) SIN subir
    el archivo todavía — solo lo encola en `pending_uploads`. El caller sube
    todo el lote junto (store_media_files_batch) antes de usar las notas, en
    vez de un POST por archivo (~2s cada uno, ver docstring de esa función)."""
    if file_path in media_cache:
        return media_cache[file_path]
    filename = Path(file_path).name
    media_cache[file_path] = filename
    pending_uploads.append((filename, PROJECT_ROOT / file_path))
    return filename


def _build_fields(conn, media_cache: dict, pending_uploads: list, word: dict, card_id: int, card_type: str) -> dict:
    primary = _fetch_primary_reading(conn, word["id"])
    if primary is None:
        raise ExportError(f"'{word['hanzi']}' (word_id={word['id']}) no tiene lectura primaria")

    example = _fetch_example(conn, card_id)
    if example is None:
        raise ExportError(f"card_id={card_id} ('{word['hanzi']}', {card_type}) no tiene card_example")

    word_audio = _fetch_audio(conn, reading_id=primary["id"], speed="slow")
    if word_audio is None:
        raise ExportError(f"card_id={card_id} ('{word['hanzi']}') no tiene audio de palabra")
    audio_word_file = _upload_audio(media_cache, pending_uploads, word_audio["file_path"])

    common = {
        "SortKey": _sort_key(word["hsk_level"], word["frequency_rank"]),
        "Hanzi": word["hanzi"],
        "HskLevel": str(word["hsk_level"]),
        "FreqBucket": get_freq_bucket(word["frequency_rank"]) or "",
        "PrimaryPinyin": primary["pinyin"],
        "PrimaryMeaningEs": primary["meaning_es"] or "",
        "PrimaryMeaningZh": primary["meaning_zh"] or "",
        "ExampleZh": example["example_zh"],
        "ExampleEs": example["example_es"],
        "BreakdownJson": example["breakdown_json"] or "[]",
        "SecondariesJson": json.dumps(_fetch_secondary_readings(conn, word["id"]), ensure_ascii=False),
        "CollocationsJson": json.dumps(_fetch_collocations(conn, word["id"]), ensure_ascii=False),
        "AudioWordFile": audio_word_file,
    }

    if card_type == "audio":
        normal = _fetch_audio(conn, card_example_id=example["id"], speed="normal")
        slow = _fetch_audio(conn, card_example_id=example["id"], speed="slow")
        if normal is None or slow is None:
            raise ExportError(f"card_id={card_id} ('{word['hanzi']}', audio) le falta audio normal y/o lento de oración")
        common["AudioSentenceNormalFile"] = _upload_audio(media_cache, pending_uploads, normal["file_path"])
        common["AudioSentenceSlowFile"] = _upload_audio(media_cache, pending_uploads, slow["file_path"])
        common["SentenceAlignmentNormalJson"] = normal["alignment_json"] or "null"
        common["SentenceAlignmentSlowJson"] = slow["alignment_json"] or "null"
    else:
        normal = _fetch_audio(conn, card_example_id=example["id"], speed="normal")
        if normal is None:
            raise ExportError(f"card_id={card_id} ('{word['hanzi']}', {card_type}) le falta audio de oración")
        common["AudioSentenceFile"] = _upload_audio(media_cache, pending_uploads, normal["file_path"])
        common["SentenceAlignmentJson"] = normal["alignment_json"] or "null"

    return common


def export_pending(hsk_level: int = 3, limit: Optional[int] = None) -> dict:
    """Exporta a Anki todas las tarjetas 'ready' cuyo mazo destino sea
    `hsk_level` (COALESCE(export_level, hsk_level) — export_level es un
    override manual de a qué mazo va, usado solo para la migración puntual
    de palabras HSK1/2 al mazo de HSK3; el chip visible en la tarjeta sigue
    mostrando el hsk_level real, ver _build_fields). Devuelve un resumen
    {created, updated, errors: [str, ...]}."""
    init_db()
    console = Console()
    deck_name = deck_name_for(hsk_level)

    console.print(f"[dim]Verificando mazo '{deck_name}' en Anki…[/dim]")
    ensure_deck(deck_name)
    console.print("[dim]Verificando/creando los 3 modelos de nota (SentenceCard/PatternCard/AudioCard)…[/dim]")
    setup_models(hsk_level)
    console.print("[dim]Listo. Buscando tarjetas pendientes de exportar…[/dim]")

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id AS card_id, c.card_type, c.anki_note_id, c.word_id
            FROM cards c JOIN words w ON w.id = c.word_id
            WHERE c.status = 'ready' AND COALESCE(w.export_level, w.hsk_level) = ?
            ORDER BY w.hsk_level, {_FREQ_BUCKET_SQL_CASE}, RANDOM()
            """,
            (hsk_level,),
        ).fetchall()

    if limit:
        rows = rows[:limit]

    created = 0
    updated = 0
    errors = []
    media_cache: dict = {}

    interrupted = False
    try:
        with Progress(
            TextColumn("[bold cyan]{task.fields[label]}"),
            BarColumn(bar_width=28),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            TextColumn("ETA"),
            TimeRemainingColumn(),
            TextColumn("[green]creadas {task.fields[created]}[/green]  [blue]actualizadas {task.fields[updated]}[/blue]  [red]errores {task.fields[errors]}[/red]"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "exportando", total=len(rows) or 1, label="iniciando…", created=0, updated=0, errors=0,
            )

            # Se procesa en lotes de EXPORT_BATCH_SIZE (mismo tamaño que usaba
            # el pipeline viejo, src/csv_to_anki.py, ya borrado) — cada
            # AnkiConnect call es un round-trip completo (medido en vivo:
            # ~2s cada uno contra esta instancia, sin importar el tamaño del
            # payload), así que agrupar 50 tarjetas en 1 sola llamada (via
            # `multi` para audio/updateNoteFields, o addNotes que ya acepta
            # una lista nativamente) es la diferencia entre minutos y horas
            # frente a una llamada por tarjeta.
            for chunk_start in range(0, len(rows), EXPORT_BATCH_SIZE):
                chunk = rows[chunk_start:chunk_start + EXPORT_BATCH_SIZE]
                pending_uploads: list = []
                built = []  # (row, word, fields) para las que sí se pudieron armar

                for row in chunk:
                    with get_connection() as conn:
                        word = _fetch_word(conn, row["word_id"])
                        progress.update(task, label=f"{word['hanzi']} · {row['card_type']}")
                        try:
                            fields = _build_fields(conn, media_cache, pending_uploads, word, row["card_id"], row["card_type"])
                        except ExportError as ex:
                            errors.append(str(ex))
                            progress.update(task, advance=1, errors=len(errors))
                            continue
                    built.append((row, word, fields))

                # Un solo request para TODOS los audios nuevos de este lote
                # (los ya subidos en un lote anterior de esta misma corrida
                # ni siquiera llegan aquí — ver media_cache en _upload_audio).
                store_media_files_batch(pending_uploads)

                creates = [(row, word, fields) for row, word, fields in built if not row["anki_note_id"]]
                updates = [(row, word, fields) for row, word, fields in built if row["anki_note_id"]]

                # Notas huérfanas: ya existen en Anki, pero cards.anki_note_id
                # quedó NULL (ej. un export anterior se cortó justo entre
                # crear la nota y guardar su id). Sin este chequeo, addNotes
                # las rechaza como duplicadas — acá se reconcilian primero y
                # pasan a actualizarse en vez de intentar crearlas de nuevo.
                if creates:
                    queries = [
                        f'note:"{model_name_for(row["card_type"], hsk_level)}" Hanzi:{word["hanzi"]}'
                        for row, word, fields in creates
                    ]
                    found = find_notes_batch(queries)
                    still_new = []
                    for (row, word, fields), note_ids in zip(creates, found):
                        if note_ids and len(note_ids) == 1:
                            updates.append((row, word, fields))
                            with get_connection() as conn:
                                conn.execute("UPDATE cards SET anki_note_id = ? WHERE id = ?", (note_ids[0], row["card_id"]))
                        elif note_ids and len(note_ids) > 1:
                            errors.append(f"'{word['hanzi']}' ({row['card_type']}): {len(note_ids)} notas huérfanas coinciden, requiere revisión manual")
                            progress.update(task, advance=1, errors=len(errors))
                        else:
                            still_new.append((row, word, fields))
                    creates = still_new

                if creates:
                    notes_payload = [
                        {
                            "deckName": deck_name,
                            "modelName": model_name_for(row["card_type"], hsk_level),
                            "fields": fields,
                            "options": {"allowDuplicate": False},
                            "tags": ["chinosrs", f"hsk{hsk_level}", row["card_type"]],
                        }
                        for row, word, fields in creates
                    ]
                    note_ids = post("addNotes", notes=notes_payload)
                    with get_connection() as conn:
                        for (row, word, fields), note_id in zip(creates, note_ids or [None] * len(creates)):
                            if note_id is None:
                                errors.append(f"'{word['hanzi']}' ({row['card_type']}): addNotes devolvió None (¿duplicado en Anki?)")
                                progress.update(task, advance=1, errors=len(errors))
                            else:
                                conn.execute("UPDATE cards SET anki_note_id = ? WHERE id = ?", (note_id, row["card_id"]))
                                created += 1
                                progress.update(task, advance=1, created=created)

                if updates:
                    update_note_fields_batch(
                        {"id": row["anki_note_id"], "fields": fields} for row, word, fields in updates
                    )
                    # La tarjeta está 'ready' -> lo que sea que la tenía flaggeada ya se
                    # corrigió (si no, seguiría flagged_bad/guardrail_failed y no habría
                    # llegado hasta aquí). Limpiar el flag AQUÍ, junto con el contenido,
                    # evita que quede "sin bandera pero con texto viejo". Agrupado para
                    # todo el lote (3 requests en vez de hasta 3 POR nota).
                    try:
                        clear_note_flags_batch(row["anki_note_id"] for row, word, fields in updates)
                    except Exception as ex:
                        errors.append(f"lote de {len(updates)} actualizaciones: no se pudo limpiar el flag en Anki: {ex}")
                    for row, word, fields in updates:
                        updated += 1
                        progress.update(task, advance=1, updated=updated, errors=len(errors))
    except KeyboardInterrupt:
        # Cada tarjeta se comitea a SQLite apenas su lote de 50 responde
        # (anki_note_id se guarda ahí) — como mucho se pierde el lote que
        # estaba a medias al interrumpir, nunca algo corrupto. Volver a
        # correr `export` retoma justo donde se quedó (idempotente: no
        # duplica lo ya subido).
        interrupted = True
        console.print(
            f"\n[yellow]Interrumpido — {created} creada(s), {updated} actualizada(s) antes de parar. "
            f"Lo ya subido queda guardado; vuelve a correr `export` para seguir con el resto.[/yellow]"
        )

    return {"created": created, "updated": updated, "errors": errors, "interrupted": interrupted}


if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser(description="Exporta tarjetas 'ready' de un nivel HSK a Anki vía AnkiConnect")
    parser.add_argument("--hsk-level", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    try:
        summary = export_pending(hsk_level=args.hsk_level, limit=args.limit)
    except KeyboardInterrupt:
        # Red de seguridad para un Ctrl+C durante ensure_deck/setup_models
        # (antes del loop principal, que ya se maneja solo más abajo) —
        # nunca debería verse un traceback crudo por interrumpir esto.
        print("\nInterrumpido antes de empezar a exportar tarjetas — nada que reportar.")
        sys.exit(130)

    print(f"Creadas:      {summary['created']}")
    print(f"Actualizadas: {summary['updated']}")
    if summary["errors"]:
        print(f"Errores ({len(summary['errors'])}):")
        for err in summary["errors"]:
            print(f"  - {err}")
    if summary.get("interrupted"):
        sys.exit(130)
