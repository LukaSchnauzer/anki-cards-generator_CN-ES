"""Grafo LangGraph que orquesta el pipeline de generación por palabra.

Un grafo por palabra: word_prep corre primero (resuelve lecturas y
colocaciones); si pasa, se abre en paralelo hacia word_audio, sentence_card,
pattern_card y audio_card (ninguno depende de otro, todos solo necesitan la
lectura principal ya resuelta). Cada tarjeta de texto encadena a su propio
nodo de audio al terminar. Usa un checkpointer SQLite (mismo archivo
outputs/chinosrs.db, conexión propia) para poder pausar y reanudar el
procesamiento de una palabra a medio camino.

run_pending_words() es el runner que de verdad le da al usuario "pausar y
reanudar todo el batch": recorre las palabras pendientes consultando la DB,
así que cortar el proceso (Ctrl+C) y volver a correrlo retoma donde quedó
sin depender del checkpointer para eso — el checkpointer es resiliencia
extra DENTRO del procesamiento de una palabra individual.
"""

import argparse
import json
import sqlite3
from typing import Callable, List, Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from src.db.database import DEFAULT_DB_PATH, get_connection
from src.generation.audio_card import run_audio_card
from src.generation.audio_gen import AudioGenError, DEFAULT_ENGINE, generate_tts_file, voice_id_for_word
from src.generation.card_common import mark_card_ready, save_audio_file
from src.generation.pattern_card import run_pattern_card
from src.generation.sentence_card import run_sentence_card
from src.generation.word_prep import run_word_prep
from src.utils.cost_tracker import get_tracker


class WordPipelineState(TypedDict):
    word_id: int
    hanzi: str
    seed_pinyin: Optional[str]
    source_meanings: Optional[list]
    word_prep_ok: bool
    sentence_card_ok: Optional[bool]
    pattern_card_ok: Optional[bool]
    audio_card_ok: Optional[bool]
    word_audio_ok: Optional[bool]
    sentence_audio_ok: Optional[bool]
    pattern_audio_ok: Optional[bool]
    audio_card_audio_ok: Optional[bool]


def word_prep_node(state: WordPipelineState) -> dict:
    # Idempotente: si ya hay lecturas resueltas por el LLM, no lo repite
    # (evita gastar de más en palabras que solo les falta UNA tarjeta).
    with get_connection() as conn:
        already = conn.execute(
            "SELECT 1 FROM readings WHERE word_id = ? AND source = 'llm' LIMIT 1", (state["word_id"],)
        ).fetchone()
    if already:
        return {"word_prep_ok": True}

    ok = run_word_prep(state["word_id"], state["hanzi"], state["seed_pinyin"], state["source_meanings"])
    with get_connection() as conn:
        # 'failed' acá es la ronda automática — igual que guardrail_failed en
        # cards, no cuenta contra el tope; solo regenerate_word_prep (llamado
        # desde `regenerate --flagged`) incrementa word_prep_attempts y puede
        # escalar a 'needs_human'.
        conn.execute(
            "UPDATE words SET word_prep_status = ? WHERE id = ?",
            ("ok" if ok else "failed", state["word_id"]),
        )
    return {"word_prep_ok": ok}


def _fetch_primary_and_card(word_id: int, card_type: str):
    with get_connection() as conn:
        primary = conn.execute(
            "SELECT * FROM readings WHERE word_id = ? AND is_primary = 1", (word_id,)
        ).fetchone()
        card = conn.execute(
            "SELECT id, status FROM cards WHERE word_id = ? AND card_type = ?", (word_id, card_type)
        ).fetchone()
        return primary, card


# Estados terminales de una tarjeta para `generate`: una vez que llega a
# cualquiera de estos dos, una corrida normal la deja quieta. 'ready' porque
# ya está lista; 'guardrail_failed' A PROPÓSITO — decisión explícita del
# usuario de no reintentarla sola e indefinidamente en cada corrida futura
# (podría estar mal de fondo, no por mala suerte del LLM). Solo se reintenta
# con `regenerate --flagged`, a mano.
_TERMINAL_CARD_STATUSES = ("ready", "guardrail_failed")


def sentence_card_node(state: WordPipelineState) -> dict:
    primary, card = _fetch_primary_and_card(state["word_id"], "sentence")
    if card["status"] in _TERMINAL_CARD_STATUSES:
        return {"sentence_card_ok": card["status"] == "ready"}
    ok = run_sentence_card(
        card["id"], primary["id"], state["hanzi"], primary["pinyin"], primary["meaning_es"], primary["meaning_zh"]
    )
    return {"sentence_card_ok": ok}


def pattern_card_node(state: WordPipelineState) -> dict:
    primary, card = _fetch_primary_and_card(state["word_id"], "pattern")
    if card["status"] in _TERMINAL_CARD_STATUSES:
        return {"pattern_card_ok": card["status"] == "ready"}
    ok = run_pattern_card(
        card["id"], primary["id"], state["hanzi"], primary["pinyin"], primary["meaning_es"], primary["meaning_zh"]
    )
    return {"pattern_card_ok": ok}


def audio_card_node(state: WordPipelineState) -> dict:
    primary, card = _fetch_primary_and_card(state["word_id"], "audio")
    if card["status"] in _TERMINAL_CARD_STATUSES:
        return {"audio_card_ok": card["status"] == "ready"}
    ok = run_audio_card(
        card["id"], primary["id"], state["hanzi"], primary["pinyin"], primary["meaning_es"], primary["meaning_zh"]
    )
    return {"audio_card_ok": ok}


def _log_audio_phase(word_id: int, phase: str, status: str, notes: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO generation_phases (word_id, phase, status, attempt, notes) VALUES (?, ?, ?, 1, ?)",
            (word_id, phase, status, notes),
        )


def word_audio_node(state: WordPipelineState) -> dict:
    """Audio de la palabra sola (solo lectura principal) — una vez por palabra,
    reutilizado por las 3 tarjetas vía reading_id.

    Se genera a velocidad LENTA (no normal): una palabra sola/corta dicha a
    velocidad conversacional normal pasa demasiado rápido para distinguirla
    bien; acá no hay ejercicio de comprensión atado, solo sirve para
    escuchar la pronunciación con claridad.
    """
    with get_connection() as conn:
        primary = conn.execute(
            "SELECT * FROM readings WHERE word_id = ? AND is_primary = 1", (state["word_id"],)
        ).fetchone()
        already = conn.execute(
            "SELECT 1 FROM audio_files WHERE reading_id = ? AND speed = 'slow'", (primary["id"],)
        ).fetchone()
    if already:
        return {"word_audio_ok": True}

    voice_id = voice_id_for_word(state["word_id"])
    try:
        path, alignment = generate_tts_file(state["hanzi"], speed="slow", prefix="word_", voice_id=voice_id)
    except AudioGenError as ex:
        _log_audio_phase(state["word_id"], "word_audio", "failed", str(ex))
        return {"word_audio_ok": False}

    with get_connection() as conn:
        save_audio_file(
            conn, scope="word", reading_id=primary["id"], speed="slow", engine=DEFAULT_ENGINE, file_path=path, alignment=alignment
        )
    return {"word_audio_ok": True}


def card_audio_node(word_id: int, card_type: str, phase: str, slow_too: bool = False) -> bool:
    """Genera (o reutiliza) el audio de la oración de una tarjeta ya con texto
    'guardrail_passed'. Público porque src/generation/regenerate.py lo reusa
    para regenerar el audio de una sola tarjeta sin pasar por el grafo."""
    with get_connection() as conn:
        card = conn.execute(
            "SELECT id, status FROM cards WHERE word_id = ? AND card_type = ?", (word_id, card_type)
        ).fetchone()

        if card["status"] == "ready":
            return True  # ya tiene audio de una corrida anterior, no repetir

        example = conn.execute("SELECT * FROM card_examples WHERE card_id = ?", (card["id"],)).fetchone()

        if card["status"] != "guardrail_passed" or example is None:
            # el texto no pasó el guardrail (o todavía no se generó) — no hay nada que ponerle audio
            return False

        already = conn.execute(
            "SELECT 1 FROM audio_files WHERE card_example_id = ? AND speed = 'normal'", (example["id"],)
        ).fetchone()

    voice_id = voice_id_for_word(word_id)
    speeds = ["normal", "slow"] if slow_too else ["normal"]
    try:
        if not already:
            for speed in speeds:
                path, alignment = generate_tts_file(example["example_zh"], speed=speed, voice_id=voice_id)
                with get_connection() as conn:
                    save_audio_file(
                        conn,
                        scope="sentence",
                        card_example_id=example["id"],
                        speed=speed,
                        engine=DEFAULT_ENGINE,
                        file_path=path,
                        alignment=alignment,
                    )
    except AudioGenError as ex:
        _log_audio_phase(word_id, phase, "failed", str(ex))
        return False

    with get_connection() as conn:
        mark_card_ready(conn, card["id"])
    return True


def sentence_audio_node(state: WordPipelineState) -> dict:
    ok = card_audio_node(state["word_id"], "sentence", "sentence_audio")
    return {"sentence_audio_ok": ok}


def pattern_audio_node(state: WordPipelineState) -> dict:
    ok = card_audio_node(state["word_id"], "pattern", "pattern_audio")
    return {"pattern_audio_ok": ok}


def audio_card_audio_node(state: WordPipelineState) -> dict:
    # slow_too=True: AudioCard es la única que necesita la versión lenta de la oración.
    ok = card_audio_node(state["word_id"], "audio", "audio_card_audio", slow_too=True)
    return {"audio_card_audio_ok": ok}


def route_after_word_prep(state: WordPipelineState) -> List[str]:
    if state["word_prep_ok"]:
        return ["word_audio", "sentence_card", "pattern_card", "audio_card"]
    return [END]


def build_graph_builder() -> StateGraph:
    builder = StateGraph(WordPipelineState)
    builder.add_node("word_prep", word_prep_node)
    builder.add_node("word_audio", word_audio_node)
    builder.add_node("sentence_card", sentence_card_node)
    builder.add_node("sentence_audio", sentence_audio_node)
    builder.add_node("pattern_card", pattern_card_node)
    builder.add_node("pattern_audio", pattern_audio_node)
    builder.add_node("audio_card", audio_card_node)
    builder.add_node("audio_card_audio", audio_card_audio_node)
    builder.add_edge(START, "word_prep")
    builder.add_conditional_edges(
        "word_prep", route_after_word_prep, ["word_audio", "sentence_card", "pattern_card", "audio_card", END]
    )
    builder.add_edge("word_audio", END)
    builder.add_edge("sentence_card", "sentence_audio")
    builder.add_edge("sentence_audio", END)
    builder.add_edge("pattern_card", "pattern_audio")
    builder.add_edge("pattern_audio", END)
    builder.add_edge("audio_card", "audio_card_audio")
    builder.add_edge("audio_card_audio", END)
    return builder


def get_checkpointer(db_path=DEFAULT_DB_PATH) -> SqliteSaver:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 5000")
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def run_word(
    word_id: int,
    hanzi: str,
    seed_pinyin: Optional[str],
    source_meanings: Optional[list],
    checkpointer: SqliteSaver,
    on_node: Optional[Callable[[str], None]] = None,
) -> dict:
    """Corre el grafo para una palabra. Si se pasa `on_node`, se llama con el
    nombre de cada nodo apenas termina (para reportar progreso en vivo)."""
    graph = build_graph_builder().compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": f"word-{word_id}"}}
    initial_state: WordPipelineState = {
        "word_id": word_id,
        "hanzi": hanzi,
        "seed_pinyin": seed_pinyin,
        "source_meanings": source_meanings,
        "word_prep_ok": False,
        "sentence_card_ok": None,
        "pattern_card_ok": None,
        "audio_card_ok": None,
        "word_audio_ok": None,
        "sentence_audio_ok": None,
        "pattern_audio_ok": None,
        "audio_card_audio_ok": None,
    }

    if on_node is None:
        return graph.invoke(initial_state, config=config)

    result: dict = dict(initial_state)
    for chunk in graph.stream(initial_state, config=config, stream_mode="updates"):
        for node_name, update in chunk.items():
            result.update(update)
            on_node(node_name)
    return result


_TERMINAL_WORD_PREP_STATUSES = ("failed", "needs_human")


def _word_needs_first_attempt(conn, word_id: int) -> bool:
    """True si a la palabra le queda alguna tarjeta que nunca se ha intentado
    (status='pending'). Una tarjeta en 'guardrail_failed' NO cuenta — a
    propósito, `generate` la deja quieta (ver _TERMINAL_CARD_STATUSES);
    solo se reintenta con `regenerate --flagged`, a mano. Mismo trato para la
    palabra completa si word_prep está 'failed'/'needs_human' — sin esto,
    generate reintentaría word_prep sin límite en cada corrida futura."""
    wp_status = conn.execute("SELECT word_prep_status FROM words WHERE id = ?", (word_id,)).fetchone()["word_prep_status"]
    if wp_status in _TERMINAL_WORD_PREP_STATUSES:
        return False
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM cards WHERE word_id = ? AND card_type IN ('sentence', 'pattern', 'audio') AND status = 'pending'",
        (word_id,),
    ).fetchone()
    return row["n"] > 0


def run_pending_words(limit: Optional[int] = None) -> int:
    """Procesa palabras que tienen al menos una tarjeta nunca intentada
    (status='pending'). Interrumpible en cualquier momento (Ctrl+C) —
    volver a correrla retoma donde quedó. Muestra progreso, ETA y costo
    estimado (LLM + ElevenLabs) en vivo."""
    checkpointer = get_checkpointer()
    tracker = get_tracker()

    with get_connection() as conn:
        all_words = conn.execute("SELECT id, hanzi, source_meanings_json FROM words ORDER BY id").fetchall()
        pending = [w for w in all_words if _word_needs_first_attempt(conn, w["id"])]

    if limit:
        pending = pending[:limit]

    console = Console()
    processed = 0
    attempted_cards = 0  # tarjetas que salieron de 'pending' en ESTA corrida (ready o guardrail_failed)
    failed_cards = 0  # de esas, cuántas agotaron sus reintentos (guardrail_failed)

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
            "[bold white]tot ${task.fields[total_cost]:.3f}[/bold white]  "
            "[red]agotadas {task.fields[fail_pct]:.1f}%[/red]"
        ),
        console=console,
    ) as progress:
        task = progress.add_task(
            "generando",
            total=len(pending) or 1,
            label="iniciando…",
            llm_cost=0.0,
            el_cost=0.0,
            total_cost=0.0,
            fail_pct=0.0,
        )

        for w in pending:
            with get_connection() as conn:
                reading = conn.execute("SELECT pinyin FROM readings WHERE word_id = ? LIMIT 1", (w["id"],)).fetchone()
                pending_types = [
                    r["card_type"]
                    for r in conn.execute(
                        "SELECT card_type FROM cards WHERE word_id = ? AND status = 'pending'", (w["id"],)
                    ).fetchall()
                ]
            seed_pinyin = reading["pinyin"] if reading else None
            source_meanings = json.loads(w["source_meanings_json"] or "[]")

            def _on_node(node_name: str, _w=w) -> None:
                progress.update(task, label=f"{_w['hanzi']} (id={_w['id']}) · {node_name}")

            run_word(w["id"], w["hanzi"], seed_pinyin, source_meanings, checkpointer, on_node=_on_node)

            if pending_types:
                with get_connection() as conn:
                    placeholders = ",".join("?" * len(pending_types))
                    new_statuses = conn.execute(
                        f"SELECT status FROM cards WHERE word_id = ? AND card_type IN ({placeholders})",
                        (w["id"], *pending_types),
                    ).fetchall()
                for row in new_statuses:
                    if row["status"] in ("ready", "guardrail_failed"):
                        attempted_cards += 1
                        if row["status"] == "guardrail_failed":
                            failed_cards += 1

            processed += 1
            fail_pct = (failed_cards / attempted_cards * 100) if attempted_cards else 0.0
            progress.update(
                task,
                advance=1,
                llm_cost=tracker.llm_cost_usd,
                el_cost=tracker.elevenlabs_cost_usd,
                total_cost=tracker.total_cost_usd,
                fail_pct=fail_pct,
            )

    console.print(f"[bold green]✓ Listo.[/bold green] {processed} palabra(s) procesada(s) en esta corrida.")
    console.print(
        f"Costo estimado (precio de lista): [bold]${tracker.total_cost_usd:.4f}[/bold]"
        f"  ·  LLM ${tracker.llm_cost_usd:.4f} ({tracker.llm_calls} llamadas)"
        f"  ·  ElevenLabs ${tracker.elevenlabs_cost_usd:.4f} ({tracker.elevenlabs_calls} llamadas)"
    )
    fail_pct_final = (failed_cards / attempted_cards * 100) if attempted_cards else 0.0
    console.print(
        f"Tarjetas agotadas (guardrail_failed): [bold red]{failed_cards}/{attempted_cards} ({fail_pct_final:.1f}%)[/bold red]"
    )
    return processed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corre el pipeline de generación sobre las palabras pendientes")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de palabras a procesar en esta corrida")
    args = parser.parse_args()
    run_pending_words(limit=args.limit)
