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
    except KeyboardInterrupt:
        # En Windows, Ctrl+C manda CTRL_C_EVENT a TODO el grupo de procesos —
        # llega al hijo (que ya debería estar parando solo, con su propio
        # resumen) Y al padre, que estaba bloqueado en subprocess.run().wait().
        # Sin este except, ese wait() interrumpido tira un traceback crudo acá
        # mismo en main.py — este mensaje es lo único que se ve en cambio.
        print_error(f"Interrupted: {description}")
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


def workflow_manual_card_batch(args):
    """Guarda en lote tarjetas manuales definidas en un archivo JSON (word/type/zh/es)."""
    print_header("✍️  Tarjetas manuales (lote)")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "-m", "src.generation.manual_card_batch", "--file", args.file, "--hsk-level", str(args.hsk_level)]

    return run_command(cmd, "Guardado de tarjetas manuales en lote")


def workflow_swap_primary(args):
    """Cambia cuál lectura de una palabra es la primaria."""
    print_header("🔀 Cambiar lectura primaria")

    python_cmd = get_python_cmd()
    cmd = [
        python_cmd, "-m", "src.generation.swap_reading",
        "--word", args.word, "--meaning", args.meaning, "--hsk-level", str(args.hsk_level),
    ]
    if args.regenerate:
        cmd.append("--regenerate")

    return run_command(cmd, "Cambio de lectura primaria")


def workflow_add_reading(args):
    """Agrega una lectura nueva a una palabra (para sentidos que word_prep nunca detectó)."""
    print_header("➕ Agregar lectura")

    python_cmd = get_python_cmd()
    cmd = [
        python_cmd, "-m", "src.generation.add_reading",
        "--word", args.word, "--pinyin", args.pinyin, "--meaning-es", args.meaning_es,
        "--hsk-level", str(args.hsk_level),
    ]
    if args.meaning_zh:
        cmd.extend(["--meaning-zh", args.meaning_zh])
    if args.register:
        cmd.extend(["--register", args.register])
    if args.secondary:
        cmd.append("--secondary")
    if args.regenerate:
        cmd.append("--regenerate")

    return run_command(cmd, "Agregar lectura")


def workflow_edit_reading(args):
    """Corrige el texto (pinyin/significado) de una lectura ya registrada."""
    print_header("✏️  Corregir lectura")

    python_cmd = get_python_cmd()
    cmd = [
        python_cmd, "-m", "src.generation.edit_reading",
        "--word", args.word, "--meaning-query", args.meaning_query, "--hsk-level", str(args.hsk_level),
    ]
    if args.new_meaning_es:
        cmd.extend(["--new-meaning-es", args.new_meaning_es])
    if args.new_meaning_zh:
        cmd.extend(["--new-meaning-zh", args.new_meaning_zh])
    if args.new_pinyin:
        cmd.extend(["--new-pinyin", args.new_pinyin])
    if args.new_register:
        cmd.extend(["--new-register", args.new_register])

    return run_command(cmd, "Corrección de lectura")


def workflow_unflag(args):
    """Quita el flag de review de una tarjeta sin tocar su contenido (falsos positivos del audit)."""
    print_header("🚩 Desflaggear tarjeta")

    python_cmd = get_python_cmd()
    cmd = [
        python_cmd, "-m", "src.generation.unflag_card",
        "--word", args.word, "--type", args.type, "--hsk-level", str(args.hsk_level),
    ]

    return run_command(cmd, "Desflaggeo de tarjeta")


def workflow_audit_naturalness(args):
    """Audita tarjetas ready/llm de palabras de 1 carácter buscando el patrón 'carácter usado como verbo/sustantivo genérico' (ej. 报/保 sin su compuesto real)."""
    print_header("🔎 Auditar naturalidad")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "-m", "src.generation.audit_naturalness"]
    if args.hsk_level is not None:
        cmd.extend(["--hsk-level", str(args.hsk_level)])
    if args.batch_size:
        cmd.extend(["--batch-size", str(args.batch_size)])

    return run_command(cmd, "Auditoría de naturalidad")


def workflow_inspect_word(args):
    """Muestra lecturas, tarjetas y últimos intentos de una palabra."""
    print_header("🔍 Inspeccionar palabra")

    python_cmd = get_python_cmd()
    cmd = [python_cmd, "-m", "src.utils.inspect_word", "--word", args.word, "--hsk-level", str(args.hsk_level)]

    return run_command(cmd, "Inspección de palabra")


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

    # Manual card batch
    manual_batch_parser = subparsers.add_parser("manual-card-batch", help="Guarda en lote tarjetas manuales definidas en un archivo JSON")
    manual_batch_parser.add_argument("--file", required=True, help="Ruta al JSON con la lista de tarjetas (word/type/zh/es)")
    manual_batch_parser.add_argument("--hsk-level", type=int, default=3)

    # Swap primary reading
    swap_parser = subparsers.add_parser("swap-primary", help="Cambia cuál lectura de una palabra es la primaria")
    swap_parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    swap_parser.add_argument("--meaning", required=True, help="Texto (parcial) del meaning_es de la lectura que debe ser primaria")
    swap_parser.add_argument("--hsk-level", type=int, default=3)
    swap_parser.add_argument("--regenerate", action="store_true", help="Regenera las 3 tarjetas de una vez con la nueva lectura primaria")

    # Add reading
    add_reading_parser = subparsers.add_parser("add-reading", help="Agrega una lectura nueva a una palabra")
    add_reading_parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    add_reading_parser.add_argument("--pinyin", required=True, help="Pinyin de la lectura nueva")
    add_reading_parser.add_argument("--meaning-es", required=True, help="Significado en español")
    add_reading_parser.add_argument("--meaning-zh", default=None, help="Definición en chino (opcional)")
    add_reading_parser.add_argument("--register", default=None, help="reg:colloquial | reg:neutral | reg:formal | reg:literary (opcional)")
    add_reading_parser.add_argument("--secondary", action="store_true", help="Agrega como secundaria en vez de primaria (default: primaria)")
    add_reading_parser.add_argument("--hsk-level", type=int, default=3)
    add_reading_parser.add_argument("--regenerate", action="store_true", help="Regenera las 3 tarjetas de una vez con la lectura nueva")

    # Edit reading
    edit_reading_parser = subparsers.add_parser("edit-reading", help="Corrige el texto de una lectura ya registrada")
    edit_reading_parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    edit_reading_parser.add_argument("--meaning-query", required=True, help="Texto (parcial) del meaning_es actual de la lectura a corregir")
    edit_reading_parser.add_argument("--new-meaning-es", default=None)
    edit_reading_parser.add_argument("--new-meaning-zh", default=None)
    edit_reading_parser.add_argument("--new-pinyin", default=None)
    edit_reading_parser.add_argument("--new-register", default=None)
    edit_reading_parser.add_argument("--hsk-level", type=int, default=3)

    # Unflag
    unflag_parser = subparsers.add_parser("unflag", help="Quita el flag de review de una tarjeta sin tocar su contenido")
    unflag_parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    unflag_parser.add_argument("--type", required=True, choices=["sentence", "pattern", "audio"])
    unflag_parser.add_argument("--hsk-level", type=int, default=3)

    # Audit naturalness
    audit_parser = subparsers.add_parser("audit-naturalness", help="Audita tarjetas de palabras de 1 carácter buscando usos forzados (patrón 报/保)")
    audit_parser.add_argument("--hsk-level", type=int, default=None, help="Filtra por nivel HSK (default: todos)")
    audit_parser.add_argument("--batch-size", type=int, default=15)

    # Inspect word
    inspect_parser = subparsers.add_parser("inspect-word", help="Muestra lecturas, tarjetas y últimos intentos de una palabra")
    inspect_parser.add_argument("--word", required=True, help="Hanzi de la palabra")
    inspect_parser.add_argument("--hsk-level", type=int, default=3, help="--hsk-level 0 para no filtrar por nivel")

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
    elif args.command == "manual-card-batch":
        success = workflow_manual_card_batch(args)
    elif args.command == "swap-primary":
        success = workflow_swap_primary(args)
    elif args.command == "add-reading":
        success = workflow_add_reading(args)
    elif args.command == "edit-reading":
        success = workflow_edit_reading(args)
    elif args.command == "unflag":
        success = workflow_unflag(args)
    elif args.command == "inspect-word":
        success = workflow_inspect_word(args)
    elif args.command == "audit-naturalness":
        success = workflow_audit_naturalness(args)
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
