"""Переранжирование кандидатов кросс-энкодером.

Эмбеддинг сжимает вопрос и фрагмент по отдельности; кросс-энкодер читает их
вместе и лучше отличает абзац, который отвечает, от абзаца на ту же тему.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger("app.corpus")
_models: dict[str, object] = {}
_lock = threading.Lock()


def _model(name: str):
    with _lock:
        if name not in _models:
            from sentence_transformers import CrossEncoder

            try:
                _models[name] = CrossEncoder(name, local_files_only=True)
            except Exception:  # noqa: BLE001 — нет в кеше: скачиваем один раз
                logger.info("скачиваю модель переранжирования %s", name)
                _models[name] = CrossEncoder(name)
        return _models[name]


def rerank(question: str, texts: list[str], name: str) -> list[float]:
    if not texts:
        return []
    model = _model(name)
    with _lock:
        scores = model.predict(
            [(question, text) for text in texts], show_progress_bar=False
        )
    return [float(s) for s in scores]
