"""AnkiConnect API utilities."""

import base64
import json
import os
import sys
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

ANKI_CONNECT_URL = os.environ.get("ANKI_CONNECT_URL", "http://localhost:8765")
DECK_NAME = os.environ.get("ANKI_DECK_NAME", "Chino SRS")


def post(action: str, **params):
    """Send a request to AnkiConnect."""
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    req = urllib.request.Request(ANKI_CONNECT_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = resp.read()
            data = json.loads(resp_data.decode("utf-8"))
            if data.get("error") is not None:
                # For addNotes, duplicates are returned in the result array, not as errors
                # Only raise if it's a real error, not a duplicate warning
                error_msg = str(data['error'])
                if action == "addNotes" and "duplicate" in error_msg.lower():
                    # Return the result anyway, it will contain None for duplicates
                    return data.get("result")
                raise RuntimeError(f"AnkiConnect error in {action}: {data['error']}")
            
            result = data.get("result")
            # If result is None for addNotes, include the full response for debugging
            if result is None and action == "addNotes":
                raise RuntimeError(f"AnkiConnect returned None for {action}. Full response: {json.dumps(data, indent=2)}")
            
            return result
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        raise RuntimeError(f"HTTP {e.code} error calling AnkiConnect at {ANKI_CONNECT_URL} for action {action}: {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Connection error calling AnkiConnect at {ANKI_CONNECT_URL} for action {action}: {e.reason}")
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"Unexpected error calling AnkiConnect at {ANKI_CONNECT_URL} for action {action}: {type(e).__name__}: {e}")


def ensure_deck(deck_name: str):
    """Create deck if it doesn't exist."""
    existing = post("deckNames")
    if deck_name not in existing:
        post("createDeck", deck=deck_name)


def store_media_file(abs_path: Path) -> str:
    """Sube un archivo al folder de medios de Anki. Devuelve el filename a usar
    en los campos de la nota (ej. src="archivo.mp3" en un <audio>).

    El nombre del archivo ya viene hasheado por contenido (ver audio_gen.py),
    así que subir el mismo archivo dos veces es un no-op idempotente para Anki."""
    filename = Path(abs_path).name
    data_b64 = base64.b64encode(Path(abs_path).read_bytes()).decode("ascii")
    post("storeMediaFile", filename=filename, data=data_b64)
    return filename


def clear_note_flags(note_id: int, only_if_flag: int = 1) -> None:
    """Pone en 0 (sin bandera) el flag de las cartas de una nota, pero SOLO
    si esa carta tiene puesto justo `only_if_flag` (rojo=1 por convención de
    este flujo de revisión). Nunca toca otros colores — el usuario puede
    estar usándolos para lo suyo (ej. marcar tarjetas ya aprendidas), y este
    flujo no debe pisarlos.

    Usa `setSpecificValueOfCard`, una acción "peligrosa" de AnkiConnect que
    escribe directo un campo interno de la carta — probada a mano contra una
    nota real antes de usarla acá. Firma real (no documentada de forma
    obvia): `card` es UN id a la vez (no una lista), y `newValues` debe ir
    como entero, no string.
    """
    card_ids = post("findCards", query=f"nid:{note_id}")
    if not card_ids:
        return
    for c in post("cardsInfo", cards=card_ids):
        if c["flags"] == only_if_flag:
            post("setSpecificValueOfCard", card=c["cardId"], keys=["flags"], newValues=[0], warning_check=True)


def model_exists(model_name: str) -> bool:
    """Check if a model/note type exists."""
    names = post("modelNames")
    return model_name in names


def delete_model(model_name: str):
    """Delete a model/note type if it exists."""
    if model_exists(model_name):
        try:
            post("deleteModel", modelName=model_name)
            print(f"Deleted model: {model_name}")
        except Exception as e:
            print(f"Warning: Could not delete model {model_name}: {e}", file=sys.stderr)
