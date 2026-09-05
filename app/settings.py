from functools import lru_cache

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
    # Корпус документов: файлы вне git, модель эмбеддингов — та же локальная
    # LM Studio, что и генерация.
    corpus_dir: str = "corpus"
    embedding_model: str = "text-embedding-multilingual-e5-small"
    # Модели семейства E5 обучены на префиксах и без них заметно теряют
    # в качестве: вопрос помечается query, фрагмент — passage.
    embedding_query_prefix: str = "query: "
    embedding_passage_prefix: str = "passage: "
    retrieval_top_k: int = 4
    # Порог косинусной близости не отделяет своё от чужого: у e5 посторонний
    # вопрос набирает столько же, сколько профильный. Релевантность решается
    # тем, сослалась ли модель на фрагмент, а не числом.
    retrieval_min_score: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
