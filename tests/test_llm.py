import ast
import asyncio
import json
import logging
from pathlib import Path

import httpx

from app.llm import LLMClient, format_conversation
from app.prompt import SYSTEM_PROMPT
from app.schemas import AppError, ChatMessage
from app.settings import Settings

ANSWER_OK = '{"answer": "ok", "sources": []}'


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
    assert answer.text == "ok"
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
            b'"choices":[{"index":0,"delta":{"content":"\\", \\"sources\\": []}"}}]}\n\n'
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


# ── форма исходящего запроса ──────────────────────────────────────────────
# Дефект дожил до рабочей машины потому, что тесты проверяли `model` и
# `base_url`, но не то, как выглядит тело запроса.


def _capture_request(content: str = ANSWER_OK) -> dict:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion_body(content))

    async def run():
        llm = LLMClient(_settings(), transport=_transport(handler))
        return await llm.complete([ChatMessage(role="user", content="вопрос")])

    captured["answer"] = _run(run()).text
    return captured


def test_outgoing_request_roles_alternate():
    body = _capture_request()["body"]
    roles = [message["role"] for message in body["messages"]]
    assert roles, "запрос без сообщений"
    assert all(a != b for a, b in zip(roles, roles[1:])), roles


def test_outgoing_request_carries_answer_schema():
    body = _capture_request()["body"]
    response_format = body.get("response_format")
    assert response_format is not None, "схема ответа не отправлена"
    assert response_format["type"] == "json_schema"
    schema = response_format["json_schema"]["schema"]
    assert schema["properties"]["answer"] == {"type": "string"}
    assert schema["properties"]["sources"] == {"type": "array", "items": {"type": "string"}}
    assert schema["required"] == ["answer", "sources"]


def test_outgoing_request_never_asks_for_json_object():
    body = _capture_request()["body"]
    assert "json_object" not in json.dumps(body)


def test_merging_preserves_every_prompt_fragment():
    body = _capture_request()["body"]
    merged = "\n".join(message["content"] for message in body["messages"])
    assert SYSTEM_PROMPT in merged
    assert "вопрос" in merged
    # инструкция о форме ответа приходит от Ax отдельным сообщением и не должна
    # потеряться при склейке ролей
    assert "JSON" in merged.upper()


def test_unparsable_model_output_is_not_returned_as_answer():
    prose = "thought\nМодель начала рассуждать вместо ответа"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_body(prose))

    async def run():
        llm = LLMClient(_settings(), transport=_transport(handler))
        return await llm.complete([ChatMessage(role="user", content="вопрос")])

    try:
        answer = _run(run())
    except AppError as exc:
        assert exc.status_code == 502
        assert exc.code == "llm_error"
    else:
        raise AssertionError(f"неразобранный ответ выдан как текст ассистента: {answer!r}")


# ── проверка совместимости модели ─────────────────────────────────────────


def test_structured_output_probe_sends_schema_and_is_cheap():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion_body())

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            llm = LLMClient(_settings(), http_client=http_client)
            await llm.check_structured_output()

    _run(run())
    assert captured["url"].endswith("/chat/completions")
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert captured["body"]["max_tokens"] == 1


def test_model_rejecting_schema_maps_to_model_incompatible():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "response_format not supported"})

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            llm = LLMClient(_settings(), http_client=http_client)
            await llm.check_structured_output()

    try:
        _run(run())
    except AppError as exc:
        assert exc.code == "model_incompatible"
        assert exc.status_code == 503
    else:
        raise AssertionError("несовместимая модель не распознана")


def test_unreachable_lmstudio_probe_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            llm = LLMClient(_settings(), http_client=http_client)
            await llm.check_structured_output()

    try:
        _run(run())
    except AppError as exc:
        assert exc.code == "llm_unavailable"
    else:
        raise AssertionError("недоступность LM Studio не распознана")


# ── отладочное рассуждение модели ─────────────────────────────────────────
# Рассуждение — клинический текст о случае пациента, поэтому запись выключена
# по умолчанию и никогда не попадает ни в ответ API, ни в журнал обращений.

REASONING = "PHI_REASONING_MARKER размышление о случае пациента"


def _body_with_reasoning() -> dict:
    body = _completion_body()
    body["choices"][0]["message"]["reasoning_content"] = REASONING
    return body


def _complete_with_reasoning(**settings_kwargs):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_body_with_reasoning())

    async def run():
        llm = LLMClient(_settings(**settings_kwargs), transport=_transport(handler))
        return await llm.complete([ChatMessage(role="user", content="вопрос")])

    return _run(run())


def test_reasoning_is_not_recorded_by_default(caplog):
    caplog.set_level(logging.DEBUG)
    assert _complete_with_reasoning().text == "ok"
    assert REASONING not in caplog.text


def test_reasoning_is_recorded_when_explicitly_enabled(caplog):
    caplog.set_level(logging.DEBUG, logger="app.reasoning")
    assert _complete_with_reasoning(log_model_reasoning=True).text == "ok"
    assert REASONING in caplog.text


def test_reasoning_never_reaches_the_access_log(caplog):
    caplog.set_level(logging.DEBUG, logger="app.access")
    _complete_with_reasoning(log_model_reasoning=True)
    access_records = [r for r in caplog.records if r.name == "app.access"]
    assert all(REASONING not in r.getMessage() for r in access_records)


def test_reasoning_is_not_part_of_the_answer():
    assert REASONING not in _complete_with_reasoning(log_model_reasoning=True).text
