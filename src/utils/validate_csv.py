"""
Validate CSV quality: check for common issues in generated vocabulary CSV.
"""

import argparse
import csv
import sys
import codecs
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Configure UTF-8 for Windows
if sys.platform == "win32":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())


class ValidationIssue:
    """Represents a validation issue found in a CSV row."""
    def __init__(self, row_num: int, hanzi: str, field: str, issue: str, severity: str = "warning"):
        self.row_num = row_num
        self.hanzi = hanzi
        self.field = field
        self.issue = issue
        self.severity = severity
    
    def __str__(self):
        icon = "ERROR" if self.severity == "error" else "WARN"
        return f"[{icon}] Row {self.row_num} ({self.hanzi}) - {self.field}: {self.issue}"


def validate_row(row: Dict[str, str], row_num: int) -> List[ValidationIssue]:
    """Run all validations on a single row."""
    issues = []
    hanzi = row.get("hanzi", "").strip()
    
    # Required fields
    required = ["hanzi", "pinyin", "definition", "example_sentence", 
                "example_translation", "tips", "collocations"]
    for field in required:
        if not row.get(field, "").strip():
            issues.append(ValidationIssue(
                row_num, hanzi or "???", field, 
                "Campo requerido vacio", "error"
            ))
    
    # Sentence count
    sentences_cn = row.get("example_sentence", "").strip()
    sentences_es = row.get("example_translation", "").strip()
    if sentences_cn:
        count_cn = len([s for s in sentences_cn.split("|") if s.strip()])
        if count_cn != 3:
            issues.append(ValidationIssue(
                row_num, hanzi, "example_sentence",
                f"Se esperan 3 oraciones, encontradas {count_cn}", "warning"
            ))
    
    if sentences_es:
        count_es = len([s for s in sentences_es.split("|") if s.strip()])
        if count_es != 3:
            issues.append(ValidationIssue(
                row_num, hanzi, "example_translation",
                f"Se esperan 3 traducciones, encontradas {count_es}", "warning"
            ))
    
    # Match CN and ES counts
    if sentences_cn and sentences_es:
        count_cn = len([s for s in sentences_cn.split("|") if s.strip()])
        count_es = len([s for s in sentences_es.split("|") if s.strip()])
        if count_cn != count_es:
            issues.append(ValidationIssue(
                row_num, hanzi, "sentences",
                f"Desbalance: {count_cn} CN vs {count_es} ES", "error"
            ))
    
    # Collocation count
    collocations = row.get("collocations", "").strip()
    if collocations:
        count = len([c for c in collocations.split("|") if c.strip()])
        if count < 3 or count > 5:
            issues.append(ValidationIssue(
                row_num, hanzi, "collocations",
                f"Esperadas 3-5 colocaciones, encontradas {count}", "warning"
            ))
    
    # Hanzi in sentences
    if hanzi and sentences_cn:
        sentences = [s.strip() for s in sentences_cn.split("|") if s.strip()]
        missing = sum(1 for s in sentences if hanzi not in s.split("(")[0])
        if missing == len(sentences):
            issues.append(ValidationIssue(
                row_num, hanzi, "example_sentence",
                f"'{hanzi}' no aparece en ninguna oracion", "error"
            ))
    
    # Definition length
    definition = row.get("definition", "").strip()
    if definition:
        if len(definition) < 20:
            issues.append(ValidationIssue(
                row_num, hanzi, "definition",
                f"Definicion muy corta ({len(definition)} chars)", "warning"
            ))
        if len(definition) > 500:
            issues.append(ValidationIssue(
                row_num, hanzi, "definition",
                f"Definicion muy larga ({len(definition)} chars)", "warning"
            ))
    
    # Pinyin format
    pinyin = row.get("pinyin", "").strip()
    if pinyin:
        if pinyin.isupper():
            issues.append(ValidationIssue(
                row_num, hanzi, "pinyin",
                "Pinyin en mayusculas", "warning"
            ))
        if any(c.isdigit() for c in pinyin):
            issues.append(ValidationIssue(
                row_num, hanzi, "pinyin",
                "Pinyin contiene numeros", "warning"
            ))
    
    # Tags
    frecuencia = row.get("frecuencia", "").strip()
    if frecuencia:
        if "hsk:" not in frecuencia:
            issues.append(ValidationIssue(
                row_num, hanzi, "frecuencia",
                "Falta etiqueta HSK", "warning"
            ))
        if "freq:" not in frecuencia:
            issues.append(ValidationIssue(
                row_num, hanzi, "frecuencia",
                "Falta etiqueta frecuencia", "warning"
            ))
    
    # Pinyin cleanup coverage
    if sentences_cn:
        for i, sentence in enumerate([s.strip() for s in sentences_cn.split("|") if s.strip()], 1):
            # Check for pinyin NOT in parentheses (won't be cleaned)
            # Look for pinyin-like patterns outside parentheses
            # Remove content in parentheses first
            without_parens = re.sub(r'\([^)]*\)', '', sentence)
            # Check if there are still latin letters (potential uncleaned pinyin)
            if re.search(r'[a-zA-Z]{2,}', without_parens):
                issues.append(ValidationIssue(
                    row_num, hanzi, f"example_sentence[{i}]",
                    "Posible pinyin fuera de parentesis (no sera limpiado)", "warning"
                ))
            
            # Check for brackets or other formats (not supported)
            if '[' in sentence or '{' in sentence:
                issues.append(ValidationIssue(
                    row_num, hanzi, f"example_sentence[{i}]",
                    "Pinyin en corchetes [] o llaves {} no sera limpiado", "warning"
                ))
    
    # Check collocations format
    if collocations:
        for i, colloc in enumerate([c.strip() for c in collocations.split("|") if c.strip()], 1):
            # Collocations should have format: "汉字 (traduccion)" or "汉字 (pinyin) - traduccion"
            if '(' not in colloc:
                issues.append(ValidationIssue(
                    row_num, hanzi, f"collocations[{i}]",
                    "Colocacion sin parentesis (formato esperado: '汉字 (glosa)')", "warning"
                ))
    
    return issues


def validate_csv(csv_path: str) -> Tuple[List[ValidationIssue], int]:
    """Validate entire CSV file."""
    issues = []
    total_rows = 0
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            total_rows += 1
            issues.extend(validate_row(row, row_num))
    
    return issues, total_rows


def main():
    parser = argparse.ArgumentParser(description="Validate vocabulary CSV quality")
    parser.add_argument("csv_file", help="Path to CSV file")
    parser.add_argument("--errors-only", action="store_true", help="Show only errors")
    args = parser.parse_args()
    
    if not Path(args.csv_file).exists():
        print(f"Error: CSV file not found: {args.csv_file}")
        sys.exit(1)
    
    print(f"Validating CSV: {args.csv_file}")
    print()
    
    issues, total_rows = validate_csv(args.csv_file)
    
    if args.errors_only:
        issues = [i for i in issues if i.severity == "error"]
    
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    
    print("=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)
    print(f"Total rows:    {total_rows}")
    print(f"Errors:        {len(errors)}")
    print(f"Warnings:      {len(warnings)}")
    print(f"Total issues:  {len(issues)}")
    print("=" * 80)
    
    if issues:
        print()
        print("ISSUES FOUND:")
        print("-" * 80)
        for issue in issues:
            print(f"  {issue}")
    else:
        print()
        print("OK: No issues found!")
    
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
