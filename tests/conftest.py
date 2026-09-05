import logging

import pytest
from fastapi.testclient import TestClient

from app.corpus.chunks import Fragment
from app.corpus.index import Hit
from app.corpus.manifest import Document, Edition, EvidenceLevel
from app.corpus.service import Grounding, Retrieval, get_retriever
from app.llm import Answer, get_llm, reset_compatibility_cache
from app.main import app
from app.schemas import AppError, ChatMessage
from app.settings import get_settings


class FakeLLM:
    def __init__(
        self,
        *,
        connect_error: bool = False,
        incompatible: bool = False,
        reply: str = "Справочный ответ",
        stream_parts: list[str] | None = None,
    ) -> None:
        self.connect_error = connect_error
        self.incompatible = incompatible
        self.compat_checks = 0
        self.fragments: list[str] = []
        self.claim_sources: list[str] = []
        self.reply = reply
        self.stream_parts = stream_parts or ["Привет", ", коллега"]
        self.calls: list[list[ChatMessage]] = []

    async def complete(self, messages: list[ChatMessage], fragments: str = "") -> Answer:
        if self.connect_error:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен")
        self.calls.append(list(messages))
        self.fragments.append(fragments)
        return Answer(self.reply, tuple(self.claim_sources))

    async def start_chat_stream(self, messages: list[ChatMessage], fragments: str = "", source_ids=None):
        if self.connect_error:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен")
        self.calls.append(list(messages))
        self.fragments.append(fragments)
        if source_ids is not None:
            source_ids.extend(self.claim_sources)

        async def gen():
            for part in self.stream_parts:
                yield part

        return gen()

    async def ping(self) -> None:
        if self.connect_error:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен")

    async def check_structured_output(self) -> None:
        if self.connect_error:
            raise AppError(503, "llm_unavailable", "LM Studio недоступен")
        if self.incompatible:
            raise AppError(
                503, "model_incompatible", "Модель не принимает структурированный вывод по схеме"
            )
        self.compat_checks += 1


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    reset_compatibility_cache()
    yield
    get_settings.cache_clear()
    reset_compatibility_cache()
    app.dependency_overrides.clear()


@pytest.fixture
def fake_llm() -> FakeLLM:
    llm = FakeLLM()
    app.dependency_overrides[get_llm] = lambda: llm
    return llm


def make_hit(document_id: str = "doc", fragment_id: str | None = None, text: str = "Фрагмент протокола.") -> Hit:
    document = Document(
        id=document_id,
        title="Стандарт центра",
        origin="РСНПМЦЗМиР",
        level=EvidenceLevel.BASE,
        revision="2025-10-09",
        editions=(Edition("ru", "https://example.invalid/doc.pdf", "doc.pdf"),),
    )
    fragment = Fragment(
        id=fragment_id or f"{document_id}:ru:1:0",
        document_id=document_id,
        language="ru",
        page=1,
        ordinal=0,
        section="4.2",
        text=text,
    )
    return Hit(fragment, document, 0.9)


def make_support(document_id: str = "who-doc") -> Document:
    return Document(
        id=document_id,
        title="WHO recommendations",
        origin="Всемирная организация здравоохранения",
        level=EvidenceLevel.SUPPORT,
        revision="2016",
        editions=(Edition("en", "https://example.invalid/who"),),
    )


def grounded(*hits: Hit, support: tuple[Document, ...] = ()) -> Retrieval:
    return Retrieval(Grounding.GROUNDED, hits or (make_hit(),), support)


class FakeRetriever:
    """Подменный отбор: тесты не ходят ни в корпус, ни в модель эмбеддингов."""

    def __init__(self, retrieval: Retrieval | None = None) -> None:
        self.retrieval = retrieval or Retrieval(Grounding.EMPTY_CORPUS)
        self.questions: list[str] = []

    def __call__(self, question: str) -> Retrieval:
        self.questions.append(question)
        return self.retrieval


@pytest.fixture
def found() -> FakeRetriever:
    """Отбор нашёл фрагмент основы — только тогда в дело вступает модель."""
    retriever = FakeRetriever(grounded())
    app.dependency_overrides[get_retriever] = lambda: retriever
    return retriever


@pytest.fixture
def client() -> TestClient:
    # Проверка совместимости модели выполняется на старте приложения, поэтому
    # подмена ставится до входа в TestClient: тесты не должны ходить в сеть.
    app.dependency_overrides.setdefault(get_llm, lambda: FakeLLM())
    app.dependency_overrides.setdefault(get_retriever, lambda: FakeRetriever())
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def caplog_access(caplog):
    caplog.set_level(logging.INFO, logger="app.access")
    return caplog
