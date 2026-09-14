"""Piezas compartidas entre los agentes de tarjeta (SentenceCard, PatternCard, ...).

Todos producen la misma forma de salida (una oración + traducción + pinyin +
desglose + notas gramaticales) y se guardan igual en card_examples, así que
esa parte vive acá en vez de duplicarse por agente.
"""

import json
from typing import List, Optional

from pydantic import BaseModel, Field


class BreakdownItemOut(BaseModel):
    hanzi: str
    pinyin: str
    grammar_role: str
    meaning: str
    usage_note: Optional[str] = None


class CardExampleOutput(BaseModel):
    example_zh: str
    example_es: str
    example_pinyin: str
    breakdown: List[BreakdownItemOut]
    grammar_notes: List[str] = Field(default_factory=list)


def build_user_prompt(hanzi: str, pinyin: str, meaning_es: str, meaning_zh: str) -> str:
    return (
        f"hanzi: {hanzi}\n"
        f"pinyin (ya determinado, no lo cambies): {pinyin}\n"
        f"significado en español (ya determinado): {meaning_es}\n"
        f"significado en chino (ya determinado): {meaning_zh}\n"
    )


def save_card_example(conn, card_id: int, reading_id: int, result: CardExampleOutput) -> None:
    """Reemplaza el ejemplo existente de la tarjeta (si lo hay) por el nuevo resultado."""
    conn.execute("DELETE FROM card_examples WHERE card_id = ?", (card_id,))
    conn.execute(
        """
        INSERT INTO card_examples (card_id, reading_id, example_zh, example_es, example_pinyin, breakdown_json, grammar_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            card_id,
            reading_id,
            result.example_zh,
            result.example_es,
            result.example_pinyin,
            json.dumps([item.model_dump() for item in result.breakdown], ensure_ascii=False),
            json.dumps(result.grammar_notes, ensure_ascii=False),
        ),
    )


def log_phase(conn, card_id: int, phase: str, status: str, attempt: int, notes: str = "") -> None:
    conn.execute(
        "INSERT INTO generation_phases (card_id, phase, status, attempt, notes) VALUES (?, ?, ?, ?, ?)",
        (card_id, phase, status, attempt, notes),
    )


def guardrail_context(hanzi: str, result: CardExampleOutput) -> str:
    return json.dumps(
        {
            "hanzi_objetivo": hanzi,
            "oracion": result.example_zh,
            "traduccion": result.example_es,
            "pinyin_de_la_oracion": result.example_pinyin,
            "desglose": [item.model_dump() for item in result.breakdown],
        },
        ensure_ascii=False,
    )


def mark_card_text_ready(conn, card_id: int) -> None:
    """El texto (oración/desglose) pasó el guardrail. Todavía falta el audio
    para que la tarjeta esté 'ready' del todo."""
    conn.execute("UPDATE cards SET status = 'guardrail_passed', updated_at = datetime('now') WHERE id = ?", (card_id,))


def mark_card_ready(conn, card_id: int) -> None:
    conn.execute("UPDATE cards SET status = 'ready', updated_at = datetime('now') WHERE id = ?", (card_id,))


def mark_card_guardrail_failed(conn, card_id: int) -> None:
    conn.execute("UPDATE cards SET status = 'guardrail_failed', updated_at = datetime('now') WHERE id = ?", (card_id,))


def save_audio_file(
    conn,
    *,
    scope: str,
    file_path: str,
    speed: str,
    engine: str,
    reading_id: int = None,
    card_example_id: int = None,
    alignment: dict = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audio_files (scope, reading_id, card_example_id, speed, engine, file_path, alignment_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scope,
            reading_id,
            card_example_id,
            speed,
            engine,
            file_path,
            json.dumps(alignment, ensure_ascii=False) if alignment else None,
        ),
    )
