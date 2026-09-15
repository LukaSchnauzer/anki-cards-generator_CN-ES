"""Corrige el TEXTO (pinyin/significado) de una lectura YA registrada —
para cuando la lectura correcta existe, pero está mal descrita y por eso
word_prep/los agentes nunca la usan de forma natural.

Caso real: 所 tenía una lectura secundaria "clasificador para casas o
edificios pequeños" — la descripción estaba mal (所 no se usa para casas
ni edificios pequeños cualquiera, sino específicamente para instituciones:
一所学校, 一所医院, 一所大学). Con la descripción mal enfocada, ningún
agente la eligió nunca — todas las oraciones forzaban "所" como sustantivo
libre ("lugar"), que casi nunca aparece así en chino real.

A diferencia de add_reading.py (agrega una lectura que NO existía) y
swap_reading.py (cambia cuál lectura es primaria), esta herramienta NO
agrega ni cambia cuál es primaria — solo corrige el texto de una que ya
está ahí. Normalmente se usa seguido de swap_reading.py si, tras
corregirla, resulta que debería ser la primaria."""

import argparse
from typing import Optional

from src.db.database import get_connection, init_db


def edit_reading(
    word_id: int,
    meaning_query: str,
    new_meaning_es: Optional[str] = None,
    new_meaning_zh: Optional[str] = None,
    new_pinyin: Optional[str] = None,
    new_register: Optional[str] = None,
) -> dict:
    """Busca entre las lecturas de la palabra una cuyo meaning_es contenga
    `meaning_query` (sin importar mayúsculas) y actualiza los campos dados
    (los que se dejen en None no se tocan). Falla si no hay match único."""
    with get_connection() as conn:
        readings = conn.execute("SELECT * FROM readings WHERE word_id = ?", (word_id,)).fetchall()
        matches = [r for r in readings if meaning_query.lower() in (r["meaning_es"] or "").lower()]

        if len(matches) == 0:
            raise ValueError(
                f"Ninguna lectura coincide con {meaning_query!r}. Lecturas disponibles: "
                f"{[r['meaning_es'] for r in readings]}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"Coinciden {len(matches)} lecturas con {meaning_query!r}, sé más específico: "
                f"{[r['meaning_es'] for r in matches]}"
            )

        target = matches[0]
        old = {"meaning_es": target["meaning_es"], "meaning_zh": target["meaning_zh"], "pinyin": target["pinyin"], "register": target["register"]}

        fields, params = [], []
        if new_meaning_es is not None:
            fields.append("meaning_es = ?")
            params.append(new_meaning_es)
        if new_meaning_zh is not None:
            fields.append("meaning_zh = ?")
            params.append(new_meaning_zh)
        if new_pinyin is not None:
            fields.append("pinyin = ?")
            params.append(new_pinyin)
        if new_register is not None:
            fields.append("register = ?")
            params.append(new_register)

        if not fields:
            raise ValueError("No se dio ningún campo nuevo para actualizar (--new-meaning-es/--new-meaning-zh/--new-pinyin/--new-register)")

        params.append(target["id"])
        conn.execute(f"UPDATE readings SET {', '.join(fields)} WHERE id = ?", params)

    return {"reading_id": target["id"], "old": old, "new": {"meaning_es": new_meaning_es, "meaning_zh": new_meaning_zh, "pinyin": new_pinyin, "register": new_register}}


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser(description="Corrige el texto (pinyin/significado) de una lectura ya registrada")
    parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    parser.add_argument("--meaning-query", required=True, help="Texto (parcial) del meaning_es actual de la lectura a corregir")
    parser.add_argument("--new-meaning-es", default=None, help="Nuevo significado en español")
    parser.add_argument("--new-meaning-zh", default=None, help="Nueva definición en chino")
    parser.add_argument("--new-pinyin", default=None, help="Nuevo pinyin (raro que haga falta)")
    parser.add_argument("--new-register", default=None, help="reg:colloquial | reg:neutral | reg:formal | reg:literary")
    parser.add_argument("--hsk-level", type=int, default=3)
    args = parser.parse_args()

    with get_connection() as conn:
        word = conn.execute(
            "SELECT id FROM words WHERE hanzi = ? AND COALESCE(export_level, hsk_level) = ?", (args.word, args.hsk_level)
        ).fetchone()
    if word is None:
        print(f"No se encontró '{args.word}' en HSK{args.hsk_level}")
    else:
        result = edit_reading(
            word["id"], args.meaning_query,
            new_meaning_es=args.new_meaning_es, new_meaning_zh=args.new_meaning_zh,
            new_pinyin=args.new_pinyin, new_register=args.new_register,
        )
        print(f"Lectura {result['reading_id']} corregida:")
        for field in ("meaning_es", "meaning_zh", "pinyin", "register"):
            if result["new"][field] is not None:
                print(f"  {field}: {result['old'][field]!r} -> {result['new'][field]!r}")
