"""Auditoría de naturalidad: revisa tarjetas `ready`/`llm` de palabras de UN
carácter buscando el patrón encontrado en 报/保 — el carácter usado como
verbo/sustantivo genérico con un objeto libre, cuando en chino real casi
siempre necesita un compuesto fijo (报警, 汇报, 保护, 保证, etc.). El
guardrail normal no detecta esto: evalúa gramática/traducción, no si esa
es la combinación que un hablante nativo elegiría de verdad.

Es SOLO diagnóstico sobre el contenido ya guardado — no regenera nada. Las
tarjetas marcadas quedan en review_status='needs_human' (con el motivo en
review_notes), así entran directo al mismo flujo de revisión humana de
siempre (dashboard -> swap-primary / add-reading / manual-card), sin
inventar una cola aparte.

Corre en lotes (BATCH_SIZE tarjetas por llamada) para no gastar una
llamada de LLM por tarjeta — con 466 candidatas de HSK3 son ~31 llamadas
en vez de 466."""

import argparse
import json
from typing import Dict, List

from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from src.db.database import get_connection, init_db
from src.llm.client import GUARDRAIL_MODEL, LLMError, call_llm
from src.utils.cost_tracker import get_tracker

BATCH_SIZE = 15

AUDIT_SYSTEM_PROMPT = """Eres un hablante nativo de chino mandarín revisando oraciones de ejemplo \
para tarjetas de estudio HSK. Cada oración usa una palabra de UN SOLO CARÁCTER.

Tu tarea: para cada oración, decide si el carácter objetivo aparece de forma NATURAL e \
IDIOMÁTICA en el chino moderno hablado/escrito, o si está forzado como verbo/sustantivo \
genérico con un objeto o complemento libre, cuando en el uso real ese carácter casi \
siempre requiere un compuesto fijo. Ejemplos YA CONFIRMADOS de este problema: "报" usado \
solo como "报 + objeto cualquiera" (ej. "报最新的消息") es forzado — el uso real es \
汇报/通报/举报/报警. "保" usado solo como "保 + objeto cualquiera" (ej. "保孩子") es forzado \
— el uso real es 保护/保证/保险. Si el carácter SÍ aparece dentro de un compuesto real \
como ese (汇报, 保护, 报警...) cuenta como natural, aunque el hueco/blank de la tarjeta \
lo muestre aislado.

Marca "natural": false SOLO cuando el uso suene forzado, artificial o gramaticalmente \
dudoso para un hablante nativo real — nunca por preferencias de estilo o registro.

Devuelve SOLO este JSON, con TODOS los ids recibidos, sin omitir ninguno:
{"results": {"<id>": {"natural": true|false, "reason": "motivo breve en español"}, ...}}
"""


class AuditItemResult(BaseModel):
    natural: bool
    reason: str


class AuditBatchResult(BaseModel):
    results: Dict[str, AuditItemResult]


def _fetch_candidates(conn, hsk_level: int = None) -> list:
    where = (
        "WHERE LENGTH(w.hanzi) = 1 AND c.status = 'ready' "
        "AND c.content_source = 'llm' AND c.review_status = 'unflagged'"
    )
    params: list = []
    if hsk_level is not None:
        where += " AND COALESCE(w.export_level, w.hsk_level) = ?"
        params.append(hsk_level)
    return conn.execute(
        f"""
        SELECT c.id AS card_id, c.card_type, w.hanzi,
               (SELECT meaning_es FROM readings WHERE word_id = w.id AND is_primary = 1) AS meaning_es,
               ce.example_zh, ce.example_es
        FROM cards c
        JOIN words w ON w.id = c.word_id
        JOIN card_examples ce ON ce.card_id = c.id
        {where}
        ORDER BY w.hanzi, c.card_type
        """,
        params,
    ).fetchall()


def _audit_batch(items: List[dict], model: str = GUARDRAIL_MODEL) -> Dict[str, AuditItemResult]:
    payload = [
        {
            "id": str(it["card_id"]),
            "hanzi": it["hanzi"],
            "significado_primario": it["meaning_es"],
            "tipo_tarjeta": it["card_type"],
            "oracion_zh": it["example_zh"],
            "oracion_es": it["example_es"],
        }
        for it in items
    ]
    user_prompt = "Audita estas oraciones:\n" + json.dumps(payload, ensure_ascii=False, indent=2)

    raw = call_llm(AUDIT_SYSTEM_PROMPT, user_prompt, model=model)
    try:
        data = json.loads(raw)
        validated = AuditBatchResult.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as ex:
        raise LLMError(f"Respuesta inválida de auditoría: {ex}\nRaw: {raw}") from ex
    return validated.results


def run_audit(hsk_level: int = None, model: str = GUARDRAIL_MODEL, batch_size: int = BATCH_SIZE) -> dict:
    with get_connection() as conn:
        candidates = _fetch_candidates(conn, hsk_level)

    console = Console()
    tracker = get_tracker()
    total_batches = max(1, -(-len(candidates) // batch_size))  # ceil division

    audited = 0
    flagged = 0
    with Progress(
        TextColumn("[bold cyan]{task.fields[label]}"),
        BarColumn(bar_width=28),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total} lotes)"),
        TimeElapsedColumn(),
        TextColumn("ETA"),
        TimeRemainingColumn(),
        TextColumn(
            "[green]LLM ${task.fields[llm_cost]:.3f}[/green]  "
            "[bold white]tot ${task.fields[total_cost]:.3f}[/bold white]  "
            "[yellow]marcadas {task.fields[flagged]}[/yellow]"
        ),
        console=console,
    ) as progress:
        task = progress.add_task(
            "auditando", total=total_batches, label="iniciando…",
            llm_cost=0.0, total_cost=0.0, flagged=0,
        )

        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            batch_num = i // batch_size + 1
            progress.update(task, label=f"lote {batch_num}/{total_batches} ({batch[0]['hanzi']}…{batch[-1]['hanzi']})")

            results = _audit_batch([dict(row) for row in batch], model=model)
            audited += len(batch)
            with get_connection() as conn:
                for row in batch:
                    r = results.get(str(row["card_id"]))
                    if r is None:
                        console.print(f"  (aviso: sin resultado para {row['hanzi']} {row['card_type']} card_id={row['card_id']} — se deja como está)")
                        continue
                    if not r.natural:
                        conn.execute(
                            "UPDATE cards SET review_status = 'needs_human', review_notes = ?, updated_at = datetime('now') WHERE id = ?",
                            (f"[audit-naturalness] {r.reason}", row["card_id"]),
                        )
                        flagged += 1
                        console.print(f"  [yellow][FLAG][/yellow] {row['hanzi']} ({row['card_type']}): {row['example_zh']} — {r.reason}")

            progress.update(
                task, advance=1, llm_cost=tracker.llm_cost_usd, total_cost=tracker.total_cost_usd, flagged=flagged,
            )

    return {"audited": audited, "flagged": flagged}


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Audita naturalidad de tarjetas ready/llm de palabras de 1 carácter")
    parser.add_argument("--hsk-level", type=int, default=None, help="Filtra por nivel HSK (default: todos)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    summary = run_audit(hsk_level=args.hsk_level, batch_size=args.batch_size)
    print(f"\nAuditadas: {summary['audited']}  ·  Marcadas needs_human: {summary['flagged']}")
    tracker = get_tracker()
    print(
        f"Costo estimado: ${tracker.total_cost_usd:.4f}"
        f"  ·  LLM ${tracker.llm_cost_usd:.4f} ({tracker.llm_calls} llamadas)"
        f"  ·  ElevenLabs ${tracker.elevenlabs_cost_usd:.4f} ({tracker.elevenlabs_calls} llamadas)"
    )
