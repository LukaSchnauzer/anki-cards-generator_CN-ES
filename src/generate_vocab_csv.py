import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests

API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"

CSV_HEADER = [
    "hanzi",
    "pinyin",
    "definition",
    "example_sentence",
    "example_translation",
    "tips",
    "collocations",
    "pos",
    "register",
    "longitud",
    "tags_seed",
    "frecuencia",
]

SYSTEM_PROMPT = (
    "Eres un hablante nativo de chino mandarín y español nativo. Enseñas chino a hispanohablantes.\n"
    "Tarea: dada una palabra en hanzi y pinyin, genera contenido DIDÁCTICO en español para un CSV.\n"
    "Devuelve SIEMPRE un JSON con las claves exactas:\n"
    "{\n"
    "  \"definition\": string,\n"
    "  \"example_sentence\": string[3],\n"
    "  \"example_translation\": string[3],\n"
    "  \"tips\": string,\n"
    "  \"collocations\": string[3..5],\n"
    "  \"register\": one of [\"reg:colloquial\",\"reg:neutral\",\"reg:formal\",\"reg:literary\"],\n"
    "  \"tags_seed\": string | string[]  // de entre: gram:ba, gram:bei, gram:le, gram:guo, gram:zhe, gram:de, gram:resultative, gram:potential\n"
    "}\n"
    "Requisitos:\n"
    "- \"definition\": breve, clara y natural; NO copies textos en inglés; explica como a un alumno hispanohablante.\n"
    "- \"example_sentence\": array de 3 oraciones SOLO en caracteres chinos (hanzi). NO incluyas pinyin, NO incluyas traducción. Solo hanzi.\n"
    "- \"example_translation\": array de 3 traducciones en español, correspondientes a las 3 oraciones anteriores.\n"
    "- \"tips\": notas de uso, matices y construcciones comunes.\n"
    "- \"collocations\": combinaciones frecuentes (3–5), en chino, con glosa española entre paréntesis.\n"
    "- Si no aplica ninguna etiqueta gramatical, deja \"tags_seed\": \"\".\n"
)


def get_hsk_from_levels(levels):
    if not levels:
        return None
    best_new = None
    best_old = None
    for lv in levels:
        if isinstance(lv, str):
            if lv.startswith("new-"):
                tail = lv[4:].rstrip('+')  # Remove trailing + if present
                if tail.isdigit():
                    n = int(tail)
                    if best_new is None or n < best_new:
                        best_new = n
            elif lv.startswith("old-"):
                tail = lv[4:].rstrip('+')
                if tail.isdigit():
                    n = int(tail)
                    if best_old is None or n < best_old:
                        best_old = n
    # Prefer new, fallback to old
    best = best_new if best_new is not None else best_old
    return f"hsk:{best}" if best else None


def get_freq_bucket(rank):
    if not rank or rank <= 0:
        return None
    if rank <= 1000:
        return "freq:top1k"
    if rank <= 3000:
        return "freq:top3k"
    if rank <= 5000:
        return "freq:top5k"
    if rank <= 10000:
        return "freq:top10k"
    return "freq:rare"


def fix_encoding(text):
    """Fix mojibake by re-encoding latin-1 as utf-8"""
    if not text or not isinstance(text, str):
        return text
    try:
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def read_entries(input_path):
    p = Path(input_path)
    items = []
    if p.is_file():
        with p.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
            items.extend(data if isinstance(data, list) else [data])
    elif p.is_dir():
        for fp in sorted(p.rglob("*.json")):
            try:
                with fp.open("r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                items.extend(data if isinstance(data, list) else [data])
            except Exception:
                pass
    else:
        raise FileNotFoundError(f"Ruta no encontrada: {p}")
    return items


def openai_generate(api_key, model, hanzi, pinyin, pos, meanings):
    # Create user message with example format
    user_content = (
        f"Genera contenido para:\n"
        f"hanzi: {hanzi}\n"
        f"pinyin: {pinyin}\n"
        f"pos: {pos}\n"
        f"meanings: {meanings}\n\n"
        f"IMPORTANTE: example_sentence debe ser un array de 3 strings, cada uno SOLO con caracteres chinos.\n"
        f"Ejemplo correcto:\n"
        f'"example_sentence": ["这件首饰非常贵重。", "他把贵重的文件放在保险箱里。", "这幅画是一个贵重的艺术品。"]\n'
        f'"example_translation": ["Esta joya es muy valiosa.", "Él guardó los documentos valiosos en la caja fuerte.", "Esta pintura es una obra de arte valiosa."]'
    )
    
    body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    r = requests.post(API_URL, headers=headers, json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI API error {r.status_code}: {r.text}")
    content = r.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def to_length_tag(hanzi):
    return "length:char" if len(hanzi) <= 1 else "length:word"


def safe_join(arr):
    if not arr:
        return ""
    if isinstance(arr, str):
        return arr
    return " | ".join(x.strip() for x in arr if isinstance(x, str) and x.strip())


def load_env_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Genera CSV de vocabulario HSK enriquecido")
    parser.add_argument("--input", "-i", required=True, help="Ruta a complete.json o carpeta con chunks")
    parser.add_argument("--output", "-o", required=True, help="Ruta del CSV de salida")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Modelo OpenAI")
    parser.add_argument("--max-items", type=int, default=0, help="Procesar solo N items (0 = todos)")
    parser.add_argument("--delay-ms", type=int, default=0, help="Retraso entre peticiones (ms)")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    for candidate in [Path.cwd() / ".env", script_dir / ".env", script_dir.parent / ".env"]:
        if candidate.exists():
            load_env_file(candidate)
            break

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        print("Error: Define OPENAI_API_KEY en .env", file=sys.stderr)
        return 1

    start_time = time.time()
    total_tokens = 0
    entries = read_entries(args.input)
    if args.max_items > 0:
        entries = entries[: args.max_items]

    print(f"Starting processing of {len(entries)} entries...")
    sys.stdout.flush()

    with open(args.output, "w", encoding="utf-8", newline="") as f_csv:
        writer = csv.writer(f_csv)
        writer.writerow(CSV_HEADER)
        f_csv.flush()

        for idx, e in enumerate(entries, 1):
            hanzi = fix_encoding(e.get("simplified", ""))
            if not hanzi:
                continue

            forms = e.get("forms", [])
            pinyin = ""
            if forms:
                pinyin = fix_encoding(forms[0].get("transcriptions", {}).get("pinyin", ""))

            pos_list = e.get("pos", [])
            pos_prefixed = [f"pos:{p}" for p in pos_list if p]

            meanings = []
            if forms:
                meanings = forms[0].get("meanings", [])

            hsk_tag = get_hsk_from_levels(e.get("level"))
            freq_bucket = get_freq_bucket(e.get("frequency", 0))
            freq_tags = []
            if hsk_tag:
                freq_tags.append(hsk_tag)
            if freq_bucket:
                freq_tags.append(freq_bucket)
            length_tag = to_length_tag(hanzi)

            try:
                gen = openai_generate(api_key, args.model, hanzi, pinyin, pos_list, meanings)
                # Estimate tokens: ~150 input + ~400 output per call
                total_tokens += 550
            except Exception as ex:
                print(f"Error [{idx}/{len(entries)}] {hanzi}: {ex}", file=sys.stderr)
                sys.stderr.flush()
                continue

            tags_seed = gen.get("tags_seed", "")
            tags_seed_str = ";".join(tags_seed) if isinstance(tags_seed, list) else str(tags_seed)

            row = [
                hanzi,
                pinyin,
                gen.get("definition", "").strip(),
                safe_join(gen.get("example_sentence", [])),
                safe_join(gen.get("example_translation", [])),
                gen.get("tips", "").strip(),
                safe_join(gen.get("collocations", [])),
                ";".join(pos_prefixed),
                gen.get("register", "reg:neutral"),
                length_tag,
                tags_seed_str,
                ";".join(freq_tags),
            ]
            writer.writerow(row)
            f_csv.flush()

            if idx % 5 == 0 or idx == 1:
                elapsed = time.time() - start_time
                rate = idx / elapsed if elapsed > 0 else 0
                remaining = (len(entries) - idx) / rate if rate > 0 else 0
                # Cost estimate: $0.150/1M input + $0.600/1M output for gpt-4o-mini
                # Approx 150 input + 400 output tokens per call = 550 total
                cost = (total_tokens * 0.15 / 1_000_000) + (total_tokens * 0.4 / 1_000_000)
                print(f"Progress: {idx}/{len(entries)} ({idx*100//len(entries)}%) | Rate: {rate:.1f}/min | ETA: {remaining/60:.1f}min | Tokens: {total_tokens:,} | Cost: ${cost:.3f}")
                sys.stdout.flush()

            if args.delay_ms > 0:
                time.sleep(args.delay_ms / 1000.0)

    print(f"CSV generado: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
