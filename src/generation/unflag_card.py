"""Quita el flag de review de una tarjeta SIN tocar su contenido — para
falsos positivos: `audit-naturalness` (o una revisión manual) la marcó
`needs_human`/`flagged_bad`, pero al revisarla resulta que ya estaba bien
y no hace falta cambiar nada (ej. 管: "这个项目由我来管" salió marcada por
el audit, pero es la misma construcción "由...来管" que otra tarjeta de la
misma palabra que SÍ pasó — inconsistencia del audit, no un error real).

No regenera nada, no habla con Anki — solo limpia review_status/
review_notes en SQLite, igual que hace `export` cuando de verdad se
corrige y resube una tarjeta."""

import argparse

from src.db.database import get_connection, init_db


def unflag_card(word_id: int, card_type: str) -> dict:
    with get_connection() as conn:
        card = conn.execute(
            "SELECT id, review_status, review_notes FROM cards WHERE word_id = ? AND card_type = ?",
            (word_id, card_type),
        ).fetchone()
        if card is None:
            raise ValueError(f"word_id={word_id}: no existe la tarjeta '{card_type}'")

        old_status, old_notes = card["review_status"], card["review_notes"]
        conn.execute(
            "UPDATE cards SET review_status = 'unflagged', review_notes = NULL, updated_at = datetime('now') WHERE id = ?",
            (card["id"],),
        )

    return {"card_id": card["id"], "old_review_status": old_status, "old_review_notes": old_notes}


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Quita el flag de review de una tarjeta sin tocar su contenido (falsos positivos)")
    parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    parser.add_argument("--type", required=True, choices=["sentence", "pattern", "audio"])
    parser.add_argument("--hsk-level", type=int, default=3)
    args = parser.parse_args()

    with get_connection() as conn:
        word = conn.execute(
            "SELECT id FROM words WHERE hanzi = ? AND COALESCE(export_level, hsk_level) = ?", (args.word, args.hsk_level)
        ).fetchone()
    if word is None:
        print(f"No se encontró '{args.word}' en HSK{args.hsk_level}")
    else:
        result = unflag_card(word["id"], args.type)
        print(f"Tarjeta {result['card_id']} ({args.word}, {args.type}) desflaggeada: '{result['old_review_status']}' -> 'unflagged'")
        if result["old_review_notes"]:
            print(f"  (nota descartada: {result['old_review_notes']})")
