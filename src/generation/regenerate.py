"""Regeneración puntual de una tarjeta ya existente (no la palabra completa),
y regeneración de word_prep para palabras que nunca lo resolvieron.

Usado para: (a) tarjetas marcadas review_status='flagged_bad' tras revisión
manual en Anki (ver src/anki/review.py y la memoria
project-manual-review-workflow), (b) tarjetas que se quedaron en
'guardrail_failed' tras agotar los intentos automáticos, y (c) palabras en
word_prep_status='failed' (word_prep agotó sus 3 intentos automáticos, así
que ninguna de sus 3 tarjetas se llegó a intentar).

regenerate_card() no vuelve a correr word_prep: la lectura primaria ya
resuelta se mantiene igual, solo se regenera la oración/desglose (y su
audio) de ESE tipo de tarjeta puntual. regenerate_word_prep() sí corre el
grafo completo, porque si word_prep nunca resolvió, las 3 tarjetas nunca se
intentaron.
"""

import argparse
import json
from typing import Optional

from src.db.database import get_connection, init_db
from src.generation.audio_card import run_audio_card
from src.generation.graph import card_audio_node, get_checkpointer, run_word
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
            # No forzar review_status='flagged_bad' aquí: eso implicaría "lo marcaste en
            # Anki", que puede ser falso para una tarjeta que vino de guardrail_failed y
            # nunca tocó Anki. status='guardrail_failed' ya basta para que la próxima
            # corrida de --flagged la vuelva a intentar — solo se toca review_status al
            # escalar a needs_human (ahí sí aplica sin importar el origen).
            attempts = card["regen_attempts"] + 1
            if attempts >= REGEN_ATTEMPTS_CAP:
                conn.execute(
                    "UPDATE cards SET review_status = 'needs_human', regen_attempts = ?, updated_at = datetime('now') WHERE id = ?",
                    (attempts, card["id"]),
                )
            else:
                conn.execute(
                    "UPDATE cards SET regen_attempts = ?, updated_at = datetime('now') WHERE id = ?",
                    (attempts, card["id"]),
                )

    return audio_ok


def regenerate_word_prep(word_id: int, model: str = "gpt-4o") -> bool:
    """Reintenta word_prep para una palabra en word_prep_status='failed'.

    Si resuelve, corre el grafo completo (`run_word`) — no solo word_prep —
    porque las 3 tarjetas de esa palabra nunca se intentaron (word_prep
    nunca terminó), así que hace falta que el fan-out normal las procese
    ahora. Mismo tope que las tarjetas: si sigue fallando, escala a
    word_prep_status='needs_human' tras REGEN_ATTEMPTS_CAP rondas."""
    with get_connection() as conn:
        word = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        reading = conn.execute("SELECT pinyin FROM readings WHERE word_id = ? LIMIT 1", (word_id,)).fetchone()
    if word is None:
        raise ValueError(f"word_id={word_id}: no existe")

    seed_pinyin = reading["pinyin"] if reading else None
    source_meanings = json.loads(word["source_meanings_json"] or "[]")

    checkpointer = get_checkpointer()
    result = run_word(word_id, word["hanzi"], seed_pinyin, source_meanings, checkpointer)
    ok = bool(result.get("word_prep_ok"))

    with get_connection() as conn:
        if ok:
            conn.execute(
                "UPDATE words SET word_prep_status = 'pending', word_prep_attempts = 0 WHERE id = ?", (word_id,)
            )
        else:
            attempts = word["word_prep_attempts"] + 1
            new_status = "needs_human" if attempts >= REGEN_ATTEMPTS_CAP else "failed"
            conn.execute(
                "UPDATE words SET word_prep_status = ?, word_prep_attempts = ? WHERE id = ?",
                (new_status, attempts, word_id),
            )
    return ok


def regenerate_flagged(hsk_level: Optional[int] = None, model: str = "gpt-4o") -> dict:
    """Regenera todo lo que esté en review_status='flagged_bad' o
    status='guardrail_failed' (opcionalmente filtrado por nivel HSK), y
    también las palabras en word_prep_status='failed'. NO toca lo escalado a
    'needs_human' — eso espera intervención humana."""
    wp_query = "SELECT id AS word_id, hanzi FROM words WHERE word_prep_status = 'failed'"
    wp_params: tuple = ()
    if hsk_level is not None:
        wp_query += " AND COALESCE(export_level, hsk_level) = ?"
        wp_params = (hsk_level,)

    with get_connection() as conn:
        wp_rows = conn.execute(wp_query, wp_params).fetchall()

    wp_details = []
    wp_fixed = 0
    wp_escalated = 0
    for row in wp_rows:
        ok = regenerate_word_prep(row["word_id"], model=model)
        wp_details.append({"hanzi": row["hanzi"], "word_id": row["word_id"], "fixed": ok})
        if ok:
            wp_fixed += 1
        else:
            with get_connection() as conn:
                st = conn.execute("SELECT word_prep_status FROM words WHERE id = ?", (row["word_id"],)).fetchone()
            if st["word_prep_status"] == "needs_human":
                wp_escalated += 1

    query = """
        SELECT c.id AS card_id, c.word_id, c.card_type, w.hanzi
        FROM cards c JOIN words w ON w.id = c.word_id
        WHERE (c.review_status = 'flagged_bad' OR c.status = 'guardrail_failed')
          AND c.review_status != 'needs_human'
    """
    params: tuple = ()
    if hsk_level is not None:
        query += " AND COALESCE(w.export_level, w.hsk_level) = ?"
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
        "word_prep_total": len(wp_rows),
        "word_prep_fixed": wp_fixed,
        "word_prep_escalated": wp_escalated,
        "word_prep_details": wp_details,
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
        if summary["word_prep_total"]:
            print(
                f"word_prep -> Total: {summary['word_prep_total']}  Arregladas: {summary['word_prep_fixed']}  "
                f"Escaladas a needs_human: {summary['word_prep_escalated']}"
            )
            for d in summary["word_prep_details"]:
                print(f"  [{'OK' if d['fixed'] else 'FAIL'}] {d['hanzi']} (word_id={d['word_id']}) · word_prep")
        print(
            f"Total: {summary['total']}  Arregladas: {summary['fixed']}  "
            f"Siguen fallando: {summary['still_failed']}  Escaladas a needs_human: {summary['escalated_to_human']}"
        )
        for d in summary["details"]:
            print(f"  [{'OK' if d['fixed'] else 'FAIL'}] {d['hanzi']} (word_id={d['word_id']}) · {d['card_type']}")
    elif args.word and args.type:
        with get_connection() as conn:
            word = conn.execute(
                "SELECT id FROM words WHERE hanzi = ? AND COALESCE(export_level, hsk_level) = ?", (args.word, args.hsk_level)
            ).fetchone()
        if word is None:
            print(f"No se encontró '{args.word}' en HSK{args.hsk_level}")
        else:
            ok = regenerate_card(word["id"], args.type)
            print("OK" if ok else "FAIL")
    else:
        parser.error("Usa --flagged, o --word <hanzi> junto con --type <sentence|pattern|audio>")
