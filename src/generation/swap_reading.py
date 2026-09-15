"""Cambia cuál lectura de una palabra es la primaria — para cuando
word_prep clasificó mal cuál acepción es la más común (ej. 把: asignó
'agarrar' como primaria cuando el uso real dominante en chino moderno es
la partícula gramatical del 把字句, ya registrada como lectura secundaria).

Al cambiar la primaria, las tarjetas ya generadas quedan desactualizadas —
demuestran el significado VIEJO, no el que ahora es primario — así que
opcionalmente las regenera de una vez (--regenerate).
"""

import argparse

from src.db.database import get_connection, init_db
from src.generation.graph import ensure_word_audio
from src.generation.regenerate import regenerate_card
from src.utils.cost_tracker import get_tracker

CARD_TYPES = ("sentence", "pattern", "audio")


def swap_primary_reading(word_id: int, meaning_query: str) -> dict:
    """Busca entre las lecturas de la palabra una cuyo meaning_es contenga
    `meaning_query` (sin importar mayúsculas) y la hace primaria, bajando a
    secundaria la que era primaria. Falla si no hay match único."""
    with get_connection() as conn:
        readings = conn.execute("SELECT * FROM readings WHERE word_id = ?", (word_id,)).fetchall()
        matches = [r for r in readings if meaning_query.lower() in (r["meaning_es"] or "").lower()]

        if len(matches) == 0:
            raise ValueError(
                f"Ninguna lectura coincide con {meaning_query!r}. Lecturas disponibles: "
                f"{[r['meaning_es'] for r in readings]}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"Coinciden {len(matches)} lecturas con {meaning_query!r}, sé más específico: "
                f"{[r['meaning_es'] for r in matches]}"
            )

        new_primary = matches[0]
        if new_primary["is_primary"]:
            return {"changed": False, "new_primary_meaning": new_primary["meaning_es"]}

        old_primary = conn.execute(
            "SELECT meaning_es FROM readings WHERE word_id = ? AND is_primary = 1", (word_id,)
        ).fetchone()
        conn.execute("UPDATE readings SET is_primary = 0 WHERE word_id = ? AND is_primary = 1", (word_id,))
        conn.execute("UPDATE readings SET is_primary = 1 WHERE id = ?", (new_primary["id"],))

    # El audio de palabra está atado a reading_id, no a word_id — si esta
    # lectura nunca fue primaria antes (el caso típico acá), nunca tuvo su
    # propio audio generado. Sin esto, export fallaba con "no tiene audio
    # de palabra" para las 3 tarjetas (encontrado en vivo: 把/所/架/较/顿).
    ensure_word_audio(word_id)

    return {
        "changed": True,
        "old_primary_meaning": old_primary["meaning_es"] if old_primary else None,
        "new_primary_meaning": new_primary["meaning_es"],
    }


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Cambia cuál lectura de una palabra es la primaria")
    parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    parser.add_argument("--meaning", required=True, help="Texto (parcial) del meaning_es de la lectura que debe ser primaria")
    parser.add_argument("--hsk-level", type=int, default=3)
    parser.add_argument("--regenerate", action="store_true", help="Regenera las 3 tarjetas de una vez con la nueva lectura primaria")
    args = parser.parse_args()

    with get_connection() as conn:
        word = conn.execute(
            "SELECT id FROM words WHERE hanzi = ? AND COALESCE(export_level, hsk_level) = ?", (args.word, args.hsk_level)
        ).fetchone()
    if word is None:
        print(f"No se encontró '{args.word}' en HSK{args.hsk_level}")
    else:
        result = swap_primary_reading(word["id"], args.meaning)
        if result["changed"]:
            print(f"Primaria cambiada: '{result['old_primary_meaning']}' -> '{result['new_primary_meaning']}'")
        else:
            print(f"Ya era primaria: '{result['new_primary_meaning']}' (nada que cambiar)")

        if args.regenerate:
            for card_type in CARD_TYPES:
                ok = regenerate_card(word["id"], card_type)
                print(f"  [{'OK' if ok else 'FAIL'}] {card_type}")

        # swap_primary_reading ya puede haber gastado en ElevenLabs (ensure_word_audio),
        # aunque no se haya pedido --regenerate — imprimir siempre que se cambió algo.
        if result["changed"]:
            tracker = get_tracker()
            print(
                f"Costo estimado: ${tracker.total_cost_usd:.4f}"
                f"  ·  LLM ${tracker.llm_cost_usd:.4f} ({tracker.llm_calls} llamadas)"
                f"  ·  ElevenLabs ${tracker.elevenlabs_cost_usd:.4f} ({tracker.elevenlabs_calls} llamadas)"
            )
