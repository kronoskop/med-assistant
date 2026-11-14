"""«Во фрагментах этого нет [2]»: ссылка без опоры не делает ответ подтверждённым."""

import json

import pytest

from app.absence import (
    drop_absence_citations,
    is_absence,
    strip_absence_markers,
    without_absence,
)
from app.corpus.service import get_retriever
from app.llm import get_llm
from app.main import app
from tests.conftest import FakeLLM, FakeRetriever, grounded, make_hit

A = make_hit("a")
B = make_hit("b")


@pytest.mark.parametrize(
    "sentence",
    [
        "Информация о дозе амоксициллина у ребёнка 5 лет отсутствует в предоставленных фрагментах [a:ru:1:0].",
        "Во фрагментах нет сведений о дозе.",
        "Фрагменты не содержат информации о лечении подагры.",
        "В протоколе нет данных о дозе для детей.",
        "The provided fragments do not contain information on this.",
        "This is not mentioned in the provided fragments.",
        "Berilgan fragmentlarda bu haqda maʼlumot yoʻq.",
    ],
)
def test_absence_is_recognised(sentence):
    assert is_absence(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "Анемией считается гемоглобин ниже 110 г/л [1].",
        "При отсутствии эффекта от терапии показано вскрытие абсцесса [3].",
        "Если нет противопоказаний, назначают окситоцин согласно протоколу [2].",
        "Препарат не назначают при отсутствии показаний, указанных в протоколе [1].",
        "If no response to treatment, the document recommends surgery [2].",
    ],
)
def test_substance_is_not_absence(sentence):
    assert not is_absence(sentence)


def test_only_citations_from_absence_sentences_are_dropped():
    text = "Анемия — гемоглобин ниже 110 г/л [a:ru:1:0]. Дозы для детей во фрагментах нет. [b:ru:1:0]"
    assert drop_absence_citations(["a:ru:1:0", "b:ru:1:0"], text) == ["a:ru:1:0"]
    assert without_absence(text) == "Анемия — гемоглобин ниже 110 г/л [a:ru:1:0]."
    assert strip_absence_markers(text).endswith("Дозы для детей во фрагментах нет. ")


def _final(response) -> dict:
    lines = [
        ln
        for ln in response.text.splitlines()
        if ln.startswith("data:") and "[DONE]" not in ln
    ]
    return json.loads(lines[-1][5:])


def test_absence_answer_with_a_citation_is_refused(client):
    llm = FakeLLM(
        stream_parts=[
            "Информация о дозе у ребёнка 5 лет отсутствует в предоставленных фрагментах [1]."
        ]
    )
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever(grounded(A, B))
    response = client.post(
        "/api/v1/chat",
        json={"stream": True, "messages": [{"role": "user", "content": "?"}]},
    )
    final = _final(response)
    assert final["grounded"] is False
    assert final["refusal"]


def test_absence_answer_is_refused_without_stream(client):
    llm = FakeLLM(reply="Во фрагментах нет сведений о дозе для детей [1].")
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever(grounded(A, B))
    body = client.post(
        "/api/v1/chat", json={"messages": [{"role": "user", "content": "?"}]}
    ).json()
    assert body["grounded"] is False
