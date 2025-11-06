"""
Script para generar audios usando Edge-TTS para las tarjetas de Anki.
Genera audios en chino mandarín a partir de frases en pinyin o hanzi.
"""

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path
import edge_tts

# Configuración
AUDIO_DIR = "resources/audios"  # Directorio de salida

# Voces disponibles (probar diferentes si una falla)
VOICES = [
    "zh-CN-XiaoxiaoNeural",  # Voz femenina china (natural y clara)
    "zh-CN-YunxiNeural",     # Voz masculina
    "zh-CN-YunyangNeural",   # Voz masculina profesional
    "zh-CN-XiaoyiNeural",    # Voz femenina alternativa
]
VOICE = VOICES[0]  # Usar la primera por defecto

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


async def generate_audio(text: str, output_path: str, voice: str = VOICE):
    """
    Genera un archivo de audio MP3 usando Edge-TTS.
    
    Args:
        text: Texto a convertir en audio (puede ser hanzi o pinyin)
        output_path: Ruta completa del archivo de salida
        voice: Voz de Edge-TTS a usar
    
    Returns:
        True si se generó correctamente, False en caso de error
    """
    try:
        # Método más simple y directo
        communicate = edge_tts.Communicate(text, voice, rate="+0%", volume="+0%")
        await communicate.save(output_path)
        
        # Verificar que el archivo se creó y tiene contenido
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True
        else:
            return False
    except Exception as e:
        print(f"  ERROR Edge-TTS: {e}")
        return False


async def process_csv_row(row: dict, row_num: int):
    """
    Procesa una fila del CSV y genera el audio correspondiente.
    
    Para esta primera versión, generamos:
    - Audio de la frase completa en chino (sentence_cn)
    """
    hanzi = row.get("hanzi", "").strip()
    sentence_cn = row.get("example_sentence", "").strip()
    
    if not sentence_cn:
        print(f"Fila {row_num}: Sin frase de ejemplo, saltando...")
        return None
    
    # Extraer solo la primera frase (antes del primer |)
    if "|" in sentence_cn:
        sentence_cn = sentence_cn.split("|")[0].strip()
    
    # Nombre del archivo: hanzi_sentence.mp3
    filename = f"{sanitize_filename(hanzi)}_sentence.mp3"
    output_path = os.path.join(AUDIO_DIR, filename)
    
    # Si ya existe, saltar
    if os.path.exists(output_path):
        print(f"Fila {row_num} ({hanzi}): Audio ya existe, saltando...")
        return filename
    
    print(f"Fila {row_num} ({hanzi}): Generando audio para '{sentence_cn[:30]}...'")
    success = await generate_audio(sentence_cn, output_path)
    
    if success:
        print(f"  -> Guardado: {filename}")
        return filename
    else:
        print(f"Fila {row_num} ({hanzi}): ERROR - No se pudo generar el audio")
        # Limpiar archivo corrupto si existe
        if os.path.exists(output_path):
            os.remove(output_path)
        return None


async def main(csv_path):
    """Función principal."""
    
    if not os.path.exists(csv_path):
        print(f"Error: No se encuentra el archivo CSV: {csv_path}")
        return
    
    print(f"Leyendo CSV: {csv_path}")
    print(f"Directorio de audios: {AUDIO_DIR}")
    print(f"Voz: {VOICE}")
    print("-" * 60)
    
    # Leer CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Total de filas: {len(rows)}")
    print("-" * 60)
    
    # Procesar cada fila
    generated = 0
    skipped = 0
    errors = 0
    
    for i, row in enumerate(rows, start=1):
        result = await process_csv_row(row, i)
        if result:
            generated += 1
        elif result is None and row.get("example_sentence", "").strip():
            errors += 1
        else:
            skipped += 1
        
        # Pequeña pausa para no saturar
        await asyncio.sleep(0.1)
    
    print("-" * 60)
    print(f"Resumen:")
    print(f"  Generados: {generated}")
    print(f"  Ya existían: {skipped}")
    print(f"  Errores: {errors}")
    print(f"  Total: {len(rows)}")


if __name__ == "__main__":
    # Configurar encoding para Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
    
    # Parse argumentos
    parser = argparse.ArgumentParser(description="Generar audios con Microsoft Edge TTS")
    parser.add_argument("--csv", required=True, help="Ruta al archivo CSV")
    args = parser.parse_args()
    
    # Ejecutar
    asyncio.run(main(args.csv))
