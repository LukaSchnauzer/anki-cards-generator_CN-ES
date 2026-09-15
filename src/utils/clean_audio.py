"""Borra archivos de audio en resources/audios/ que ya nadie referencia en
audio_files (quedan huérfanos cuando regenerate_card reemplaza un
card_example: el cascade borra la fila de audio_files, pero el .mp3/.json
físico se queda en disco). Por defecto es dry-run — hay que pasar --yes
para borrar de verdad."""

import argparse

from src.utils.dashboard import clean_orphaned_audio


def main() -> None:
    parser = argparse.ArgumentParser(description="Limpia audio huérfano en resources/audios/")
    parser.add_argument("--yes", action="store_true", help="Borra de verdad (sin esto, solo muestra qué se borraría)")
    args = parser.parse_args()

    result = clean_orphaned_audio(dry_run=not args.yes)
    action = "Borrados" if result["deleted"] else "Se borrarían"
    size_mb = result["total_size_bytes"] / (1024 * 1024)
    print(f"{action}: {result['count']} archivo(s), {size_mb:.1f} MB")
    for f in result["files"]:
        print(f"  - {f}")
    if not result["deleted"] and result["count"]:
        print("\n(dry-run — corre con --yes para borrarlos de verdad)")


if __name__ == "__main__":
    main()
