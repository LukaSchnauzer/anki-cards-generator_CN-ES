# dump_notes.py
# Exporta todas las notas de un mazo de Anki a un JSON (vía AnkiConnect).
# Uso:
#   python dump_notes.py "Nombre del Mazo"
#
# Salida:
#   anki_dump_<nombre_sanitizado>.json (con noteId, modelName, fields, tags)

import sys
import json
import re
import os
import requests
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de AnkiConnect desde .env o default
ANKI = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")

def call(action, **params):
    resp = requests.post(ANKI, json={"action": action, "version": 6, "params": params})
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data["result"]

def sanitize_filename(name: str) -> str:
    # Reemplaza caracteres problemáticos para nombres de archivo en Windows
    return re.sub(r'[^-\w\.]+', '_', name, flags=re.UNICODE)

def main():
    if len(sys.argv) < 2:
        print("Uso: python dump_notes.py \"Nombre del Mazo\"")
        sys.exit(1)

    deck_name = sys.argv[1]
    out_name = f"anki_dump_{sanitize_filename(deck_name)}.json"
    root_dir = os.path.dirname(os.path.dirname(__file__))
    outputs_dir = os.path.join(root_dir, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    out_path = os.path.join(outputs_dir, out_name)

    # 0) Comprobación básica de conexión
    try:
        _ = call("version")
    except Exception as e:
        print("❌ No se pudo contactar AnkiConnect. "
              "Asegúrate de que Anki está abierto y AnkiConnect instalado.")
        print("Detalle:", e)
        sys.exit(1)

    # 1) Buscar notas del mazo
    query = f'deck:"{deck_name}"'
    note_ids = call("findNotes", query=query)
    print(f"🔎 Mazo: {deck_name}")
    print(f"🧾 Notas encontradas: {len(note_ids)}")

    if not note_ids:
        print("⚠️ No se encontraron notas. Revisa el nombre exacto del mazo.")
        sys.exit(0)

    # 2) Obtener información detallada por tandas
    chunk = 1000
    info = []
    for i in range(0, len(note_ids), chunk):
        part = note_ids[i:i+chunk]
        info.extend(call("notesInfo", notes=part))
        print(f"… procesadas {min(i+chunk, len(note_ids))}/{len(note_ids)}")

    # 3) Construir salida compacta y útil
    export = []
    for n in info:
        export.append({
            "noteId": n["noteId"],
            "modelName": n["modelName"],
            "fields": {k: v.get("value", "") for k, v in n.get("fields", {}).items()},
            "tags": n.get("tags", []),
        })

    # 4) Guardar JSON
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

    print(f"✅ Exportadas {len(export)} notas a: {out_path}")

if __name__ == "__main__":
    main()
