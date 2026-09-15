"""Agente PatternCard: genera la oración de ejemplo + desglose para el tipo
de tarjeta 'pattern' (cloze deletion — recuerdo activo de la palabra).

Igual que SentenceCard, corre después de word_prep y solo genera la oración
(no vuelve a decidir significado/pronunciación). La diferencia es el tipo de
oración que le pide al LLM: debe blanquearse sin ambigüedad (la palabra
aparece una sola vez de forma independiente) y el contexto debe restringir
semánticamente la respuesta (nada de oraciones donde cualquier palabra cabe).
"""

import json
from typing import Optional

from pydantic import ValidationError

from src.db.database import get_connection
from src.generation.card_common import (
    CardExampleOutput,
    apply_reference_pinyin,
    build_user_prompt,
    guardrail_checks_for,
    guardrail_context,
    log_phase,
    mark_card_guardrail_failed,
    mark_card_text_ready,
    save_card_example,
)
from src.generation.guardrail import run_guardrail
from src.generation.prompts import PATTERN_CARD_SYSTEM_PROMPT
from src.llm.client import GENERATION_MODEL, LLMError, call_llm

MAX_ATTEMPTS = 3
PHASE = "pattern_card"
PATTERN_CARD_GUARDRAIL_CHECKS = [
    "grammar_correct",
    "no_compound_leak",
    "pinyin_accuracy",
    "breakdown_accuracy",
    "translation_accuracy",
    "cloze_single_occurrence",
    "cloze_inferable",
]


def generate_pattern_card(
    hanzi: str, pinyin: str, meaning_es: str, meaning_zh: str, model: str = GENERATION_MODEL,
    previous_error: Optional[str] = None,
) -> CardExampleOutput:
    user_prompt = build_user_prompt(hanzi, pinyin, meaning_es, meaning_zh, previous_error=previous_error)
    raw = call_llm(PATTERN_CARD_SYSTEM_PROMPT, user_prompt, model=model)
    try:
        data = json.loads(raw)
        return CardExampleOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as ex:
        raise LLMError(f"Respuesta inválida del LLM (PatternCard) para '{hanzi}': {ex}\nRaw: {raw}") from ex


def run_pattern_card(
    card_id: int, reading_id: int, hanzi: str, pinyin: str, meaning_es: str, meaning_zh: str, model: str = GENERATION_MODEL
) -> bool:
    """Genera + verifica + guarda la PatternCard, con reintentos.

    Devuelve True si se guardó un resultado que pasó el guardrail, False si
    se agotaron los intentos (la tarjeta queda en status='guardrail_failed'
    para revisión humana).

    No mantiene una conexión a la DB abierta durante las llamadas al LLM —
    abre una conexión corta solo para cada escritura.
    """
    previous_error: Optional[str] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = generate_pattern_card(hanzi, pinyin, meaning_es, meaning_zh, model=model, previous_error=previous_error)
            apply_reference_pinyin(result)
            checks = guardrail_checks_for(PATTERN_CARD_GUARDRAIL_CHECKS, hanzi)
            guardrail_result = run_guardrail(checks, guardrail_context(hanzi, result))
        except LLMError as ex:
            previous_error = f"Respuesta del LLM inválida/no siguió el schema: {ex}"
            with get_connection() as conn:
                log_phase(conn, card_id, PHASE, "failed", attempt, previous_error)
            continue

        if guardrail_result.passed:
            with get_connection() as conn:
                save_card_example(conn, card_id, reading_id, result)
                log_phase(conn, card_id, PHASE, "passed", attempt)
                mark_card_text_ready(conn, card_id)
            return True

        previous_error = "; ".join(
            f"{name}: {check.reason}" for name, check in guardrail_result.checks.items() if not check.passed
        )
        with get_connection() as conn:
            log_phase(conn, card_id, PHASE, "failed", attempt, previous_error)

    with get_connection() as conn:
        mark_card_guardrail_failed(conn, card_id)
    return False
