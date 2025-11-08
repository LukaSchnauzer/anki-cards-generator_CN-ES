"""
CSV to Anki converter for ChinoSRS.
Generates three types of cards: SentenceCard, PatternCard, and AudioCard.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
import random
import time
from datetime import timedelta
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
        "Audio": "",
        "WordAudio": "",
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
        "Audio": "",
        "WordAudio": "",
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
        "Audio": "",
        "WordAudio": "",
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


def get_cache_filename(csv_file: str) -> str:
    """Generate cache filename from CSV filename in outputs directory.
    
    Args:
        csv_file: Path to CSV file
    
    Returns:
        Path to JSON cache file in outputs/ directory
    """
    # Get just the filename without extension
    basename = os.path.basename(csv_file)
    name_without_ext = os.path.splitext(basename)[0]
    
    # Always save cache in outputs directory
    cache_dir = "outputs"
    os.makedirs(cache_dir, exist_ok=True)
    
    return os.path.join(cache_dir, f"{name_without_ext}.json")


def save_notes_to_cache(notes: List[Dict], cache_file: str) -> None:
    """Save generated notes to JSON cache file.
    
    Args:
        notes: List of Anki note dictionaries
        cache_file: Path to cache file
    """
    print(f"\nGuardando {len(notes)} notas en caché: {cache_file}")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    print(f"Caché guardado exitosamente.")


def load_notes_from_cache(cache_file: str) -> List[Dict]:
    """Load notes from JSON cache file.
    
    Args:
        cache_file: Path to cache file
    
    Returns:
        List of Anki note dictionaries
    """
    print(f"Cargando notas desde caché: {cache_file}")
    with open(cache_file, "r", encoding="utf-8") as f:
        notes = json.load(f)
    print(f"Cargadas {len(notes)} notas desde caché.")
    return notes


def deduplicate_sort_keys(notes: List[Dict]) -> tuple[List[Dict], List[Dict]]:
    """Deduplicate SortKey values in notes by modifying the random component.
    
    Args:
        notes: List of Anki note dictionaries
    
    Returns:
        Tuple of (all_notes, deduplicated_notes_only)
    """
    print(f"\n🔍 Verificando SortKeys duplicados...")
    print(f"   Analizando {len(notes)} notas...")
    
    # Track seen SortKeys and which notes have them
    sortkey_map = {}  # {sortkey: [list of note indices]}
    deduplicated_indices = set()
    
    # First pass: identify all duplicates
    for idx, note in enumerate(notes):
        if "fields" in note and "SortKey" in note["fields"]:
            sortkey = note["fields"]["SortKey"]
            if sortkey not in sortkey_map:
                sortkey_map[sortkey] = []
            sortkey_map[sortkey].append(idx)
    
    print(f"   Encontrados {len(sortkey_map)} SortKeys únicos")
    
    # Count duplicates
    duplicate_groups = {k: v for k, v in sortkey_map.items() if len(v) > 1}
    
    if not duplicate_groups:
        print(f"✅ No se encontraron SortKeys duplicados")
        return notes, []
    
    print(f"   Detectados {len(duplicate_groups)} grupos con duplicados")
    total_duplicates = sum(len(v) - 1 for v in duplicate_groups.values())
    print(f"   Total de notas a desduplicar: {total_duplicates}")
    
    # Track all used SortKeys
    used_sortkeys = set(sortkey_map.keys())
    
    # Second pass: fix duplicates (only process groups with duplicates)
    duplicates_found = 0
    groups_processed = 0
    for sortkey, indices in duplicate_groups.items():
        groups_processed += 1
        
        # Show progress every 10 groups
        if groups_processed % 10 == 0 or groups_processed == len(duplicate_groups):
            print(f"   Procesando grupo {groups_processed}/{len(duplicate_groups)}...", end="\r")
        
        # Parse the original key components once
        hsk = sortkey[:2]
        freq = sortkey[2:4]
        bucket_key = f"{hsk}{freq}"
        base_random = int(sortkey[4:8])
        
        # Check bucket saturation
        num_duplicates = len(indices) - 1
        if num_duplicates > 100:
            print(f"\n   ⚠️  Grupo grande detectado: {sortkey} con {num_duplicates} duplicados")
        
        # Keep first occurrence, modify the rest
        offset = 1
        current_freq = int(freq)
        max_sequential_attempts = 1000  # Try to find slot in current bucket
        
        for i, note_idx in enumerate(indices[1:], start=1):
            duplicates_found += 1
            deduplicated_indices.add(note_idx)
            note = notes[note_idx]
            
            # Try to find available slot
            attempts = 0
            found_slot = False
            
            while not found_slot:
                new_random = (base_random + offset) % 10000
                current_freq_str = f"{current_freq:02d}"
                new_key = f"{hsk}{current_freq_str}{new_random:04d}"
                
                if new_key not in used_sortkeys:
                    # Found available slot
                    found_slot = True
                    note["fields"]["SortKey"] = new_key
                    used_sortkeys.add(new_key)
                    offset += 1
                else:
                    offset += 1
                    attempts += 1
                    
                    # If current bucket is saturated, move to next frequency bucket
                    if attempts > max_sequential_attempts:
                        current_freq += 1
                        offset = 0  # Reset offset for new bucket
                        attempts = 0
                        print(f"\n   ⚠️  Bucket {hsk}{freq} saturado, moviendo a {hsk}{current_freq:02d}...")
                        
                        # Safety check - don't go beyond 99
                        if current_freq > 99:
                            print(f"\n   ❌ ERROR: No hay buckets disponibles")
                            raise RuntimeError(f"Todos los buckets HSK {hsk} están saturados")
    
    print(f"\n✅ Desduplicados {duplicates_found} SortKeys")
    
    # Extract only deduplicated notes
    deduplicated_notes = [notes[idx] for idx in sorted(deduplicated_indices)]
    
    return notes, deduplicated_notes


def main():
    parser = argparse.ArgumentParser(description="Convert CSV vocabulary to Anki notes")
    parser.add_argument("csv_file", help="Path to CSV file")
    parser.add_argument("--limit", type=int, help="Limit number of entries to process")
    parser.add_argument("--force-recreate", action="store_true", help="Force recreate card models")
    parser.add_argument("--skip-cache", action="store_true", help="Skip cache and regenerate notes from CSV")
    parser.add_argument("--only-deduplicated", action="store_true", help="Only upload notes that were deduplicated (had duplicate SortKeys)")
    args = parser.parse_args()

    if not os.path.isfile(args.csv_file):
        print(f"Error: CSV file not found: {args.csv_file}", file=sys.stderr)
        sys.exit(1)

    print("Setting up Anki deck and card models...")
    ensure_deck(DECK_NAME)
    setup_models(force_recreate=args.force_recreate)

    # Check if cache file exists
    cache_file = get_cache_filename(args.csv_file)
    use_cache = False
    
    if os.path.isfile(cache_file) and not args.skip_cache:
        print(f"\n¡Caché encontrado! ({cache_file})")
        response = input("¿Deseas usar el caché existente? (s/n): ").strip().lower()
        use_cache = (response == 's')
    
    if use_cache:
        all_notes = load_notes_from_cache(cache_file)
    else:
        if args.skip_cache:
            print(f"\nOmitiendo caché (--skip-cache activado)")
        print(f"\nGenerando notas desde CSV: {args.csv_file}")
        
        # Count total rows first
        with open(args.csv_file, "r", encoding="utf-8") as f:
            total_rows = sum(1 for _ in csv.DictReader(f))
            if args.limit:
                total_rows = min(total_rows, args.limit)
        
        all_notes = []
        start_time = time.time()
        last_update = start_time
        
        with open(args.csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if args.limit and i >= args.limit:
                    break
                notes = build_notes_from_row(row)
                all_notes.extend(notes)
                
                # Update progress every second
                current_time = time.time()
                if current_time - last_update >= 1.0 or i == total_rows - 1:
                    elapsed = current_time - start_time
                    progress = (i + 1) / total_rows
                    if progress > 0:
                        eta_seconds = (elapsed / progress) - elapsed
                        eta_str = str(timedelta(seconds=int(eta_seconds)))
                        print(f"\rProgreso: {i+1}/{total_rows} ({progress*100:.1f}%) | ETA: {eta_str}", end="", flush=True)
                    last_update = current_time
        
        print()  # New line after progress
        elapsed_total = time.time() - start_time
        print(f"Generación completada en {str(timedelta(seconds=int(elapsed_total)))}")
        
        # Save to cache after generation
        save_notes_to_cache(all_notes, cache_file)
    
    # Deduplicate SortKeys to avoid conflicts
    all_notes, deduplicated_notes = deduplicate_sort_keys(all_notes)
    
    # Decide which notes to upload
    if args.only_deduplicated:
        notes_to_upload = deduplicated_notes
        print(f"\n📌 Modo: Solo subir notas desduplicadas")
        print(f"Total notes to add: {len(notes_to_upload)} (desduplicadas)")
    else:
        notes_to_upload = all_notes
        print(f"\nTotal notes to add: {len(notes_to_upload)}")
    
    if len(notes_to_upload) == 0:
        print("No hay notas para subir.")
        return
    
    # Send notes in batches
    batch_size = 50
    total_batches = (len(notes_to_upload) + batch_size - 1) // batch_size
    print("Sending notes to Anki in batches...")
    
    start_time = time.time()
    total_added = 0
    total_failed = 0
    
    for i in range(0, len(notes_to_upload), batch_size):
        batch_num = i // batch_size + 1
        batch = notes_to_upload[i:i + batch_size]
        
        batch_start = time.time()
        
        try:
            result = post("addNotes", notes=batch)
            batch_time = time.time() - batch_start
            
            # Count successful and failed notes
            added = sum(1 for r in result if r is not None)
            failed = len(result) - added
            total_added += added
            total_failed += failed
            
            # Calculate ETA
            elapsed = time.time() - start_time
            progress = batch_num / total_batches
            if progress > 0:
                eta_seconds = (elapsed / progress) - elapsed
                eta_str = str(timedelta(seconds=int(eta_seconds)))
                print(f"Batch {batch_num}/{total_batches}: {added} added, {failed} failed/duplicates | ETA: {eta_str}")
            else:
                print(f"Batch {batch_num}/{total_batches}: {added} added, {failed} failed/duplicates")
                
        except Exception as e:
            batch_time = time.time() - batch_start
            print(f"\n{'='*80}")
            print(f"❌ Batch {batch_num}/{total_batches}: EXCEPCIÓN CAPTURADA")
            print(f"{'='*80}")
            print(f"📍 Batch range: notas {i+1} a {min(i+batch_size, len(notes_to_upload))}")
            print(f"🔴 Tipo de error: {type(e).__name__}")
            print(f"💬 Mensaje de error:\n{str(e)}")
            print(f"{'='*80}\n")
            total_failed += len(batch)
            
            # Save problematic batch for inspection
            problem_file = f"outputs/batch_{batch_num}_error.json"
            try:
                with open(problem_file, "w", encoding="utf-8") as f:
                    json.dump(batch, f, ensure_ascii=False, indent=2)
                print(f"💾 Batch problemático guardado en: {problem_file}")
                
                # Try to identify which specific note(s) in the batch are problematic
                print(f"\n🔍 Intentando identificar nota problemática...")
                for idx, note in enumerate(batch):
                    note_num = i + idx + 1
                    try:
                        # Try to add this single note
                        single_result = post("addNotes", notes=[note])
                        if single_result is None or single_result[0] is None:
                            print(f"   ⚠️  Nota #{note_num} falló (posible duplicado)")
                            print(f"      Hanzi: {note['fields'].get('Hanzi', 'N/A')}")
                            print(f"      Model: {note.get('modelName', 'N/A')}")
                    except Exception as single_e:
                        print(f"   ❌ Nota #{note_num} causó error:")
                        print(f"      Hanzi: {note['fields'].get('Hanzi', 'N/A')}")
                        print(f"      Model: {note.get('modelName', 'N/A')}")
                        print(f"      Error: {str(single_e)[:200]}")
                        # Save the specific problematic note
                        problem_note_file = f"outputs/note_{note_num}_error.json"
                        with open(problem_note_file, "w", encoding="utf-8") as nf:
                            json.dump(note, nf, ensure_ascii=False, indent=2)
                        print(f"      Guardada en: {problem_note_file}")
                        break  # Stop after finding first problematic note
                print()
            except Exception as save_error:
                print(f"⚠️  No se pudo guardar el batch: {save_error}\n")
            
            continue
    
    elapsed_total = time.time() - start_time
    print(f"\nSubida completada en {str(timedelta(seconds=int(elapsed_total)))}")

    print(f"\nResumen final:")
    print(f"  - Notas agregadas: {total_added}")
    print(f"  - Notas fallidas/duplicadas: {total_failed}")
    print(f"  - Total procesadas: {total_added + total_failed}")


if __name__ == "__main__":
    main()