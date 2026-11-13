from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    lmstudio_base_url: str = "http://127.0.0.1:1234/v1"
    lmstudio_model: str = "med-gemma-1.5-4b"
    lmstudio_api_key: str = "lm-studio"
    lmstudio_timeout_seconds: float = 120
    # Рассуждение модели содержит клинический текст запроса, поэтому отладочная
    # запись выключена по умолчанию и включается явно.
    log_model_reasoning: bool = False
    # Потолок длины генерации. Ответ врачу укладывается в несколько абзацев;
    # без потолка редкий разгон модели держит запрос до таймаута.
    # 800 токенов — около 25 с на Mac. Узбекский текст занимает заметно больше
    # токенов, чем русский: при 600 ответы обрывались. Зацикливание
    # останавливает RepeatGuard, а не потолок.
    answer_max_tokens: int = 800
    # Штраф за повтор: MedGemma 4B иногда пишет один абзац по кругу до потолка.
    repeat_penalty: float = 1.1
    clarify_max_tokens: int = 400
    # Уточнения и противоречия считаются отдельным коротким запросом:
    # parallel — вместе с ответом, after — после него (если сервер модели
    # не обрабатывает два запроса одновременно), off — не считаются вовсе.
    clarify_mode: Literal["parallel", "after", "off"] = "parallel"
    # Корпус документов: файлы вне git, модель эмбеддингов — та же локальная
    # LM Studio, что и генерация.
    corpus_dir: str = "corpus"
    # Где считаются эмбеддинги. local — в процессе сервиса исходной моделью
    # с Hugging Face (скачивается один раз, дальше работает без сети); lmstudio —
    # через LM Studio. GGUF-сборка e5-small в LM Studio оказалась сломанной:
    # посторонней фразе она давала близость выше, чем фразе по теме.
    embedding_backend: Literal["local", "lmstudio"] = "local"
    local_embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_model: str = "text-embedding-multilingual-e5-small"
    # Модели семейства E5 обучены на префиксах и без них заметно теряют
    # в качестве: вопрос помечается query, фрагмент — passage.
    embedding_query_prefix: str = "query: "
    embedding_passage_prefix: str = "passage: "
    retrieval_top_k: int = 4
    # Таблицы в выдаче нужны для ссылок, но не должны вытеснять прозу:
    # их содержимое модели не показывается.
    retrieval_max_tables: int = 2
    # Порог косинусной близости не отделяет своё от чужого: у e5 посторонний
    # вопрос набирает столько же, сколько профильный. Релевантность решается
    # тем, сослалась ли модель на фрагмент, а не числом.
    retrieval_min_score: float = 0.0
    # Запасное сопоставление: если модель не поставила ни одной ссылки, каждое
    # предложение ответа сравнивается с отобранными фрагментами, и сноской
    # становится фрагмент, близкий не меньше порога. Такие сноски помечаются
    # (attribution=similarity). 0 — выключено. Порог подбирается по замеру:
    # в журнале app.timing пишется лучшая близость (attribution_best).
    # Замер на kmm 2026-11-13: посторонние вопросы набирали до 0.872, верные
    # ответы — от 0.870 до 0.930. 0.875 отсекает все посторонние ценой трёх
    # верных ответов с самой низкой близостью: ложная опора опаснее отказа.
    attribution_min_score: float = 0.875


@lru_cache
def get_settings() -> Settings:
    return Settings()
