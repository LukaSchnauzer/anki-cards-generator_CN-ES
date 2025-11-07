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
from pathlib import Path

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
        result = subprocess.run(cmd, check=True)
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
    if os.path.exists("anki-venv/Scripts/python.exe"):
        return "anki-venv/Scripts/python.exe"
    elif os.path.exists("anki-venv/bin/python"):
        return "anki-venv/bin/python"
    else:
        return "python"


def workflow_generate_vocab(args):
    """Workflow 1: Generate vocabulary CSV with AI enrichment."""
    print_header("📚 Generate Vocabulary CSV")
    
    python_cmd = get_python_cmd()
    cmd = [python_cmd, "src/generate_vocab_csv.py"]
    
    if args.input:
        cmd.extend(["--input", args.input])
    if args.output:
        cmd.extend(["--output", args.output])
    if args.limit:
        cmd.extend(["--max-items", str(args.limit)])
    
    return run_command(cmd, "Vocabulary generation with AI enrichment")


def workflow_generate_audio(args):
    """Workflow 2: Generate audio files from CSV."""
    print_header("🔊 Generate Audio Files")
    
    if not args.csv:
        print_error("CSV file is required. Use --csv <path>")
        return False
    
    if not os.path.exists(args.csv):
        print_error(f"CSV file not found: {args.csv}")
        return False
    
    python_cmd = get_python_cmd()
    
    # Determine engine name for display
    engine_name = "Google TTS" if args.engine == "gtts" else "Azure TTS"
    
    # Run audio generation
    cmd = [python_cmd, "src/audio/generate_audio.py", "--csv", args.csv, "--engine", args.engine]
    print_info(f"Using CSV: {args.csv}")
    print_info(f"Engine: {engine_name}")
    
    return run_command(cmd, f"Audio generation with {engine_name}")


def workflow_create_anki_deck(args):
    """Workflow 3: Create Anki deck from CSV."""
    print_header("🎴 Create Anki Deck")
    
    if not args.csv:
        print_error("CSV file is required. Use --csv <path>")
        return False
    
    if not os.path.exists(args.csv):
        print_error(f"CSV file not found: {args.csv}")
        return False
    
    python_cmd = get_python_cmd()
    cmd = [python_cmd, "src/csv_to_anki.py", args.csv]
    
    if args.limit:
        cmd.extend(["--limit", str(args.limit)])
    if args.force_recreate:
        cmd.append("--force-recreate")
    
    return run_command(cmd, "Anki deck creation")


def workflow_dump_deck(args):
    """Workflow 4: Dump Anki deck contents."""
    print_header("📋 Dump Anki Deck")
    
    python_cmd = get_python_cmd()
    cmd = [python_cmd, "src/utils/dump_deck.py"]
    
    if args.deck:
        cmd.extend(["--deck", args.deck])
    if args.output:
        cmd.extend(["--output", args.output])
    
    return run_command(cmd, "Anki deck dump")




def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ChinoSRS - Chinese SRS Card Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate vocabulary CSV
  python main.py vocab --input data/words.json --output outputs/vocab.csv
  
  # Generate audio with Google TTS
  python main.py audio --engine gtts
  
  # Generate audio with both engines
  python main.py audio --engine both
  
  # Create Anki deck
  python main.py anki --csv outputs/vocab.csv --limit 10
  
  # Dump Anki deck
  python main.py dump --deck "Chino SRS" --output deck_backup.json
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Vocab generation
    vocab_parser = subparsers.add_parser("vocab", help="Generate vocabulary CSV with AI enrichment")
    vocab_parser.add_argument("--input", help="Input JSON file")
    vocab_parser.add_argument("--output", help="Output CSV file")
    vocab_parser.add_argument("--limit", type=int, help="Limit number of entries")
    
    # Audio generation
    audio_parser = subparsers.add_parser("audio", help="Generate audio files")
    audio_parser.add_argument("--engine", choices=["gtts", "azure"], default="gtts",
                             help="TTS engine to use (default: gtts)")
    audio_parser.add_argument("--csv", required=True, help="CSV file to process")
    
    # Anki deck creation
    anki_parser = subparsers.add_parser("anki", help="Create Anki deck from CSV")
    anki_parser.add_argument("--csv", required=True, help="Input CSV file")
    anki_parser.add_argument("--limit", type=int, help="Limit number of entries")
    anki_parser.add_argument("--force-recreate", action="store_true",
                            help="Force recreate card models")
    
    # Dump deck
    dump_parser = subparsers.add_parser("dump", help="Dump Anki deck contents")
    dump_parser.add_argument("--deck", default="Chino SRS", help="Deck name")
    dump_parser.add_argument("--output", help="Output file")
    
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
    if args.command == "vocab":
        success = workflow_generate_vocab(args)
    elif args.command == "audio":
        success = workflow_generate_audio(args)
    elif args.command == "anki":
        success = workflow_create_anki_deck(args)
    elif args.command == "dump":
        success = workflow_dump_deck(args)
    
    # Exit with appropriate code
    if success:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ Operation completed successfully!{Colors.END}\n")
        sys.exit(0)
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}✗ Operation failed!{Colors.END}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
