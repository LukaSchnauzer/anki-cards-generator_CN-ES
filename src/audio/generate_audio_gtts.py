"""
Script para generar audios usando Google TTS (gTTS) para las tarjetas de Anki.
Genera audios en chino mandarín a partir de frases en hanzi.
"""

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from gtts import gTTS

# Configuración
AUDIO_DIR = "resources/audios"  # Directorio de salida
LANG = "zh-CN"  # Chino mandarín

# Asegurar que el directorio existe
os.makedirs(AUDIO_DIR, exist_ok=True)


def sanitize_filename(text: str) -> str:
    """Convierte texto a nombre de archivo seguro."""
    # Reemplazar caracteres problemáticos
    safe = text.replace(" ", "_").replace("/", "_").replace("\\", "_")
    safe = safe.replace(":", "_").replace("?", "_").replace("*", "_")
    safe = safe.replace("|", "_").replace("<", "_").replace(">", "_")
    safe = safe.replace('"', "_").replace("'", "_")
    return safe[:100]  # Limitar longitud


def generate_audio(text: str, output_path: str, lang: str = LANG, slow: bool = False):
    """
    Genera un archivo de audio MP3 usando Google TTS.
    
    Args:
        text: Texto a convertir en audio (hanzi)
        output_path: Ruta completa del archivo de salida
        lang: Código de idioma
        slow: Si True, habla más despacio (útil para aprendizaje)
    
    Returns:
        True si se generó correctamente, False en caso de error
    """
    try:
        # Usar servidor normal de Google (más confiable)
        tts = gTTS(text=text, lang=lang, slow=slow)
        tts.save(output_path)
        
        # Verificar que el archivo tiene contenido
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True
        else:
            return False
    except Exception as e:
        print(f"  ERROR al generar audio: {e}")
        return False


def process_csv_row(row: dict, row_num: int):
    """
    Procesa una fila del CSV y genera audios para todas las frases de ejemplo.
    
    Genera:
    - Audio para cada frase de ejemplo (pueden ser múltiples separadas por |)
    """
    hanzi = row.get("hanzi", "").strip()
    sentence_cn = row.get("example_sentence", "").strip()
    
    if not sentence_cn:
        print(f"Fila {row_num} ({hanzi}): Sin frase de ejemplo, saltando...")
        return []
    
    # Separar múltiples frases por |
    sentences = [s.strip() for s in sentence_cn.split("|") if s.strip()]
    
    generated_files = []
    
    for idx, sentence in enumerate(sentences, start=1):
        # Nombre del archivo basado en la frase (hash para evitar nombres muy largos)
        import hashlib
        sentence_hash = hashlib.md5(sentence.encode('utf-8')).hexdigest()[:8]
        filename = f"{sanitize_filename(sentence[:30])}_{sentence_hash}.mp3"
        output_path = os.path.join(AUDIO_DIR, filename)
        
        # Si ya existe, saltar
        if os.path.exists(output_path):
            print(f"Fila {row_num} ({hanzi}) [{idx}/{len(sentences)}]: Audio ya existe")
            generated_files.append(filename)
            continue
        
        print(f"Fila {row_num} ({hanzi}) [{idx}/{len(sentences)}]: Generando '{sentence[:30]}...'")
        
        if generate_audio(sentence, output_path):
            print(f"  -> Guardado: {filename}")
            generated_files.append(filename)
        else:
            print(f"  -> ERROR al generar")
    
    return generated_files


def main(csv_path):
    """Función principal."""
    if not os.path.exists(csv_path):
        print(f"Error: No se encuentra el archivo CSV: {csv_path}")
        return
    
    print(f"Leyendo CSV: {csv_path}")
    print(f"Directorio de audios: {AUDIO_DIR}")
    print(f"Idioma: {LANG}")
    print("-" * 60)
    
    # Leer CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Total de filas: {len(rows)}")
    print("-" * 60)
    
    # Procesar cada fila
    total_generated = 0
    total_files = 0
    
    for i, row in enumerate(rows, start=1):
        files = process_csv_row(row, i)
        if files:
            total_generated += len(files)
            total_files += len(files)
        
        # Pequeña pausa para no saturar la API
        time.sleep(0.5)
    
    print("-" * 60)
    print(f"Resumen:")
    print(f"  Total de audios generados: {total_generated}")
    print(f"  Total de entradas procesadas: {len(rows)}")
    print(f"  Promedio de audios por entrada: {total_generated / len(rows) if rows else 0:.1f}")


if __name__ == "__main__":
    # Configurar encoding para Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
    
    # Parse argumentos
    parser = argparse.ArgumentParser(description="Generar audios con Google TTS")
    parser.add_argument("--csv", required=True, help="Ruta al archivo CSV")
    args = parser.parse_args()
    
    # Ejecutar
    main(args.csv)
