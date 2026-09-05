"""Векторные представления фрагментов.

Считает локальная модель в LM Studio: текст вопроса и содержимое корпуса
не покидают машину.
"""

from __future__ import annotations

import httpx
import numpy as np

from app.schemas import AppError
from app.settings import Settings

BATCH = 32


def embed_query(text: str, settings: Settings, **kwargs) -> np.ndarray:
    return embed_texts([text], settings, prefix=settings.embedding_query_prefix, **kwargs)


def embed_passages(texts: list[str], settings: Settings, **kwargs) -> np.ndarray:
    return embed_texts(texts, settings, prefix=settings.embedding_passage_prefix, **kwargs)


def embed_texts(
    texts: list[str],
    settings: Settings,
    *,
    prefix: str = "",
    client: httpx.Client | None = None,
) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    texts = [prefix + text for text in texts] if prefix else texts
    url = settings.lmstudio_base_url.rstrip("/") + "/embeddings"
    vectors: list[list[float]] = []
    owned = client is None
    http = client or httpx.Client(timeout=settings.lmstudio_timeout_seconds)
    try:
        for start in range(0, len(texts), BATCH):
            chunk = texts[start : start + BATCH]
            try:
                response = http.post(url, json={"model": settings.embedding_model, "input": chunk})
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                raise AppError(504, "llm_timeout", "Превышено время ожидания модели эмбеддингов") from exc
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                raise AppError(503, "llm_unavailable", "LM Studio недоступен") from exc
            except httpx.HTTPStatusError as exc:
                raise AppError(502, "llm_error", "Модель эмбеддингов вернула ошибку") from exc
            payload = response.json()
            for item in sorted(payload["data"], key=lambda d: d.get("index", 0)):
                vectors.append(item["embedding"])
    finally:
        if owned:
            http.close()
    matrix = np.asarray(vectors, dtype=np.float32)
    return normalize(matrix)


def normalize(matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms
