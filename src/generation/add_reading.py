"""Agrega una lectura (acepción) NUEVA a una palabra — para cuando
word_prep nunca detectó el sentido realmente dominante en absoluto (a
diferencia de swap_reading.py, donde el sentido correcto ya existía como
lectura secundaria y solo había que promoverlo).

Caso real: 系 quedó con solo dos lecturas — "sistema" (primaria) y "atar"
(secundaria, otra pronunciación) — pero el uso más común de 系 solo (sin
"统") en chino moderno es "departamento/facultad académica" (物理系, 中文系),
un sentido específico que ninguna de las dos lecturas registradas cubre.
"sistema" no está mal, pero es demasiado abstracto para que el LLM genere
una oración natural con la palabra sola.

Por defecto la nueva lectura se vuelve la primaria (degradando la que lo
era a secundaria) — es el caso típico: la acepción que faltaba es la que
de verdad domina el uso real."""

import argparse

from src.db.database import get_connection, init_db
from src.generation.regenerate import regenerate_card
from src.utils.cost_tracker import get_tracker

CARD_TYPES = ("sentence", "pattern", "audio")


def add_reading(
    word_id: int,
    pinyin: str,
    meaning_es: str,
    meaning_zh: str = None,
    make_primary: bool = True,
    register: str = None,
) -> dict:
    """Inserta una lectura nueva. source='llm' porque, igual que las
    lecturas que sí pasaron por word_prep, ya está verificada (por un
    humano, en vez de por el LLM) — así word_prep_node sigue sin repetir
    trabajo para esta palabra."""
    with get_connection() as conn:
        old_primary = conn.execute(
            "SELECT meaning_es FROM readings WHERE word_id = ? AND is_primary = 1", (word_id,)
        ).fetchone()

        if make_primary:
            conn.execute("UPDATE readings SET is_primary = 0 WHERE word_id = ? AND is_primary = 1", (word_id,))

        cur = conn.execute(
            """INSERT INTO readings (word_id, pinyin, is_primary, meaning_es, meaning_zh, register, source)
               VALUES (?, ?, ?, ?, ?, ?, 'llm')""",
            (word_id, pinyin, 1 if make_primary else 0, meaning_es, meaning_zh, register),
        )
        new_id = cur.lastrowid

    return {
        "new_reading_id": new_id,
        "is_primary": make_primary,
        "old_primary_meaning": old_primary["meaning_es"] if (old_primary and make_primary) else None,
        "new_meaning": meaning_es,
    }


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Agrega una lectura nueva a una palabra")
    parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    parser.add_argument("--pinyin", required=True, help="Pinyin de la lectura nueva")
    parser.add_argument("--meaning-es", required=True, help="Significado en español")
    parser.add_argument("--meaning-zh", default=None, help="Definición en chino (opcional)")
    parser.add_argument("--register", default=None, help="reg:colloquial | reg:neutral | reg:formal | reg:literary (opcional)")
    parser.add_argument("--secondary", action="store_true", help="Agrega como secundaria en vez de primaria (default: primaria)")
    parser.add_argument("--hsk-level", type=int, default=3)
    parser.add_argument("--regenerate", action="store_true", help="Regenera las 3 tarjetas de una vez con la lectura nueva")
    args = parser.parse_args()

    with get_connection() as conn:
        word = conn.execute(
            "SELECT id FROM words WHERE hanzi = ? AND COALESCE(export_level, hsk_level) = ?", (args.word, args.hsk_level)
        ).fetchone()
    if word is None:
        print(f"No se encontró '{args.word}' en HSK{args.hsk_level}")
    else:
        result = add_reading(
            word["id"], args.pinyin, args.meaning_es, args.meaning_zh,
            make_primary=not args.secondary, register=args.register,
        )
        if result["is_primary"]:
            print(f"Lectura nueva agregada y vuelta primaria: '{result['old_primary_meaning']}' -> '{result['new_meaning']}'")
        else:
            print(f"Lectura nueva agregada como secundaria: '{result['new_meaning']}'")

        if args.regenerate:
            for card_type in CARD_TYPES:
                ok = regenerate_card(word["id"], card_type)
                print(f"  [{'OK' if ok else 'FAIL'}] {card_type}")
            tracker = get_tracker()
            print(
                f"Costo estimado: ${tracker.total_cost_usd:.4f}"
                f"  ·  LLM ${tracker.llm_cost_usd:.4f} ({tracker.llm_calls} llamadas)"
                f"  ·  ElevenLabs ${tracker.elevenlabs_cost_usd:.4f} ({tracker.elevenlabs_calls} llamadas)"
            )
