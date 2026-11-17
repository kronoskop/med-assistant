"""История консультаций: свои диалоги сохраняются, открываются, продолжаются и удаляются."""

from fastapi.testclient import TestClient

from app.main import app
from tests.test_review import ADMIN, PASSWORD, admin, medics, secured, session  # noqa: F401

ITEMS = [
    {"role": "user", "content": "Порог гемоглобина при беременности?"},
    {"role": "assistant", "content": "Ниже 110 г/л [1].", "done": True, "sources": [{"id": "doc:ru:1:0"}]},
]


def save(client, items=ITEMS, title="Порог гемоглобина при беременности?", conversation_id=None):
    body = {"title": title, "language": "ru", "items": items}
    if conversation_id is None:
        return client.post("/api/v1/conversations", json=body)
    return client.put(f"/api/v1/conversations/{conversation_id}", json=body)


def test_saved_conversation_is_listed_and_opened(medics):
    created = save(medics[0])
    assert created.status_code == 201, created.text
    conversation = created.json()
    assert conversation["turns"] == 1

    listed = medics[0].get("/api/v1/conversations").json()["items"]
    assert [c["id"] for c in listed] == [conversation["id"]]
    assert "items" not in listed[0]  # список лёгкий: реплики — только при открытии

    opened = medics[0].get(f"/api/v1/conversations/{conversation['id']}").json()
    assert opened["items"] == ITEMS
    assert opened["title"] == "Порог гемоглобина при беременности?"


def test_continued_conversation_moves_to_the_top(medics):
    first = save(medics[0]).json()
    second = save(medics[0], title="Второй вопрос").json()
    longer = ITEMS + [{"role": "user", "content": "А при двойне?"}, {"role": "assistant", "content": "Так же."}]
    updated = save(medics[0], items=longer, conversation_id=first["id"])
    assert updated.status_code == 200, updated.text
    assert updated.json()["turns"] == 2

    listed = medics[0].get("/api/v1/conversations").json()["items"]
    assert [c["id"] for c in listed] == [first["id"], second["id"]]
    assert medics[0].get(f"/api/v1/conversations/{first['id']}").json()["items"] == longer


def test_conversation_is_deleted_for_good(medics):
    conversation = save(medics[0]).json()
    assert medics[0].delete(f"/api/v1/conversations/{conversation['id']}").status_code == 200
    assert medics[0].get("/api/v1/conversations").json()["items"] == []
    assert medics[0].get(f"/api/v1/conversations/{conversation['id']}").status_code == 404
    assert medics[0].delete(f"/api/v1/conversations/{conversation['id']}").status_code == 404
    # Продолжить удалённый диалог нельзя: интерфейс тогда сохранит его как новый.
    assert save(medics[0], conversation_id=conversation["id"]).status_code == 404


def test_nobody_sees_other_peoples_history(admin, medics):
    conversation = save(medics[0]).json()
    path = f"/api/v1/conversations/{conversation['id']}"
    for other in (medics[1], admin):
        assert other.get("/api/v1/conversations").json()["items"] == []
        assert other.get(path).status_code == 404
        assert save(other, conversation_id=conversation["id"]).status_code == 404
        assert other.delete(path).status_code == 404
    assert medics[0].get(path).json()["items"] == ITEMS


def test_history_requires_login(secured):
    assert TestClient(app).get("/api/v1/conversations").status_code == 401
    assert save(TestClient(app)).status_code == 401


def test_guest_without_login_has_no_history(client):
    # Режим без входа (замеры, тесты API): сохранять историю некому.
    assert client.get("/api/v1/conversations").status_code == 403
    assert save(client).status_code == 403


def test_oversized_conversation_is_refused(medics):
    huge = [{"role": "user", "content": "x" * 600_000} for _ in range(4)]
    response = save(medics[0], items=huge)
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"
