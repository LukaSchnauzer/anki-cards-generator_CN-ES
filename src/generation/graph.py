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
from typing import List, Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from src.db.database import DEFAULT_DB_PATH, get_connection
from src.generation.audio_card import run_audio_card
from src.generation.audio_gen import AudioGenError, DEFAULT_ENGINE, generate_tts_file, voice_id_for_word
from src.generation.card_common import mark_card_ready, save_audio_file
from src.generation.pattern_card import run_pattern_card
from src.generation.sentence_card import run_sentence_card
from src.generation.word_prep import run_word_prep


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
    ok = run_word_prep(state["word_id"], state["hanzi"], state["seed_pinyin"], state["source_meanings"])
    return {"word_prep_ok": ok}


def _fetch_primary_and_card(word_id: int, card_type: str):
    with get_connection() as conn:
        primary = conn.execute(
            "SELECT * FROM readings WHERE word_id = ? AND is_primary = 1", (word_id,)
        ).fetchone()
        card = conn.execute(
            "SELECT id FROM cards WHERE word_id = ? AND card_type = ?", (word_id, card_type)
        ).fetchone()
        return primary, card


def sentence_card_node(state: WordPipelineState) -> dict:
    primary, card = _fetch_primary_and_card(state["word_id"], "sentence")
    ok = run_sentence_card(
        card["id"], primary["id"], state["hanzi"], primary["pinyin"], primary["meaning_es"], primary["meaning_zh"]
    )
    return {"sentence_card_ok": ok}


def pattern_card_node(state: WordPipelineState) -> dict:
    primary, card = _fetch_primary_and_card(state["word_id"], "pattern")
    ok = run_pattern_card(
        card["id"], primary["id"], state["hanzi"], primary["pinyin"], primary["meaning_es"], primary["meaning_zh"]
    )
    return {"pattern_card_ok": ok}


def audio_card_node(state: WordPipelineState) -> dict:
    primary, card = _fetch_primary_and_card(state["word_id"], "audio")
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


def _card_audio_node(word_id: int, card_type: str, phase: str, slow_too: bool = False) -> bool:
    with get_connection() as conn:
        card = conn.execute(
            "SELECT id, status FROM cards WHERE word_id = ? AND card_type = ?", (word_id, card_type)
        ).fetchone()
        example = conn.execute("SELECT * FROM card_examples WHERE card_id = ?", (card["id"],)).fetchone()
        already = conn.execute(
            "SELECT 1 FROM audio_files WHERE card_example_id = ? AND speed = 'normal'", (example["id"],)
        ).fetchone()

    if card["status"] != "guardrail_passed" or example is None:
        # el texto no pasó el guardrail — no hay nada que ponerle audio
        return False

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
    ok = _card_audio_node(state["word_id"], "sentence", "sentence_audio")
    return {"sentence_audio_ok": ok}


def pattern_audio_node(state: WordPipelineState) -> dict:
    ok = _card_audio_node(state["word_id"], "pattern", "pattern_audio")
    return {"pattern_audio_ok": ok}


def audio_card_audio_node(state: WordPipelineState) -> dict:
    # slow_too=True: AudioCard es la única que necesita la versión lenta de la oración.
    ok = _card_audio_node(state["word_id"], "audio", "audio_card_audio", slow_too=True)
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


def run_word(word_id: int, hanzi: str, seed_pinyin: Optional[str], source_meanings: Optional[list], checkpointer: SqliteSaver) -> dict:
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
    return graph.invoke(initial_state, config=config)


def _is_word_done(conn, word_id: int) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM cards WHERE word_id = ? AND card_type IN ('sentence', 'pattern', 'audio') AND status = 'ready'",
        (word_id,),
    ).fetchone()
    return row["n"] == 3


def run_pending_words(limit: Optional[int] = None) -> int:
    """Procesa palabras pendientes (sin sentence+pattern en 'ready'). Interrumpible
    en cualquier momento (Ctrl+C) — volver a correrla retoma donde quedó."""
    checkpointer = get_checkpointer()

    with get_connection() as conn:
        words = conn.execute("SELECT id, hanzi, source_meanings_json FROM words ORDER BY id").fetchall()

    processed = 0
    for w in words:
        with get_connection() as conn:
            if _is_word_done(conn, w["id"]):
                continue
            reading = conn.execute("SELECT pinyin FROM readings WHERE word_id = ? LIMIT 1", (w["id"],)).fetchone()

        seed_pinyin = reading["pinyin"] if reading else None
        source_meanings = json.loads(w["source_meanings_json"] or "[]")

        print(f"Procesando {w['hanzi']} (word_id={w['id']})...")
        run_word(w["id"], w["hanzi"], seed_pinyin, source_meanings, checkpointer)
        processed += 1
        if limit and processed >= limit:
            break

    print(f"Listo. {processed} palabra(s) procesada(s) en esta corrida.")
    return processed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corre el pipeline de generación sobre las palabras pendientes")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de palabras a procesar en esta corrida")
    args = parser.parse_args()
    run_pending_words(limit=args.limit)
