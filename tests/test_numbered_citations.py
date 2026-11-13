"""Ссылки номерами: маленькая модель не переписывает длинные идентификаторы
фрагментов и просто их опускает, а номер [2] ставит. Сервер переводит номер
обратно в идентификатор; если ссылок нет вовсе — сопоставляет сам и помечает это."""

import asyncio
import json

import httpx
import numpy as np
import pytest

from app.answer import (
    MarkerRewriter,
    confirmed_questions,
    numbered_to_ids,
    question_language,
)
from app.corpus import embed
from app.corpus.service import attribute, get_retriever
from app.llm import LLMClient, get_llm
from app.main import app
from app.schemas import AppError, ChatMessage
from app.settings import Settings
from tests.conftest import FakeLLM, FakeRetriever, grounded, make_hit
from tests.test_llm import _completion_body, _transport

A = make_hit("a", text="Анемия: гемоглобин ниже 110 г/л.")
B = make_hit("b", text="Монохориальная двойня: УЗИ каждые 2 недели.")
HITS = (A, B)


def _frames(response) -> list[dict]:
    out = []
    for line in response.text.splitlines():
        if line.startswith("data:") and line[5:].strip() != "[DONE]":
            out.append(json.loads(line[5:]))
    return out


def test_numbers_become_fragment_ids():
    text = "Анемия ниже 110 г/л [1]. УЗИ каждые 2 недели [2]. Оба [1, 2]. Чужой [7]."
    assert numbered_to_ids(text, HITS) == (
        "Анемия ниже 110 г/л [a:ru:1:0]. УЗИ каждые 2 недели [b:ru:1:0]. "
        "Оба [a:ru:1:0][b:ru:1:0]. Чужой ."
    )


@pytest.mark.parametrize("step", [1, 2, 3, 5])
def test_rewriter_handles_markers_split_between_chunks(step):
    raw = "Гемоглобин [1]. Двойня [2]; диапазон [10-20 мг] остаётся."
    rewriter = MarkerRewriter(HITS)
    out = (
        "".join(rewriter.feed(raw[i : i + step]) for i in range(0, len(raw), step))
        + rewriter.flush()
    )
    assert (
        out == "Гемоглобин [a:ru:1:0]. Двойня [b:ru:1:0]; диапазон [10-20 мг] остаётся."
    )


def test_question_source_may_be_a_number():
    claimed = [
        {"question": "Срок беременности?", "source": "2"},
        {"question": "Вес?", "source": "[9]"},
    ]
    out = confirmed_questions(claimed, HITS)
    assert [q.source.id for q in out] == ["b:ru:1:0"]


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("Какой порог гемоглобина у беременных?", "ru"),
        ("Homiladorlikda anemiya qanday davolanadi?", "uz"),
        ("Gemoglobin darajasi qachon past hisoblanadi?", "uz"),
        ("What is the haemoglobin threshold in pregnancy?", "en"),
    ],
)
def test_question_language(text, lang):
    assert question_language(text) == lang


def _use(llm: FakeLLM, retriever) -> None:
    app.dependency_overrides[get_retriever] = lambda: retriever
    app.dependency_overrides[get_llm] = lambda: llm


def test_stream_with_numbers_is_grounded(client):
    llm = FakeLLM(stream_parts=["Анемия ниже 110 г/л [", "1]. Двойня [2", "]."])
    _use(llm, FakeRetriever(grounded(*HITS)))
    response = client.post(
        "/api/v1/chat",
        json={"stream": True, "messages": [{"role": "user", "content": "Анемия?"}]},
    )
    frames = _frames(response)
    text = "".join(f["text"] for f in frames if "text" in f)
    assert text == "Анемия ниже 110 г/л [a:ru:1:0]. Двойня [b:ru:1:0]."
    final = frames[-1]
    assert final["grounded"] is True
    assert final["attribution"] == "model"
    assert [s["id"] for s in final["sources"]] == ["a:ru:1:0", "b:ru:1:0"]


class Attributing(FakeRetriever):
    def __init__(self, retrieval, found):
        super().__init__(retrieval)
        self.found = found
        self.texts: list[str] = []

    def attribute(self, text, hits):
        self.texts.append(text)
        return self.found, 0.91


def test_stream_without_markers_falls_back_to_similarity(client):
    llm = FakeLLM(stream_parts=["Анемия — гемоглобин ниже 110 г/л."])
    retriever = Attributing(grounded(*HITS), ["a:ru:1:0"])
    _use(llm, retriever)
    response = client.post(
        "/api/v1/chat",
        json={"stream": True, "messages": [{"role": "user", "content": "Анемия?"}]},
    )
    final = _frames(response)[-1]
    assert retriever.texts == ["Анемия — гемоглобин ниже 110 г/л."]
    assert final["grounded"] is True
    assert final["attribution"] == "similarity"
    assert [s["id"] for s in final["sources"]] == ["a:ru:1:0"]


def test_fallback_finding_nothing_stays_ungrounded(client):
    llm = FakeLLM(stream_parts=["Ответ из памяти модели."])
    _use(llm, Attributing(grounded(*HITS), []))
    response = client.post(
        "/api/v1/chat",
        json={"stream": True, "messages": [{"role": "user", "content": "Вопрос?"}]},
    )
    assert _frames(response)[-1]["grounded"] is False


def test_model_markers_skip_the_fallback(client):
    llm = FakeLLM(stream_parts=["Анемия [1]."])
    retriever = Attributing(grounded(*HITS), ["b:ru:1:0"])
    _use(llm, retriever)
    client.post(
        "/api/v1/chat",
        json={"stream": True, "messages": [{"role": "user", "content": "?"}]},
    )
    assert retriever.texts == []


def test_non_stream_numbers_are_woven_into_footnotes(client):
    llm = FakeLLM(reply="Двойня [2]. Анемия [1].")
    _use(llm, FakeRetriever(grounded(*HITS)))
    body = client.post(
        "/api/v1/chat", json={"messages": [{"role": "user", "content": "?"}]}
    ).json()
    assert body["message"]["content"] == "Двойня [1]. Анемия [2]."
    assert [s["id"] for s in body["sources"]] == ["b:ru:1:0", "a:ru:1:0"]
    assert body["attribution"] == "model"


def test_language_reminder_goes_to_the_answer_only():
    seen: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if body["response_format"]["json_schema"]["name"] == "assistant_clarify":
            return httpx.Response(
                200, json=_completion_body('{"questions": [], "conflicts": []}')
            )
        return httpx.Response(200, json=_completion_body('{"answer": "ok [1]"}'))

    llm = LLMClient(Settings(_env_file=None), transport=_transport(handler))
    asyncio.run(
        llm.complete(
            [ChatMessage(role="user", content="q")], "[1] текст", language="en"
        )
    )
    by_name = {
        b["response_format"]["json_schema"]["name"]: b["messages"][-1]["content"]
        for b in seen
    }
    assert "in English" in by_name["assistant_answer"]
    assert "in English" not in by_name["assistant_clarify"]


def test_attribute_links_close_sentences_only(monkeypatch):
    # Пространство из двух осей: «анемия» и «двойня».
    def fake(texts, settings, prefix=""):
        rows = [
            [1.0, 0.0]
            if "емоглобин" in t or "немия" in t
            else [0.0, 1.0]
            if "войн" in t
            else [0.6, 0.6]
            for t in texts
        ]
        return embed.normalize(np.asarray(rows, dtype=np.float32))

    monkeypatch.setattr(embed, "embed_texts", fake)
    monkeypatch.setattr(
        embed, "embed_passages", lambda texts, settings: fake(texts, settings)
    )
    settings = Settings(_env_file=None, attribution_min_score=0.9)
    text = "Гемоглобин ниже 110 г/л считается анемией. Что-то общее без опоры на фрагменты."
    ids, best = attribute(text, HITS, settings)
    assert ids == ["a:ru:1:0"]
    assert best == 1.0
    assert attribute(text, HITS, Settings(_env_file=None, attribution_min_score=0)) == (
        [],
        0.0,
    )


def test_repeat_guard_stops_a_looping_answer(client):
    loop = "Вскрытие показано при признаках острого гнойного воспаления [1]. "
    llm = FakeLLM(
        stream_parts=[
            loop,
            "Другое предложение про лечение железы [2]. ",
            loop,
            loop,
            loop,
        ]
    )
    _use(llm, FakeRetriever(grounded(*HITS)))
    response = client.post(
        "/api/v1/chat",
        json={"stream": True, "messages": [{"role": "user", "content": "?"}]},
    )
    frames = _frames(response)
    text = "".join(f["text"] for f in frames if "text" in f)
    assert text.count("Вскрытие показано") == 2, "поток остановлен на первом повторе"
    assert frames[-1]["grounded"] is True


def test_failure_mid_stream_leaves_an_error_frame(client, caplog):
    class Broken(FakeLLM):
        async def start_chat_stream(
            self, messages, fragments="", claims=None, language=None
        ):
            async def gen():
                yield "Начало ответа [1]. "
                raise AppError(502, "llm_error", "Модель вернула пустой ответ")

            return gen()

    _use(Broken(), FakeRetriever(grounded(*HITS)))
    response = client.post(
        "/api/v1/chat",
        json={"stream": True, "messages": [{"role": "user", "content": "?"}]},
    )
    assert _frames(response)[-1] == {"error": "llm_error"}
    assert "[DONE]" not in response.text


def test_similarity_score_reaches_the_final_frame(client):
    _use(
        FakeLLM(stream_parts=["Без ссылок, но по теме."]),
        Attributing(grounded(*HITS), ["a:ru:1:0"]),
    )
    response = client.post(
        "/api/v1/chat",
        json={"stream": True, "messages": [{"role": "user", "content": "?"}]},
    )
    assert _frames(response)[-1]["attribution_score"] == 0.91


def test_citation_support_scores_cited_sentences_only(monkeypatch):
    from app.corpus.service import citation_support

    def fake(texts, settings, prefix=""):
        rows = [[1.0, 0.0] if "немия" in t or "емоглобин" in t else [0.0, 1.0] for t in texts]
        return embed.normalize(np.asarray(rows, dtype=np.float32))

    monkeypatch.setattr(embed, "embed_texts", fake)
    monkeypatch.setattr(embed, "embed_passages", lambda texts, settings: fake(texts, settings))
    s = Settings(_env_file=None)
    assert citation_support("Волны шумят у берега морского [a:ru:1:0].", HITS, s) == 0.0
    assert citation_support("Анемия — гемоглобин ниже 110 г/л [a:ru:1:0].", HITS, s) == 1.0
    assert citation_support("Без ссылок вовсе, просто длинное предложение.", HITS, s) is None
