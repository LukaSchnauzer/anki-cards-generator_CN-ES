"""Guarda una tarjeta con una oración ESCRITA A MANO (aprobada por un
humano), en vez de generada por el LLM desde cero.

Para palabras donde el LLM falló repetidamente en encontrar una oración
natural (ver review_status='needs_human') — a veces la palabra es un
morfema que casi nunca aparece independiente en el chino moderno (ej. 乐,
报, 保), y el camino más confiable es que un humano escriba la oración
directamente en vez de seguir pidiéndole al LLM que la invente.

El LLM se usa ÚNICAMENTE para el desglose palabra por palabra — una tarea
de ANÁLISIS de una oración ya fija, no de creación. La oración y la
traducción nunca se tocan. No corre ningún guardrail: un humano ya aprobó
el contenido real (oración + traducción); lo único que podría fallar es el
desglose, que se puede revisar a ojo si hace falta.
"""

import argparse
import json
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

from src.db.database import get_connection, init_db
from src.generation.card_common import (
    BreakdownItemOut,
    CardExampleOutput,
    apply_reference_pinyin,
    log_phase,
    mark_card_text_ready,
    save_card_example,
)
from src.generation.graph import card_audio_node
from src.generation.prompts import BREAKDOWN_ONLY_SYSTEM_PROMPT
from src.llm.client import GENERATION_MODEL, LLMError, call_llm
from src.utils.cost_tracker import get_tracker

CARD_TYPES = ("sentence", "pattern", "audio")


class BreakdownOnlyOutput(BaseModel):
    breakdown: List[BreakdownItemOut]
    grammar_notes: List[str] = Field(default_factory=list)


def generate_breakdown(
    hanzi: str, example_zh: str, example_es: str, model: str = GENERATION_MODEL, must_isolate: Optional[str] = None
) -> BreakdownOnlyOutput:
    user_prompt = (
        f"palabra objetivo: {hanzi}\n"
        f"oración (YA aprobada, no la cambies): {example_zh}\n"
        f"traducción (YA aprobada, no la cambies): {example_es}\n"
    )
    if must_isolate:
        # PatternCard ubica el hueco por posición exacta (hanzi == objetivo) —
        # si '{must_isolate}' normalmente iría pegado a otra palabra en una
        # expresión fija (ej. 过冬), hay que forzar que aparezca como su
        # propio elemento igual. _force_isolate_target() es la red de
        # seguridad determinística si esto no se respeta.
        user_prompt += (
            f"\nIMPORTANTE: '{must_isolate}' DEBE aparecer como su PROPIO elemento en el desglose "
            f"(hanzi == '{must_isolate}' exactamente), sin importar si normalmente formaría parte de "
            f"una expresión fija con la palabra vecina. Si es así (ej. la oración usa '过冬'), "
            f"desglósalo como DOS (o más) elementos separados: '过' y '冬', cada uno con su propio "
            f"significado y función gramatical — nunca como un solo elemento '过冬'.\n"
        )
    raw = call_llm(BREAKDOWN_ONLY_SYSTEM_PROMPT, user_prompt, model=model)
    try:
        data = json.loads(raw)
        return BreakdownOnlyOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as ex:
        raise LLMError(f"Respuesta inválida del LLM (breakdown) para {hanzi!r}: {ex}\nRaw: {raw}") from ex


def _force_isolate_target(breakdown: List[BreakdownItemOut], target_hanzi: str) -> List[BreakdownItemOut]:
    """Red de seguridad determinística: si `target_hanzi` no quedó como su
    propio elemento del desglose, parte el elemento que lo contiene en
    (prefijo, objetivo, sufijo) — sin LLM, pura manipulación de texto, así
    que la posición SIEMPRE queda correcta para el hueco de PatternCard.
    El pinyin de las 3 partes se recalcula después vía apply_reference_pinyin,
    así que no importa lo que se ponga acá."""
    if any(item.hanzi == target_hanzi for item in breakdown):
        return breakdown

    new_breakdown: List[BreakdownItemOut] = []
    already_split = False
    for item in breakdown:
        if not already_split and target_hanzi in item.hanzi and item.hanzi != target_hanzi:
            idx = item.hanzi.index(target_hanzi)
            prefix, suffix = item.hanzi[:idx], item.hanzi[idx + len(target_hanzi):]
            if prefix:
                new_breakdown.append(BreakdownItemOut(
                    hanzi=prefix, pinyin="", grammar_role=item.grammar_role,
                    meaning=f"(parte de '{item.hanzi}': {item.meaning})",
                ))
            new_breakdown.append(BreakdownItemOut(
                hanzi=target_hanzi, pinyin="", grammar_role=item.grammar_role,
                meaning=item.meaning, usage_note=item.usage_note or f"Aquí es parte de '{item.hanzi}'.",
            ))
            if suffix:
                new_breakdown.append(BreakdownItemOut(
                    hanzi=suffix, pinyin="", grammar_role=item.grammar_role,
                    meaning=f"(parte de '{item.hanzi}': {item.meaning})",
                ))
            already_split = True
        else:
            new_breakdown.append(item)
    return new_breakdown


def save_manual_card(word_id: int, card_type: str, example_zh: str, example_es: str, model: str = GENERATION_MODEL) -> bool:
    """Guarda una tarjeta con oración manual: desglose vía LLM (solo
    análisis), pinyin vía herramienta determinística, audio normal (+ lento
    si es AudioCard). Deja la tarjeta 'ready' y limpia review_status si el
    audio se genera bien."""
    with get_connection() as conn:
        word = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
        primary = conn.execute("SELECT * FROM readings WHERE word_id = ? AND is_primary = 1", (word_id,)).fetchone()
        card = conn.execute("SELECT * FROM cards WHERE word_id = ? AND card_type = ?", (word_id, card_type)).fetchone()
    if word is None or primary is None or card is None:
        raise ValueError(f"word_id={word_id}: falta la palabra, su lectura primaria o la tarjeta '{card_type}'")

    if card_type == "pattern" and word["hanzi"] not in example_zh:
        raise ValueError(f"'{word['hanzi']}' no aparece en la oración dada — revisa el texto.")

    bd = None
    last_err = None
    for _ in range(3):
        try:
            bd = generate_breakdown(
                word["hanzi"], example_zh, example_es, model=model,
                must_isolate=word["hanzi"] if card_type == "pattern" else None,
            )
            break
        except LLMError as ex:
            last_err = ex
    if bd is None:
        raise LLMError(f"No se pudo generar el desglose tras 3 intentos: {last_err}")

    breakdown = bd.breakdown
    if card_type == "pattern":
        before = [item.hanzi for item in breakdown]
        breakdown = _force_isolate_target(breakdown, word["hanzi"])
        if [item.hanzi for item in breakdown] != before:
            print(f"  (aviso: el LLM no aisló '{word['hanzi']}' pese a la instrucción — se partió a mano)")

    result = CardExampleOutput(
        example_zh=example_zh,
        example_es=example_es,
        example_pinyin="",
        breakdown=breakdown,
        grammar_notes=bd.grammar_notes,
    )
    apply_reference_pinyin(result)

    phase = f"{card_type}_card"
    with get_connection() as conn:
        save_card_example(conn, card["id"], primary["id"], result)
        log_phase(conn, card["id"], phase, "passed", 1, "manual (oración escrita por un humano)")
        mark_card_text_ready(conn, card["id"])

    audio_ok = card_audio_node(word_id, card_type, f"{card_type}_audio_manual", slow_too=(card_type == "audio"))
    if audio_ok:
        with get_connection() as conn:
            conn.execute(
                """UPDATE cards SET review_status = 'unflagged', regen_attempts = 0, content_source = 'manual',
                   updated_at = datetime('now') WHERE id = ?""",
                (card["id"],),
            )
    return audio_ok


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Guarda una tarjeta con una oración escrita a mano")
    parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    parser.add_argument("--type", required=True, choices=CARD_TYPES, help="Tipo de tarjeta")
    parser.add_argument("--zh", required=True, help="Oración en chino (ya aprobada)")
    parser.add_argument("--es", required=True, help="Traducción al español (ya aprobada)")
    parser.add_argument("--hsk-level", type=int, default=3)
    args = parser.parse_args()

    with get_connection() as conn:
        word = conn.execute(
            "SELECT id FROM words WHERE hanzi = ? AND COALESCE(export_level, hsk_level) = ?", (args.word, args.hsk_level)
        ).fetchone()
    if word is None:
        print(f"No se encontró '{args.word}' en HSK{args.hsk_level}")
    else:
        ok = save_manual_card(word["id"], args.type, args.zh, args.es)
        print("OK" if ok else "FAIL (revisa el audio/desglose)")
        tracker = get_tracker()
        print(
            f"Costo estimado: ${tracker.total_cost_usd:.4f}"
            f"  ·  LLM ${tracker.llm_cost_usd:.4f} ({tracker.llm_calls} llamadas)"
            f"  ·  ElevenLabs ${tracker.elevenlabs_cost_usd:.4f} ({tracker.elevenlabs_calls} llamadas)"
        )
