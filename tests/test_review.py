"""Вход, роли, уточнения ответов медиками и принятые ответы в выдаче."""

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.corpus.service import get_retriever
from app.llm import get_llm
from app.main import app
from app.review.verified import get_question_embedder
from app.settings import get_settings
from tests.conftest import FakeLLM, FakeRetriever, grounded

ADMIN = ("admin", "admin-password")
PASSWORD = "medic-password"


class FakeEmbedder:
    """Вектор по первому слову вопроса: одинаковое начало — тот же смысл."""

    model = "fake"

    def __call__(self, question: str) -> np.ndarray:
        vector = np.zeros(8, dtype=np.float32)
        vector[len(question.split()[0]) % 8] = 1.0
        return vector


@pytest.fixture
def secured(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("VERIFIED_MIN_SCORE", "0.9")
    get_settings.cache_clear()
    llm = FakeLLM()
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever(grounded())
    app.dependency_overrides[get_question_embedder] = FakeEmbedder
    with TestClient(app):  # запуск создаёт первого администратора
        yield llm


def session(login: str, password: str = PASSWORD) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/v1/auth/login", json={"login": login, "password": password})
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def admin(secured) -> TestClient:
    return session(*ADMIN)


@pytest.fixture
def medics(admin) -> list[TestClient]:
    clients = []
    for n in range(5):
        created = admin.post(
            "/api/v1/admin/users",
            json={"login": f"medic{n}", "name": f"Медик {n}", "role": "medic", "password": PASSWORD},
        )
        assert created.status_code == 201, created.text
        clients.append(session(f"medic{n}"))
    return clients


def refine(client, question="Анемия у беременных: порог гемоглобина?", text="Ниже 110 г/л.", history=()):
    response = client.post(
        "/api/v1/refinements",
        json={"question": question, "text": text, "model_answer": "Ответ модели", "history": list(history)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def agree(client, refinement_id):
    return client.post(f"/api/v1/refinements/{refinement_id}/vote", json={"agree": True})


def ask(client, question, stream=False):
    return client.post(
        "/api/v1/chat", json={"messages": [{"role": "user", "content": question}], "stream": stream}
    )


# ── вход и роли ───────────────────────────────────────────
def test_chat_requires_login(secured):
    response = ask(TestClient(app), "Вопрос")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_login_rejects_wrong_password(secured):
    response = TestClient(app).post("/api/v1/auth/login", json={"login": "admin", "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json()["code"] == "bad_credentials"


def test_login_pauses_after_repeated_failures(secured):
    client = TestClient(app)
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"login": "someone", "password": "wrong-password"})
    assert client.post("/api/v1/auth/login", json={"login": "someone", "password": "x"}).status_code == 429


def test_me_and_logout(admin):
    assert admin.get("/api/v1/auth/me").json()["user"]["role"] == "admin"
    admin.post("/api/v1/auth/logout")
    assert admin.get("/api/v1/auth/me").status_code == 401


def test_only_admin_manages_users(medics):
    assert medics[0].get("/api/v1/admin/users").status_code == 403
    created = medics[0].post(
        "/api/v1/admin/users", json={"login": "x1", "name": "X", "role": "admin", "password": PASSWORD}
    )
    assert created.status_code == 403


def test_admin_cannot_remove_last_admin(admin):
    me = admin.get("/api/v1/auth/me").json()["user"]
    response = admin.patch(f"/api/v1/admin/users/{me['id']}", json={"role": "medic"})
    assert response.status_code == 409
    assert response.json()["code"] == "last_admin"


def test_deactivated_user_loses_session(admin, medics):
    user = next(u for u in admin.get("/api/v1/admin/users").json()["items"] if u["login"] == "medic0")
    admin.patch(f"/api/v1/admin/users/{user['id']}", json={"active": False})
    assert medics[0].get("/api/v1/auth/me").status_code == 401
    assert TestClient(app).post(
        "/api/v1/auth/login", json={"login": "medic0", "password": PASSWORD}
    ).status_code == 401


def test_duplicate_login_and_weak_password(admin):
    body = {"login": "doc", "name": "Док", "role": "observer", "password": PASSWORD}
    assert admin.post("/api/v1/admin/users", json=body).status_code == 201
    assert admin.post("/api/v1/admin/users", json=body).json()["code"] == "login_taken"
    assert admin.post("/api/v1/admin/users", json={**body, "login": "doc2", "password": "123"}).status_code == 422


def test_user_changes_own_password(medics):
    changed = medics[0].post("/api/v1/auth/password", json={"current": PASSWORD, "new": "another-password"})
    assert changed.status_code == 200
    assert medics[0].get("/api/v1/auth/me").status_code == 200  # текущий сеанс остаётся
    session("medic0", "another-password")


def test_observer_and_admin_cannot_refine(admin):
    admin.post("/api/v1/admin/users", json={"login": "obs", "name": "Н", "role": "observer", "password": PASSWORD})
    body = {"question": "Вопрос", "text": "Ответ"}
    assert session("obs").post("/api/v1/refinements", json=body).status_code == 403
    assert admin.post("/api/v1/refinements", json=body).status_code == 403


# ── голосование ───────────────────────────────────────────
def test_three_confirmations_accept(medics):
    item = refine(medics[0])
    assert item["status"] == "pending" and item["required"] == 3
    assert agree(medics[1], item["id"]).json()["status"] == "pending"
    assert agree(medics[2], item["id"]).json()["status"] == "pending"
    done = agree(medics[3], item["id"]).json()
    assert done["status"] == "accepted" and done["confirmations"] == 3
    kinds = [n["kind"] for n in medics[0].get("/api/v1/notifications").json()["items"]]
    assert kinds == ["refinement_accepted"]


def test_author_cannot_confirm_own(medics):
    item = refine(medics[0])
    response = agree(medics[0], item["id"])
    assert response.status_code == 403 and response.json()["code"] == "own_refinement"


def test_no_double_vote(medics):
    item = refine(medics[0])
    agree(medics[1], item["id"])
    assert agree(medics[1], item["id"]).json()["code"] == "already_voted"


def test_one_disagreement_rejects(medics):
    item = refine(medics[0])
    agree(medics[1], item["id"])
    no_comment = medics[2].post(f"/api/v1/refinements/{item['id']}/vote", json={"agree": False})
    assert no_comment.json()["code"] == "comment_required"
    rejected = medics[2].post(
        f"/api/v1/refinements/{item['id']}/vote", json={"agree": False, "comment": "Порог другой"}
    ).json()
    assert rejected["status"] == "rejected"
    assert agree(medics[3], item["id"]).json()["code"] == "closed"
    note = medics[0].get("/api/v1/notifications").json()["items"][0]
    assert note["kind"] == "refinement_rejected" and note["comment"] == "Порог другой"
    assert ask(medics[4], item["question"]).json().get("verified") is None


def test_queue_hides_own_and_voted(medics):
    item = refine(medics[0])
    assert medics[0].get("/api/v1/refinements?scope=queue").json()["items"] == []
    assert [i["id"] for i in medics[1].get("/api/v1/refinements?scope=queue").json()["items"]] == [item["id"]]
    assert medics[1].get("/api/v1/auth/me").json()["counts"]["queue"] == 1
    agree(medics[1], item["id"])
    assert medics[1].get("/api/v1/refinements?scope=queue").json()["items"] == []


def test_required_confirmations_is_configurable(admin, medics):
    item = refine(medics[0])
    agree(medics[1], item["id"])
    assert medics[0].put("/api/v1/admin/settings", json={"required_confirmations": 1}).status_code == 403
    # Порог снижен до уже набранного числа — ожидающее уточнение принимается.
    assert admin.put("/api/v1/admin/settings", json={"required_confirmations": 1}).status_code == 200
    assert medics[0].get("/api/v1/refinements?scope=mine").json()["items"][0]["status"] == "accepted"
    assert admin.put("/api/v1/admin/settings", json={"required_confirmations": 0}).status_code == 422


# ── своя формулировка ─────────────────────────────────────
def propose(client, refinement_id, text="Ниже 110 г/л в I и III триместрах."):
    response = client.post(f"/api/v1/refinements/{refinement_id}/proposals", json={"text": text})
    assert response.status_code == 201, response.text
    return response.json()["proposals"][-1]


def test_author_accepts_new_wording_and_voting_restarts(medics):
    item = refine(medics[0])
    agree(medics[2], item["id"])
    proposal = propose(medics[1], item["id"])
    note = medics[0].get("/api/v1/notifications").json()["items"][0]
    assert note["kind"] == "proposal_received" and note["proposal_text"] == proposal["text"]

    # Решает только автор исходного уточнения.
    stranger = medics[3].post(f"/api/v1/proposals/{proposal['id']}/decision", json={"accept": True})
    assert stranger.status_code == 403

    fresh = medics[0].post(f"/api/v1/proposals/{proposal['id']}/decision", json={"accept": True}).json()
    assert fresh["id"] != item["id"] and fresh["parent_id"] == item["id"]
    assert fresh["text"] == proposal["text"] and fresh["status"] == "pending"
    assert fresh["author_id"] == proposal["author_id"]
    # Прежние голоса не переносятся; согласие автора — первое подтверждение.
    assert fresh["confirmations"] == 1
    old = medics[0].get("/api/v1/refinements?scope=mine").json()["items"][0]
    assert old["status"] == "replaced"
    assert agree(medics[3], item["id"]).json()["code"] == "closed"
    assert medics[1].get("/api/v1/notifications").json()["items"][0]["kind"] == "proposal_accepted"

    agree(medics[2], fresh["id"])
    assert agree(medics[3], fresh["id"]).json()["status"] == "accepted"


def test_author_declines_new_wording(medics):
    item = refine(medics[0])
    proposal = propose(medics[1], item["id"])
    same = medics[0].post(f"/api/v1/proposals/{proposal['id']}/decision", json={"accept": False}).json()
    assert same["id"] == item["id"] and same["status"] == "pending"
    assert medics[1].get("/api/v1/notifications").json()["items"][0]["kind"] == "proposal_declined"
    again = medics[0].post(f"/api/v1/proposals/{proposal['id']}/decision", json={"accept": False})
    assert again.json()["code"] == "closed"


def test_author_cannot_propose_to_self(medics):
    item = refine(medics[0])
    response = medics[0].post(f"/api/v1/refinements/{item['id']}/proposals", json={"text": "Иначе"})
    assert response.status_code == 403


# ── принятый ответ в выдаче ───────────────────────────────
def accept(medics, **kwargs):
    item = refine(medics[0], **kwargs)
    for medic in medics[1:4]:
        agree(medic, item["id"])
    return item


def test_accepted_answer_is_served_verbatim_without_model(medics, secured):
    item = accept(medics)
    response = ask(medics[4], "  анемия у беременных — порог гемоглобина  ")
    body = response.json()
    assert body["message"]["content"] == "Ниже 110 г/л."
    assert body["grounding"] == "verified" and body["grounded"] is True
    assert body["verified"]["refinement_id"] == item["id"]
    assert body["verified"]["confirmations"] == 3
    assert secured.calls == []


def test_similar_question_gets_accepted_answer_and_other_does_not(medics, secured):
    accept(medics)
    close = ask(medics[4], "Анемия при беременности, какой гемоглобин считать низким?").json()
    assert close["verified"] and close["message"]["content"] == "Ниже 110 г/л."
    other = ask(medics[4], "Преэклампсия: когда госпитализировать?").json()
    assert other["verified"] is None
    assert len(secured.calls) == 1


def test_by_default_only_the_same_question_matches(medics, monkeypatch):
    monkeypatch.delenv("VERIFIED_MIN_SCORE")
    get_settings.cache_clear()
    item = accept(medics)
    assert ask(medics[4], "Анемия при беременности, какой гемоглобин считать низким?").json()["verified"] is None
    assert ask(medics[4], item["question"].upper()).json()["verified"]["similarity"] == 1.0


def test_pending_answer_is_not_served(medics, secured):
    item = refine(medics[0])
    agree(medics[1], item["id"])
    assert ask(medics[4], item["question"]).json()["verified"] is None


def test_accepted_answer_streams(medics):
    item = accept(medics)
    frames = [
        json.loads(line[5:])
        for line in ask(medics[4], item["question"], stream=True).text.splitlines()
        if line.startswith("data:") and "[DONE]" not in line
    ]
    assert frames[0] == {"text": "Ниже 110 г/л."}
    assert frames[1]["grounding"] == "verified" and frames[1]["verified"]["refinement_id"] == item["id"]


def test_follow_up_question_goes_to_model(medics, secured):
    item = accept(medics)
    response = medics[4].post(
        "/api/v1/chat",
        json={
            "messages": [
                {"role": "user", "content": "Первый вопрос"},
                {"role": "assistant", "content": "Ответ"},
                {"role": "user", "content": item["question"]},
            ]
        },
    )
    assert response.json()["verified"] is None


def test_refinement_of_follow_up_is_kept_for_export_only(admin, medics):
    history = [{"role": "user", "content": "Анемия у беременных"}, {"role": "assistant", "content": "Ответ"}]
    accept(medics, question="А в третьем триместре?", text="Ниже 105 г/л.", history=history)
    assert ask(medics[4], "А в третьем триместре?").json()["verified"] is None
    rows = [json.loads(line) for line in admin.get("/api/v1/admin/export.jsonl").text.splitlines()]
    assert [m["content"] for m in rows[0]["messages"]] == [
        "Анемия у беременных", "Ответ", "А в третьем триместре?", "Ниже 105 г/л."
    ]


def test_last_accepted_wins_and_previous_is_archived(medics):
    first = accept(medics)
    second = refine(medics[1], text="Ниже 110 г/л; во II триместре ниже 105 г/л.")
    for medic in (medics[0], medics[2], medics[3]):
        agree(medic, second["id"])
    assert ask(medics[4], first["question"]).json()["verified"]["refinement_id"] == second["id"]
    statuses = {i["id"]: i["status"] for i in medics[0].get("/api/v1/refinements?scope=mine").json()["items"]}
    assert statuses[first["id"]] == "archived"


def test_admin_archives_accepted_answer(admin, medics):
    item = accept(medics)
    assert medics[1].post(f"/api/v1/refinements/{item['id']}/archive").status_code == 403
    assert admin.post(f"/api/v1/refinements/{item['id']}/archive").json()["status"] == "archived"
    assert ask(medics[4], item["question"]).json()["verified"] is None


def test_export_requires_admin(medics):
    assert medics[0].get("/api/v1/admin/export.jsonl").status_code == 403


def test_review_assets_served(secured):
    client = TestClient(app)
    for name in ("review.js", "review-i18n.js", "review.css"):
        assert client.get(f"/ui/{name}").status_code == 200, name
