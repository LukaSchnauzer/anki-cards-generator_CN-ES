"""Flujo de revisión manual: el usuario flaggea tarjetas malas con el flag
nativo de colores de Anki (Ctrl+1..7) y las filtra ahí mismo (`flag:N` en el
Browser); este módulo trae esa lista de vuelta a SQLite como
cards.review_status='flagged_bad', sin tocar nada en Anki (solo lee).

El mapeo de vuelta a la fila de `cards` no necesita ningún campo nuevo en la
nota: el nombre del modelo (ChinoSRS_{CardType}_HSK{nivel}) ya da el
card_type y el nivel, y el campo Hanzi da la palabra. Ver la memoria
project-manual-review-workflow.
"""

import argparse
import re

from src.anki.api import post
from src.anki.models import CARD_TYPE_LABELS
from src.db.database import get_connection, init_db

LABEL_TO_CARD_TYPE = {v: k for k, v in CARD_TYPE_LABELS.items()}
MODEL_NAME_RE = re.compile(r"^ChinoSRS_(SentenceCard|PatternCard|AudioCard)_HSK(\d+)$")


def flag_batch(flag: int, notes_text: str = "") -> dict:
    """Busca notas ChinoSRS con `flag:N` en Anki y marca sus tarjetas como
    review_status='flagged_bad' en SQLite. Devuelve {flagged, unmatched}."""
    init_db()
    # Acotado al mazo real (no "Chino SRS" legacy ni "ChinoSRS Debug") — el
    # mazo viejo tiene miles de flags propios de otra época que no son de
    # este flujo, y mezclarlos solo generaría ruido de "sin mapear".
    note_ids = post("findNotes", query=f'flag:{flag} deck:"ChinoSRS - HSK*" note:ChinoSRS_*')
    if not note_ids:
        return {"flagged": 0, "unmatched": []}

    infos = post("notesInfo", notes=note_ids)
    flagged = 0
    unmatched = []

    for info in infos:
        m = MODEL_NAME_RE.match(info["modelName"])
        if not m:
            unmatched.append(f"noteId={info['noteId']}: modelo desconocido '{info['modelName']}'")
            continue
        label, hsk_level = m.group(1), int(m.group(2))
        card_type = LABEL_TO_CARD_TYPE[label]
        hanzi = info["fields"].get("Hanzi", {}).get("value")
        if not hanzi:
            unmatched.append(f"noteId={info['noteId']}: sin campo Hanzi")
            continue

        with get_connection() as conn:
            word = conn.execute(
                "SELECT id FROM words WHERE hanzi = ? AND hsk_level = ?", (hanzi, hsk_level)
            ).fetchone()
            if word is None:
                unmatched.append(f"noteId={info['noteId']}: '{hanzi}' HSK{hsk_level} no existe en la DB")
                continue
            card = conn.execute(
                "SELECT id FROM cards WHERE word_id = ? AND card_type = ?", (word["id"], card_type)
            ).fetchone()
            if card is None:
                unmatched.append(f"noteId={info['noteId']}: '{hanzi}' no tiene tarjeta '{card_type}'")
                continue
            conn.execute(
                "UPDATE cards SET review_status = 'flagged_bad', review_notes = ?, updated_at = datetime('now') WHERE id = ?",
                (notes_text, card["id"]),
            )
            # Log de cuántas veces se ha flaggeado esta tarjeta (para el dashboard) —
            # reusa generation_phases en vez de una tabla/columna nueva.
            prev = conn.execute(
                "SELECT COALESCE(MAX(attempt), 0) AS n FROM generation_phases WHERE card_id = ? AND phase = 'review_flag'",
                (card["id"],),
            ).fetchone()
            conn.execute(
                "INSERT INTO generation_phases (card_id, phase, status, attempt, notes) VALUES (?, 'review_flag', 'flagged_bad', ?, ?)",
                (card["id"], prev["n"] + 1, notes_text),
            )
        flagged += 1

    return {"flagged": flagged, "unmatched": unmatched}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importa tarjetas flageadas en Anki (flag:N) a review_status='flagged_bad'")
    parser.add_argument("--flag", type=int, required=True, choices=range(1, 8), help="Color de flag de Anki (1-7)")
    parser.add_argument("--notes", default="", help="Nota de por qué se flaggearon (aplica a todas las encontradas)")
    args = parser.parse_args()

    summary = flag_batch(args.flag, notes_text=args.notes)
    print(f"Flaggeadas: {summary['flagged']}")
    if summary["unmatched"]:
        print(f"Sin mapear ({len(summary['unmatched'])}):")
        for u in summary["unmatched"]:
            print(f"  - {u}")
