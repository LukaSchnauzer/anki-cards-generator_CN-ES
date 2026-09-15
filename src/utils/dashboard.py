"""Dashboard de estado de la DB de generación: cuántas tarjetas hay en cada
estado, cuáles fallaron guardrails, cuáles están flaggeadas/escaladas a
revisión humana, y qué archivos de audio en disco ya no los referencia
nadie (huérfanos, dejados por regenerate_card al reemplazar card_examples).
"""

import argparse
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from src.db.database import get_connection, init_db
from src.generation.audio_gen import AUDIO_DIR


def _where(hsk_level: Optional[int]) -> tuple:
    if hsk_level is None:
        return "", ()
    return "WHERE w.hsk_level = ?", (hsk_level,)


def _status_table(conn, hsk_level: Optional[int]) -> Table:
    where, params = _where(hsk_level)
    rows = conn.execute(
        f"""
        SELECT w.hsk_level, c.card_type, c.status, COUNT(*) AS n
        FROM cards c JOIN words w ON w.id = c.word_id
        {where}
        GROUP BY w.hsk_level, c.card_type, c.status
        ORDER BY w.hsk_level, c.card_type, c.status
        """,
        params,
    ).fetchall()

    table = Table(title="Tarjetas por estado")
    table.add_column("HSK")
    table.add_column("Tipo")
    table.add_column("Estado")
    table.add_column("Cantidad", justify="right")
    for r in rows:
        table.add_row(str(r["hsk_level"]), r["card_type"], r["status"], str(r["n"]))
    return table


def _review_table(conn, hsk_level: Optional[int]) -> Table:
    where, params = _where(hsk_level)
    rows = conn.execute(
        f"""
        SELECT c.review_status, COUNT(*) AS n
        FROM cards c JOIN words w ON w.id = c.word_id
        {where}
        GROUP BY c.review_status
        ORDER BY c.review_status
        """,
        params,
    ).fetchall()

    table = Table(title="Tarjetas por review_status")
    table.add_column("review_status")
    table.add_column("Cantidad", justify="right")
    for r in rows:
        table.add_row(r["review_status"], str(r["n"]))
    return table


def _guardrail_failed_table(conn, hsk_level: Optional[int]) -> Table:
    where, params = _where(hsk_level)
    clause = f"{where} AND" if where else "WHERE"
    rows = conn.execute(
        f"""
        SELECT w.hanzi, c.id AS card_id, c.card_type, c.regen_attempts,
               (SELECT COUNT(*) FROM generation_phases gp
                WHERE gp.card_id = c.id AND gp.phase = c.card_type || '_card' AND gp.status = 'failed') AS fail_count,
               (SELECT notes FROM generation_phases gp
                WHERE gp.card_id = c.id ORDER BY gp.id DESC LIMIT 1) AS last_notes
        FROM cards c JOIN words w ON w.id = c.word_id
        {clause} c.status = 'guardrail_failed'
        ORDER BY w.hanzi
        """,
        params,
    ).fetchall()

    table = Table(title="Fallando guardrails (status='guardrail_failed')")
    table.add_column("Hanzi")
    table.add_column("Tipo")
    table.add_column("Intentos fallidos", justify="right")
    table.add_column("Rondas regen", justify="right")
    table.add_column("Último motivo")
    for r in rows:
        table.add_row(r["hanzi"], r["card_type"], str(r["fail_count"]), str(r["regen_attempts"]), (r["last_notes"] or "")[:80])
    return table


def _review_flagged_table(conn, hsk_level: Optional[int]) -> Table:
    where, params = _where(hsk_level)
    clause = f"{where} AND" if where else "WHERE"
    rows = conn.execute(
        f"""
        SELECT w.hanzi, c.card_type, c.review_status, c.review_notes, c.regen_attempts,
               (SELECT COALESCE(MAX(attempt), 0) FROM generation_phases gp
                WHERE gp.card_id = c.id AND gp.phase = 'review_flag') AS times_flagged
        FROM cards c JOIN words w ON w.id = c.word_id
        {clause} c.review_status IN ('flagged_bad', 'needs_human')
        ORDER BY c.review_status DESC, w.hanzi
        """,
        params,
    ).fetchall()

    table = Table(title="Flaggeadas / escaladas a revisión humana")
    table.add_column("Hanzi")
    table.add_column("Tipo")
    table.add_column("review_status")
    table.add_column("Veces flaggeada", justify="right")
    table.add_column("Rondas regen", justify="right")
    table.add_column("Nota")
    for r in rows:
        table.add_row(
            r["hanzi"], r["card_type"], r["review_status"], str(r["times_flagged"]), str(r["regen_attempts"]),
            (r["review_notes"] or "")[:60],
        )
    return table


def _stuck_word_prep_table(conn, hsk_level: Optional[int]) -> Table:
    where, params = _where(hsk_level)
    clause = f"{where} AND" if where else "WHERE"
    rows = conn.execute(
        f"""
        SELECT w.id, w.hanzi,
               (SELECT COUNT(*) FROM generation_phases gp WHERE gp.word_id = w.id AND gp.phase = 'word_prep' AND gp.status = 'failed') AS fail_count
        FROM words w
        {clause} NOT EXISTS (SELECT 1 FROM readings r WHERE r.word_id = w.id AND r.source = 'llm')
          AND EXISTS (SELECT 1 FROM generation_phases gp WHERE gp.word_id = w.id AND gp.phase = 'word_prep' AND gp.status = 'failed')
        ORDER BY w.hanzi
        """,
        params,
    ).fetchall()

    table = Table(title="Palabras atascadas en word_prep (nunca resolvieron lectura)")
    table.add_column("Hanzi")
    table.add_column("Intentos fallidos", justify="right")
    for r in rows:
        table.add_row(r["hanzi"], str(r["fail_count"]))
    return table


def find_orphaned_audio() -> list:
    """Archivos en resources/audios/ que ningún audio_files.file_path referencia.
    Incluye los .alignment.json huérfanos (sidecar del mp3 correspondiente)."""
    if not AUDIO_DIR.exists():
        return []
    with get_connection() as conn:
        referenced_names = {
            Path(row["file_path"]).name for row in conn.execute("SELECT DISTINCT file_path FROM audio_files").fetchall()
        }

    orphans = []
    for f in AUDIO_DIR.iterdir():
        if not f.is_file():
            continue
        if f.name.endswith(".alignment.json"):
            mp3_name = f.name.replace(".alignment.json", ".mp3")
        elif f.suffix == ".mp3":
            mp3_name = f.name
        else:
            continue  # no es un audio/sidecar nuestro (ej. .gitkeep) — no tocar
        if mp3_name not in referenced_names:
            orphans.append(f)
    return orphans


def clean_orphaned_audio(dry_run: bool = True) -> dict:
    orphans = find_orphaned_audio()
    total_size = sum(f.stat().st_size for f in orphans)
    if not dry_run:
        for f in orphans:
            f.unlink()
    return {"count": len(orphans), "total_size_bytes": total_size, "files": [str(f) for f in orphans], "deleted": not dry_run}


def print_dashboard(hsk_level: Optional[int] = None) -> None:
    init_db()
    console = Console()
    with get_connection() as conn:
        console.print(_status_table(conn, hsk_level))
        console.print(_review_table(conn, hsk_level))
        console.print(_guardrail_failed_table(conn, hsk_level))
        console.print(_review_flagged_table(conn, hsk_level))
        console.print(_stuck_word_prep_table(conn, hsk_level))

    orphans = find_orphaned_audio()
    size_mb = sum(f.stat().st_size for f in orphans) / (1024 * 1024)
    console.print(f"\n[bold]Audio huérfano:[/bold] {len(orphans)} archivo(s), {size_mb:.1f} MB — `main.py clean-audio` para revisar/borrar")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dashboard de estado de la DB de ChinoSRS")
    parser.add_argument("--hsk-level", type=int, default=None, help="Filtrar por nivel HSK (default: todos)")
    args = parser.parse_args()
    print_dashboard(hsk_level=args.hsk_level)
