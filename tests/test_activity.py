"""Страница «Активность»: журнал входов, вопросов и сбоев, сводка по дням."""

import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.llm import get_llm
from app.main import app
from app.review.auth import get_store
from tests.conftest import FakeLLM
from tests.test_review import ADMIN, PASSWORD, admin, agree, ask, medics, refine, secured  # noqa: F401


def today(tz_minutes: int = 0) -> str:
    return datetime.fromtimestamp(time.time() + tz_minutes * 60, timezone.utc).strftime("%Y-%m-%d")


def days(client, tz=0):
    response = client.get(f"/api/v1/admin/activity?tz={tz}")
    assert response.status_code == 200, response.text
    return response.json()["days"]


def details(client, day, tz=0):
    response = client.get(f"/api/v1/admin/activity/{day}?tz={tz}")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_only_admin_sees_activity(medics):
    assert medics[0].get("/api/v1/admin/activity").status_code == 403
    assert medics[0].get(f"/api/v1/admin/activity/{today()}").status_code == 403
    assert TestClient(app).get("/api/v1/admin/activity").status_code == 401


def test_logins_and_failed_logins_are_counted(admin, medics):
    TestClient(app).post("/api/v1/auth/login", json={"login": "medic1", "password": "wrong-password"})
    row = days(admin)[0]
    assert row["day"] == today()
    assert row["logins"] == 6  # администратор и пять медиков
    assert row["failed_logins"] == 1
    kinds = [item["kind"] for item in details(admin, today())]
    assert kinds.count("login") == 6 and "login_failed" in kinds


def test_questions_with_text_author_and_duration(admin, medics, secured):
    secured.claim_sources = ["doc:ru:1:0"]
    assert ask(medics[0], "Порог гемоглобина при беременности?").status_code == 200
    with medics[0].stream(
        "POST", "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "Дозировка железа?"}], "stream": True},
    ) as response:
        "".join(response.iter_text())
    assert ask(medics[1], "Ещё вопрос").status_code == 200

    row = days(admin)[0]
    assert row["questions"] == 3
    assert row["per_user"] == [{"name": "Медик 0", "questions": 2}, {"name": "Медик 1", "questions": 1}]
    assert row["answer_ms"] is not None
    questions = [i for i in details(admin, today()) if i["kind"] == "question"]
    assert [q["question"] for q in questions] == ["Порог гемоглобина при беременности?", "Дозировка железа?", "Ещё вопрос"]
    assert {q["user"] for q in questions} == {"Медик 0", "Медик 1"}
    assert all(q["status"] == "answered" and q["total_ms"] is not None for q in questions)
    assert questions[1]["first_ms"] is not None  # у потока есть время первого слова


def test_model_failure_is_an_error(admin, medics):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(connect_error=True)
    assert ask(medics[0], "Вопрос при упавшей модели").status_code == 503
    row = days(admin)[0]
    assert row["errors"] == 1
    item = next(i for i in details(admin, today()) if i["kind"] == "question")
    assert item["status"] == "error" and item["error"] == "llm_unavailable"
    assert row["answer_ms"] is None  # сбой не портит среднее время


def test_refinements_votes_and_acceptance(admin, medics):
    created = refine(medics[0])
    for client in medics[1:4]:
        agree(client, created["id"])
    row = days(admin)[0]
    assert row["refinements"] == 1
    assert row["votes_agree"] == 3
    assert row["accepted"] == 1
    kinds = [i["kind"] for i in details(admin, today())]
    assert kinds.count("vote") == 3 and "refinement" in kinds and "refinement_accepted" in kinds


def test_day_follows_admin_time_zone(admin):
    store = app.dependency_overrides.get(get_store, get_store)()
    store.log_event("question", question="Ночной вопрос")
    # Тот же миг в UTC−12 и UTC+14 приходится на разные сутки.
    west, east = days(admin, tz=-720)[0]["day"], days(admin, tz=840)[0]["day"]
    assert west != east
    assert any(i["question"] == "Ночной вопрос" for i in details(admin, east, tz=840))
    assert not any(i["question"] == "Ночной вопрос" for i in details(admin, "2000-01-01"))


def test_bad_day_is_rejected(admin):
    assert admin.get("/api/v1/admin/activity/вчера").status_code in (404, 422)
    assert admin.get("/api/v1/admin/activity/2026-13-40").status_code == 422


def test_ready_polling_is_not_an_error(admin):
    app.dependency_overrides[get_llm] = lambda: FakeLLM(connect_error=True)
    assert admin.get("/ready").status_code == 503
    assert all(row["errors"] == 0 for row in days(admin))
