"""Cliente LLM genérico, agnóstico de proveedor.

Hoy solo implementa OpenAI (vía requests, sin el SDK oficial de OpenAI) para
no atar el proyecto al cliente de un proveedor específico. Cambiar de
proveedor más adelante implica tocar solo este archivo: la firma de
call_llm() no asume nada de OpenAI.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o"


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
    r = requests.post(OPENAI_API_URL, headers=headers, json=body, timeout=60)
    if r.status_code != 200:
        raise LLMError(f"Error de API {r.status_code}: {r.text}")
    return r.json()["choices"][0]["message"]["content"]
