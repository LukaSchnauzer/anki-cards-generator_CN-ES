"""Regeneración puntual de una tarjeta ya existente (no la palabra completa).

Usado para: (a) tarjetas marcadas review_status='flagged_bad' tras revisión
manual en Anki (ver src/anki/review.py y la memoria
project-manual-review-workflow), y (b) tarjetas que se quedaron en
'guardrail_failed' tras agotar los intentos automáticos.

No vuelve a correr word_prep: la lectura primaria ya resuelta se mantiene
igual, solo se regenera la oración/desglose (y su audio) de ESE tipo de
tarjeta puntual.
"""

import argparse
from typing import Optional

from src.db.database import get_connection, init_db
from src.generation.audio_card import run_audio_card
from src.generation.graph import card_audio_node
from src.generation.pattern_card import run_pattern_card
from src.generation.sentence_card import run_sentence_card

RUNNERS = {"sentence": run_sentence_card, "pattern": run_pattern_card, "audio": run_audio_card}

# Rondas de regenerate_card fallidas CONSECUTIVAS que se toleran antes de
# escalar a review_status='needs_human' y dejar de reintentar solo (decisión
# explícita del usuario: 1 ronda automática inicial + hasta 2 rondas de
# regenerate = hasta 9 llamadas al LLM en total antes de rendirse).
REGEN_ATTEMPTS_CAP = 2


def _fetch_context(word_id: int, card_type: str):
    with get_connection() as conn:
        word = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        primary = conn.execute("SELECT * FROM readings WHERE word_id = ? AND is_primary = 1", (word_id,)).fetchone()
        card = conn.execute("SELECT * FROM cards WHERE word_id = ? AND card_type = ?", (word_id, card_type)).fetchone()
    return word, primary, card


def regenerate_card(word_id: int, card_type: str, model: str = "gpt-4o") -> bool:
    """Regenera el texto + audio de una tarjeta puntual. Devuelve True si
    quedó 'ready' de nuevo. Solo toca SQLite — NO habla con Anki (ni sube el
    contenido nuevo ni limpia el flag): eso lo hace `export`, que es quien de
    verdad sincroniza el contenido, así que hace falta correrlo después para
    que la nota deje de verse desactualizada. Ver [[project-manual-review-workflow]].

    Si falla, incrementa regen_attempts; al llegar a REGEN_ATTEMPTS_CAP deja
    de marcarla 'flagged_bad' (que `regenerate --flagged` reintentaría solo)
    y la escala a 'needs_human' — ahí se detiene el gasto automático."""
    word, primary, card = _fetch_context(word_id, card_type)
    if word is None or primary is None or card is None:
        raise ValueError(f"word_id={word_id}: falta la palabra, su lectura primaria o la tarjeta '{card_type}'")

    runner = RUNNERS[card_type]
    text_ok = runner(
        card["id"], primary["id"], word["hanzi"], primary["pinyin"], primary["meaning_es"], primary["meaning_zh"],
        model=model,
    )
    audio_ok = text_ok and card_audio_node(
        word_id, card_type, f"{card_type}_audio_regen", slow_too=(card_type == "audio")
    )

    with get_connection() as conn:
        if audio_ok:
            conn.execute(
                """UPDATE cards SET review_status = 'pending', review_notes = NULL, regen_attempts = 0,
                   updated_at = datetime('now') WHERE id = ?""",
                (card["id"],),
            )
        else:
            attempts = card["regen_attempts"] + 1
            new_review_status = "needs_human" if attempts >= REGEN_ATTEMPTS_CAP else "flagged_bad"
            conn.execute(
                """UPDATE cards SET review_status = ?, regen_attempts = ?, updated_at = datetime('now') WHERE id = ?""",
                (new_review_status, attempts, card["id"]),
            )

    return audio_ok


def regenerate_flagged(hsk_level: Optional[int] = None, model: str = "gpt-4o") -> dict:
    """Regenera todo lo que esté en review_status='flagged_bad' o
    status='guardrail_failed' (opcionalmente filtrado por nivel HSK).
    NO toca lo escalado a 'needs_human' — eso espera intervención humana."""
    query = """
        SELECT c.id AS card_id, c.word_id, c.card_type, w.hanzi
        FROM cards c JOIN words w ON w.id = c.word_id
        WHERE (c.review_status = 'flagged_bad' OR c.status = 'guardrail_failed')
          AND c.review_status != 'needs_human'
    """
    params: tuple = ()
    if hsk_level is not None:
        query += " AND w.hsk_level = ?"
        params = (hsk_level,)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    details = []
    fixed = 0
    escalated = 0
    for row in rows:
        ok = regenerate_card(row["word_id"], row["card_type"], model=model)
        details.append({"hanzi": row["hanzi"], "word_id": row["word_id"], "card_type": row["card_type"], "fixed": ok})
        if ok:
            fixed += 1
        else:
            with get_connection() as conn:
                rs = conn.execute("SELECT review_status FROM cards WHERE id = ?", (row["card_id"],)).fetchone()
            if rs["review_status"] == "needs_human":
                escalated += 1

    return {
        "total": len(rows),
        "fixed": fixed,
        "still_failed": len(rows) - fixed,
        "escalated_to_human": escalated,
        "details": details,
    }


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Regenera tarjetas puntuales (flaggeadas o fallidas)")
    parser.add_argument("--flagged", action="store_true", help="Regenera todo lo marcado flagged_bad/guardrail_failed")
    parser.add_argument("--word", help="Hanzi de una palabra puntual (junto con --type)")
    parser.add_argument("--type", choices=list(RUNNERS.keys()), help="Tipo de tarjeta puntual (junto con --word)")
    parser.add_argument("--hsk-level", type=int, default=3)
    args = parser.parse_args()

    if args.flagged:
        summary = regenerate_flagged(hsk_level=args.hsk_level)
        print(
            f"Total: {summary['total']}  Arregladas: {summary['fixed']}  "
            f"Siguen fallando: {summary['still_failed']}  Escaladas a needs_human: {summary['escalated_to_human']}"
        )
        for d in summary["details"]:
            print(f"  [{'OK' if d['fixed'] else 'FAIL'}] {d['hanzi']} (word_id={d['word_id']}) · {d['card_type']}")
    elif args.word and args.type:
        with get_connection() as conn:
            word = conn.execute(
                "SELECT id FROM words WHERE hanzi = ? AND hsk_level = ?", (args.word, args.hsk_level)
            ).fetchone()
        if word is None:
            print(f"No se encontró '{args.word}' en HSK{args.hsk_level}")
        else:
            ok = regenerate_card(word["id"], args.type)
            print("OK" if ok else "FAIL")
    else:
        parser.error("Usa --flagged, o --word <hanzi> junto con --type <sentence|pattern|audio>")
