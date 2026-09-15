"""Rastreo de costo en memoria para una corrida del pipeline.

No guarda nada en disco ni consulta ninguna cuenta — solo acumula el USO
real reportado por cada respuesta de API (tokens de OpenAI, caracteres
enviados a ElevenLabs) y lo multiplica por el precio de lista público.
Si el plan/cuenta real tiene otra tarifa, esto es un estimado, no el
gasto exacto de la cuenta.

Precios de lista (revisar si cambian):
- gpt-4o: $2.50 / 1M tokens de entrada, $10.00 / 1M tokens de salida.
- ElevenLabs (eleven_multilingual_v2): $0.10 / 1000 caracteres.
"""

GPT4O_INPUT_PER_TOKEN = 2.50 / 1_000_000
GPT4O_OUTPUT_PER_TOKEN = 10.00 / 1_000_000
ELEVENLABS_PER_CHAR = 0.10 / 1_000


class CostTracker:
    def __init__(self):
        self.llm_input_tokens = 0
        self.llm_output_tokens = 0
        self.llm_calls = 0
        self.elevenlabs_chars = 0
        self.elevenlabs_calls = 0

    def add_llm_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.llm_input_tokens += input_tokens
        self.llm_output_tokens += output_tokens
        self.llm_calls += 1

    def add_elevenlabs_chars(self, n_chars: int) -> None:
        self.elevenlabs_chars += n_chars
        self.elevenlabs_calls += 1

    @property
    def llm_cost_usd(self) -> float:
        return self.llm_input_tokens * GPT4O_INPUT_PER_TOKEN + self.llm_output_tokens * GPT4O_OUTPUT_PER_TOKEN

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
