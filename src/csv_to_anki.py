"""
CSV to Anki converter for ChinoSRS.
Generates three types of cards: SentenceCard, PatternCard, and AudioCard.
"""

import argparse
import csv
import os
import sys
import random
from typing import Dict, List

# Import our modules
from anki.api import ensure_deck, post, find_audio_for_sentence, find_audio_for_word, DECK_NAME
from anki.models import setup_models
from anki.hints import build_hints, lookup_pos, lookup_register, lookup_frequency, clean_pinyin_from_sentence, oculta_objetivo_en_texto


def generate_sort_key(frecuencia: str) -> str:
    """Generate a sort key based on HSK level, frequency bucket, and random order.
    
    Format: {HSK_level:02d}{freq_bucket:02d}{random:04d}
    
    Args:
        frecuencia: String like "hsk:2;freq:top1k" or "hsk:7;freq:rare"
    
    Returns:
        Sort key string like "02010123" (HSK 2, top1k, random 123)
    """
    # Parse HSK level
    hsk_level = 99  # Default for unknown
    if frecuencia:
        for tag in frecuencia.split(";"):
            tag = tag.strip()
            if tag.startswith("hsk:"):
                try:
                    hsk_level = int(tag.split(":")[1])
                except (ValueError, IndexError):
                    pass
    
    # Parse frequency bucket
    freq_bucket = 99  # Default for unknown
    freq_map = {
        "top1k": 1,
        "top3k": 3,
        "top5k": 5,
        "top10k": 10,
        "rare": 90
    }
    
    if frecuencia:
        for tag in frecuencia.split(";"):
            tag = tag.strip()
            if tag.startswith("freq:"):
                freq_name = tag.split(":")[1]
                freq_bucket = freq_map.get(freq_name, 99)
    
    # Generate random number for ordering within same bucket
    random_num = random.randint(0, 9999)
    
    # Format: HSK (2 digits) + Freq (2 digits) + Random (4 digits)
    sort_key = f"{hsk_level:02d}{freq_bucket:02d}{random_num:04d}"
    
    return sort_key


def build_notes_from_row(row: Dict[str, str]) -> List[Dict]:
    """Build three Anki notes (SentenceCard, PatternCard, AudioCard) from a CSV row."""
    # Extract basic fields
    hanzi = (row.get("hanzi") or "").strip()
    pinyin = (row.get("pinyin") or "").strip()
    meaning = (row.get("definition") or "").strip()
    tips = (row.get("tips") or "").strip()
    colloc = (row.get("collocations") or "").strip()
    pos = (row.get("pos") or "").strip()
    register = (row.get("register") or "").strip()
    pattern = (row.get("pattern") or "").strip()
    tags_seed = (row.get("tags_seed") or "").strip()
    frecuencia = (row.get("frecuencia") or "").strip()
    
    # Build combined tags
    all_tags = []
    if tags_seed:
        all_tags.extend([t.strip() for t in tags_seed.split(";") if t.strip()])
    if frecuencia:
        all_tags.extend([t.strip() for t in frecuencia.split(";") if t.strip()])
    if register:
        all_tags.append(register)
    combined_tags = ";".join(all_tags)

    # Get all available sentences (separated by |) and clean pinyin
    all_sentences_cn = [clean_pinyin_from_sentence(s.strip()) for s in (row.get("example_sentence") or "").split("|") if s.strip()]
    all_sentences_es = [s.strip() for s in (row.get("example_translation") or "").split("|") if s.strip()]
    
    # Default values if no sentences
    if not all_sentences_cn:
        all_sentences_cn = [""]
    if not all_sentences_es:
        all_sentences_es = [""]
    
    # Ensure both lists have the same size
    while len(all_sentences_es) < len(all_sentences_cn):
        all_sentences_es.append(all_sentences_es[-1] if all_sentences_es else "")
    
    # Audio directory (absolute path)
    audio_dir_abs = os.path.abspath("resources/audios")
    
    # Build readable versions for card backs
    pos_readable = lookup_pos(pos) if pos else ""
    register_readable = lookup_register(register) if register else ""
    frecuencia_readable = lookup_frequency(frecuencia) if frecuencia else ""

    notes = []

    # ===== SentenceCard =====
    # Use first sentence
    idx_sentence = 0
    sent_cn_sentence = all_sentences_cn[idx_sentence]
    sent_es_sentence = all_sentences_es[idx_sentence]
    
    # Build hints (don't hide word in collocation for SentenceCard)
    hint_data_sentence = build_hints(row, hanzi, pinyin, hide_word_in_collocation=False)
    
    # Find audio for sentence and word
    audio_path_sentence = find_audio_for_sentence(sent_cn_sentence, audio_dir=audio_dir_abs)
    audio_filename_sentence = os.path.basename(audio_path_sentence) if audio_path_sentence else ""
    
    audio_path_word = find_audio_for_word(hanzi, audio_dir=audio_dir_abs)
    audio_filename_word = os.path.basename(audio_path_word) if audio_path_word else ""
    
    front_line = f"{sent_cn_sentence} → ¿Qué es {hanzi}?"
    fields_sentence = {
        "Hanzi": hanzi,
        "Pinyin": pinyin,
        "Meaning": meaning,
        "SentenceCN": sent_cn_sentence,
        "SentenceES": sent_es_sentence,
        "Tips": tips,
        "Collocations": colloc,
        "POS": pos_readable,
        "Register": register_readable,
        "Frecuencia": frecuencia_readable,
        "Tags": combined_tags,
        "Audio": audio_filename_sentence,
        "WordAudio": audio_filename_word,
        "FrontLine": front_line,
        "Hint1": hint_data_sentence["hint1"],
        "Hint2": hint_data_sentence["hint2"],
        "Hint3": hint_data_sentence["hint3"],
        "SortKey": generate_sort_key(frecuencia)
    }
    
    anki_tags = ["SRS", "Sentence"] + [t.replace(":", "-") for t in all_tags]
    note_sentence = {
        "deckName": DECK_NAME,
        "modelName": "ChinoSRS_SentenceCard",
        "fields": fields_sentence,
        "options": {"allowDuplicate": False},
        "tags": anki_tags,
    }
    
    # Add audio files
    audio_list = []
    if audio_path_sentence and os.path.isfile(audio_path_sentence):
        audio_list.append({"path": audio_path_sentence, "filename": audio_filename_sentence, "fields": ["Audio"]})
    if audio_path_word and os.path.isfile(audio_path_word):
        audio_list.append({"path": audio_path_word, "filename": audio_filename_word, "fields": ["WordAudio"]})
    if audio_list:
        note_sentence["audio"] = audio_list
    
    notes.append(note_sentence)

    # ===== PatternCard =====
    # Use second sentence (or first if only one exists)
    idx_pattern = 1 if len(all_sentences_cn) > 1 else 0
    sent_cn_pattern = all_sentences_cn[idx_pattern]
    sent_es_pattern = all_sentences_es[idx_pattern]
    
    # Build cloze sentence
    cloze_sentence = oculta_objetivo_en_texto(sent_cn_pattern, hanzi)
    
    # Build hints (include definition for PatternCard)
    hint_data_pattern = build_hints(row, hanzi, pinyin, include_definition=True)
    
    # Find audio for sentence and word
    audio_path_pattern = find_audio_for_sentence(sent_cn_pattern, audio_dir=audio_dir_abs)
    audio_filename_pattern = os.path.basename(audio_path_pattern) if audio_path_pattern else ""
    
    fields_pattern = {
        "Hanzi": hanzi,
        "Pinyin": pinyin,
        "Meaning": meaning,
        "SentenceCN": sent_cn_pattern,
        "SentenceES": sent_es_pattern,
        "Tips": tips,
        "Pattern": pattern,
        "POS": pos_readable,
        "Register": register_readable,
        "Frecuencia": frecuencia_readable,
        "Audio": audio_filename_pattern,
        "WordAudio": audio_filename_word,
        "Tags": combined_tags,
        "ClozeSentence": cloze_sentence,
        "MissingPart": hanzi,
        "Hint1": hint_data_pattern["hint1"],
        "Hint2": hint_data_pattern["hint2"],
        "Hint3": hint_data_pattern["hint3"],
        "Hint4": hint_data_pattern.get("hint4", ""),
        "SortKey": generate_sort_key(frecuencia)
    }
    
    anki_tags = ["SRS", "Pattern"] + [t.replace(":", "-") for t in all_tags]
    note_pattern = {
        "deckName": DECK_NAME,
        "modelName": "ChinoSRS_PatternCard",
        "fields": fields_pattern,
        "options": {"allowDuplicate": False},
        "tags": anki_tags,
    }
    
    # Add audio files
    audio_list = []
    if audio_path_pattern and os.path.isfile(audio_path_pattern):
        audio_list.append({"path": audio_path_pattern, "filename": audio_filename_pattern, "fields": ["Audio"]})
    if audio_path_word and os.path.isfile(audio_path_word):
        audio_list.append({"path": audio_path_word, "filename": audio_filename_word, "fields": ["WordAudio"]})
    if audio_list:
        note_pattern["audio"] = audio_list
    
    notes.append(note_pattern)

    # ===== AudioCard =====
    # Use third sentence (or second/first if not enough)
    idx_audio = 2 if len(all_sentences_cn) > 2 else (1 if len(all_sentences_cn) > 1 else 0)
    sent_cn_audio = all_sentences_cn[idx_audio]
    sent_es_audio = all_sentences_es[idx_audio]
    
    # Build hints (include definition for AudioCard)
    hint_data_audio = build_hints(row, hanzi, pinyin, include_definition=True)
    
    # Find audio for sentence and word
    audio_path_audio = find_audio_for_sentence(sent_cn_audio, audio_dir=audio_dir_abs)
    audio_filename_audio = os.path.basename(audio_path_audio) if audio_path_audio else ""
    
    fields_audio = {
        "Hanzi": hanzi,
        "Pinyin": pinyin,
        "Meaning": meaning,
        "SentenceCN": sent_cn_audio,
        "SentenceES": sent_es_audio,
        "Tips": tips,
        "POS": pos_readable,
        "Register": register_readable,
        "Frecuencia": frecuencia_readable,
        "Tags": combined_tags,
        "Audio": audio_filename_audio,
        "WordAudio": audio_filename_word,
        "Hint1": hint_data_audio["hint1"],
        "Hint2": hint_data_audio["hint2"],
        "Hint3": hint_data_audio["hint3"],
        "Hint4": hint_data_audio.get("hint4", ""),
        "SortKey": generate_sort_key(frecuencia)
    }
    
    anki_tags = ["SRS", "Audio"] + [t.replace(":", "-") for t in all_tags]
    note_audio = {
        "deckName": DECK_NAME,
        "modelName": "ChinoSRS_AudioCard",
        "fields": fields_audio,
        "options": {"allowDuplicate": False},
        "tags": anki_tags,
    }
    
    # Add audio files
    audio_list = []
    if audio_path_audio and os.path.isfile(audio_path_audio):
        audio_list.append({"path": audio_path_audio, "filename": audio_filename_audio, "fields": ["Audio"]})
    if audio_path_word and os.path.isfile(audio_path_word):
        audio_list.append({"path": audio_path_word, "filename": audio_filename_word, "fields": ["WordAudio"]})
    if audio_list:
        note_audio["audio"] = audio_list
    
    notes.append(note_audio)

    return notes


def main():
    parser = argparse.ArgumentParser(description="Convert CSV vocabulary to Anki notes")
    parser.add_argument("csv_file", help="Path to CSV file")
    parser.add_argument("--limit", type=int, help="Limit number of entries to process")
    parser.add_argument("--force-recreate", action="store_true", help="Force recreate card models")
    args = parser.parse_args()

    if not os.path.isfile(args.csv_file):
        print(f"Error: CSV file not found: {args.csv_file}", file=sys.stderr)
        sys.exit(1)

    print("Setting up Anki deck and card models...")
    ensure_deck(DECK_NAME)
    setup_models(force_recreate=args.force_recreate)

    print(f"Reading CSV: {args.csv_file}")
    all_notes = []
    with open(args.csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if args.limit and i >= args.limit:
                break
            notes = build_notes_from_row(row)
            all_notes.extend(notes)

    print(f"\nTotal notes to add: {len(all_notes)}")
    
    # Send notes in batches
    batch_size = 50
    print("Sending notes to Anki in batches...")
    for i in range(0, len(all_notes), batch_size):
        batch = all_notes[i:i + batch_size]
        result = post("addNotes", notes=batch)
        added = sum(1 for r in result if r is not None)
        failed = len(result) - added
        print(f"Batch {i//batch_size + 1}: {added} added, {failed} failed/duplicates")

    print(f"\nSuccessfully added: {len([r for r in result if r is not None])} notes")
    print(f"Notas agregadas: {len([r for r in result if r is not None])}")


if __name__ == "__main__":
    main()
