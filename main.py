#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChinoSRS - Main Orchestrator
Command-line interface for all ChinoSRS workflows.
"""

import argparse
import os
import sys
import subprocess

# Fix Windows console encoding
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


# ANSI color codes for pretty output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """Print a colored header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(60)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}\n")


def print_success(text):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text):
    """Print error message."""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_info(text):
    """Print info message."""
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")


def run_command(cmd, description):
    """Run a command and handle errors."""
    print_info(f"Running: {description}")
    print(f"{Colors.YELLOW}Command: {' '.join(cmd)}{Colors.END}\n")

    try:
        # PYTHONUTF8: sin esto, el proceso hijo en Windows detecta una consola
        # legacy (cp1252) y truena al imprimir hanzi (rich cae a un renderer
        # que no soporta esos caracteres).
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(cmd, check=True, env=env)
        print_success(f"Completed: {description}")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed: {description}")
        print_error(f"Error code: {e.returncode}")
        return False
    except FileNotFoundError:
        print_error(f"Command not found. Make sure Python is in your PATH.")
        return False


def get_python_cmd():
    """Get the appropriate Python command."""
    # Ruta absoluta: en Windows, subprocess.run() con una ruta relativa con
    # "/" a veces no la encuentra (WinError 2) según el shell que invoque esto.
    if os.path.exists("anki-venv/Scripts/python.exe"):
        return os.path.abspath("anki-venv/Scripts/python.exe")
    elif os.path.exists("anki-venv/bin/python"):
        return os.path.abspath("anki-venv/bin/python")
    else:
        return "python"


def workflow_dump_deck(args):
    """Dump Anki deck contents."""
    print_header("📋 Dump Anki Deck")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "src/utils/dump_deck.py"]

    if args.deck:
        cmd.extend(["--deck", args.deck])
    if args.output:
        cmd.extend(["--output", args.output])

    return run_command(cmd, "Anki deck dump")


def workflow_load(args):
    """Carga un JSON de vocabulario HSK (ej. resources/complete.json) en la base SQLite."""
    print_header("📥 Cargar vocabulario en SQLite")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "-m", "src.db.load_words", "--input", args.input, "--db", args.db, "--hsk-level", str(args.hsk_level)]

    return run_command(cmd, "Carga de vocabulario")


def workflow_generate(args):
    """Corre el pipeline LangGraph de generación sobre las palabras pendientes."""
    print_header("⚙️  Generar tarjetas (pipeline LangGraph)")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "-m", "src.generation.graph"]
    if args.limit is not None:
        cmd.extend(["--limit", str(args.limit)])

    return run_command(cmd, "Generación de tarjetas")


def workflow_export(args):
    """Exporta tarjetas 'ready' a Anki vía AnkiConnect."""
    print_header("📤 Exportar a Anki")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "-m", "src.anki.export", "--hsk-level", str(args.hsk_level)]
    if args.limit is not None:
        cmd.extend(["--limit", str(args.limit)])

    return run_command(cmd, "Exportación a Anki")


def workflow_flag_batch(args):
    """Importa tarjetas flageadas en Anki a review_status='flagged_bad'."""
    print_header("🚩 Importar flags de Anki")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "-m", "src.anki.review", "--flag", str(args.flag)]
    if args.notes:
        cmd.extend(["--notes", args.notes])

    return run_command(cmd, "Importación de flags")


def workflow_regenerate(args):
    """Regenera tarjetas puntuales (flaggeadas o fallidas)."""
    print_header("🔁 Regenerar tarjetas")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "-m", "src.generation.regenerate", "--hsk-level", str(args.hsk_level)]
    if args.flagged:
        cmd.append("--flagged")
    if args.word:
        cmd.extend(["--word", args.word])
    if args.type:
        cmd.extend(["--type", args.type])

    return run_command(cmd, "Regeneración de tarjetas")


def workflow_manual_card(args):
    """Guarda una tarjeta con una oración escrita a mano (desglose vía LLM, oración/traducción intactas)."""
    print_header("✍️  Tarjeta manual")

    python_cmd = get_python_cmd()
    cmd = [
        python_cmd, "-m", "src.generation.manual_card",
        "--word", args.word, "--type", args.type, "--zh", args.zh, "--es", args.es,
        "--hsk-level", str(args.hsk_level),
    ]

    return run_command(cmd, "Guardado de tarjeta manual")


def workflow_dashboard(args):
    """Muestra el estado de la DB: tarjetas por estado, fallos de guardrail, flaggeadas y audio huérfano."""
    print_header("📊 Dashboard de estado")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "-m", "src.utils.dashboard"]
    if args.hsk_level is not None:
        cmd.extend(["--hsk-level", str(args.hsk_level)])

    return run_command(cmd, "Dashboard")


def workflow_clean_audio(args):
    """Limpia archivos de audio huérfanos en resources/audios/."""
    print_header("🧹 Limpiar audio huérfano")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "-m", "src.utils.clean_audio"]
    if args.yes:
        cmd.append("--yes")

    return run_command(cmd, "Limpieza de audio")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ChinoSRS - Chinese SRS Card Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dump Anki deck
  python main.py dump --deck "Chino SRS" --output deck_backup.json

  # Cargar vocabulario HSK3 en la base SQLite
  python main.py load --input resources/complete.json

  # Correr el pipeline de generación (LangGraph + SQLite + ElevenLabs)
  python main.py generate
  python main.py generate --limit 10

  # Exportar tarjetas listas al mazo "ChinoSRS - HSK3" (AnkiConnect)
  python main.py export --hsk-level 3
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Dump deck
    dump_parser = subparsers.add_parser("dump", help="Dump Anki deck contents")
    dump_parser.add_argument("--deck", default="Chino SRS", help="Deck name")
    dump_parser.add_argument("--output", help="Output file")

    # Load vocabulary
    load_parser = subparsers.add_parser("load", help="Carga vocabulario HSK en la base SQLite")
    load_parser.add_argument("--input", "-i", default="resources/complete.json", help="Ruta al JSON de vocabulario")
    load_parser.add_argument("--db", default="outputs/chinosrs.db", help="Ruta a la base SQLite")
    load_parser.add_argument(
        "--hsk-level", type=int, default=3,
        help="Solo carga palabras de este nivel HSK (default: 3). --hsk-level 0 carga todo el JSON sin filtrar.",
    )

    # Generate cards
    generate_parser = subparsers.add_parser("generate", help="Corre el pipeline de generación (LangGraph)")
    generate_parser.add_argument("--limit", type=int, default=None, help="Máximo de palabras a procesar en esta corrida")

    # Export to Anki
    export_parser = subparsers.add_parser("export", help="Exporta tarjetas listas a Anki (AnkiConnect)")
    export_parser.add_argument("--hsk-level", type=int, default=3, help="Nivel HSK a exportar")
    export_parser.add_argument("--limit", type=int, default=None, help="Máximo de tarjetas a exportar en esta corrida")

    # Flag batch import
    flag_parser = subparsers.add_parser("flag-batch", help="Importa tarjetas flageadas en Anki (flag:N) a la DB")
    flag_parser.add_argument("--flag", type=int, required=True, choices=range(1, 8), help="Color de flag de Anki (1-7)")
    flag_parser.add_argument("--notes", default="", help="Nota de por qué se flaggearon")

    # Regenerate
    regen_parser = subparsers.add_parser("regenerate", help="Regenera tarjetas puntuales (flaggeadas o fallidas)")
    regen_parser.add_argument("--flagged", action="store_true", help="Regenera todo lo flaggeado/fallido de este nivel")
    regen_parser.add_argument("--word", help="Hanzi de una palabra puntual (junto con --type)")
    regen_parser.add_argument("--type", choices=["sentence", "pattern", "audio"], help="Tipo de tarjeta puntual")
    regen_parser.add_argument("--hsk-level", type=int, default=3)

    # Manual card
    manual_parser = subparsers.add_parser("manual-card", help="Guarda una tarjeta con una oración escrita a mano")
    manual_parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    manual_parser.add_argument("--type", required=True, choices=["sentence", "pattern", "audio"])
    manual_parser.add_argument("--zh", required=True, help="Oración en chino (ya aprobada)")
    manual_parser.add_argument("--es", required=True, help="Traducción al español (ya aprobada)")
    manual_parser.add_argument("--hsk-level", type=int, default=3)

    # Dashboard
    dashboard_parser = subparsers.add_parser("dashboard", help="Muestra el estado de la DB de generación")
    dashboard_parser.add_argument("--hsk-level", type=int, default=None, help="Filtrar por nivel HSK (default: todos)")

    # Clean audio
    clean_audio_parser = subparsers.add_parser("clean-audio", help="Limpia audio huérfano en resources/audios/")
    clean_audio_parser.add_argument("--yes", action="store_true", help="Borra de verdad (default: dry-run)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Print banner
    print(f"\n{Colors.BOLD}{Colors.HEADER}")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║           ChinoSRS - Orchestrator             ║")
    print("  ║      Chinese SRS Card Generator v1.0          ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print(f"{Colors.END}")

    # Execute the appropriate workflow
    success = False
    if args.command == "dump":
        success = workflow_dump_deck(args)
    elif args.command == "load":
        success = workflow_load(args)
    elif args.command == "generate":
        success = workflow_generate(args)
    elif args.command == "export":
        success = workflow_export(args)
    elif args.command == "flag-batch":
        success = workflow_flag_batch(args)
    elif args.command == "regenerate":
        success = workflow_regenerate(args)
    elif args.command == "manual-card":
        success = workflow_manual_card(args)
    elif args.command == "dashboard":
        success = workflow_dashboard(args)
    elif args.command == "clean-audio":
        success = workflow_clean_audio(args)

    # Exit with appropriate code
    if success:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ Operation completed successfully!{Colors.END}\n")
        sys.exit(0)
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}✗ Operation failed!{Colors.END}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
