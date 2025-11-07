"""
Validate coverage: check which JSON entries were not generated in CSV.
"""

import argparse
import csv
import json
import sys
import codecs
from pathlib import Path

# Configure UTF-8 for Windows
if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())


def load_json_entries(json_path: str) -> set:
    """Load hanzi entries from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract hanzi from each entry (try both 'hanzi' and 'simplified' keys)
    hanzi_set = set()
    for entry in data:
        hanzi = entry.get('hanzi', entry.get('simplified', '')).strip()
        if hanzi:
            hanzi_set.add(hanzi)
    
    return hanzi_set


def load_csv_entries(csv_path: str) -> set:
    """Load hanzi entries from CSV file."""
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        hanzi_set = set()
        for row in reader:
            hanzi = row.get('hanzi', '').strip()
            if hanzi:
                hanzi_set.add(hanzi)
    
    return hanzi_set


def load_full_json_data(json_path: str) -> list:
    """Load full JSON data."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_coverage(json_path: str, csv_path: str):
    """Validate which JSON entries are missing from CSV."""
    print(f"Loading JSON entries from: {json_path}")
    json_entries = load_json_entries(json_path)
    print(f"  Found {len(json_entries)} entries in JSON")
    
    print(f"\nLoading CSV entries from: {csv_path}")
    csv_entries = load_csv_entries(csv_path)
    print(f"  Found {len(csv_entries)} entries in CSV")
    
    # Find missing entries
    missing = json_entries - csv_entries
    
    print("\n" + "=" * 60)
    print("COVERAGE VALIDATION RESULTS")
    print("=" * 60)
    print(f"Total entries in JSON:     {len(json_entries)}")
    print(f"Total entries in CSV:      {len(csv_entries)}")
    print(f"Missing entries:           {len(missing)}")
    if len(json_entries) > 0:
        print(f"Coverage:                  {(len(csv_entries) / len(json_entries) * 100):.2f}%")
    else:
        print(f"Coverage:                  N/A (no entries in JSON)")
    print("=" * 60)
    
    if missing:
        print(f"\n⚠️  {len(missing)} entries from JSON were not generated in CSV")
    else:
        print("\n✅ All JSON entries were successfully generated in CSV!")
    
    return missing


def export_missing_entries(json_path: str, missing_hanzi: set, output_path: str):
    """Export missing entries to a new JSON file."""
    # Load full JSON data
    full_data = load_full_json_data(json_path)
    
    # Filter entries that are missing
    missing_entries = []
    for entry in full_data:
        hanzi = entry.get('hanzi', entry.get('simplified', '')).strip()
        if hanzi in missing_hanzi:
            missing_entries.append(entry)
    
    # Write to output file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(missing_entries, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Exported {len(missing_entries)} missing entries to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Validate coverage between JSON input and CSV output"
    )
    parser.add_argument(
        "json_file",
        help="Path to input JSON file"
    )
    parser.add_argument(
        "csv_file",
        help="Path to output CSV file"
    )
    parser.add_argument(
        "--show-missing",
        action="store_true",
        help="Show list of missing entries"
    )
    parser.add_argument(
        "--export-missing",
        metavar="OUTPUT_JSON",
        help="Export missing entries to a JSON file for re-processing"
    )
    
    args = parser.parse_args()
    
    # Validate files exist
    if not Path(args.json_file).exists():
        print(f"Error: JSON file not found: {args.json_file}")
        sys.exit(1)
    
    if not Path(args.csv_file).exists():
        print(f"Error: CSV file not found: {args.csv_file}")
        sys.exit(1)
    
    # Run validation
    missing = validate_coverage(args.json_file, args.csv_file)
    
    # Show missing entries if requested
    if args.show_missing and missing:
        print(f"\nMissing entries ({len(missing)}):")
        print("-" * 60)
        for hanzi in sorted(missing):
            print(f"  {hanzi}")
    
    # Export missing entries if requested
    if args.export_missing and missing:
        export_missing_entries(args.json_file, missing, args.export_missing)
    
    # Exit with error code if there are missing entries
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
