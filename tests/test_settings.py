from app.settings import Settings


def test_default_settings():
    settings = Settings(_env_file=None)
    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8000
    assert settings.lmstudio_base_url == "http://127.0.0.1:1234/v1"
    assert settings.lmstudio_model == "med-gemma-1.5-4b"
    assert settings.lmstudio_api_key == "lm-studio"
    assert settings.lmstudio_timeout_seconds == 120


def test_lmstudio_env_override(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_BASE_URL", "http://lm.internal:1234/v1")
    monkeypatch.setenv("LMSTUDIO_MODEL", "custom-med-model")
    monkeypatch.setenv("LMSTUDIO_TIMEOUT_SECONDS", "30")
    settings = Settings(_env_file=None)
    assert settings.lmstudio_base_url == "http://lm.internal:1234/v1"
    assert settings.lmstudio_model == "custom-med-model"
    assert settings.lmstudio_timeout_seconds == 30
