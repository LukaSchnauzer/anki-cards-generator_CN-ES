"""Hint generation utilities for Anki cards."""

import re
import unicodedata
from typing import Dict


def strip_diacritics(text: str) -> str:
    """Remove tone marks from pinyin."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


def pinyin_mask(pinyin: str) -> str:
    """
    Mask pinyin syllables: "xià yǔ" -> "x_ y_"
    """
    if not pinyin:
        return ""
    p = strip_diacritics(pinyin).strip()
    syllables = [s for s in re.split(r"\s+", p) if s]
    masked = []
    for syl in syllables:
        first_letter = syl[0]
        masked.append(f"{first_letter}_")
    return " ".join(masked)


def first_piece(text: str) -> str:
    """Get first piece from pipe-separated text."""
    if not text:
        return ""
    parts = [p.strip() for p in str(text).split("|")]
    return parts[0] if parts else ""


def remove_parentheses(text: str) -> str:
    """Remove content in parentheses from text."""
    if not text:
        return ""
    return re.sub(r'\s*\([^)]*\)', '', text).strip()


def oculta_objetivo_en_texto(texto: str, objetivo: str) -> str:
    """Replace target word with blanks."""
    if not texto or not objetivo:
        return texto or ""
    return texto.replace(objetivo, "___")


def lookup_pos(pos_code: str) -> str:
    """Convert POS code to readable Spanish."""
    if not pos_code:
        return ""
    
    pos_map = {
        "n.": "sustantivo", "v.": "verbo", "adj.": "adjetivo", "adv.": "adverbio",
        "prep.": "preposición", "conj.": "conjunción", "pron.": "pronombre",
        "num.": "numeral", "mw.": "clasificador", "part.": "partícula",
        "interj.": "interjección", "a": "adjetivo", "ad": "adj. adverbial",
        "ag": "morfema adj.", "an": "adj. nominal", "b": "adj. no-predicativo",
        "c": "conjunción", "d": "adverbio", "dg": "morfema adv.",
        "e": "interjección", "f": "localidad direccional", "g": "morfema",
        "h": "prefijo", "i": "modismo", "j": "abreviatura", "k": "sufijo",
        "l": "expresión fija", "m": "numeral", "mg": "morfema num.",
        "n": "sustantivo", "ng": "morfema sust.", "nr": "nombre personal",
        "ns": "nombre de lugar", "nt": "nombre organización", "nx": "cadena nominal",
        "nz": "nombre propio", "o": "onomatopeya", "p": "preposición",
        "q": "clasificador", "r": "pronombre", "rg": "morfema pron.",
        "s": "palabra espacial", "t": "palabra temporal", "tg": "morfema temporal",
        "u": "auxiliar", "v": "verbo", "vd": "verbo adverbial",
        "vg": "morfema verbal", "vn": "verbo nominal", "w": "símbolo/puntuación",
        "x": "no clasificado", "y": "partícula modal", "z": "descriptivo"
    }
    
    parts = []
    for code in pos_code.split(";"):
        code = code.strip()
        if code.startswith("pos:"):
            code = code[4:]
        readable = pos_map.get(code.lower(), code)
        if readable and readable not in parts:
            parts.append(readable)
    
    return ", ".join(parts) if parts else pos_code


def lookup_register(reg_code: str) -> str:
    """Convert register code to readable Spanish."""
    reg_map = {
        "reg:colloquial": "coloquial",
        "reg:neutral": "neutral",
        "reg:formal": "formal",
        "reg:literary": "literario"
    }
    return reg_map.get(reg_code, reg_code)


def lookup_frequency(freq_code: str) -> str:
    """Convert frequency code to readable Spanish."""
    if not freq_code:
        return ""
    parts = []
    for code in freq_code.split(";"):
        code = code.strip()
        if code.startswith("hsk:"):
            level = code.split(":")[1]
            parts.append(f"HSK {level}")
        elif code.startswith("freq:"):
            freq = code.split(":")[1]
            freq_map = {
                "top1k": "muy frecuente (top 1000)",
                "top3k": "frecuente (top 3000)",
                "top5k": "común (top 5000)",
                "top10k": "poco común (top 10k)",
                "rare": "rara"
            }
            parts.append(freq_map.get(freq, freq))
    return ", ".join(parts) if parts else freq_code


def lookup_length(length_code: str) -> str:
    """Convert length code to readable Spanish."""
    if not length_code:
        return ""
    
    if length_code.startswith("length:"):
        length_code = length_code[7:]
    
    if length_code == "char":
        return "1 carácter"
    elif length_code == "word":
        return "palabra"
    
    length_map = {
        "1": "1 carácter", "2": "2 caracteres", "3": "3 caracteres",
        "4": "4 caracteres", "5": "5 caracteres", "5+": "5+ caracteres"
    }
    return length_map.get(length_code, f"{length_code} caracteres")


def build_hints(row: Dict[str, str], hanzi: str, pinyin: str) -> Dict[str, str]:
    """Build hints in 3 phases for progressive revelation."""
    pos = row.get("pos", "").strip()
    register = row.get("register", "").strip()
    collocations = row.get("collocations", "").strip()
    longitud = row.get("longitud", "").strip()
    frecuencia = row.get("frecuencia", "").strip()

    # Phase 1: Basic info
    phase1 = []
    if pos:
        pos_readable = lookup_pos(pos)
        phase1.append(f"Tipo: {pos_readable}")
    if register:
        reg_readable = lookup_register(register)
        phase1.append(f"Registro: {reg_readable}")
    if frecuencia:
        freq_readable = lookup_frequency(frecuencia)
        phase1.append(f"Nivel: {freq_readable}")

    # Phase 2: Collocation hint
    phase2 = ""
    if collocations:
        colloc_first = first_piece(collocations)
        colloc_hint = oculta_objetivo_en_texto(colloc_first, hanzi)
        colloc_hint = remove_parentheses(colloc_hint)
        if colloc_hint:
            phase2 = f"Colocación: {colloc_hint}"

    # Phase 3: Pinyin and length
    phase3 = []
    mask = pinyin_mask(pinyin)
    if mask:
        phase3.append(f"Pinyin: {mask}")
    if longitud:
        longitud_readable = lookup_length(longitud)
        phase3.append(longitud_readable)

    return {
        "hint1": " | ".join(phase1) if phase1 else "",
        "hint2": phase2,
        "hint3": " | ".join(phase3) if phase3 else ""
    }
