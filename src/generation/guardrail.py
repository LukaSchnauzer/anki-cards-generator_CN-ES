"""Guardrail genérico y composable.

Un nodo pide una lista de checks (de src.generation.prompts.GUARDRAIL_CHECKS)
y este módulo arma el prompt + el esquema de salida dinámicamente, llama al
LLM una sola vez, y devuelve el resultado de cada check individual más el
resultado global (pasa solo si TODOS los checks incluidos pasaron).
"""

import json
from typing import Dict, List

from pydantic import BaseModel, ValidationError, create_model

from src.generation.prompts import GUARDRAIL_CHECKS, GUARDRAIL_SYSTEM_PROMPT_TEMPLATE
from src.llm.client import LLMError, call_llm


class CheckResult(BaseModel):
    passed: bool
    reason: str


class GuardrailResult(BaseModel):
    passed: bool
    checks: Dict[str, CheckResult]


def _build_prompt(check_ids: List[str]) -> str:
    unknown = [c for c in check_ids if c not in GUARDRAIL_CHECKS]
    if unknown:
        raise ValueError(f"Checks desconocidos: {unknown}")

    checks_list = "\n".join(f"- {GUARDRAIL_CHECKS[c]}" for c in check_ids)
    checks_schema = json.dumps(
        {c: {"passed": "boolean", "reason": "string"} for c in check_ids},
        ensure_ascii=False,
        indent=2,
    )
    return GUARDRAIL_SYSTEM_PROMPT_TEMPLATE.format(checks_list=checks_list, checks_schema=checks_schema)


def _build_output_model(check_ids: List[str]):
    fields = {c: (CheckResult, ...) for c in check_ids}
    return create_model("DynamicGuardrailOutput", **fields)


def run_guardrail(check_ids: List[str], content_context: str, model: str = "gpt-4o") -> GuardrailResult:
    """Corre el guardrail sobre `content_context` (texto describiendo lo generado) para los
    checks pedidos. Devuelve el resultado global y el detalle de cada check."""
    system_prompt = _build_prompt(check_ids)
    output_model = _build_output_model(check_ids)

    raw = call_llm(system_prompt, content_context, model=model)
    try:
        data = json.loads(raw)
        validated = output_model.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as ex:
        raise LLMError(f"Respuesta inválida del guardrail: {ex}\nRaw: {raw}") from ex

    checks = {c: getattr(validated, c) for c in check_ids}
    all_passed = all(r.passed for r in checks.values())
    return GuardrailResult(passed=all_passed, checks=checks)
