import json

from app.corpus.service import Grounding, Retrieval, get_retriever
from app.llm import get_llm
from app.main import app
from app.prompt import REFUSAL_EMPTY_CORPUS, REFUSAL_NO_MATCH
from tests.conftest import FakeLLM, FakeRetriever, grounded, make_hit, make_support


def _post(client, content: str = "Вопрос о протоколе", stream: bool = False):
    body = {"messages": [{"role": "user", "content": content}]}
    if stream:
        body["stream"] = True
    return client.post("/api/v1/chat", json=body)


def _use(retrieval: Retrieval, *, claims: list[str] | None = None) -> FakeLLM:
    llm = FakeLLM()
    llm.claim_sources = claims or []
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever(retrieval)
    return llm


# ── фрагменты доходят до модели ───────────────────────────────────────────


def test_retrieved_fragments_reach_the_model(client):
    hit = make_hit(text="Кратность наблюдения выше при монохориальной плацентации.")
    llm = _use(grounded(hit))
    _post(client)
    assert llm.fragments, "фрагменты в модель не передавались"
    assert hit.fragment.id in llm.fragments[0]
    assert "Кратность наблюдения выше" in llm.fragments[0]


# ── ссылка подтверждается только реально отобранным фрагментом ────────────


def test_invented_fragment_reference_is_dropped(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(grounded(hit), claims=["doc:ru:99:9", "выдуманный-фрагмент"])
    body = _post(client).json()
    assert body["sources"] == [], "ссылка на неотобранный фрагмент попала в ответ"


def test_confirmed_reference_survives_with_its_coordinates(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(grounded(hit), claims=["doc:ru:1:0"])
    body = _post(client).json()
    assert [s["id"] for s in body["sources"]] == ["doc:ru:1:0"]
    source = body["sources"][0]
    assert source["location"] == "с. 1, разд. 4.2"
    assert source["language"] == "ru"
    assert source["document_title"]


def test_duplicate_references_collapse(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    _use(grounded(hit), claims=["doc:ru:1:0", "doc:ru:1:0"])
    assert len(_post(client).json()["sources"]) == 1


# ── подкрепление не подтверждает утверждений ──────────────────────────────


def test_support_document_cannot_confirm_a_claim(client):
    support = make_support("who-doc")
    _use(grounded(make_hit(), support=(support,)), claims=["who-doc", "who-doc:en:1:0"])
    body = _post(client).json()
    assert body["sources"] == [], "документ подкрепления подтвердил утверждение"
    assert [d["document_id"] for d in body["support"]] == ["who-doc"]


def test_support_is_listed_separately_from_sources(client):
    _use(grounded(make_hit(), support=(make_support(),)), claims=["doc:ru:1:0"])
    body = _post(client).json()
    assert len(body["sources"]) == 1
    assert len(body["support"]) == 1
    assert "url" in body["support"][0]


# ── отказ вместо ответа по памяти ─────────────────────────────────────────


def test_empty_corpus_refuses_without_calling_the_model(client):
    llm = _use(Retrieval(Grounding.EMPTY_CORPUS))
    body = _post(client).json()
    assert llm.calls == [], "модель вызвана при пустом корпусе"
    assert body["message"]["content"] == REFUSAL_EMPTY_CORPUS
    assert body["grounded"] is False
    assert body["grounding"] == "empty_corpus"


def test_no_match_refuses_without_calling_the_model(client):
    llm = _use(Retrieval(Grounding.NO_MATCH))
    body = _post(client).json()
    assert llm.calls == []
    assert body["message"]["content"] == REFUSAL_NO_MATCH
    assert body["sources"] == []


def test_support_only_refuses_and_names_the_gap(client):
    support = make_support()
    llm = _use(Retrieval(Grounding.SUPPORT_ONLY, (), (support,)))
    body = _post(client).json()
    assert llm.calls == [], "модель вызвана, когда основы не нашлось"
    assert body["grounding"] == "support_only"
    assert body["sources"] == []
    assert "в документах центра" in body["message"]["content"].lower()
    assert len(body["support"]) == 1


def test_refusal_streams_and_still_terminates(client):
    _use(Retrieval(Grounding.NO_MATCH))
    text = _post(client, stream=True).text
    assert REFUSAL_NO_MATCH[:40] in text
    assert text.rstrip().endswith("[DONE]")


# ── аддитивность контракта ────────────────────────────────────────────────


def test_existing_response_fields_are_untouched(client):
    _use(grounded(make_hit()), claims=["doc:ru:1:0"])
    body = _post(client).json()
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"]
    assert body["disclaimer"]


def test_stream_carries_sources_before_done(client):
    _use(grounded(make_hit()), claims=["doc:ru:1:0"])
    frames = [line[5:].strip() for line in _post(client, stream=True).text.split("\n") if line.startswith("data:")]
    assert frames[-1] == "[DONE]"
    payload = json.loads(frames[-2])
    assert [s["id"] for s in payload["sources"]] == ["doc:ru:1:0"]
    assert payload["grounded"] is True


# ── корпус и вопрос не уходят наружу ──────────────────────────────────────


def test_retrieval_talks_only_to_the_configured_local_address(monkeypatch):
    """Отбор обращается только к настроенному локальному адресу: ни текст
    вопроса, ни содержимое корпуса не должны уходить во внешние сервисы."""
    import httpx

    from app.corpus import embed
    from app.settings import Settings

    seen: list[str] = []

    class SpyClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def post(self, url, json):
            seen.append(url)
            vectors = [{"index": i, "embedding": [0.1, 0.2, 0.3]} for i, _ in enumerate(json["input"])]
            return httpx.Response(200, json={"data": vectors}, request=httpx.Request("POST", url))

        def close(self) -> None:
            pass

    monkeypatch.setattr(embed.httpx, "Client", SpyClient)
    settings = Settings(_env_file=None)
    embed.embed_texts(["секретный клинический текст"], settings)

    assert seen, "обращений не было"
    for url in seen:
        assert url.startswith(settings.lmstudio_base_url.rstrip("/")), url
        assert "127.0.0.1" in url or "localhost" in url, url


def test_answer_without_citations_becomes_a_refusal(client):
    """Косинусная близость не отделяет профильный вопрос от постороннего,
    поэтому ответ, в котором модель ни на что не сослалась, заземлённым
    не считается — иначе врач увидел бы прозу модели как подтверждённую."""
    llm = _use(grounded(make_hit()), claims=[])
    body = _post(client).json()
    assert llm.calls, "модель должна была получить фрагменты"
    assert body["grounded"] is False
    assert body["grounding"] == "no_match"
    assert body["sources"] == []
    assert body["message"]["content"] == REFUSAL_NO_MATCH


# ── сноски у утверждений ──────────────────────────────────────────────────


def test_inline_citation_becomes_a_numbered_footnote(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    llm = _use(grounded(hit))
    llm.reply = "Кратность наблюдения выше [doc:ru:1:0]."
    body = _post(client).json()
    assert body["message"]["content"] == "Кратность наблюдения выше [1]."
    assert [s["id"] for s in body["sources"]] == ["doc:ru:1:0"]


def test_invented_inline_citation_is_removed_from_the_text(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    llm = _use(grounded(hit))
    llm.reply = "Подтверждено [doc:ru:1:0]. Выдумано [нет-такого:ru:9:9]."
    body = _post(client).json()
    text = body["message"]["content"]
    assert "нет-такого" not in text, "ссылка в никуда осталась в тексте"
    assert text == "Подтверждено [1]. Выдумано."
    assert len(body["sources"]) == 1


def test_claim_without_citation_gets_no_footnote(client):
    hit = make_hit(fragment_id="doc:ru:1:0")
    llm = _use(grounded(hit))
    llm.reply = "Подтверждённое утверждение [doc:ru:1:0]. Утверждение без ссылки."
    text = _post(client).json()["message"]["content"]
    assert text.endswith("Утверждение без ссылки.")
    assert text.count("[1]") == 1


def test_footnote_numbers_follow_reading_order(client):
    first = make_hit("a", "a:ru:1:0")
    second = make_hit("b", "b:ru:2:0")
    llm = _use(grounded(second, first))  # порядок отбора обратный порядку в тексте
    llm.reply = "Раз [a:ru:1:0]. Два [b:ru:2:0]. Снова раз [a:ru:1:0]."
    body = _post(client).json()
    assert body["message"]["content"] == "Раз [1]. Два [2]. Снова раз [1]."
    assert [s["id"] for s in body["sources"]] == ["a:ru:1:0", "b:ru:2:0"]
