"""
Validate audio files: check that all required audio files exist for CSV entries.
"""

import argparse
import csv
import sys
import codecs
import os
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Configure UTF-8 for Windows
if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())


def clean_pinyin_from_sentence(sentence: str) -> str:
    """Remove pinyin in parentheses from Chinese sentences."""
    if not sentence:
        return ""
    result = re.sub(r'\s*\([^)]*\)\s*', '', sentence)
    return result.strip()


def sanitize_filename(text: str) -> str:
    """Sanitize text for use in filename (same as generate_audio.py)."""
    # Remove or replace problematic characters
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'\s+', '_', text)
    return text[:50]  # Limit length


def calculate_hash(text: str) -> str:
    """Calculate MD5 hash for audio filename (first 8 characters)."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:8]


def get_expected_audio_files(row: Dict[str, str], audio_dir: str) -> List[Tuple[str, str, bool]]:
    """Get list of expected audio files for a CSV row.
    
    Returns:
        List of tuples: (audio_type, expected_path, exists)
    """
    hanzi = row.get("hanzi", "").strip()
    sentences_raw = row.get("example_sentence", "").strip()
    
    expected_files = []
    
    # Word audio
    if hanzi:
        word_hash = calculate_hash(hanzi)
        # Use sanitize_filename to match generate_audio.py
        word_filename = f"word_{sanitize_filename(hanzi)}_{word_hash}.mp3"
        word_path = os.path.join(audio_dir, word_filename)
        exists = os.path.exists(word_path)
        expected_files.append(("word", word_path, exists))
    
    # Sentence audios
    if sentences_raw:
        sentences = [s.strip() for s in sentences_raw.split("|") if s.strip()]
        for i, sentence in enumerate(sentences, 1):
            # Clean pinyin before calculating hash
            clean_sentence = clean_pinyin_from_sentence(sentence)
            if clean_sentence:
                sentence_hash = calculate_hash(clean_sentence)
                # Use first 30 chars and sanitize to match generate_audio.py
                sentence_filename = f"{sanitize_filename(clean_sentence[:30])}_{sentence_hash}.mp3"
                sentence_path = os.path.join(audio_dir, sentence_filename)
                exists = os.path.exists(sentence_path)
                expected_files.append((f"sentence[{i}]", sentence_path, exists))
    
    return expected_files


def validate_audio(csv_path: str, audio_dir: str) -> Tuple[int, int, List[Dict]]:
    """Validate audio files for all CSV entries.
    
    Returns:
        Tuple of (total_files_expected, missing_files, missing_details)
    """
    total_expected = 0
    missing_count = 0
    missing_details = []
    
    # Track unique audio files to avoid counting duplicates
    seen_files = set()
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row_num, row in enumerate(reader, start=2):
            hanzi = row.get("hanzi", "").strip()
            expected_files = get_expected_audio_files(row, audio_dir)
            
            for audio_type, audio_path, exists in expected_files:
                # Only count unique files (same sentence may appear in multiple entries)
                if audio_path not in seen_files:
                    seen_files.add(audio_path)
                    total_expected += 1
                    if not exists:
                        missing_count += 1
                        missing_details.append({
                            "row": row_num,
                            "hanzi": hanzi,
                            "type": audio_type,
                            "path": audio_path
                        })
    
    return total_expected, missing_count, missing_details


def main():
    parser = argparse.ArgumentParser(
        description="Validate that all required audio files exist"
    )
    parser.add_argument(
        "csv_file",
        help="Path to CSV file"
    )
    parser.add_argument(
        "--audio-dir",
        default="resources/audios",
        help="Directory containing audio files (default: resources/audios)"
    )
    parser.add_argument(
        "--show-missing",
        action="store_true",
        help="Show list of missing audio files"
    )
    parser.add_argument(
        "--export-missing",
        metavar="OUTPUT_FILE",
        help="Export list of missing files to text file"
    )
    
    args = parser.parse_args()
    
    # Validate files exist
    if not Path(args.csv_file).exists():
        print(f"Error: CSV file not found: {args.csv_file}")
        sys.exit(1)
    
    if not Path(args.audio_dir).exists():
        print(f"Error: Audio directory not found: {args.audio_dir}")
        sys.exit(1)
    
    print(f"Validating audio files for: {args.csv_file}")
    print(f"Audio directory: {args.audio_dir}")
    print()
    
    # Run validation
    total_expected, missing_count, missing_details = validate_audio(
        args.csv_file, args.audio_dir
    )
    
    # Print results
    print("=" * 80)
    print("AUDIO VALIDATION RESULTS")
    print("=" * 80)
    print(f"Total audio files expected:  {total_expected}")
    print(f"Missing audio files:         {missing_count}")
    print(f"Coverage:                    {((total_expected - missing_count) / total_expected * 100):.2f}%")
    print("=" * 80)
    
    if missing_count > 0:
        print()
        print(f"WARNING: {missing_count} audio files are missing!")
        
        if args.show_missing:
            print()
            print("MISSING AUDIO FILES:")
            print("-" * 80)
            for detail in missing_details:
                print(f"  Row {detail['row']} ({detail['hanzi']}) - {detail['type']}")
                print(f"    Expected: {detail['path']}")
        
        if args.export_missing:
            with open(args.export_missing, 'w', encoding='utf-8') as f:
                f.write("Missing Audio Files Report\n")
                f.write("=" * 80 + "\n\n")
                for detail in missing_details:
                    f.write(f"Row {detail['row']} ({detail['hanzi']}) - {detail['type']}\n")
                    f.write(f"  Expected: {detail['path']}\n\n")
            print()
            print(f"✅ OK: Missing files list exported to: {args.export_missing}")
    else:
        print()
        print("✅ OK: All audio files are present!")
    
    # Always exit with success - finding missing files is expected behavior
    sys.exit(0)


if __name__ == "__main__":
    main()
