import logging

import pytest
from fastapi.testclient import TestClient

from app.llm import get_llm
from app.main import app
from app.schemas import AppError, ChatMessage
from app.settings import get_settings


class FakeLLM:
    def __init__(
        self,
        *,
        connect_error: bool = False,
        reply: str = "Справочный ответ",
        stream_parts: list[str] | None = None,
    ) -> None:
        self.connect_error = connect_error
        self.reply = reply
        self.stream_parts = stream_parts or ["Привет", ", коллега"]
        self.calls: list[list[ChatMessage]] = []

    async def complete(self, messages: list[ChatMessage]) -> str:
        if self.connect_error:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен")
        self.calls.append(list(messages))
        return self.reply

    async def start_chat_stream(self, messages: list[ChatMessage]):
        if self.connect_error:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен")
        self.calls.append(list(messages))

        async def gen():
            for part in self.stream_parts:
                yield part

        return gen()

    async def ping(self) -> None:
        if self.connect_error:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен")


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    app.dependency_overrides.clear()


@pytest.fixture
def fake_llm() -> FakeLLM:
    llm = FakeLLM()
    app.dependency_overrides[get_llm] = lambda: llm
    return llm


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def caplog_access(caplog):
    caplog.set_level(logging.INFO, logger="app.access")
    return caplog
