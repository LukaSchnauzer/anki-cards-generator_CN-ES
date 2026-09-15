"""Cliente LLM genérico, agnóstico de proveedor.

Hoy solo implementa OpenAI (vía requests, sin el SDK oficial de OpenAI) para
no atar el proyecto al cliente de un proveedor específico. Cambiar de
proveedor más adelante implica tocar solo este archivo: la firma de
call_llm() no asume nada de OpenAI.
"""

import os

import requests
from dotenv import load_dotenv

from src.utils.cost_tracker import get_tracker

load_dotenv()

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# Modelos configurables por separado en .env — generación y guardrail tienen
# perfiles de costo/calidad distintos (el guardrail es una tarea de
# verificación, no de creación de contenido), así que no tiene por qué usar
# el mismo modelo caro. Default a gpt-4o en ambos si no se define nada, para
# no cambiar el comportamiento actual silenciosamente.
GENERATION_MODEL = os.getenv("LLM_GENERATION_MODEL", "gpt-4o")
GUARDRAIL_MODEL = os.getenv("LLM_GUARDRAIL_MODEL", "gpt-4o")
DEFAULT_MODEL = GENERATION_MODEL


class LLMError(RuntimeError):
    """Error al llamar al LLM o al recibir una respuesta inválida."""


def call_llm(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL, temperature: float = 0.2) -> str:
    """Llama al LLM y devuelve el contenido de la respuesta como texto JSON crudo.

    El caller es responsable de parsear/validar ese JSON (ej. con un modelo pydantic).
    """
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        raise LLMError("Define OPENAI_API_KEY en .env")

    body = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        r = requests.post(OPENAI_API_URL, headers=headers, json=body, timeout=60)
    except requests.exceptions.RequestException as ex:
        # Timeout, conexión perdida, DNS, etc. — sin esto, un simple hiccup de
        # red tumbaba TODO el batch de `generate` en vez de tratarse como un
        # intento fallido más (los retry loops de cada agente ya solo
        # atrapan LLMError, no excepciones de red crudas).
        raise LLMError(f"Error de red llamando al LLM: {ex}") from ex

    if r.status_code != 200:
        raise LLMError(f"Error de API {r.status_code}: {r.text}")

    data = r.json()
    usage = data.get("usage", {})
    get_tracker().add_llm_usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

    return data["choices"][0]["message"]["content"]
