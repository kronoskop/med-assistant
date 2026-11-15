"""Принятые медиками ответы в выдаче.

Вопрос, совпавший с вопросом принятого уточнения, получает этот ответ
дословно: модель не зовётся. Совпадение — тот же текст с точностью до
регистра и знаков либо смысловая близость не ниже порога.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from fastapi import Depends

from app.review.auth import get_store
from app.review.store import Store, normalize_question
from app.settings import get_settings

logger = logging.getLogger("app.review")


@dataclass(frozen=True)
class Verified:
    refinement_id: int
    text: str
    confirmations: int
    accepted_at: float
    similarity: float
    question: str

    def payload(self) -> dict:
        return {
            "refinement_id": self.refinement_id,
            "confirmations": self.confirmations,
            "accepted_at": self.accepted_at,
            "similarity": round(self.similarity, 3),
            # На какой вопрос этот ответ был принят: врач видит, если его
            # вопрос совпал по смыслу, а не дословно.
            "question": self.question,
        }


class QuestionEmbedder:
    """Вектор вопроса той же моделью, что и поиск по документам."""

    def __init__(self) -> None:
        from app.corpus.embed import model_id

        self.model = model_id(get_settings())

    def __call__(self, question: str) -> np.ndarray:
        from app.corpus.embed import embed_query

        return embed_query(question, get_settings())[0]


def get_question_embedder() -> QuestionEmbedder:
    return QuestionEmbedder()


def safe_embedding(embedder, question: str) -> np.ndarray | None:
    """Модель эмбеддингов недоступна — остаётся точное совпадение вопроса."""
    try:
        return embedder(question)
    except Exception as exc:  # noqa: BLE001
        logger.warning("вектор вопроса не посчитан: %s", type(exc).__name__)
        return None


class VerifiedAnswers:
    def __init__(self, store: Store, embedder) -> None:
        self.store = store
        self.embedder = embedder

    def __call__(self, question: str) -> Verified | None:
        accepted = self.store.accepted_for_matching()
        if not accepted:
            return None  # обычный путь: ни одного лишнего вычисления
        norm = normalize_question(question)
        for row in accepted:  # отсортированы от последнего принятого
            if row["question_norm"] == norm:
                return self._found(row, 1.0)
        threshold = get_settings().verified_min_score
        model = getattr(self.embedder, "model", "")
        candidates = [r for r in accepted if r["embedding"] is not None and r["embedding_model"] == model]
        if threshold <= 0 or not candidates:
            return None
        vector = safe_embedding(self.embedder, question)
        if vector is None:
            return None
        scores = np.stack([r["embedding"] for r in candidates]) @ vector
        # Среди подходящих действует последний принятый, а не самый похожий.
        for row, score in zip(candidates, scores):
            if score >= threshold:
                return self._found(row, float(score))
        return None

    @staticmethod
    def _found(row: dict, score: float) -> Verified:
        return Verified(row["id"], row["text"], row["confirmations"], row["decided_at"], score, row["question"])


def get_verified_answers(
    store: Store = Depends(get_store), embedder=Depends(get_question_embedder)
) -> VerifiedAnswers:
    return VerifiedAnswers(store, embedder)
