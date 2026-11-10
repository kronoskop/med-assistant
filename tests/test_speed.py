"""Ускоренный конвейер: ответ и уточнения — разные запросы, у каждого свой
потолок длины, промпт без противоречивых правил, отбор не держит сервер."""

import asyncio
import json
import logging
import threading

import httpx
import pytest

from app.corpus.service import get_retriever
from app.llm import AnswerStream, Claims, LLMClient, cited_ids
from app.main import app
from app.schemas import ChatMessage
from app.settings import Settings
from tests.conftest import FakeRetriever, grounded
from tests.test_llm import _completion_body, _transport

FRAGMENT = "doc:ru:1:0"
ANSWER = json.dumps({"answer": f"Тактика по протоколу [{FRAGMENT}]."}, ensure_ascii=False)
CLARIFY = json.dumps(
    {"questions": [{"question": "Какой срок беременности?", "source": FRAGMENT}], "conflicts": []},
    ensure_ascii=False,
)


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def _program(body: dict) -> str:
    return body["response_format"]["json_schema"]["name"]


def _handler(seen: list[dict], *, clarify_status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if _program(body) == "assistant_clarify":
            if clarify_status != 200:
                return httpx.Response(clarify_status, json={"error": "boom"})
            return httpx.Response(200, json=_completion_body(CLARIFY))
        return httpx.Response(200, json=_completion_body(ANSWER))

    return handler


def _complete(seen: list[dict], **settings):
    async def run():
        llm = LLMClient(_settings(**settings), transport=_transport(_handler(seen)))
        return await llm.complete([ChatMessage(role="user", content="вопрос")], f"[{FRAGMENT}] текст")

    return asyncio.run(run())


def test_answer_and_clarifications_are_separate_requests():
    seen: list[dict] = []
    answer = _complete(seen)
    assert sorted(_program(b) for b in seen) == ["assistant_answer", "assistant_clarify"]
    assert answer.source_ids == (FRAGMENT,), "ссылки берутся из маркеров в тексте"
    assert answer.questions[0]["source"] == FRAGMENT


def test_each_request_has_its_own_token_ceiling():
    seen: list[dict] = []
    _complete(seen, answer_max_tokens=321, clarify_max_tokens=123)
    ceilings = {_program(b): b["max_tokens"] for b in seen}
    assert ceilings == {"assistant_answer": 321, "assistant_clarify": 123}
    assert all("max_completion_tokens" not in b for b in seen)


def test_contradicting_format_rule_is_removed_from_prompt():
    seen: list[dict] = []
    _complete(seen)
    for body in seen:
        system = body["messages"][0]["content"]
        assert "<formatting_rules>" not in system
        assert "field name: value" not in system
        # просьба вернуть JSON остаётся: она согласована со схемой
        assert "JSON" in "\n".join(m["content"] for m in body["messages"])


def test_clarifications_can_be_switched_off():
    seen: list[dict] = []
    answer = _complete(seen, clarify_mode="off")
    assert [_program(b) for b in seen] == ["assistant_answer"]
    assert answer.questions == ()


def test_clarifications_after_the_answer_run_in_order():
    seen: list[dict] = []
    _complete(seen, clarify_mode="after")
    assert [_program(b) for b in seen] == ["assistant_answer", "assistant_clarify"]


def test_failed_clarifications_do_not_lose_the_answer(caplog):
    seen: list[dict] = []
    caplog.set_level(logging.WARNING, logger="app.clarify")

    async def run():
        llm = LLMClient(_settings(), transport=_transport(_handler(seen, clarify_status=500)))
        return await llm.complete([ChatMessage(role="user", content="вопрос")], "фрагменты")

    answer = asyncio.run(run())
    assert answer.text.startswith("Тактика")
    assert answer.questions == ()
    assert "вопрос" not in caplog.text, "текст запроса попал в журнал"


def _sse(content: str) -> bytes:
    frames = []
    for piece in (content[i : i + 5] for i in range(0, len(content), 5)):
        chunk = {"choices": [{"index": 0, "delta": {"content": piece}}]}
        frames.append(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")
    frames.append("data: [DONE]\n\n")
    return "".join(frames).encode()


def test_stream_collects_citations_from_text_and_clarifications():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if _program(body) == "assistant_clarify":
            return httpx.Response(200, json=_completion_body(CLARIFY))
        return httpx.Response(200, content=_sse(ANSWER))

    async def run():
        llm = LLMClient(_settings(), transport=_transport(handler))
        claims = Claims()
        stream = await llm.start_chat_stream([ChatMessage(role="user", content="вопрос")], "ф", claims)
        text = "".join([part async for part in stream])
        return text, claims

    text, claims = asyncio.run(run())
    assert text == json.loads(ANSWER)["answer"]
    assert claims.source_ids == [FRAGMENT]
    assert claims.questions and claims.questions[0]["source"] == FRAGMENT


@pytest.mark.parametrize("step", [1, 2, 3, 11])
def test_answer_stream_decodes_any_split(step):
    text = 'Строка\nс "кавычками", \\ слэшем и эмодзи 😀 [a:ru:1:0]'
    raw = json.dumps({"answer": text})
    reader = AnswerStream()
    out = "".join(reader.feed(raw[i : i + step]) for i in range(0, len(raw), step))
    assert out == text


def test_cited_ids_keep_first_mention_order():
    assert cited_ids("а [b:ru:2:0] б [a:ru:1:0] в [b:ru:2:0]") == ("b:ru:2:0", "a:ru:1:0")


def test_retrieval_runs_off_the_event_loop(client, fake_llm):
    retrieval_threads: list[int] = []
    loop_threads: list[int] = []

    class Recording(FakeRetriever):
        def __call__(self, question: str):
            retrieval_threads.append(threading.get_ident())
            return super().__call__(question)

    original = fake_llm.complete

    async def complete(*args, **kwargs):  # корутина модели исполняется в потоке event loop
        loop_threads.append(threading.get_ident())
        return await original(*args, **kwargs)

    fake_llm.complete = complete
    app.dependency_overrides[get_retriever] = lambda: Recording(grounded())
    client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "вопрос"}]})
    assert retrieval_threads and loop_threads
    assert retrieval_threads[0] != loop_threads[0], "отбор фрагментов выполнялся в потоке event loop"


def test_timing_log_carries_no_clinical_text(client, fake_llm, caplog):
    caplog.set_level(logging.INFO, logger="app.timing")
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever(grounded())
    fake_llm.claim_sources = [FRAGMENT]
    client.post(
        "/api/v1/chat",
        json={"stream": True, "messages": [{"role": "user", "content": "СЕКРЕТНЫЙ_СЛУЧАЙ"}]},
    )
    records = [r.getMessage() for r in caplog.records if r.name == "app.timing"]
    assert records and "retrieval_ms=" in records[0] and "first_token_ms=" in records[0]
    assert all("СЕКРЕТНЫЙ_СЛУЧАЙ" not in r for r in records)
