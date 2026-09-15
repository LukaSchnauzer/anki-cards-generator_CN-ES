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

from src.anki.api import clear_note_flags, ensure_deck, post, store_media_file
from src.anki.models import CARD_TYPE_LABELS, model_name_for, setup_models
from src.db.database import get_connection, init_db
from src.utils.frequency import get_freq_bucket

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DECK_PREFIX = "ChinoSRS"

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


def _sort_key(frequency_rank: Optional[int]) -> str:
    """Primer campo del modelo -> Anki lo usa como Sort Field por defecto.
    bucket (2 dígitos) + aleatorio (4 dígitos), para que el Browser ordene
    igual que como se crearon las notas (ver _FREQ_BUCKET_SQL_CASE)."""
    bucket_code = _FREQ_BUCKET_ORDER.get(get_freq_bucket(frequency_rank), 9)
    return f"{bucket_code:02d}{random.randint(0, 9999):04d}"


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


def _upload_audio(media_cache: dict, file_path: str) -> str:
    if file_path in media_cache:
        return media_cache[file_path]
    filename = store_media_file(PROJECT_ROOT / file_path)
    media_cache[file_path] = filename
    return filename


def _build_fields(conn, media_cache: dict, word: dict, card_id: int, card_type: str) -> dict:
    primary = _fetch_primary_reading(conn, word["id"])
    if primary is None:
        raise ExportError(f"'{word['hanzi']}' (word_id={word['id']}) no tiene lectura primaria")

    example = _fetch_example(conn, card_id)
    if example is None:
        raise ExportError(f"card_id={card_id} ('{word['hanzi']}', {card_type}) no tiene card_example")

    word_audio = _fetch_audio(conn, reading_id=primary["id"], speed="slow")
    if word_audio is None:
        raise ExportError(f"card_id={card_id} ('{word['hanzi']}') no tiene audio de palabra")
    audio_word_file = _upload_audio(media_cache, word_audio["file_path"])

    common = {
        "SortKey": _sort_key(word["frequency_rank"]),
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
        common["AudioSentenceNormalFile"] = _upload_audio(media_cache, normal["file_path"])
        common["AudioSentenceSlowFile"] = _upload_audio(media_cache, slow["file_path"])
        common["SentenceAlignmentNormalJson"] = normal["alignment_json"] or "null"
        common["SentenceAlignmentSlowJson"] = slow["alignment_json"] or "null"
    else:
        normal = _fetch_audio(conn, card_example_id=example["id"], speed="normal")
        if normal is None:
            raise ExportError(f"card_id={card_id} ('{word['hanzi']}', {card_type}) le falta audio de oración")
        common["AudioSentenceFile"] = _upload_audio(media_cache, normal["file_path"])
        common["SentenceAlignmentJson"] = normal["alignment_json"] or "null"

    return common


def export_pending(hsk_level: int = 3, limit: Optional[int] = None) -> dict:
    """Exporta a Anki todas las tarjetas 'ready' de `hsk_level`. Devuelve un
    resumen {created, updated, errors: [str, ...]}."""
    init_db()
    deck_name = deck_name_for(hsk_level)
    ensure_deck(deck_name)
    setup_models(hsk_level)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id AS card_id, c.card_type, c.anki_note_id, c.word_id
            FROM cards c JOIN words w ON w.id = c.word_id
            WHERE c.status = 'ready' AND w.hsk_level = ?
            ORDER BY {_FREQ_BUCKET_SQL_CASE}, RANDOM()
            """,
            (hsk_level,),
        ).fetchall()

    if limit:
        rows = rows[:limit]

    created = 0
    updated = 0
    errors = []
    media_cache: dict = {}

    for row in rows:
        with get_connection() as conn:
            word = _fetch_word(conn, row["word_id"])
            try:
                fields = _build_fields(conn, media_cache, word, row["card_id"], row["card_type"])
            except ExportError as ex:
                errors.append(str(ex))
                continue

        model_name = model_name_for(row["card_type"], hsk_level)

        if row["anki_note_id"]:
            post("updateNoteFields", note={"id": row["anki_note_id"], "fields": fields})
            # La tarjeta está 'ready' -> lo que sea que la tenía flaggeada ya
            # se corrigió (si no, seguiría flagged_bad/guardrail_failed y no
            # habría llegado hasta aquí). Limpiar el flag AQUÍ, junto con el
            # contenido, evita que quede "sin bandera pero con texto viejo".
            try:
                clear_note_flags(row["anki_note_id"])
            except Exception as ex:
                errors.append(f"'{word['hanzi']}' ({row['card_type']}): no se pudo limpiar el flag en Anki: {ex}")
            updated += 1
            continue

        note_ids = post(
            "addNotes",
            notes=[
                {
                    "deckName": deck_name,
                    "modelName": model_name,
                    "fields": fields,
                    "options": {"allowDuplicate": False},
                    "tags": ["chinosrs", f"hsk{hsk_level}", row["card_type"]],
                }
            ],
        )
        note_id = note_ids[0] if note_ids else None
        if note_id is None:
            errors.append(f"'{word['hanzi']}' ({row['card_type']}): addNotes devolvió None (¿duplicado en Anki?)")
            continue

        with get_connection() as conn:
            conn.execute("UPDATE cards SET anki_note_id = ? WHERE id = ?", (note_id, row["card_id"]))
        created += 1

    return {"created": created, "updated": updated, "errors": errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exporta tarjetas 'ready' de un nivel HSK a Anki vía AnkiConnect")
    parser.add_argument("--hsk-level", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    summary = export_pending(hsk_level=args.hsk_level, limit=args.limit)
    print(f"Creadas:      {summary['created']}")
    print(f"Actualizadas: {summary['updated']}")
    if summary["errors"]:
        print(f"Errores ({len(summary['errors'])}):")
        for err in summary["errors"]:
            print(f"  - {err}")
