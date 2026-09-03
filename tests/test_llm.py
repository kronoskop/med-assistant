import ast
import asyncio
import json
from pathlib import Path

import httpx

from app.llm import LLMClient, format_conversation
from app.prompt import SYSTEM_PROMPT
from app.schemas import AppError, ChatMessage
from app.settings import Settings

ANSWER_OK = '{"answer": "ok"}'


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def _run(coro):
    return asyncio.run(coro)


def _completion_body(content: str = ANSWER_OK) -> dict:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "med-gemma-1.5-4b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def _transport(handler):
    def transport(call: dict):
        request = httpx.Request(
            call["method"],
            call["url"],
            headers=call.get("headers"),
            json=call.get("json"),
        )
        try:
            response = handler(request)
        except httpx.ConnectError as exc:
            raise OSError(str(exc)) from exc
        except httpx.ReadTimeout as exc:
            raise TimeoutError(str(exc)) from exc
        if call.get("stream"):
            return [response.content]
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = response.text
        return {"status": response.status_code, "json": body}

    return transport


def test_completion_sends_configured_model():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion_body())

    async def run():
        llm = LLMClient(
            _settings(lmstudio_model="custom-med-model"),
            transport=_transport(handler),
        )
        return await llm.complete([ChatMessage(role="user", content="вопрос")])

    answer = _run(run())
    assert answer == "ok"
    assert captured["body"]["model"] == "custom-med-model"
    assert "127.0.0.1:1234" in captured["url"]
    assert "api.openai.com" not in captured["url"]
    assert captured["body"]["messages"][0]["role"] == "system"
    assert SYSTEM_PROMPT in captured["body"]["messages"][0]["content"]


def test_default_model_id():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion_body())

    async def run():
        llm = LLMClient(_settings(), transport=_transport(handler))
        await llm.complete([ChatMessage(role="user", content="вопрос")])

    _run(run())
    assert captured["body"]["model"] == "med-gemma-1.5-4b"


def test_conversation_history_is_program_input():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion_body())

    messages = [
        ChatMessage(role="user", content="первая"),
        ChatMessage(role="assistant", content="ответ"),
        ChatMessage(role="user", content="уточнение"),
    ]

    async def run():
        llm = LLMClient(_settings(), transport=_transport(handler))
        await llm.complete(messages)

    _run(run())
    user_contents = [
        item["content"]
        for item in captured["body"]["messages"]
        if item["role"] == "user"
    ]
    joined = "\n".join(user_contents)
    assert "user: первая" in joined
    assert "assistant: ответ" in joined
    assert "user: уточнение" in joined
    assert SYSTEM_PROMPT in captured["body"]["messages"][0]["content"]


def test_format_conversation_does_not_keep_server_history():
    first = format_conversation([ChatMessage(role="user", content="первый")])
    second = format_conversation([ChatMessage(role="user", content="второй")])
    assert "первый" in first
    assert "второй" in second
    assert "первый" not in second


def test_connection_error_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    async def run():
        llm = LLMClient(_settings(), transport=_transport(handler))
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
        llm = LLMClient(_settings(), transport=_transport(handler))
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
        llm = LLMClient(_settings(), transport=_transport(handler))
        await llm.complete([ChatMessage(role="user", content="вопрос")])

    try:
        _run(run())
    except AppError as exc:
        assert exc.status_code == 502
        assert exc.code == "llm_error"
        assert "sk-" not in exc.message
    else:
        raise AssertionError("expected AppError")


def test_empty_program_output_maps_to_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_body('{"answer": ""}'))

    async def run():
        llm = LLMClient(_settings(), transport=_transport(handler))
        await llm.complete([ChatMessage(role="user", content="вопрос")])

    try:
        _run(run())
    except AppError as exc:
        assert exc.status_code == 502
        assert exc.code == "llm_error"
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


def test_stream_yields_answer_text():
    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"id":"1","object":"chat.completion.chunk",'
            b'"choices":[{"index":0,"delta":{"content":"{\\"answer\\": \\""}}]}\n\n'
            b'data: {"id":"1","object":"chat.completion.chunk",'
            b'"choices":[{"index":0,"delta":{"content":"ok"}}]}\n\n'
            b'data: {"id":"1","object":"chat.completion.chunk",'
            b'"choices":[{"index":0,"delta":{"content":"\\"}"}}]}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body)

    async def run():
        llm = LLMClient(_settings(), transport=_transport(handler))
        stream = await llm.start_chat_stream([ChatMessage(role="user", content="вопрос")])
        return "".join([part async for part in stream])

    assert _run(run()) == "ok"


def test_chat_module_has_no_optimizer_or_agents():
    tree = ast.parse(Path("app/llm.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "axllm":
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            imported.add(node.func.id)
    assert "AxGEPA" not in imported
    assert "optimize" not in imported
    assert "agent" not in imported
    assert "AxMCPClient" not in imported
    assert "ax" in imported
    assert "OpenAICompatibleClient" in imported
