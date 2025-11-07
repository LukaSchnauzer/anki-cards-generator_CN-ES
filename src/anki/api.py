"""AnkiConnect API utilities."""

import json
import os
import sys
import hashlib
import urllib.request
from typing import Optional
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

ANKI_CONNECT_URL = os.environ.get("ANKI_CONNECT_URL", "http://localhost:8765")
DECK_NAME = os.environ.get("ANKI_DECK_NAME", "Chino SRS")
AUDIO_DIR = os.environ.get("ANKI_AUDIO_DIR", "")


def post(action: str, **params):
    """Send a request to AnkiConnect."""
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    req = urllib.request.Request(ANKI_CONNECT_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = resp.read()
            data = json.loads(resp_data.decode("utf-8"))
            if data.get("error") is not None:
                raise RuntimeError(f"AnkiConnect error in {action}: {data['error']}")
            return data.get("result")
    except Exception as e:
        raise RuntimeError(f"HTTP error calling AnkiConnect at {ANKI_CONNECT_URL} for action {action}: {e}")


def ensure_deck(deck_name: str):
    """Create deck if it doesn't exist."""
    existing = post("deckNames")
    if deck_name not in existing:
        post("createDeck", deck=deck_name)


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


def resolve_audio_path(audio_field: str, hanzi: str) -> Optional[str]:
    """
    Resolve audio file path from CSV field or hanzi.
    Returns absolute path if file exists, None otherwise.
    """
    if not audio_field:
        audio_field = f"{hanzi}.mp3"
    
    if AUDIO_DIR:
        candidate = os.path.join(AUDIO_DIR, audio_field)
    else:
        candidate = audio_field
    
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)
    return None


def find_audio_for_sentence(sentence: str, audio_dir: str = "resources/audios") -> Optional[str]:
    """
    Find audio file for a given sentence using hash-based matching.
    Returns absolute path if found, None otherwise.
    """
    if not sentence or not os.path.isdir(audio_dir):
        return None
    
    sentence_hash = hashlib.md5(sentence.encode('utf-8')).hexdigest()[:8]
    
    for filename in os.listdir(audio_dir):
        if filename.endswith('.mp3') and sentence_hash in filename:
            return os.path.abspath(os.path.join(audio_dir, filename))
    
    return None


def find_audio_for_word(hanzi: str, audio_dir: str = "resources/audios") -> Optional[str]:
    """
    Find audio file for a given word (hanzi) using hash-based matching.
    Returns absolute path if found, None otherwise.
    """
    if not hanzi or not os.path.isdir(audio_dir):
        return None
    
    word_hash = hashlib.md5(hanzi.encode('utf-8')).hexdigest()[:8]
    
    for filename in os.listdir(audio_dir):
        if filename.startswith('word_') and filename.endswith('.mp3') and word_hash in filename:
            return os.path.abspath(os.path.join(audio_dir, filename))
    
    return None
