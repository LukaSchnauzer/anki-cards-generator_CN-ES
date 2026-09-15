"""Agente AudioCard: genera la oración de ejemplo + desglose para el tipo
de tarjeta 'audio' (comprensión auditiva — el frente solo reproduce audio).

Igual que Sentence/Pattern, corre después de word_prep. La diferencia frente
a esas dos: sin homófonos con significado distinto, la palabra podría sonar
ambigua sin apoyo visual, así que el guardrail agrega un check de
desambiguación auditiva (más relajado que el de cloze).
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
from src.generation.prompts import AUDIO_CARD_SYSTEM_PROMPT
from src.llm.client import LLMError, call_llm

MAX_ATTEMPTS = 3
PHASE = "audio_card"
AUDIO_CARD_GUARDRAIL_CHECKS = [
    "grammar_correct",
    "no_compound_leak",
    "pinyin_accuracy",
    "breakdown_accuracy",
    "translation_accuracy",
    "audio_disambiguation",
]


def generate_audio_card(
    hanzi: str, pinyin: str, meaning_es: str, meaning_zh: str, model: str = "gpt-4o",
    previous_error: Optional[str] = None,
) -> CardExampleOutput:
    user_prompt = build_user_prompt(hanzi, pinyin, meaning_es, meaning_zh, previous_error=previous_error)
    raw = call_llm(AUDIO_CARD_SYSTEM_PROMPT, user_prompt, model=model)
    try:
        data = json.loads(raw)
        return CardExampleOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as ex:
        raise LLMError(f"Respuesta inválida del LLM (AudioCard) para '{hanzi}': {ex}\nRaw: {raw}") from ex


def run_audio_card(
    card_id: int, reading_id: int, hanzi: str, pinyin: str, meaning_es: str, meaning_zh: str, model: str = "gpt-4o"
) -> bool:
    """Genera + verifica + guarda el texto de la AudioCard, con reintentos.

    Solo cubre la parte de texto (igual que Sentence/Pattern) — el audio (2
    velocidades) lo genera un nodo separado del grafo una vez que el texto
    pasa el guardrail (status='guardrail_passed').
    """
    previous_error: Optional[str] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = generate_audio_card(hanzi, pinyin, meaning_es, meaning_zh, model=model, previous_error=previous_error)
            apply_reference_pinyin(result)
            checks = guardrail_checks_for(AUDIO_CARD_GUARDRAIL_CHECKS, hanzi)
            guardrail_result = run_guardrail(checks, guardrail_context(hanzi, result), model=model)
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
