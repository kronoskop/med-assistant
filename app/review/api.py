"""HTTP API входа, уточнений, личного кабинета и админки."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.review.auth import COOKIE, current_user, get_store, require_admin, require_medic, throttle
from app.review.store import Store
from app.review.verified import get_question_embedder, safe_embedding
from app.schemas import AppError, ChatMessage
from app.settings import get_settings

router = APIRouter(prefix="/api/v1")

Role = Literal["admin", "medic", "observer"]
LONG = 20_000


class LoginBody(BaseModel):
    login: str = Field(max_length=64)
    password: str = Field(max_length=256)


class PasswordBody(BaseModel):
    current: str = Field(max_length=256)
    new: str = Field(max_length=256)


class RefinementBody(BaseModel):
    question: str = Field(min_length=1, max_length=LONG)
    text: str = Field(min_length=1, max_length=LONG)
    model_answer: str = Field(default="", max_length=LONG)
    language: str = Field(default="", max_length=8)
    # Реплики диалога до вопроса: уточнение ответа на «а детям?» без них бессмысленно.
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)


class VoteBody(BaseModel):
    agree: bool
    comment: str = Field(default="", max_length=2000)


class ProposalBody(BaseModel):
    text: str = Field(min_length=1, max_length=LONG)
    comment: str = Field(default="", max_length=2000)


class DecisionBody(BaseModel):
    accept: bool


class UserCreate(BaseModel):
    login: str = Field(max_length=64)
    name: str = Field(max_length=120)
    role: Role
    password: str = Field(max_length=256)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=256)


class SettingsBody(BaseModel):
    required_confirmations: int


# ── вход ──────────────────────────────────────────────────
@router.post("/auth/login")
def login(body: LoginBody, request: Request, response: Response, store: Store = Depends(get_store)):
    throttle.check(body.login)
    settings = get_settings()
    found = store.login(body.login, body.password, settings.session_hours * 3600)
    throttle.record(body.login, found is not None)
    if found is None:
        raise AppError(401, "bad_credentials", "Неверный логин или пароль")
    token, user = found
    response.set_cookie(
        COOKIE,
        token,
        max_age=int(settings.session_hours * 3600),
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )
    return {"user": user}


@router.post("/auth/logout")
def logout(request: Request, response: Response, store: Store = Depends(get_store)):
    store.logout(request.cookies.get(COOKIE, ""))
    response.delete_cookie(COOKIE, path="/")
    return {"status": "ok"}


@router.get("/auth/me")
def me(user: dict = Depends(current_user), store: Store = Depends(get_store)):
    return {"user": user, "counts": store.counts(user), "required_confirmations": store.required_confirmations()}


@router.post("/auth/password")
def change_password(
    body: PasswordBody, request: Request, user: dict = Depends(current_user), store: Store = Depends(get_store)
):
    store.change_password(user["id"], body.current, body.new, keep_token=request.cookies.get(COOKIE, ""))
    return {"status": "ok"}


# ── уточнения ─────────────────────────────────────────────
@router.post("/refinements", status_code=201)
async def create_refinement(
    body: RefinementBody,
    user: dict = Depends(require_medic),
    store: Store = Depends(get_store),
    embedder=Depends(get_question_embedder),
):
    vector = await asyncio.to_thread(safe_embedding, embedder, body.question)
    return await asyncio.to_thread(
        store.create_refinement,
        user,
        question=body.question,
        text=body.text,
        model_answer=body.model_answer,
        history=[m.model_dump() for m in body.history],
        language=body.language,
        embedding=vector,
        embedding_model=getattr(embedder, "model", "") if vector is not None else "",
    )


@router.get("/refinements")
def list_refinements(
    scope: Literal["queue", "mine", "accepted", "all"] = "queue",
    user: dict = Depends(current_user),
    store: Store = Depends(get_store),
):
    if user["role"] == "observer" or (scope == "all" and user["role"] != "admin"):
        raise AppError(403, "forbidden", "Недостаточно прав")
    return {"items": store.list_refinements(user, scope)}


@router.post("/refinements/{refinement_id}/vote")
def vote(
    refinement_id: int, body: VoteBody, user: dict = Depends(require_medic), store: Store = Depends(get_store)
):
    return store.vote(user, refinement_id, body.agree, body.comment)


@router.post("/refinements/{refinement_id}/proposals", status_code=201)
def propose(
    refinement_id: int, body: ProposalBody, user: dict = Depends(require_medic), store: Store = Depends(get_store)
):
    return store.propose(user, refinement_id, body.text, body.comment)


@router.post("/proposals/{proposal_id}/decision")
def decide(
    proposal_id: int, body: DecisionBody, user: dict = Depends(require_medic), store: Store = Depends(get_store)
):
    return store.decide_proposal(user, proposal_id, body.accept)


@router.post("/refinements/{refinement_id}/archive")
def archive(refinement_id: int, user: dict = Depends(require_admin), store: Store = Depends(get_store)):
    return store.archive(user, refinement_id)


# ── личный кабинет ────────────────────────────────────────
@router.get("/notifications")
def notifications(user: dict = Depends(current_user), store: Store = Depends(get_store)):
    return {"items": store.notifications(user)}


@router.post("/notifications/read")
def notifications_read(user: dict = Depends(current_user), store: Store = Depends(get_store)):
    store.mark_read(user)
    return {"status": "ok"}


# ── админка ───────────────────────────────────────────────
@router.get("/admin/users")
def users(_: dict = Depends(require_admin), store: Store = Depends(get_store)):
    return {"items": store.list_users()}


@router.post("/admin/users", status_code=201)
def create_user(body: UserCreate, _: dict = Depends(require_admin), store: Store = Depends(get_store)):
    return store.create_user(body.login, body.name, body.role, body.password)


@router.patch("/admin/users/{user_id}")
def update_user(
    user_id: int, body: UserUpdate, _: dict = Depends(require_admin), store: Store = Depends(get_store)
):
    return store.update_user(user_id, **body.model_dump())


@router.get("/admin/settings")
def admin_settings(_: dict = Depends(require_admin), store: Store = Depends(get_store)):
    return {"required_confirmations": store.required_confirmations()}


@router.put("/admin/settings")
def update_settings(body: SettingsBody, _: dict = Depends(require_admin), store: Store = Depends(get_store)):
    return {"required_confirmations": store.set_required_confirmations(body.required_confirmations)}


@router.get("/admin/export.jsonl")
def export(_: dict = Depends(require_admin), store: Store = Depends(get_store)):
    """Принятые пары для будущего дообучения: строка — один диалог."""
    lines = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in store.export_rows())
    return Response(
        lines,
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="accepted-refinements.jsonl"'},
    )
