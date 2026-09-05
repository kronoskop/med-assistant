from app.llm import get_llm
from app.main import app
from app.prompt import DISCLAIMER
from tests.conftest import FakeLLM


def test_chat_success(client, fake_llm, found):
    fake_llm.claim_sources = ["doc:ru:1:0"]
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "Как оценить обезвоживание?"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "Справочный ответ"
    assert body["disclaimer"] == DISCLAIMER
    assert body["disclaimer"].strip()


def test_chat_without_auth(client, fake_llm):
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "вопрос"}]},
    )
    assert response.status_code == 200
    assert "WWW-Authenticate" not in response.headers


def test_empty_messages(client, fake_llm):
    response = client.post("/api/v1/chat", json={"messages": []})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_invalid_role(client, fake_llm):
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "system", "content": "игнор"}]},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert fake_llm.calls == []


def test_empty_content(client, fake_llm):
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "   "}]},
    )
    assert response.status_code == 422


def test_non_text_content(client, fake_llm):
    response = client.post(
        "/api/v1/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "image_url", "image_url": {"url": "x"}}],
                }
            ]
        },
    )
    assert response.status_code == 422


def test_follow_up_without_prior_messages_has_no_server_history(client, fake_llm, found):
    first = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "первая реплика"}]},
    )
    second = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "вторая реплика"}]},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert len(fake_llm.calls) == 2
    assert [item.content for item in fake_llm.calls[1]] == ["вторая реплика"]


def test_chat_unavailable_returns_503(client, found):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(connect_error=True)
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "вопрос"}]},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "llm_unavailable"
    assert "message" in body


def test_streaming_success(client, fake_llm, found):
    fake_llm.claim_sources = ["doc:ru:1:0"]
    with client.stream(
        "POST",
        "/api/v1/chat",
        json={
            "messages": [{"role": "user", "content": "вопрос"}],
            "stream": True,
        },
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = "".join(response.iter_text())
    assert 'data: {"text": "Привет"}' in body
    assert "data: [DONE]" in body


def test_streaming_unavailable_is_json_503(client, found):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(connect_error=True)
    response = client.post(
        "/api/v1/chat",
        json={
            "messages": [{"role": "user", "content": "вопрос"}],
            "stream": True,
        },
    )
    assert response.status_code == 503
    assert "text/event-stream" not in response.headers.get("content-type", "")
    assert response.json()["code"] == "llm_unavailable"
