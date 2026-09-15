"""Corre `manual_card.save_manual_card` sobre una lista de tarjetas
definida en un archivo JSON — para cuando se acumularon varias correcciones
manuales (ej. tras una revisión palabra por palabra) y conviene guardarlas
todas en una sola corrida en vez de un comando `manual-card` a la vez.

Formato del JSON: una lista de objetos con "word", "type", "zh", "es"
(cualquier otro campo, ej. una "nota" de contexto, se ignora). Ejemplo:

[
  {"word": "亲", "type": "sentence", "zh": "...", "es": "..."},
  {"word": "亲", "type": "pattern", "zh": "...", "es": "..."}
]

El archivo NO es parte del repo — vive donde el usuario quiera juntarlo
(ej. el scratchpad de una sesión) mientras se decide qué oraciones usar."""

import argparse
import json

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from src.db.database import get_connection, init_db
from src.generation.manual_card import save_manual_card
from src.utils.cost_tracker import get_tracker


def run_batch(file_path: str, hsk_level: int = 3) -> dict:
    with open(file_path, encoding="utf-8") as f:
        entries = json.load(f)

    console = Console()
    tracker = get_tracker()
    ok_count = 0
    fail_count = 0
    failures = []

    with Progress(
        TextColumn("[bold cyan]{task.fields[label]}"),
        BarColumn(bar_width=28),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        TextColumn("ETA"),
        TimeRemainingColumn(),
        TextColumn(
            "[green]LLM ${task.fields[llm_cost]:.3f}[/green]  "
            "[magenta]11L ${task.fields[el_cost]:.3f}[/magenta]  "
            "[bold white]tot ${task.fields[total_cost]:.3f}[/bold white]"
        ),
        console=console,
    ) as progress:
        task = progress.add_task(
            "guardando", total=len(entries) or 1, label="iniciando…",
            llm_cost=0.0, el_cost=0.0, total_cost=0.0,
        )

        for entry in entries:
            hanzi, card_type = entry["word"], entry["type"]
            progress.update(task, label=f"{hanzi} · {card_type}")

            with get_connection() as conn:
                word = conn.execute(
                    "SELECT id FROM words WHERE hanzi = ? AND COALESCE(export_level, hsk_level) = ?",
                    (hanzi, hsk_level),
                ).fetchone()

            if word is None:
                fail_count += 1
                failures.append(f"{hanzi} ({card_type}): no se encontró en HSK{hsk_level}")
            else:
                try:
                    ok = save_manual_card(word["id"], card_type, entry["zh"], entry["es"])
                    if ok:
                        ok_count += 1
                    else:
                        fail_count += 1
                        failures.append(f"{hanzi} ({card_type}): audio/desglose falló")
                except Exception as ex:
                    fail_count += 1
                    failures.append(f"{hanzi} ({card_type}): {ex}")

            progress.update(
                task, advance=1, llm_cost=tracker.llm_cost_usd, el_cost=tracker.elevenlabs_cost_usd,
                total_cost=tracker.total_cost_usd,
            )

    return {"ok": ok_count, "fail": fail_count, "failures": failures}


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Guarda en lote tarjetas manuales definidas en un archivo JSON")
    parser.add_argument("--file", required=True, help="Ruta al JSON con la lista de tarjetas (word/type/zh/es)")
    parser.add_argument("--hsk-level", type=int, default=3)
    args = parser.parse_args()

    summary = run_batch(args.file, args.hsk_level)
    print(f"\nGuardadas: {summary['ok']}  ·  Fallidas: {summary['fail']}")
    for f in summary["failures"]:
        print(f"  [FAIL] {f}")

    tracker = get_tracker()
    print(
        f"Costo estimado: ${tracker.total_cost_usd:.4f}"
        f"  ·  LLM ${tracker.llm_cost_usd:.4f} ({tracker.llm_calls} llamadas)"
        f"  ·  ElevenLabs ${tracker.elevenlabs_cost_usd:.4f} ({tracker.elevenlabs_calls} llamadas)"
    )
