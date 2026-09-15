"""Rastreo de costo en memoria para una corrida del pipeline.

No guarda nada en disco ni consulta ninguna cuenta — solo acumula el USO
real reportado por cada respuesta de API (tokens de OpenAI, caracteres
enviados a ElevenLabs) y lo multiplica por el precio de lista público.
Si el plan/cuenta real tiene otra tarifa, esto es un estimado, no el
gasto exacto de la cuenta.

Precios de lista (revisar si cambian), por modelo — GENERATION_MODEL y
GUARDRAIL_MODEL pueden ser distintos (ver src/llm/client.py), así que el
costo se calcula por modelo real usado en cada llamada, no con una tarifa
fija para todo:
- gpt-4o: $2.50 / 1M tokens de entrada, $10.00 / 1M tokens de salida.
- gpt-4o-mini: $0.15 / 1M tokens de entrada, $0.60 / 1M tokens de salida.
- ElevenLabs (eleven_multilingual_v2): $0.10 / 1000 caracteres.
"""

LLM_PRICING_PER_TOKEN = {
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
}
# Modelo cuya tarifa se usa si add_llm_usage recibe uno no listado arriba —
# evita que un modelo nuevo/no catalogado reporte costo $0 silenciosamente.
_FALLBACK_PRICING_MODEL = "gpt-4o"

ELEVENLABS_PER_CHAR = 0.10 / 1_000


class CostTracker:
    def __init__(self):
        self.llm_usage_by_model: dict = {}  # model -> {"input": n, "output": n, "calls": n}
        self.elevenlabs_chars = 0
        self.elevenlabs_calls = 0

    def add_llm_usage(self, input_tokens: int, output_tokens: int, model: str = _FALLBACK_PRICING_MODEL) -> None:
        bucket = self.llm_usage_by_model.setdefault(model, {"input": 0, "output": 0, "calls": 0})
        bucket["input"] += input_tokens
        bucket["output"] += output_tokens
        bucket["calls"] += 1

    def add_elevenlabs_chars(self, n_chars: int) -> None:
        self.elevenlabs_chars += n_chars
        self.elevenlabs_calls += 1

    @property
    def llm_calls(self) -> int:
        return sum(b["calls"] for b in self.llm_usage_by_model.values())

    @property
    def llm_input_tokens(self) -> int:
        return sum(b["input"] for b in self.llm_usage_by_model.values())

    @property
    def llm_output_tokens(self) -> int:
        return sum(b["output"] for b in self.llm_usage_by_model.values())

    @property
    def llm_cost_usd(self) -> float:
        total = 0.0
        for model, bucket in self.llm_usage_by_model.items():
            pricing = LLM_PRICING_PER_TOKEN.get(model, LLM_PRICING_PER_TOKEN[_FALLBACK_PRICING_MODEL])
            total += bucket["input"] * pricing["input"] + bucket["output"] * pricing["output"]
        return total

    @property
    def elevenlabs_cost_usd(self) -> float:
        return self.elevenlabs_chars * ELEVENLABS_PER_CHAR

    @property
    def total_cost_usd(self) -> float:
        return self.llm_cost_usd + self.elevenlabs_cost_usd


_tracker = CostTracker()


def get_tracker() -> CostTracker:
    return _tracker


def reset_tracker() -> None:
    global _tracker
    _tracker = CostTracker()
