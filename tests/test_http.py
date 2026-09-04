import logging

from app.llm import get_llm
from app.main import app
from tests.conftest import FakeLLM


def test_health_ok_json(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "ok"}
    assert "<html" not in response.text.lower()


def test_chat_response_is_json_not_html(client, fake_llm):
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "Вопрос"}]},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "<html" not in response.text.lower()


def test_unknown_path_json_404(client):
    response = client.get("/no-such-route")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert "message" in body


def test_health_does_not_need_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert "WWW-Authenticate" not in response.headers


def test_malformed_json_is_json_error(client, fake_llm):
    response = client.post(
        "/api/v1/chat",
        content="{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "message" in body


def test_ready_when_lmstudio_up(client, fake_llm):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_when_lmstudio_down(client):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(connect_error=True)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["code"] == "llm_unavailable"


def test_access_log_omits_chat_body(client, fake_llm, caplog):
    secret = "SECRET_PHI_TOKEN_XYZ"
    caplog.set_level(logging.INFO, logger="app.access")
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": secret}]},
    )
    assert response.status_code == 200
    assert secret not in caplog.text
    assert "POST" in caplog.text
    assert "/api/v1/chat" in caplog.text
