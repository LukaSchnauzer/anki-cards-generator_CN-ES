"""Carga un JSON de vocabulario HSK (ej. resources/hsk3.json) en la base SQLite.

Por cada entrada:
  - inserta la palabra en `words`
  - inserta una lectura semilla en `readings` (pinyin de la fuente, source='seed',
    sin significado todavía — eso lo llena el LLM más adelante y puede corregir el pinyin)
  - crea las 3 tarjetas (sentence/pattern/audio) en `cards` con status='pending'

Es idempotente: correrlo varias veces sobre el mismo JSON no duplica filas.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.db.database import DEFAULT_DB_PATH, get_connection, init_db

CARD_TYPES = ("sentence", "pattern", "audio")


def get_hsk_info(levels):
    """Devuelve (hsk_level, hsk_standard) prefiriendo el estándar 'new' sobre 'old'."""
    if not levels:
        return None, None
    best_new = None
    best_old = None
    for lv in levels:
        if not isinstance(lv, str):
            continue
        if lv.startswith("new-"):
            tail = lv[4:].rstrip("+")
            if tail.isdigit():
                n = int(tail)
                if best_new is None or n < best_new:
                    best_new = n
        elif lv.startswith("old-"):
            tail = lv[4:].rstrip("+")
            if tail.isdigit():
                n = int(tail)
                if best_old is None or n < best_old:
                    best_old = n
    if best_new is not None:
        return best_new, "new"
    if best_old is not None:
        return best_old, "old"
    return None, None


def load_entries(conn, entries):
    stats = {"words_new": 0, "words_existing": 0, "readings_seeded": 0, "cards_created": 0}

    for e in entries:
        hanzi = e.get("simplified")
        if not hanzi:
            continue

        hsk_level, hsk_standard = get_hsk_info(e.get("level"))
        forms = e.get("forms") or []
        traditional = forms[0].get("traditional") if forms else None
        pinyin = forms[0].get("transcriptions", {}).get("pinyin") if forms else None
        meanings = forms[0].get("meanings", []) if forms else []

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO words
                (hanzi, traditional, radical, hsk_level, hsk_standard, frequency_rank, pos_json, source_meanings_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hanzi,
                traditional,
                e.get("radical"),
                hsk_level,
                hsk_standard,
                e.get("frequency") or None,
                json.dumps(e.get("pos", []), ensure_ascii=False),
                json.dumps(meanings, ensure_ascii=False),
            ),
        )

        if cur.rowcount:
            word_id = cur.lastrowid
            stats["words_new"] += 1
        else:
            stats["words_existing"] += 1
            row = conn.execute(
                "SELECT id FROM words WHERE hanzi = ? AND hsk_level IS ?",
                (hanzi, hsk_level),
            ).fetchone()
            word_id = row["id"]

        has_reading = conn.execute(
            "SELECT 1 FROM readings WHERE word_id = ? LIMIT 1", (word_id,)
        ).fetchone()
        if not has_reading and pinyin:
            conn.execute(
                """
                INSERT INTO readings (word_id, pinyin, is_primary, source)
                VALUES (?, ?, 1, 'seed')
                """,
                (word_id, pinyin),
            )
            stats["readings_seeded"] += 1

        for card_type in CARD_TYPES:
            cur = conn.execute(
                "INSERT OR IGNORE INTO cards (word_id, card_type) VALUES (?, ?)",
                (word_id, card_type),
            )
            if cur.rowcount:
                stats["cards_created"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Carga un JSON de vocabulario HSK en la base SQLite")
    parser.add_argument("--input", "-i", required=True, help="Ruta al JSON (ej. resources/hsk3.json)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Ruta a la base SQLite")
    args = parser.parse_args()

    db_path = Path(args.db)
    init_db(db_path)

    with open(args.input, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    entries = data if isinstance(data, list) else [data]

    with get_connection(db_path) as conn:
        stats = load_entries(conn, entries)

    print(f"Palabras nuevas:      {stats['words_new']}")
    print(f"Palabras ya existían: {stats['words_existing']}")
    print(f"Lecturas sembradas:   {stats['readings_seeded']}")
    print(f"Tarjetas creadas:     {stats['cards_created']}")


if __name__ == "__main__":
    main()
