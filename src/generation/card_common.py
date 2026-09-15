"""Piezas compartidas entre los agentes de tarjeta (SentenceCard, PatternCard, ...).

Todos producen la misma forma de salida (una oración + traducción + pinyin +
desglose + notas gramaticales) y se guardan igual en card_examples, así que
esa parte vive acá en vez de duplicarse por agente.
"""

import json
from typing import List, Optional

from pydantic import BaseModel, Field

from src.utils.pinyin_ref import reference_pinyin


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


def apply_reference_pinyin(result: CardExampleOutput) -> None:
    """Sobreescribe example_pinyin y el pinyin de cada elemento del desglose
    con el valor calculado por la herramienta determinística (pypinyin,
    sandhi tonal incluido) — no confiamos en que el LLM lo escriba bien de
    memoria, ya demostrado poco confiable (ver memoria
    project-pinyin-guardrail-hallucination). Muta `result` in-place, antes
    de armar el contexto del guardrail, así el check de pinyin ya parte de
    un valor correcto por construcción."""
    result.example_pinyin = reference_pinyin(result.example_zh)
    for item in result.breakdown:
        item.pinyin = reference_pinyin(item.hanzi)


def guardrail_checks_for(base_checks: List[str], hanzi: str) -> List[str]:
    """Quita 'no_compound_leak' de la lista si la palabra objetivo NO es un
    solo carácter — el check mismo dice en su texto que solo aplica a
    caracteres sueltos ("si la palabra objetivo es un solo carácter"), pero
    el LLM no respeta esa condición de forma confiable: alucina que una
    palabra de 2+ caracteres "aparece escondida dentro del compuesto X" aun
    cuando X es la palabra misma o no se nombra ningún compuesto real (visto
    en 保持/保证/变化/城市/etc. — ver memoria project-no-compound-leak-scope).
    Para un solo carácter el check SÍ funciona bien (nombra un compuesto
    real y distinto, ej. 报 -> 报告), así que ahí se deja."""
    if len(hanzi) > 1:
        return [c for c in base_checks if c != "no_compound_leak"]
    return base_checks


def build_user_prompt(
    hanzi: str, pinyin: str, meaning_es: str, meaning_zh: str, previous_error: Optional[str] = None
) -> str:
    prompt = (
        f"hanzi: {hanzi}\n"
        f"pinyin (ya determinado, no lo cambies): {pinyin}\n"
        f"significado en español (ya determinado): {meaning_es}\n"
        f"significado en chino (ya determinado): {meaning_zh}\n"
    )
    if previous_error:
        # Sin esto, cada reintento repetía el mismo prompt exacto — el LLM
        # no tenía ninguna señal de qué corregir, solo volvía a tirar los
        # dados. Pasarle el motivo del rechazo anterior le da una chance
        # real de arreglar específicamente eso.
        prompt += (
            f"\nIMPORTANTE: un intento anterior de generar esta tarjeta fue rechazado por este motivo: "
            f"{previous_error}\nGenera una oración NUEVA que corrija específicamente ese problema — "
            f"no repitas el mismo error.\n"
        )
    return prompt


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
            "pinyin_de_la_oracion_sin_espacios": result.example_pinyin.replace(" ", ""),
            "pinyin_referencia_oracion_herramienta_sin_espacios": reference_pinyin(result.example_zh).replace(" ", ""),
            "nota_referencia": (
                "para 'pinyin_de_la_oracion', compara 'pinyin_de_la_oracion_sin_espacios' contra "
                "'pinyin_referencia_oracion_herramienta_sin_espacios' (calculado por una herramienta "
                "determinística, no un LLM) — es más confiable que recordar tonos de memoria. "
                "Cada elemento del desglose trae 'pinyin_referencia_herramienta_sin_espacios', "
                "calculado igual — úsalo como fuente de "
                "verdad para verificar el pinyin de ESE elemento en vez de recordar tonos de "
                "memoria. Compara contra 'pinyin_sin_espacios' del mismo elemento (mismo dato que "
                "'pinyin', sin separadores) — los espacios entre sílabas son solo un separador "
                "visual, nunca una diferencia real de pronunciación."
            ),
            "desglose": [
                {
                    **item.model_dump(),
                    "pinyin_sin_espacios": item.pinyin.replace(" ", ""),
                    "pinyin_referencia_herramienta_sin_espacios": reference_pinyin(item.hanzi).replace(" ", ""),
                }
                for item in result.breakdown
            ],
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
