"""ElevenLabs TTS engine, con alineación por carácter (para el resaltado
de palabras sincronizado — ver el prototipo "AudioCard Sync")."""

import base64
import os

import requests
from dotenv import load_dotenv

from src.utils.cost_tracker import get_tracker

load_dotenv()

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"


class ElevenLabsEngine:
    """ElevenLabs Text-to-Speech, con soporte de timestamps por carácter."""

    def __init__(self, voice_id: str, speed: float = 1.0, model_id: str = "eleven_multilingual_v2"):
        self.voice_id = voice_id
        self.speed = speed
        self.model_id = model_id
        self.name = "ElevenLabs"
        self.api_key = os.getenv("ELEVEN_LABS_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_audio(self, text: str, output_path: str) -> bool:
        """Interfaz simple compatible con los otros motores (sin alineación)."""
        return self.generate_audio_with_alignment(text, output_path) is not None

    def generate_audio_with_alignment(self, text: str, output_path: str):
        """Genera el audio y devuelve el dict de alineación de ElevenLabs, o None si falla."""
        if not self.api_key:
            print("  ERROR ElevenLabs: falta ELEVEN_LABS_API_KEY en .env")
            return None

        url = API_URL.format(voice_id=self.voice_id)
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        body = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {"speed": self.speed},
        }
        try:
            r = requests.post(url, headers=headers, json=body, timeout=30)
            if r.status_code != 200:
                print(f"  ERROR ElevenLabs {r.status_code}: {r.text[:300]}")
                return None
            data = r.json()
            audio_bytes = base64.b64decode(data["audio_base64"])
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            get_tracker().add_elevenlabs_chars(len(text))
            return data.get("alignment")
        except Exception as ex:
            print(f"  ERROR ElevenLabs: {ex}")
            return None
