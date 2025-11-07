"""
Unified audio generation script for ChinoSRS.
Supports multiple TTS engines: Google TTS (gTTS) and Microsoft Edge TTS.
"""

import argparse
import csv
import hashlib
import os
import re
import sys
import time
from typing import Optional

# Configure UTF-8 encoding for Windows
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

# Import TTS engines
from engines.gtts_engine import GTTSEngine
from engines.azure_engine import AzureTTSEngine

# Add parent directory to path to import from anki module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from anki.hints import clean_pinyin_from_sentence


# Configuración
AUDIO_DIR = "resources/audios"  # Directorio de salida


def sanitize_filename(text: str) -> str:
    """Sanitize text for use in filename."""
    # Remove or replace problematic characters
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'\s+', '_', text)
    return text[:50]  # Limit length


def get_tts_engine(engine_name: str):
    """Get TTS engine instance by name.
    
    Args:
        engine_name: Name of the engine ('gtts' or 'azure')
        
    Returns:
        TTS engine instance
        
    Raises:
        ValueError: If engine name is invalid or unavailable
    """
    if engine_name == "gtts":
        engine = GTTSEngine(lang="zh-CN")
        if not engine.is_available():
            raise ValueError("Google TTS is not available. Install with: pip install gtts")
        return engine
    elif engine_name == "azure":
        # Get speed and random voice settings from environment or defaults
        speed = float(os.getenv("AZURE_TTS_SPEED", "1.0"))
        random_voice = os.getenv("AZURE_TTS_RANDOM_VOICE", "false").lower() == "true"
        
        engine = AzureTTSEngine(speed=speed, random_voice=random_voice)
        if not engine.is_available():
            raise ValueError(
                "Azure TTS requires AZURE_TTS_KEY in .env file.\n"
                "Get your key from: https://portal.azure.com\n"
                "See docs/AZURE_TTS_SETUP.md for setup instructions."
            )
        
        print("  ℹ️  Usando Azure TTS (API oficial de Microsoft)")
        if random_voice:
            print(f"  🎭 Voces aleatorias activadas ({len(AzureTTSEngine.CHINESE_VOICES)} voces disponibles)")
        if speed != 1.0:
            print(f"  ⚡ Velocidad: {speed}x")
        
        return engine
    else:
        raise ValueError(f"Unknown engine: {engine_name}. Use 'gtts' or 'azure'")


def process_csv_row(row: dict, row_num: int, engine, audio_dir: str):
    """
    Process a CSV row and generate audio files for the word and example sentences.
    
    Generates:
    - Audio for the word alone (hanzi)
    - Audio for each example sentence (can be multiple separated by |)
    
    Args:
        row: CSV row dictionary
        row_num: Row number for logging
        engine: TTS engine instance
        audio_dir: Directory to save audio files
        
    Returns:
        List of generated filenames
    """
    hanzi = row.get("hanzi", "").strip()
    sentence_cn = row.get("example_sentence", "").strip()
    
    # Clean pinyin from sentences to match CSV processing
    sentence_cn = clean_pinyin_from_sentence(sentence_cn)
    
    generated_files = []
    
    # 1. Generate audio for the word alone
    if hanzi:
        word_hash = hashlib.md5(hanzi.encode('utf-8')).hexdigest()[:8]
        word_filename = f"word_{sanitize_filename(hanzi)}_{word_hash}.mp3"
        word_output_path = os.path.join(audio_dir, word_filename)
        
        if os.path.exists(word_output_path):
            print(f"Fila {row_num} ({hanzi}) [WORD]: Audio ya existe")
            generated_files.append(word_filename)
        else:
            print(f"Fila {row_num} ({hanzi}) [WORD]: Generando audio de palabra...")
            if engine.generate_audio(hanzi, word_output_path):
                print(f"  -> Guardado: {word_filename}")
                generated_files.append(word_filename)
            else:
                print(f"  -> ERROR al generar audio de palabra")
    
    # 2. Generate audio for example sentences
    if not sentence_cn:
        print(f"Fila {row_num} ({hanzi}): Sin frase de ejemplo, solo palabra generada")
        return generated_files
    
    # Separate multiple sentences by | and clean pinyin from each
    sentences = [clean_pinyin_from_sentence(s.strip()) for s in sentence_cn.split("|") if s.strip()]
    
    for idx, sentence in enumerate(sentences, start=1):
        # Filename based on sentence (hash to avoid very long names)
        sentence_hash = hashlib.md5(sentence.encode('utf-8')).hexdigest()[:8]
        filename = f"{sanitize_filename(sentence[:30])}_{sentence_hash}.mp3"
        output_path = os.path.join(audio_dir, filename)
        
        # Skip if already exists
        if os.path.exists(output_path):
            print(f"Fila {row_num} ({hanzi}) [{idx}/{len(sentences)}]: Audio ya existe")
            generated_files.append(filename)
            continue
        
        print(f"Fila {row_num} ({hanzi}) [{idx}/{len(sentences)}]: Generando '{sentence[:30]}...'")
        
        if engine.generate_audio(sentence, output_path):
            print(f"  -> Guardado: {filename}")
            generated_files.append(filename)
        else:
            print(f"  -> ERROR al generar")
    
    return generated_files


def main():
    """Main function."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Generar audios con TTS (Google o Azure)")
    parser.add_argument("--csv", required=True, help="Ruta al archivo CSV")
    parser.add_argument("--engine", choices=["gtts", "azure"], default="gtts",
                       help="Motor TTS a usar (default: gtts)")
    parser.add_argument("--audio-dir", default=AUDIO_DIR,
                       help=f"Directorio de salida de audio (default: {AUDIO_DIR})")
    args = parser.parse_args()
    
    csv_path = args.csv
    audio_dir = args.audio_dir
    
    if not os.path.exists(csv_path):
        print(f"Error: No se encuentra el archivo CSV: {csv_path}")
        return 1
    
    # Initialize TTS engine
    try:
        engine = get_tts_engine(args.engine)
        print(f"Motor TTS: {engine.name}")
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    
    print(f"Leyendo CSV: {csv_path}")
    print(f"Directorio de audios: {audio_dir}")
    print("-" * 60)
    
    # Ensure audio directory exists
    os.makedirs(audio_dir, exist_ok=True)
    
    # Read CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Total de filas: {len(rows)}")
    print("-" * 60)
    
    # Process each row with progress tracking
    total_generated = 0
    total_rows = len(rows)
    start_time = time.time()
    
    for i, row in enumerate(rows, start=1):
        row_start = time.time()
        files = process_csv_row(row, i, engine, audio_dir)
        total_generated += len(files)
        
        # Progress tracking
        elapsed = time.time() - start_time
        progress_pct = (i / total_rows) * 100
        
        if i > 0:
            avg_time_per_row = elapsed / i
            remaining_rows = total_rows - i
            eta_seconds = avg_time_per_row * remaining_rows
            eta_minutes = eta_seconds / 60
            
            # Print progress every 5 rows or at the end
            if i % 5 == 0 or i == total_rows:
                print(f"\n📊 Progreso: {i}/{total_rows} ({progress_pct:.1f}%) | "
                      f"Tiempo: {elapsed/60:.1f}min | "
                      f"ETA: {eta_minutes:.1f}min | "
                      f"Audios: {total_generated}")
                sys.stdout.flush()
    
    # Final summary
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("✅ Resumen Final:")
    print(f"  Total de audios generados: {total_generated}")
    print(f"  Total de entradas procesadas: {len(rows)}")
    if len(rows) > 0:
        print(f"  Promedio de audios por entrada: {total_generated / len(rows):.1f}")
    print(f"  Tiempo total: {total_time/60:.2f} minutos")
    print(f"  Velocidad: {len(rows)/(total_time/60):.1f} entradas/min")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
