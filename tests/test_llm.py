import asyncio
import json

import httpx

from app.llm import LLMClient
from app.prompt import SYSTEM_PROMPT
from app.schemas import AppError, ChatMessage
from app.settings import Settings

COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 1,
    "model": "med-gemma-1.5-4b",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "ok"},
            "finish_reason": "stop",
        }
    ],
}


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def _run(coro):
    return asyncio.run(coro)


def test_completion_sends_configured_model():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=COMPLETION)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            llm = LLMClient(_settings(lmstudio_model="custom-med-model"), http_client)
            await llm.complete([ChatMessage(role="user", content="вопрос")])

    _run(run())
    assert captured["body"]["model"] == "custom-med-model"
    assert captured["body"]["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert "127.0.0.1:1234" in captured["url"]
    assert "api.openai.com" not in captured["url"]


def test_default_model_id():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=COMPLETION)
        return httpx.Response(200, json={"data": []})

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            llm = LLMClient(_settings(), http_client)
            await llm.complete([ChatMessage(role="user", content="вопрос")])

    _run(run())
    assert captured["body"]["model"] == "med-gemma-1.5-4b"


def test_connection_error_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            llm = LLMClient(_settings(), http_client)
            await llm.complete([ChatMessage(role="user", content="вопрос")])

    try:
        _run(run())
    except AppError as exc:
        assert exc.status_code == 503
        assert exc.code == "llm_unavailable"
    else:
        raise AssertionError("expected AppError")


def test_timeout_maps_to_llm_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            llm = LLMClient(_settings(), http_client)
            await llm.complete([ChatMessage(role="user", content="вопрос")])

    try:
        _run(run())
    except AppError as exc:
        assert exc.status_code == 504
        assert exc.code == "llm_timeout"
    else:
        raise AssertionError("expected AppError")


def test_upstream_http_error_maps_to_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "model not found"}})

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            llm = LLMClient(_settings(), http_client)
            await llm.complete([ChatMessage(role="user", content="вопрос")])

    try:
        _run(run())
    except AppError as exc:
        assert exc.status_code == 502
        assert exc.code == "llm_error"
        assert "sk-" not in exc.message
    else:
        raise AssertionError("expected AppError")


def test_ping_uses_models_list_not_completion():
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(f"{request.method} {request.url.path}")
        if request.method == "GET" and request.url.path.endswith("/models"):
            return httpx.Response(200, json={"object": "list", "data": []})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            llm = LLMClient(_settings(), http_client)
            await llm.ping()

    _run(run())
    assert any(item.startswith("GET ") and item.endswith("/models") for item in paths)


def test_build_messages_does_not_keep_server_history():
    llm = LLMClient(_settings())
    first = llm.build_messages([ChatMessage(role="user", content="первый")])
    second = llm.build_messages([ChatMessage(role="user", content="второй")])
    assert first[1]["content"] == "первый"
    assert second[1]["content"] == "второй"
    assert all(item["content"] != "первый" for item in second[1:])
