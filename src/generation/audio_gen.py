"""Generación de archivos de audio TTS para el pipeline de generación.

Motor por defecto: ElevenLabs (voces en mandarín + alineación por carácter,
necesaria para el resaltado de palabras sincronizado en AudioCard). El
nombre del archivo se deriva de un hash del texto + velocidad + voz, solo
como cache/optimización — el LINK real hacia la palabra u oración vive en
audio_files vía foreign key (reading_id / card_example_id), no en el nombre
del archivo.
"""

import hashlib
import json
from pathlib import Path
from typing import Optional, Tuple

from src.audio.engines.elevenlabs_engine import ElevenLabsEngine
from src.audio.engines.gtts_engine import GTTSEngine

AUDIO_DIR = Path(__file__).resolve().parents[2] / "resources" / "audios"
DEFAULT_ENGINE = "elevenlabs"

# Rotación de voces: fija por palabra (determinística por word_id) para que
# el audio de la palabra y el de sus 3 oraciones usen la misma voz, pero
# distintas palabras roten entre estas 5 para no aburrir con la misma voz.
VOICE_IDS = [
    "MI36FIkp9wRP7cpWKPTl",
    "lt7GBaCoAHWbT7JSZ5Xs",
    "4NQthjVhIGGVfL3Si000",
    "YxbjaPemDJV2xlfvkiIG",
    "APSIkVZudNbPAwyPoeVO",
]


def voice_id_for_word(word_id: int) -> str:
    return VOICE_IDS[word_id % len(VOICE_IDS)]


class AudioGenError(RuntimeError):
    pass


def _get_engine(engine_name: str, speed: str, voice_id: Optional[str]):
    if engine_name == "gtts":
        return GTTSEngine(lang="zh-CN", slow=(speed == "slow"))
    if engine_name == "elevenlabs":
        if not voice_id:
            raise ValueError("El motor 'elevenlabs' requiere voice_id")
        eleven_speed = 0.7 if speed == "slow" else 1.0
        return ElevenLabsEngine(voice_id=voice_id, speed=eleven_speed)
    raise ValueError(f"Motor TTS desconocido: {engine_name}")


def generate_tts_file(
    text: str,
    speed: str = "normal",
    prefix: str = "",
    engine_name: str = DEFAULT_ENGINE,
    voice_id: Optional[str] = None,
) -> Tuple[str, Optional[dict]]:
    """Genera (o reutiliza si ya existe) un audio para `text`.

    Devuelve (ruta_relativa, alineación). La alineación es un dict de
    ElevenLabs (characters + character_start/end_times_seconds) o None si
    el motor no la soporta (ej. gTTS).
    """
    text_hash = hashlib.md5(f"{text}|{speed}|{engine_name}|{voice_id or ''}".encode("utf-8")).hexdigest()[:10]
    filename = f"{prefix}{text_hash}_{speed}.mp3"
    output_path = AUDIO_DIR / filename
    alignment_path = AUDIO_DIR / f"{prefix}{text_hash}_{speed}.alignment.json"
    rel_path = f"resources/audios/{filename}"

    if output_path.exists():
        alignment = json.loads(alignment_path.read_text(encoding="utf-8")) if alignment_path.exists() else None
        return rel_path, alignment

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    engine = _get_engine(engine_name, speed, voice_id)

    if engine_name == "elevenlabs":
        alignment = engine.generate_audio_with_alignment(text, str(output_path))
        if alignment is None:
            raise AudioGenError(f"No se pudo generar audio (elevenlabs, {speed}) para: {text!r}")
        alignment_path.write_text(json.dumps(alignment, ensure_ascii=False), encoding="utf-8")
        return rel_path, alignment

    if not engine.generate_audio(text, str(output_path)):
        raise AudioGenError(f"No se pudo generar audio ({engine_name}, {speed}) para: {text!r}")
    return rel_path, None
