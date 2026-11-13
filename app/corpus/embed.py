"""Векторные представления фрагментов.

Считает локальная модель — в процессе сервиса или в LM Studio: текст вопроса
и содержимое корпуса не покидают машину. Из сети один раз скачиваются только
веса модели.
"""

from __future__ import annotations

import logging
import threading

import httpx
import numpy as np

from app.schemas import AppError
from app.settings import Settings

BATCH = 32

# Один клиент на процесс: соединение с LM Studio переиспользуется между
# вопросами, а не открывается заново на каждый эмбеддинг вопроса врача.
_shared: dict[float, httpx.Client] = {}


def _shared_client(timeout: float) -> httpx.Client:
    if timeout not in _shared:
        _shared[timeout] = httpx.Client(timeout=timeout)
    return _shared[timeout]


logger = logging.getLogger("app.embed")

_models: dict[str, object] = {}
_model_lock = threading.Lock()


def _local_model(name: str):
    """Модель загружается один раз на процесс. Сначала — только из локального
    кеша, чтобы рабочий сервис не ходил в сеть; при первом запуске — скачивание."""
    with _model_lock:
        if name not in _models:
            from sentence_transformers import SentenceTransformer

            try:
                _models[name] = SentenceTransformer(name, device="cpu", local_files_only=True)
            except Exception:  # noqa: BLE001 — в кеше нет: скачиваем
                logger.info("скачиваю модель эмбеддингов %s", name)
                _models[name] = SentenceTransformer(name, device="cpu")
        return _models[name]


def model_id(settings: Settings) -> str:
    """Чем считались векторы: индекс и вопрос обязаны совпадать."""
    if settings.embedding_backend == "local":
        return f"local:{settings.local_embedding_model}"
    return f"lmstudio:{settings.embedding_model}"


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
    if settings.embedding_backend == "local":
        model = _local_model(settings.local_embedding_model)
        with _model_lock:  # один прогон модели за раз: так проще и предсказуемее по памяти
            matrix = model.encode(texts, batch_size=BATCH, convert_to_numpy=True, show_progress_bar=False)
        return normalize(np.asarray(matrix, dtype=np.float32))
    url = settings.lmstudio_base_url.rstrip("/") + "/embeddings"
    vectors: list[list[float]] = []
    http = client or _shared_client(settings.lmstudio_timeout_seconds)
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
    matrix = np.asarray(vectors, dtype=np.float32)
    return normalize(matrix)


def normalize(matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


# Пара для проверки: фраза по теме обязана быть ближе к вопросу, чем чужая.
# Сломанная модель (неверное усреднение, не та сборка) этого не делает, и
# поиск молча превращается в случайный.
_PROBE_QUERY = "анемия у беременных, уровень гемоглобина"
_PROBE_RELATED = "Железодефицитная анемия у беременных: гемоглобин ниже 110 г/л."
_PROBE_UNRELATED = "Кесарево сечение при поперечном положении плода."


def check_quality(settings: Settings, **kwargs) -> tuple[float, float]:
    """Близость фразы по теме и чужой фразы к проверочному вопросу.

    Бросает AppError, если модель ставит чужое не ниже своего.
    """
    query = embed_query(_PROBE_QUERY, settings, **kwargs)[0]
    passages = embed_passages([_PROBE_RELATED, _PROBE_UNRELATED], settings, **kwargs)
    related, unrelated = float(passages[0] @ query), float(passages[1] @ query)
    if related - unrelated < 0.02:
        raise AppError(
            503,
            "embedding_broken",
            f"Модель эмбеддингов {model_id(settings)} не различает смысл: "
            f"фраза по теме {related:.3f}, чужая {unrelated:.3f}",
        )
    return related, unrelated
