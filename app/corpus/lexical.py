"""Поиск по словам (BM25) рядом с векторным.

Векторный поиск хорошо находит документ по смыслу, но промахивается мимо
абзаца с конкретикой: порогом «110 г/л», названием препарата, сроком. Слова
и числа в таких абзацах совпадают с вопросом буквально, и BM25 их достаёт.

Морфология русского и узбекского закрывается грубо, но без словарей: слово
обрезается до первых `STEM` букв («беременных», «беременности» → «беремен»).
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

import numpy as np

STEM = 6
K1 = 1.2
B = 0.75

_TOKEN = re.compile(r"[^\W_]+(?:[ʻʼ'’`][^\W_]+)*", re.UNICODE)
# Служебные слова не различают фрагменты, а вопрос ими полон.
_STOP = {
    "и",
    "в",
    "во",
    "на",
    "с",
    "со",
    "по",
    "при",
    "для",
    "не",
    "что",
    "как",
    "какой",
    "какая",
    "какие",
    "каков",
    "ли",
    "или",
    "у",
    "к",
    "о",
    "об",
    "от",
    "до",
    "из",
    "за",
    "это",
    "так",
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "for",
    "to",
    "and",
    "or",
    "is",
    "are",
    "what",
    "which",
    "how",
    "when",
    "with",
    "by",
    "be",
    "at",
    "va",
    "bilan",
    "uchun",
    "qanday",
    "nima",
    "qachon",
}


def tokens(text: str) -> list[str]:
    out = []
    for raw in _TOKEN.findall(text.lower()):
        word = re.sub(r"[ʻʼ'’`]", "", raw)
        if word in _STOP:
            continue
        out.append(word if word.isdigit() else word[:STEM])
    return out


class LexicalIndex:
    """Обратный индекс по фрагментам; оценки считаются массивом на весь корпус."""

    def __init__(self, texts: list[str]) -> None:
        self.size = len(texts)
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        lengths = np.zeros(self.size, dtype=np.float32)
        for doc, text in enumerate(texts):
            counts = Counter(tokens(text))
            lengths[doc] = sum(counts.values())
            for term, tf in counts.items():
                postings[term].append((doc, tf))
        self.avg = float(lengths.mean()) if self.size else 0.0
        self.norm = K1 * (1 - B + B * lengths / (self.avg or 1.0))
        self.postings = {
            term: (
                np.array([d for d, _ in items], dtype=np.int32),
                np.array([t for _, t in items], dtype=np.float32),
            )
            for term, items in postings.items()
        }

    def scores(self, query: str) -> np.ndarray:
        out = np.zeros(self.size, dtype=np.float32)
        for term in set(tokens(query)):
            found = self.postings.get(term)
            if found is None:
                continue
            docs, tf = found
            idf = math.log(1 + (self.size - len(docs) + 0.5) / (len(docs) + 0.5))
            out[docs] += idf * tf * (K1 + 1) / (tf + self.norm[docs])
        return out


def fuse(
    vector: np.ndarray, lexical: np.ndarray, *, depth: int, k: int = 60
) -> list[int]:
    """Слияние двух рейтингов по рангу (reciprocal rank fusion): оценки BM25 и
    косинуса несравнимы, а места в выдаче — сравнимы."""
    total: dict[int, float] = defaultdict(float)
    for rank, position in enumerate(np.argsort(-vector)[:depth]):
        total[int(position)] += 1.0 / (k + rank + 1)
    for rank, position in enumerate(np.argsort(-lexical)[:depth]):
        if lexical[position] <= 0:
            break  # дальше фрагменты без единого общего слова
        total[int(position)] += 1.0 / (k + rank + 1)
    return sorted(total, key=lambda p: -total[p])
