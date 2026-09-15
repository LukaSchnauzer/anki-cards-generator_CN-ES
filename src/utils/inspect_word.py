"""Muestra todo el estado de una palabra en un solo comando: lecturas,
tarjetas (estado/review/origen), la oración guardada de cada una, y los
últimos intentos de generación con su motivo de fallo si los hay.

Antes de esto, revisar una palabra a mano significaba escribir un SELECT
directo contra SQLite cada vez (útil para el desarrollo, pero no algo que
el usuario final debería tener que hacer). Esto empaqueta esas mismas
consultas en un comando normal de main.py."""

import argparse
from typing import Optional

from rich.console import Console
from rich.table import Table

from src.db.database import get_connection, init_db

RECENT_ATTEMPTS_PER_CARD = 3


def inspect_word(hanzi: str, hsk_level: Optional[int] = 3) -> None:
    console = Console()
    with get_connection() as conn:
        query = "SELECT * FROM words WHERE hanzi = ?"
        params = [hanzi]
        if hsk_level is not None:
            query += " AND COALESCE(export_level, hsk_level) = ?"
            params.append(hsk_level)
        word = conn.execute(query, params).fetchone()

        if word is None:
            console.print(f"[red]No se encontró '{hanzi}'" + (f" en HSK{hsk_level}" if hsk_level is not None else "") + "[/red]")
            return

        readings = conn.execute(
            "SELECT * FROM readings WHERE word_id = ? ORDER BY is_primary DESC, id", (word["id"],)
        ).fetchall()
        cards = conn.execute(
            "SELECT * FROM cards WHERE word_id = ? ORDER BY card_type", (word["id"],)
        ).fetchall()

        console.print(
            f"\n[bold cyan]{word['hanzi']}[/bold cyan]  "
            f"(word_id={word['id']}, HSK{word['hsk_level']}"
            + (f", export_level={word['export_level']}" if word["export_level"] else "")
            + f", word_prep_status={word['word_prep_status']})\n"
        )

        readings_table = Table(title="Lecturas")
        readings_table.add_column("primaria")
        readings_table.add_column("pinyin")
        readings_table.add_column("meaning_es")
        readings_table.add_column("meaning_zh")
        readings_table.add_column("source")
        for r in readings:
            readings_table.add_row(
                "★" if r["is_primary"] else "", r["pinyin"], r["meaning_es"] or "", r["meaning_zh"] or "", r["source"]
            )
        console.print(readings_table)

        cards_table = Table(title="Tarjetas")
        cards_table.add_column("tipo")
        cards_table.add_column("status")
        cards_table.add_column("review_status")
        cards_table.add_column("content_source")
        cards_table.add_column("regen_attempts", justify="right")
        examples = {}
        for c in cards:
            ex = conn.execute(
                "SELECT example_zh, example_es FROM card_examples WHERE card_id = ?", (c["id"],)
            ).fetchone()
            examples[c["id"]] = ex
            cards_table.add_row(c["card_type"], c["status"], c["review_status"], c["content_source"], str(c["regen_attempts"]))
        console.print(cards_table)

        console.print()
        for c in cards:
            ex = examples[c["id"]]
            if ex and (ex["example_zh"] or ex["example_es"]):
                console.print(f"  [bold]{c['card_type']}[/bold]: {ex['example_zh']}")
                console.print(f"           -> {ex['example_es']}")

        attempts_table = Table(title=f"Últimos intentos (máx {RECENT_ATTEMPTS_PER_CARD} por tarjeta)")
        attempts_table.add_column("tipo")
        attempts_table.add_column("fase")
        attempts_table.add_column("status")
        attempts_table.add_column("intento", justify="right")
        attempts_table.add_column("notas")
        any_attempt = False
        for c in cards:
            phases = conn.execute(
                "SELECT phase, status, attempt, notes FROM generation_phases WHERE card_id = ? ORDER BY id DESC LIMIT ?",
                (c["id"], RECENT_ATTEMPTS_PER_CARD),
            ).fetchall()
            for p in phases:
                any_attempt = True
                attempts_table.add_row(c["card_type"], p["phase"], p["status"], str(p["attempt"]), (p["notes"] or "")[:100])
        if any_attempt:
            console.print(attempts_table)


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Muestra lecturas, tarjetas y últimos intentos de una palabra")
    parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    parser.add_argument("--hsk-level", type=int, default=3, help="Usa --hsk-level 0 para no filtrar por nivel")
    args = parser.parse_args()

    hsk_level = None if args.hsk_level == 0 else args.hsk_level
    inspect_word(args.word, hsk_level)
