"""Agente SentenceCard: genera la oración de ejemplo + desglose para el tipo
de tarjeta 'sentence' (aprender la palabra en contexto).

Corre DESPUÉS de word_prep: toma la lectura primaria ya resuelta (pinyin +
significado) y solo genera la oración, su traducción, pinyin completo y el
desglose palabra por palabra. No vuelve a decidir significado/pronunciación
ni genera colocaciones (eso es de word_prep, a nivel de palabra).

Una sola oración por tarjeta, siempre atada a la lectura principal — ver
[[project-card-generation-design]] en memoria: nunca una tarjeta por lectura.
"""

import json

from pydantic import ValidationError

from src.db.database import get_connection
from src.generation.card_common import (
    CardExampleOutput,
    build_user_prompt,
    guardrail_context,
    log_phase,
    mark_card_guardrail_failed,
    mark_card_text_ready,
    save_card_example,
)
from src.generation.guardrail import run_guardrail
from src.generation.prompts import SENTENCE_CARD_SYSTEM_PROMPT
from src.llm.client import LLMError, call_llm

MAX_ATTEMPTS = 3
PHASE = "sentence_card"
SENTENCE_CARD_GUARDRAIL_CHECKS = [
    "grammar_correct",
    "no_compound_leak",
    "pinyin_accuracy",
    "breakdown_accuracy",
    "translation_accuracy",
]


def generate_sentence_card(
    hanzi: str, pinyin: str, meaning_es: str, meaning_zh: str, model: str = "gpt-4o"
) -> CardExampleOutput:
    user_prompt = build_user_prompt(hanzi, pinyin, meaning_es, meaning_zh)
    raw = call_llm(SENTENCE_CARD_SYSTEM_PROMPT, user_prompt, model=model)
    try:
        data = json.loads(raw)
        return CardExampleOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as ex:
        raise LLMError(f"Respuesta inválida del LLM (SentenceCard) para '{hanzi}': {ex}\nRaw: {raw}") from ex


def run_sentence_card(
    card_id: int, reading_id: int, hanzi: str, pinyin: str, meaning_es: str, meaning_zh: str, model: str = "gpt-4o"
) -> bool:
    """Genera + verifica + guarda la SentenceCard, con reintentos.

    Devuelve True si se guardó un resultado que pasó el guardrail, False si
    se agotaron los intentos (la tarjeta queda en status='guardrail_failed'
    para revisión humana).

    No mantiene una conexión a la DB abierta durante las llamadas al LLM —
    abre una conexión corta solo para cada escritura.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = generate_sentence_card(hanzi, pinyin, meaning_es, meaning_zh, model=model)
            guardrail_result = run_guardrail(SENTENCE_CARD_GUARDRAIL_CHECKS, guardrail_context(hanzi, result), model=model)
        except LLMError as ex:
            with get_connection() as conn:
                log_phase(conn, card_id, PHASE, "failed", attempt, f"Respuesta del LLM inválida/no siguió el schema: {ex}")
            continue

        if guardrail_result.passed:
            with get_connection() as conn:
                save_card_example(conn, card_id, reading_id, result)
                log_phase(conn, card_id, PHASE, "passed", attempt)
                mark_card_text_ready(conn, card_id)
            return True

        reasons = "; ".join(
            f"{name}: {check.reason}" for name, check in guardrail_result.checks.items() if not check.passed
        )
        with get_connection() as conn:
            log_phase(conn, card_id, PHASE, "failed", attempt, reasons)

    with get_connection() as conn:
        mark_card_guardrail_failed(conn, card_id)
    return False
