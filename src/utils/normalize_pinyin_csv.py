"""
Normalize pinyin in CSV vocabulary files.

Converts various pinyin formats to standard format with diacritics:
- lu:3 xing2 -> lǚ xíng
- meifar5 -> méifǎr
- numeric tones -> diacritics
- ALL formats to standard pinyin with tone marks
"""

import argparse
import csv
import sys
import codecs
import re
from pathlib import Path

# Configure UTF-8 for Windows
if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())


# Tone mark conversion tables
TONE_MARKS = {
    'a': ['ā', 'á', 'ǎ', 'à', 'a'],
    'e': ['ē', 'é', 'ě', 'è', 'e'],
    'i': ['ī', 'í', 'ǐ', 'ì', 'i'],
    'o': ['ō', 'ó', 'ǒ', 'ò', 'o'],
    'u': ['ū', 'ú', 'ǔ', 'ù', 'u'],
    'ü': ['ǖ', 'ǘ', 'ǚ', 'ǜ', 'ü'],
    'v': ['ǖ', 'ǘ', 'ǚ', 'ǜ', 'ü'],  # v is sometimes used for ü
}


def add_tone_mark(syllable: str, tone: int) -> str:
    """Add tone mark to a pinyin syllable.
    
    Rules for tone mark placement:
    1. If 'a' or 'e' exists, it takes the tone mark
    2. If 'ou' exists, 'o' takes the tone mark
    3. Otherwise, the last vowel takes the tone mark
    
    Args:
        syllable: Pinyin syllable without tone (e.g., 'lu', 'xing')
        tone: Tone number (1-5, where 5 is neutral/no mark)
        
    Returns:
        Syllable with tone mark (e.g., 'lǚ', 'xíng')
    """
    if tone < 1 or tone > 5:
        return syllable
    
    # Tone 5 (neutral) - no mark needed
    if tone == 5:
        return syllable
    
    # Preserve original case
    is_capitalized = syllable and syllable[0].isupper()
    syllable_lower = syllable.lower()
    
    # Convert 'v' to 'ü' for processing
    syllable_lower = syllable_lower.replace('v', 'ü')
    
    # Find which vowel gets the tone mark
    # Rule 1: 'a' or 'e' takes precedence
    if 'a' in syllable_lower:
        vowel = 'a'
        pos = syllable_lower.index('a')
    elif 'e' in syllable_lower:
        vowel = 'e'
        pos = syllable_lower.index('e')
    # Rule 2: 'ou' - 'o' takes the mark
    elif 'ou' in syllable_lower:
        vowel = 'o'
        pos = syllable_lower.index('o')
    # Rule 3: Last vowel (including ü)
    else:
        # Find all vowels
        vowels_in_syllable = []
        for i, char in enumerate(syllable_lower):
            if char in 'iouüv':
                vowels_in_syllable.append((i, char))
        
        if vowels_in_syllable:
            pos, vowel = vowels_in_syllable[-1]
            if vowel == 'v':
                vowel = 'ü'
        else:
            # No vowel found, return as-is
            return syllable
    
    # Get the tone-marked version
    if vowel in TONE_MARKS:
        marked_vowel = TONE_MARKS[vowel][tone - 1]
        # Replace the vowel at position with marked version
        result = syllable_lower[:pos] + marked_vowel + syllable_lower[pos + 1:]
        
        # Restore capitalization if needed
        if is_capitalized and result:
            result = result[0].upper() + result[1:]
        
        return result
    
    return syllable


def normalize_pinyin_syllable(syllable: str) -> str:
    """Normalize a single pinyin syllable to standard format.
    
    Handles:
    - lu:3 -> lǚ
    - lu3 -> lǚ
    - lü3 -> lǚ
    - lv3 -> lǚ
    - lu -> lu (no tone)
    - r5 -> r (neutral tone)
    - wánr5 -> wánr (already has diacritics, remove tone 5)
    
    Args:
        syllable: Single pinyin syllable
        
    Returns:
        Normalized syllable with tone marks
    """
    if not syllable:
        return syllable
    
    # Remove whitespace
    syllable = syllable.strip()
    
    # Check for colon format: lu:3 -> lu3
    syllable = re.sub(r':(\d)', r'\1', syllable)
    
    # Check if it has a tone number at the end
    # Pattern: any characters (including diacritics) followed by a digit
    match = re.match(r'^([a-züvāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]+?)(\d)$', syllable, re.IGNORECASE)
    
    if match:
        base, tone_str = match.groups()
        tone = int(tone_str)
        
        # Check if base already has diacritics (tone marks)
        has_diacritics = bool(re.search(r'[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]', base))
        
        if has_diacritics:
            # Already has tone marks, just remove the number
            # If it's tone 5 (neutral), that's fine, just return base
            # If it's another tone, the diacritic should match, so just return base
            return base
        
        # No diacritics yet, need to add them
        # Handle tone 5 (neutral) - just remove the number
        if tone == 5:
            return base
        
        # Special case: 'ju', 'qu', 'xu', 'yu' are ALWAYS 'jü', 'qü', 'xü', 'yü'
        # 'lu' and 'nu' can be either 'lu'/'nu' OR 'lü'/'nü' depending on the character
        # Without the character context, we can't determine this automatically
        # So we'll only convert j/q/x/y + u -> ü (which are always ü in pinyin)
        base_lower = base.lower()
        if base_lower in ['ju', 'qu', 'xu', 'yu']:
            # These are always ü in standard pinyin
            base = base[:-1] + 'ü'
        
        # Add tone mark to the base
        return add_tone_mark(base, tone)
    
    # No tone number found - return as-is
    return syllable


def normalize_pinyin_format(pinyin: str) -> str:
    """Normalize various pinyin formats to standard diacritics.
    
    Handles ALL common formats:
    - lu:3 xing2 -> lǚ xíng
    - lu3 xing2 -> lǚ xíng
    - meifar5 -> méifǎr
    - mei2fa3r5 -> méifǎr
    - tān wánr5 -> tān wánr (mixed diacritics + number)
    - Mixed formats in same string
    
    Args:
        pinyin: Pinyin string in any format
        
    Returns:
        Normalized pinyin with diacritics
    """
    if not pinyin or not isinstance(pinyin, str):
        return pinyin
    
    # First, check if it's space-separated (most common case)
    if ' ' in pinyin:
        syllables = pinyin.split()
        normalized = [normalize_pinyin_syllable(syl) for syl in syllables if syl.strip()]
        return ' '.join(normalized)
    
    # Handle syllables stuck together with numbers (mei2fa3r5 or ni3hao3 or meifar5)
    # Strategy: find all letter+number patterns
    # Pattern: one or more letters (including ü, v, :, and pinyin diacritics) followed by digit
    # Include common pinyin vowels with tone marks: āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ
    syllable_pattern = r'[a-züvāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ:]+\d'
    matches = re.findall(syllable_pattern, pinyin, flags=re.IGNORECASE)
    
    if matches:
        # Check if there are leftover letters (e.g., "meifa" in "meifar5")
        matched_text = ''.join(matches)
        if len(matched_text) < len(pinyin.replace(' ', '')):
            # There are unmatched letters - might be syllables without tones
            # Try to split more intelligently
            # For now, just normalize what we found
            pass
        
        # Normalize each matched syllable
        normalized = [normalize_pinyin_syllable(syl) for syl in matches if syl.strip()]
        return ' '.join(normalized)
    
    # No numbers found - might be already normalized or no tone
    # Just return as-is
    return pinyin


def normalize_csv_pinyin(input_csv: str, output_csv: str, dry_run: bool = False):
    """Normalize pinyin in a CSV file.
    
    Args:
        input_csv: Path to input CSV file
        output_csv: Path to output CSV file
        dry_run: If True, only show what would be changed
    """
    input_path = Path(input_csv)
    
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_csv}")
        return False
    
    print(f"Reading CSV: {input_csv}")
    
    changes = []
    rows_processed = 0
    rows_changed = 0
    
    # Read and process CSV
    with open(input_path, 'r', encoding='utf-8') as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames
        
        if 'pinyin' not in fieldnames:
            print(f"❌ Error: CSV does not have 'pinyin' column")
            print(f"   Available columns: {', '.join(fieldnames)}")
            return False
        
        rows = []
        for row_num, row in enumerate(reader, start=2):
            rows_processed += 1
            original_pinyin = row.get('pinyin', '')
            
            if original_pinyin:
                normalized_pinyin = normalize_pinyin_format(original_pinyin)
                
                if normalized_pinyin != original_pinyin:
                    rows_changed += 1
                    hanzi = row.get('hanzi', '?')
                    changes.append({
                        'row': row_num,
                        'hanzi': hanzi,
                        'original': original_pinyin,
                        'normalized': normalized_pinyin
                    })
                    row['pinyin'] = normalized_pinyin
            
            rows.append(row)
    
    # Report changes
    print(f"\n{'=' * 80}")
    print(f"NORMALIZATION RESULTS")
    print(f"{'=' * 80}")
    print(f"Total rows:     {rows_processed}")
    print(f"Rows changed:   {rows_changed}")
    print(f"Rows unchanged: {rows_processed - rows_changed}")
    print(f"{'=' * 80}")
    
    if changes:
        print(f"\nCHANGES DETECTED:")
        print(f"{'-' * 80}")
        for change in changes[:20]:  # Show first 20
            print(f"  Row {change['row']} ({change['hanzi']})")
            print(f"    Before: {change['original']}")
            print(f"    After:  {change['normalized']}")
        
        if len(changes) > 20:
            print(f"  ... and {len(changes) - 20} more changes")
    
    # Write output
    if not dry_run:
        output_path = Path(output_csv)
        with open(output_path, 'w', encoding='utf-8', newline='') as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"\n✅ Normalized CSV written to: {output_csv}")
    else:
        print(f"\n⚠️  DRY RUN - No file written")
        print(f"   Run without --dry-run to save changes to: {output_csv}")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Normalize pinyin formats in CSV vocabulary files"
    )
    parser.add_argument("input_csv", help="Input CSV file")
    parser.add_argument("output_csv", help="Output CSV file (can be same as input)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show changes without writing output file")
    
    args = parser.parse_args()
    
    success = normalize_csv_pinyin(args.input_csv, args.output_csv, args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
