"""Уточняющие вопросы и противоречия: что доходит до врача, а что вычёркивается.

Вопрос — это утверждение «протокол требует это учитывать», поэтому здесь
проверяется та же граница доверия, что и для сносок: без отобранного фрагмента
под вопросом он не отличим от догадки модели.
"""

import json

from app.corpus.service import Grounding, Retrieval, get_retriever
from app.llm import get_llm
from app.main import app
from tests.conftest import FakeLLM, FakeRetriever, grounded, make_hit


def _post(client, content: str = "Вопрос о ведении", stream: bool = False):
    body = {"messages": [{"role": "user", "content": content}]}
    if stream:
        body["stream"] = True
    return client.post("/api/v1/chat", json=body)


def _use(retrieval: Retrieval, *, claims=None, questions=None, conflicts=None) -> FakeLLM:
    llm = FakeLLM()
    llm.claim_sources = claims or []
    llm.claim_questions = questions or []
    llm.claim_conflicts = conflicts or []
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever(retrieval)
    return llm


def _ask(fragment_id: str, question: str = "Каков срок гестации?") -> dict:
    return {"question": question, "source": fragment_id}


def _frames(response) -> list[dict]:
    out = []
    for line in response.text.splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            out.append(json.loads(line[6:]))
    return out


# ── вопрос опирается на отобранный фрагмент ───────────────────────────────


def test_question_from_a_retrieved_fragment_reaches_the_doctor(client):
    hit = make_hit(fragment_id="doc:ru:9:0", text="Оценивают срок гестации и анамнез.")
    _use(grounded(hit), claims=["doc:ru:9:0"], questions=[_ask("doc:ru:9:0")])
    body = _post(client).json()
    assert [q["question"] for q in body["questions"]] == ["Каков срок гестации?"]
    assert body["questions"][0]["source"]["id"] == "doc:ru:9:0"


def test_question_carries_the_fragment_it_follows_from(client):
    """Фрагмент вопроса может быть не процитирован в ответе — тогда сноски,
    ведущей к нему, не существует, и вопрос несёт документ при себе."""
    cited = make_hit(fragment_id="doc:ru:1:0")
    other = make_hit(fragment_id="doc:ru:9:0", text="Оценивают срок гестации.")
    _use(grounded(cited, other), claims=["doc:ru:1:0"], questions=[_ask("doc:ru:9:0")])
    body = _post(client).json()
    assert [s["id"] for s in body["sources"]] == ["doc:ru:1:0"]
    source = body["questions"][0]["source"]
    assert source["id"] == "doc:ru:9:0"
    assert source["document_title"] and source["location"]


def test_question_about_an_unretrieved_fragment_is_dropped(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(grounded(hit), claims=["doc:ru:1:0"], questions=[_ask("doc:ru:77:7")])
    assert _post(client).json()["questions"] == [], "вопрос без опоры на фрагмент попал в ответ"


def test_malformed_question_is_dropped(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(
        grounded(hit),
        claims=["doc:ru:1:0"],
        questions=["просто строка", {"source": "doc:ru:1:0"}, _ask("doc:ru:1:0", "   ")],
    )
    assert _post(client).json()["questions"] == []


def test_no_questions_when_the_model_asks_nothing(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(grounded(hit), claims=["doc:ru:1:0"])
    assert _post(client).json()["questions"] == []


# ── немного и по делу ─────────────────────────────────────────────────────


def test_at_most_three_questions(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(
        grounded(hit),
        claims=["doc:ru:1:0"],
        questions=[_ask("doc:ru:1:0", f"Вопрос {n}?") for n in range(6)],
    )
    body = _post(client).json()
    assert len(body["questions"]) == 3
    assert [q["question"] for q in body["questions"]] == ["Вопрос 0?", "Вопрос 1?", "Вопрос 2?"]


def test_repeated_question_appears_once(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(
        grounded(hit),
        claims=["doc:ru:1:0"],
        questions=[_ask("doc:ru:1:0", "Каков срок?"), _ask("doc:ru:1:0", "каков срок?")],
    )
    assert len(_post(client).json()["questions"]) == 1


# ── уточнения не заменяют ответ и не сопровождают отказ ───────────────────


def test_answer_comes_with_the_questions_not_instead_of_it(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    llm = _use(grounded(hit), claims=["doc:ru:1:0"], questions=[_ask("doc:ru:1:0")])
    llm.reply = "Наблюдение по протоколу [doc:ru:1:0]."
    body = _post(client).json()
    assert body["grounded"] is True
    assert "Наблюдение по протоколу" in body["message"]["content"]
    assert body["questions"], "ответ пришёл без уточнений"


def test_refusal_carries_no_questions(client):
    _use(Retrieval(Grounding.EMPTY_CORPUS), questions=[_ask("doc:ru:1:0")])
    body = _post(client).json()
    assert body["grounded"] is False
    assert body["questions"] == [], "уточнения приложены к отказу"


def test_uncited_answer_refuses_without_questions(client):
    """Модель ответила, но ни на что не сослалась: это отказ, и спрашивать не о чем."""
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(grounded(hit), claims=[], questions=[_ask("doc:ru:1:0")])
    body = _post(client).json()
    assert body["grounded"] is False
    assert body["questions"] == []


# ── противоречия внутри слов врача ────────────────────────────────────────

СЛУЧАЙ = "Первая беременность, но в анамнезе двое родов. Как вести ГСД?"


def _conflicts(client, *items, said: str = СЛУЧАЙ):
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(grounded(hit), claims=["doc:ru:1:0"], conflicts=list(items))
    return _post(client, said).json()["conflicts"]


def test_conflict_shows_both_sides(client):
    got = _conflicts(client, {"first": "Первая беременность", "second": "в анамнезе двое родов"})
    assert got == [{"first": "Первая беременность", "second": "в анамнезе двое родов"}]


def test_side_the_doctor_never_said_is_dropped(client):
    """Сторона — цитата из слов врача. Непроверенная приписала бы ему то, чего
    он не говорил: та же фальшивая трассируемость, что и выдуманная сноска."""
    got = _conflicts(client, {"first": "Первая беременность", "second": "сахарный диабет 1 типа"})
    assert got == [], "приписанная врачу цитата попала в ответ"


def test_quote_matches_despite_case_and_punctuation(client):
    """Модель цитирует с кавычками и точкой — это та же фраза, не подделка."""
    got = _conflicts(client, {"first": "«первая беременность»", "second": "В анамнезе двое родов."})
    assert len(got) == 1


def test_sentence_and_its_own_part_are_not_two_sides(client):
    """Вложенность — признак того, что модель сложила в отметку предложение
    целиком и его же часть: сторон здесь не две, а одна."""
    got = _conflicts(
        client,
        {"first": "Первая беременность, но в анамнезе двое родов", "second": "двое родов"},
    )
    assert got == []


def test_two_mismatches_come_as_two_marks(client):
    """Разные несовпадения не складываются в одну отметку."""
    said = "Срок 12 недель, по УЗИ 28 недель. Первая беременность, в анамнезе двое родов."
    got = _conflicts(
        client,
        {"first": "Срок 12 недель", "second": "по УЗИ 28 недель"},
        {"first": "Первая беременность", "second": "в анамнезе двое родов"},
        said=said,
    )
    assert [(c["first"], c["second"]) for c in got] == [
        ("Срок 12 недель", "по УЗИ 28 недель"),
        ("Первая беременность", "в анамнезе двое родов"),
    ]


def test_one_sided_conflict_is_dropped(client):
    got = _conflicts(
        client,
        {"first": "Первая беременность", "second": ""},
        {"second": "в анамнезе двое родов"},
    )
    assert got == [], "отметка без обеих сторон попала в ответ"


def test_conflict_of_a_statement_with_itself_is_dropped(client):
    got = _conflicts(client, {"first": "Первая беременность", "second": "первая беременность"})
    assert got == []


def test_the_same_pair_reversed_appears_once(client):
    got = _conflicts(
        client,
        {"first": "Первая беременность", "second": "в анамнезе двое родов"},
        {"first": "в анамнезе двое родов", "second": "Первая беременность"},
    )
    assert len(got) == 1


def test_assistant_words_are_not_a_source_of_quotes(client):
    """Противоречие ищется в сведениях о случае, а не в тексте модели."""
    from app.answer import doctor_words
    from app.schemas import ChatMessage

    said = doctor_words([
        ChatMessage(role="user", content="Первая беременность"),
        ChatMessage(role="assistant", content="в анамнезе двое родов"),
    ])
    assert "Первая беременность" in said
    assert "двое родов" not in said


# ── поток ─────────────────────────────────────────────────────────────────


def test_stream_delivers_questions_before_it_ends(client):
    hit = make_hit(fragment_id="doc:ru:9:0")
    _use(grounded(hit), claims=["doc:ru:9:0"], questions=[_ask("doc:ru:9:0")])
    response = _post(client, stream=True)
    assert response.text.rstrip().endswith("data: [DONE]")
    last = _frames(response)[-1]
    assert [q["question"] for q in last["questions"]] == ["Каков срок гестации?"]
    assert last["questions"][0]["source"]["id"] == "doc:ru:9:0"


def test_stream_refusal_carries_no_questions(client):
    _use(Retrieval(Grounding.NO_MATCH), questions=[_ask("doc:ru:1:0")])
    last = _frames(_post(client, stream=True))[-1]
    assert last["grounded"] is False
    assert last["questions"] == []


# ── совместимость ─────────────────────────────────────────────────────────


def test_existing_response_fields_are_untouched(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(grounded(hit), claims=["doc:ru:1:0"], questions=[_ask("doc:ru:1:0")])
    body = _post(client).json()
    for field in ("message", "disclaimer", "grounded", "grounding", "sources", "support"):
        assert field in body, f"поле {field} пропало из ответа"
    assert body["message"]["role"] == "assistant"
