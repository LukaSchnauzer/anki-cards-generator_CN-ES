"""Pinyin de referencia determinístico (pypinyin), usado para anclar los
guardrails de pinyin en un dato concreto en vez de pedirle al LLM que
recuerde tonos de memoria — eso resultó ser poco confiable incluso para
input idéntico repetido (ver memoria project-pinyin-guardrail-hallucination).

pypinyin usa un diccionario de frases + fallback por carácter — para la
lectura MÁS COMÚN de una palabra (lo que marcamos is_primary=true en
word_prep) es una referencia sólida. No sirve para verificar lecturas
secundarias/polífonas legítimas, que por definición no son "la más común".
"""

from typing import List

from pypinyin import Style, pinyin


def reference_pinyin(hanzi: str) -> str:
    """Pinyin más común para `hanzi` (carácter o frase), tonos con diacríticos,
    sílabas separadas por espacio."""
    segments = pinyin(hanzi, style=Style.TONE, heteronym=False)
    return " ".join(seg[0] for seg in segments)


def reference_pinyin_candidates(hanzi: str) -> List[str]:
    """Todas las lecturas conocidas de un carácter SUELTO (heteronym=True) —
    útil para validar lecturas secundarias/polífonas de un solo hanzi. Para
    frases de varios caracteres, pypinyin no da combinaciones completas, así
    que devuelve solo la más común (igual que reference_pinyin)."""
    segments = pinyin(hanzi, style=Style.TONE, heteronym=True)
    if len(segments) == 1:
        return segments[0]
    return [reference_pinyin(hanzi)]
