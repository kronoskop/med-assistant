import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.llm import get_llm, reset_compatibility_cache
from app.main import app
from tests.conftest import FakeLLM


def test_ready_reports_incompatible_model(client):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(incompatible=True)
    reset_compatibility_cache()   # как после истечения TTL проверки
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["code"] == "model_incompatible"
    assert "message" in body


def test_ready_checks_model_not_only_liveness(fake_llm, client):
    reset_compatibility_cache()
    response = client.get("/ready")
    assert response.status_code == 200
    assert fake_llm.compat_checks >= 1, "проверка совместимости модели не выполнялась"


def test_startup_stops_on_incompatible_model():
    app.dependency_overrides[get_llm] = lambda: FakeLLM(incompatible=True)
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


def test_startup_survives_unavailable_lmstudio(caplog):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(connect_error=True)
    caplog.set_level(logging.WARNING, logger="app.startup")
    with TestClient(app) as test_client:
        assert test_client.get("/health").status_code == 200
    assert "llm_unavailable" in caplog.text


def test_chat_response_carries_no_model_reasoning(client, fake_llm):
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "вопрос"}]},
    )
    assert response.status_code == 200
    assert "reasoning" not in response.text.lower()
    assert {"message", "disclaimer"} <= set(response.json())
    assert "reasoning" not in json.dumps(response.json(), ensure_ascii=False).lower()
