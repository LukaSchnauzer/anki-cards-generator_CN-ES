"""Nodo word_prep: corre una sola vez por palabra (no por tarjeta).

Determina la(s) lectura(s) reales de la palabra (pinyin + significado ES/ZH,
detectando polífonos) y sus colocaciones. Corrige el pinyin/significado
"semilla" que vino de la fuente JSON sin verificar (que puede estar mal:
ej. asignar un significado de apellido como principal).

Las 3 tarjetas (Sentence/Pattern/Audio) de una palabra comparten estas
lecturas, así que este paso corre antes que los agentes de tarjeta.
"""

import json
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.db.database import get_connection
from src.generation.guardrail import run_guardrail
from src.generation.prompts import WORD_PREP_SYSTEM_PROMPT
from src.llm.client import LLMError, call_llm
from src.utils.pinyin_ref import reference_pinyin

MAX_ATTEMPTS = 3
WORD_PREP_GUARDRAIL_CHECKS = ["pinyin_accuracy", "meaning_not_archaic_or_surname"]


class ReadingOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pinyin: str
    meaning_es: str
    meaning_zh: str
    register_tag: str = Field(default="reg:neutral", alias="register")
    tags_seed: List[str] = Field(default_factory=list)
    is_primary: bool = False


class CollocationOut(BaseModel):
    pattern_zh: str
    gloss_es: str


class WordPrepOutput(BaseModel):
    readings: List[ReadingOut]
    collocations: List[CollocationOut] = Field(default_factory=list)


def build_user_prompt(
    hanzi: str, seed_pinyin: Optional[str], source_meanings: Optional[list], previous_error: Optional[str] = None
) -> str:
    meanings_str = "; ".join(source_meanings) if source_meanings else "(sin datos)"
    prompt = (
        f"hanzi: {hanzi}\n"
        f"pinyin de referencia (sin verificar): {seed_pinyin or '(sin datos)'}\n"
        f"significados en inglés de la fuente (solo referencia, no traducir literalmente): {meanings_str}\n"
    )
    if previous_error:
        prompt += (
            f"\nIMPORTANTE: un intento anterior fue rechazado por este motivo: {previous_error}\n"
            f"Corrige específicamente eso en este nuevo intento — no repitas el mismo error.\n"
        )
    return prompt


def generate_word_prep(
    hanzi: str,
    seed_pinyin: Optional[str] = None,
    source_meanings: Optional[list] = None,
    model: str = "gpt-4o",
    previous_error: Optional[str] = None,
) -> WordPrepOutput:
    """Llama al LLM y devuelve las lecturas + colocaciones validadas para una palabra."""
    user_prompt = build_user_prompt(hanzi, seed_pinyin, source_meanings, previous_error=previous_error)
    raw = call_llm(WORD_PREP_SYSTEM_PROMPT, user_prompt, model=model)
    try:
        data = json.loads(raw)
        return WordPrepOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as ex:
        raise LLMError(f"Respuesta inválida del LLM para '{hanzi}': {ex}\nRaw: {raw}") from ex


def save_word_prep(conn, word_id: int, result: WordPrepOutput) -> None:
    """Reemplaza las lecturas/colocaciones semilla de una palabra con el resultado del LLM."""
    conn.execute("DELETE FROM readings WHERE word_id = ?", (word_id,))
    conn.execute("DELETE FROM collocations WHERE word_id = ?", (word_id,))

    for reading in result.readings:
        conn.execute(
            """
            INSERT INTO readings (word_id, pinyin, is_primary, meaning_es, meaning_zh, register, tags_seed, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'llm')
            """,
            (
                word_id,
                reading.pinyin,
                1 if reading.is_primary else 0,
                reading.meaning_es,
                reading.meaning_zh,
                reading.register_tag,
                ";".join(reading.tags_seed),
            ),
        )

    for idx, coll in enumerate(result.collocations):
        conn.execute(
            "INSERT INTO collocations (word_id, pattern_zh, gloss_es, sort_order) VALUES (?, ?, ?, ?)",
            (word_id, coll.pattern_zh, coll.gloss_es, idx),
        )


def _log_phase(conn, word_id: int, status: str, attempt: int, notes: str = "") -> None:
    conn.execute(
        "INSERT INTO generation_phases (word_id, phase, status, attempt, notes) VALUES (?, 'word_prep', ?, ?, ?)",
        (word_id, status, attempt, notes),
    )


def _guardrail_context(hanzi: str, result: WordPrepOutput) -> str:
    ref_sin_espacios = reference_pinyin(hanzi).replace(" ", "")
    return json.dumps(
        {
            "hanzi": hanzi,
            "pinyin_mas_comun_segun_herramienta_SIN_ESPACIOS": ref_sin_espacios,
            "nota_referencia": (
                "el campo anterior es la lectura MÁS COMÚN calculada por una herramienta "
                "determinística (no un LLM) — úsala como fuente de verdad para la lectura "
                "is_primary=true en vez de recordar tonos de memoria. Cada lectura de abajo ya "
                "trae su propio 'pinyin_sin_espacios' (mismo dato, sin separadores) — compara ESE "
                "campo, sílaba por sílaba, contra la referencia; los espacios son solo un "
                "separador visual, nunca una diferencia real de pronunciación. Las lecturas "
                "is_primary=false son pronunciaciones secundarias legítimas y pueden no coincidir "
                "con esta referencia a propósito; evalúalas con tu propio conocimiento."
            ),
            "readings": [
                {
                    "pinyin": r.pinyin,
                    "pinyin_sin_espacios": r.pinyin.replace(" ", ""),
                    "meaning_es": r.meaning_es,
                    "meaning_zh": r.meaning_zh,
                    "is_primary": r.is_primary,
                }
                for r in result.readings
            ],
        },
        ensure_ascii=False,
    )


def run_word_prep(
    word_id: int,
    hanzi: str,
    seed_pinyin: Optional[str] = None,
    source_meanings: Optional[list] = None,
    model: str = "gpt-4o",
) -> bool:
    """Genera + verifica + guarda word_prep para una palabra, con reintentos.

    Reintenta hasta MAX_ATTEMPTS veces si el guardrail rechaza el resultado.
    Cada intento queda logueado en generation_phases. Devuelve True si se
    guardó un resultado que pasó el guardrail, False si se agotaron los
    intentos (la palabra queda para revisión humana).

    No mantiene una conexión a la DB abierta durante las llamadas al LLM
    (son lentas) — abre una conexión corta solo para cada escritura, así
    no bloquea a otros nodos del grafo que escriben en paralelo.
    """
    previous_error: Optional[str] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = generate_word_prep(hanzi, seed_pinyin, source_meanings, model=model, previous_error=previous_error)
            for r in result.readings:
                if r.is_primary:
                    # No confiamos en que el LLM recuerde bien los tonos (incluido sandhi de
                    # 不/一) — lo calcula la herramienta determinística. Las lecturas
                    # secundarias/polífonas se dejan tal cual, pypinyin solo sabe la más común.
                    r.pinyin = reference_pinyin(hanzi)
            guardrail_result = run_guardrail(WORD_PREP_GUARDRAIL_CHECKS, _guardrail_context(hanzi, result), model=model)
        except LLMError as ex:
            previous_error = f"Respuesta del LLM inválida/no siguió el schema: {ex}"
            with get_connection() as conn:
                _log_phase(conn, word_id, "failed", attempt, previous_error)
            continue

        if guardrail_result.passed:
            with get_connection() as conn:
                save_word_prep(conn, word_id, result)
                _log_phase(conn, word_id, "passed", attempt)
            return True

        previous_error = "; ".join(
            f"{name}: {check.reason}" for name, check in guardrail_result.checks.items() if not check.passed
        )
        with get_connection() as conn:
            _log_phase(conn, word_id, "failed", attempt, previous_error)

    return False
