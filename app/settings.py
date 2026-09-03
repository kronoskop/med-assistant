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


@lru_cache
def get_settings() -> Settings:
    return Settings()
