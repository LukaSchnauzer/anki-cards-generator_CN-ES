"""Conversión de frecuencia numérica a bucket legible (top1k, top3k, ...).

Cálculo puro y determinístico a partir de words.frequency_rank — no depende
del LLM ni se persiste; se calcula al armar cada tarjeta.
"""

from typing import Optional


def get_freq_bucket(rank: Optional[int]) -> Optional[str]:
    if not rank or rank <= 0:
        return None
    if rank <= 1000:
        return "top1k"
    if rank <= 3000:
        return "top3k"
    if rank <= 5000:
        return "top5k"
    if rank <= 10000:
        return "top10k"
    return "rare"
