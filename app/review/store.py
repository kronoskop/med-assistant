"""Хранилище пользователей, уточнений и голосов — один файл SQLite.

Отдельного сервера базы нет: демо живёт на одной машине, а записей — сотни.
Соединение открывается на каждую операцию: это микросекунды, зато нет общего
состояния между потоками.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from app.schemas import AppError

ROLES = ("admin", "medic", "observer")
DEFAULT_CONFIRMATIONS = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    login TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS refinements (
    id INTEGER PRIMARY KEY,
    question TEXT NOT NULL,
    question_norm TEXT NOT NULL,
    history TEXT NOT NULL DEFAULT '[]',
    model_answer TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT '',
    author_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'pending',
    parent_id INTEGER REFERENCES refinements(id),
    embedding BLOB,
    embedding_model TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    decided_at REAL
);
CREATE INDEX IF NOT EXISTS refinements_status ON refinements(status);
CREATE TABLE IF NOT EXISTS votes (
    refinement_id INTEGER NOT NULL REFERENCES refinements(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    agree INTEGER NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    PRIMARY KEY (refinement_id, user_id)
);
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY,
    refinement_id INTEGER NOT NULL REFERENCES refinements(id),
    author_id INTEGER NOT NULL REFERENCES users(id),
    text TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    decided_at REAL
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    refinement_id INTEGER,
    proposal_id INTEGER,
    actor_id INTEGER,
    created_at REAL NOT NULL,
    read_at REAL
);
CREATE INDEX IF NOT EXISTS notifications_user ON notifications(user_id, read_at);
-- Журнал для страницы «Активность»: входы, вопросы, сбои. Уточнения, голоса и
-- формулировки сюда не дублируются — у них свои таблицы с временем.
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    kind TEXT NOT NULL,
    user_id INTEGER,
    login TEXT NOT NULL DEFAULT '',
    question TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    followup INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    first_ms REAL,
    total_ms REAL,
    refinement_id INTEGER,
    ip TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_time ON events(created_at);
-- История консультаций: диалог целиком, как его видит интерфейс. Владелец —
-- один пользователь, чужие диалоги не видны никому, в том числе администратору.
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT '',
    items TEXT NOT NULL DEFAULT '[]',
    turns INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS conversations_user ON conversations(user_id, updated_at);
"""

# Виды событий журнала и исходы вопроса.
EVENT_KINDS = ("login", "login_failed", "logout", "question", "error", "refinement_accepted", "refinement_rejected")
QUESTION_STATUSES = ("answered", "refused", "verified", "stopped", "error")


_journal_logger = logging.getLogger("app.activity")


def safe_log(store: "Store", kind: str, **fields) -> None:
    """Запись в журнал активности не должна ломать вход или ответ врачу."""
    try:
        store.log_event(kind, **fields)
    except Exception:  # noqa: BLE001
        _journal_logger.exception("не удалось записать событие %s", kind)


def normalize_question(text: str) -> str:
    """Один и тот же вопрос с другим регистром, пробелами и знаком в конце."""
    return re.sub(r"[\s\W_]+", " ", text.casefold(), flags=re.UNICODE).strip()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$")
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _error(status: int, code: str, message: str) -> AppError:
    return AppError(status, code, message)


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(_SCHEMA)
            # Колонки, добавленные после первого выпуска журнала.
            have = {r["name"] for r in db.execute("PRAGMA table_info(events)")}
            for column in ("ip", "location"):
                if column not in have:
                    db.execute(f"ALTER TABLE events ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:  # одна транзакция на операцию
                yield db
        finally:
            db.close()

    # ── пользователи ──────────────────────────────────────
    @staticmethod
    def _user(row) -> dict:
        return {
            "id": row["id"],
            "login": row["login"],
            "name": row["name"],
            "role": row["role"],
            "active": bool(row["active"]),
        }

    def has_users(self) -> bool:
        with self._db() as db:
            return db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def list_users(self) -> list[dict]:
        with self._db() as db:
            return [self._user(r) for r in db.execute("SELECT * FROM users ORDER BY id")]

    def create_user(self, login: str, name: str, role: str, password: str) -> dict:
        login, name = login.strip(), name.strip()
        self._check_user_fields(login=login, name=name, role=role, password=password)
        with self._db() as db:
            try:
                cursor = db.execute(
                    "INSERT INTO users (login, name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                    (login, name, role, hash_password(password), time.time()),
                )
            except sqlite3.IntegrityError as exc:
                raise _error(409, "login_taken", "Такой логин уже есть") from exc
            return self._user(db.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone())

    @staticmethod
    def _check_user_fields(*, login=None, name=None, role=None, password=None) -> None:
        if login is not None and not re.fullmatch(r"[\w.@-]{2,64}", login):
            raise _error(422, "bad_login", "Логин: 2–64 символа, буквы, цифры, точка, дефис")
        if name is not None and not 1 <= len(name) <= 120:
            raise _error(422, "bad_name", "Укажите имя")
        if role is not None and role not in ROLES:
            raise _error(422, "bad_role", "Неизвестная роль")
        if password is not None and len(password) < 8:
            raise _error(422, "weak_password", "Пароль не короче 8 символов")

    def update_user(self, user_id: int, *, name=None, role=None, active=None, password=None) -> dict:
        self._check_user_fields(name=name.strip() if name is not None else None, role=role, password=password)
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise _error(404, "not_found", "Не найдено")
            loses_admin = row["role"] == "admin" and row["active"] and (
                (role is not None and role != "admin") or active is False
            )
            if loses_admin:
                others = db.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1 AND id != ?", (user_id,)
                ).fetchone()[0]
                if not others:
                    raise _error(409, "last_admin", "Нельзя оставить систему без администратора")
            if name is not None:
                db.execute("UPDATE users SET name = ? WHERE id = ?", (name.strip(), user_id))
            if role is not None:
                db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            if active is not None:
                db.execute("UPDATE users SET active = ? WHERE id = ?", (int(active), user_id))
            if password is not None:
                db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
            if password is not None or active is False:
                # Сброшенный пароль и отключение выбивают открытые сеансы.
                db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            return self._user(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def change_password(self, user_id: int, current: str, new: str, keep_token: str = "") -> None:
        self._check_user_fields(password=new)
        with self._db() as db:
            row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None or not verify_password(current, row["password_hash"]):
                raise _error(403, "bad_credentials", "Неверный текущий пароль")
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user_id))
            db.execute(
                "DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (user_id, _token_hash(keep_token))
            )

    # ── сеансы ────────────────────────────────────────────
    def login(self, login: str, password: str, ttl_seconds: float) -> tuple[str, dict] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE login = ?", (login.strip(),)).fetchone()
            if row is None or not row["active"] or not verify_password(password, row["password_hash"]):
                return None
            token = secrets.token_urlsafe(32)
            now = time.time()
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            db.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (_token_hash(token), row["id"], now + ttl_seconds),
            )
            return token, self._user(row)

    def session_user(self, token: str) -> dict | None:
        if not token:
            return None
        with self._db() as db:
            row = db.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1",
                (_token_hash(token), time.time()),
            ).fetchone()
            return self._user(row) if row else None

    def logout(self, token: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    # ── настройки ─────────────────────────────────────────
    def required_confirmations(self) -> int:
        with self._db() as db:
            return self._required(db)

    @staticmethod
    def _required(db) -> int:
        row = db.execute("SELECT value FROM config WHERE key = 'required_confirmations'").fetchone()
        return int(row["value"]) if row else DEFAULT_CONFIRMATIONS

    def set_required_confirmations(self, value: int) -> int:
        if not 1 <= value <= 50:
            raise _error(422, "bad_value", "Число подтверждений: от 1 до 50")
        with self._db() as db:
            db.execute(
                "INSERT INTO config (key, value) VALUES ('required_confirmations', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(value),),
            )
            # Порог снизили — ожидающие, которым теперь хватает голосов, принимаются.
            for row in db.execute("SELECT id FROM refinements WHERE status = 'pending' ORDER BY id").fetchall():
                self._accept_if_confirmed(db, row["id"])
        return value

    # ── уточнения ─────────────────────────────────────────
    def create_refinement(
        self,
        author: dict,
        *,
        question: str,
        text: str,
        model_answer: str = "",
        history: list[dict] | None = None,
        language: str = "",
        embedding: np.ndarray | None = None,
        embedding_model: str = "",
    ) -> dict:
        question, text = question.strip(), text.strip()
        if not question or not text:
            raise _error(422, "validation_error", "Нужны вопрос и текст уточнения")
        with self._db() as db:
            new_id = self._insert(
                db, author["id"], question, text, model_answer, history or [], language, embedding, embedding_model
            )
            return self._view(db, new_id, author)

    @staticmethod
    def _insert(db, author_id, question, text, model_answer, history, language, embedding, embedding_model,
                parent_id=None) -> int:
        blob = None if embedding is None else np.asarray(embedding, dtype=np.float32).tobytes()
        return db.execute(
            "INSERT INTO refinements (question, question_norm, history, model_answer, text, language, author_id, "
            "parent_id, embedding, embedding_model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (question, normalize_question(question), json.dumps(history, ensure_ascii=False), model_answer, text,
             language, author_id, parent_id, blob, embedding_model, time.time()),
        ).lastrowid

    def _pending(self, db, refinement_id: int):
        row = db.execute("SELECT * FROM refinements WHERE id = ?", (refinement_id,)).fetchone()
        if row is None:
            raise _error(404, "not_found", "Не найдено")
        if row["status"] != "pending":
            raise _error(409, "closed", "Голосование по этому уточнению уже закрыто")
        return row

    def vote(self, user: dict, refinement_id: int, agree: bool, comment: str = "") -> dict:
        comment = comment.strip()
        with self._db() as db:
            row = self._pending(db, refinement_id)
            if row["author_id"] == user["id"]:
                raise _error(403, "own_refinement", "Своё уточнение подтверждать нельзя")
            if not agree and not comment:
                raise _error(422, "comment_required", "К несогласию нужен комментарий")
            try:
                db.execute(
                    "INSERT INTO votes (refinement_id, user_id, agree, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                    (refinement_id, user["id"], int(agree), comment, time.time()),
                )
            except sqlite3.IntegrityError as exc:
                raise _error(409, "already_voted", "Вы уже голосовали") from exc
            if agree:
                self._accept_if_confirmed(db, refinement_id)
            else:
                # Одного несогласия достаточно: уточнение не действует.
                self._close(db, refinement_id, "rejected")
                self._decided(db, refinement_id, "refinement_rejected")
                self._close_proposals(db, refinement_id)
                self._notify(db, row["author_id"], "refinement_rejected", refinement_id, actor_id=user["id"])
            return self._view(db, refinement_id, user)

    @staticmethod
    def _close(db, refinement_id: int, status: str) -> None:
        db.execute(
            "UPDATE refinements SET status = ?, decided_at = ? WHERE id = ?", (status, time.time(), refinement_id)
        )

    def _close_proposals(self, db, refinement_id: int, except_id: int | None = None, actor_id=None) -> None:
        """Голосование закрылось — висящие формулировки к нему теряют смысл."""
        rows = db.execute(
            "SELECT id, author_id FROM proposals WHERE refinement_id = ? AND status = 'pending'", (refinement_id,)
        ).fetchall()
        for row in rows:
            if row["id"] == except_id:
                continue
            db.execute(
                "UPDATE proposals SET status = 'declined', decided_at = ? WHERE id = ?", (time.time(), row["id"])
            )
            self._notify(db, row["author_id"], "proposal_declined", refinement_id, row["id"], actor_id)

    def _accept_if_confirmed(self, db, refinement_id: int) -> bool:
        agreed = db.execute(
            "SELECT COUNT(*) FROM votes WHERE refinement_id = ? AND agree = 1", (refinement_id,)
        ).fetchone()[0]
        if agreed < self._required(db):
            return False
        row = db.execute("SELECT * FROM refinements WHERE id = ?", (refinement_id,)).fetchone()
        # Действует последний принятый: прежний ответ на тот же вопрос уходит в архив.
        for old in db.execute(
            "SELECT id, author_id FROM refinements WHERE status = 'accepted' AND question_norm = ? AND history = ?",
            (row["question_norm"], row["history"]),
        ).fetchall():
            self._close(db, old["id"], "archived")
            self._notify(db, old["author_id"], "refinement_archived", old["id"])
        self._close(db, refinement_id, "accepted")
        self._decided(db, refinement_id, "refinement_accepted")
        self._close_proposals(db, refinement_id)
        self._notify(db, row["author_id"], "refinement_accepted", refinement_id)
        return True

    def archive(self, admin: dict, refinement_id: int) -> dict:
        """Администратор снимает принятый ответ: система перестаёт его использовать."""
        with self._db() as db:
            row = db.execute("SELECT * FROM refinements WHERE id = ?", (refinement_id,)).fetchone()
            if row is None:
                raise _error(404, "not_found", "Не найдено")
            if row["status"] not in ("accepted", "pending"):
                raise _error(409, "closed", "Уточнение уже закрыто")
            self._close(db, refinement_id, "archived")
            self._close_proposals(db, refinement_id, actor_id=admin["id"])
            self._notify(db, row["author_id"], "refinement_archived", refinement_id, actor_id=admin["id"])
            return self._view(db, refinement_id, admin)

    # ── своя формулировка ─────────────────────────────────
    def propose(self, user: dict, refinement_id: int, text: str, comment: str = "") -> dict:
        text = text.strip()
        if not text:
            raise _error(422, "validation_error", "Нужен текст формулировки")
        with self._db() as db:
            row = self._pending(db, refinement_id)
            if row["author_id"] == user["id"]:
                raise _error(403, "own_refinement", "Своё уточнение правит сам автор")
            if db.execute(
                "SELECT 1 FROM proposals WHERE refinement_id = ? AND author_id = ? AND status = 'pending'",
                (refinement_id, user["id"]),
            ).fetchone():
                raise _error(409, "already_proposed", "Ваша формулировка уже ждёт решения автора")
            proposal_id = db.execute(
                "INSERT INTO proposals (refinement_id, author_id, text, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                (refinement_id, user["id"], text, comment.strip(), time.time()),
            ).lastrowid
            self._notify(db, row["author_id"], "proposal_received", refinement_id, proposal_id, user["id"])
            return self._view(db, refinement_id, user)

    def decide_proposal(self, user: dict, proposal_id: int, accept: bool) -> dict:
        """Автор уточнения принимает или отклоняет чужую формулировку.

        Принял — текущее уточнение закрывается, голосование начинается заново
        по новой формулировке; согласие автора считается первым подтверждением.
        """
        with self._db() as db:
            proposal = db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            if proposal is None:
                raise _error(404, "not_found", "Не найдено")
            if proposal["status"] != "pending":
                raise _error(409, "closed", "По этой формулировке решение уже принято")
            row = self._pending(db, proposal["refinement_id"])
            if row["author_id"] != user["id"]:
                raise _error(403, "forbidden", "Решает автор уточнения")
            now = time.time()
            if not accept:
                db.execute("UPDATE proposals SET status = 'declined', decided_at = ? WHERE id = ?", (now, proposal_id))
                self._notify(db, proposal["author_id"], "proposal_declined", row["id"], proposal_id, user["id"])
                return self._view(db, row["id"], user)
            db.execute("UPDATE proposals SET status = 'accepted', decided_at = ? WHERE id = ?", (now, proposal_id))
            self._close(db, row["id"], "replaced")
            self._close_proposals(db, row["id"], except_id=proposal_id, actor_id=user["id"])
            new_id = db.execute(
                "INSERT INTO refinements (question, question_norm, history, model_answer, text, language, author_id, "
                "parent_id, embedding, embedding_model, created_at) "
                "SELECT question, question_norm, history, model_answer, ?, language, ?, id, embedding, "
                "embedding_model, ? FROM refinements WHERE id = ?",
                (proposal["text"], proposal["author_id"], now, row["id"]),
            ).lastrowid
            db.execute(
                "INSERT INTO votes (refinement_id, user_id, agree, comment, created_at) VALUES (?, ?, 1, '', ?)",
                (new_id, user["id"], now),
            )
            self._notify(db, proposal["author_id"], "proposal_accepted", new_id, proposal_id, user["id"])
            self._accept_if_confirmed(db, new_id)
            return self._view(db, new_id, user)

    # ── чтение ────────────────────────────────────────────
    def get_refinement(self, user: dict, refinement_id: int) -> dict:
        with self._db() as db:
            if db.execute("SELECT 1 FROM refinements WHERE id = ?", (refinement_id,)).fetchone() is None:
                raise _error(404, "not_found", "Не найдено")
            return self._view(db, refinement_id, user)

    def list_refinements(self, user: dict, scope: str) -> list[dict]:
        uid = user["id"]
        queries = {
            # Очередь: чужие ожидающие, по которым я ещё не высказался.
            "queue": (
                "SELECT id FROM refinements r WHERE status = 'pending' AND author_id != ? AND NOT EXISTS "
                "(SELECT 1 FROM votes v WHERE v.refinement_id = r.id AND v.user_id = ?) ORDER BY id",
                (uid, uid),
            ),
            "mine": ("SELECT id FROM refinements WHERE author_id = ? ORDER BY id DESC LIMIT 200", (uid,)),
            "accepted": ("SELECT id FROM refinements WHERE status = 'accepted' ORDER BY decided_at DESC", ()),
            "all": ("SELECT id FROM refinements ORDER BY id DESC LIMIT 500", ()),
        }
        if scope not in queries:
            raise _error(422, "validation_error", "Неизвестный список")
        sql, params = queries[scope]
        with self._db() as db:
            return [self._view(db, r["id"], user) for r in db.execute(sql, params).fetchall()]

    def counts(self, user: dict) -> dict:
        uid = user["id"]
        with self._db() as db:
            queue = db.execute(
                "SELECT COUNT(*) FROM refinements r WHERE status = 'pending' AND author_id != ? AND NOT EXISTS "
                "(SELECT 1 FROM votes v WHERE v.refinement_id = r.id AND v.user_id = ?)",
                (uid, uid),
            ).fetchone()[0]
            unread = db.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL", (uid,)
            ).fetchone()[0]
        return {"queue": queue if user["role"] == "medic" else 0, "unread": unread}

    def _view(self, db, refinement_id: int, viewer: dict) -> dict:
        row = db.execute(
            "SELECT r.*, u.name AS author_name FROM refinements r JOIN users u ON u.id = r.author_id WHERE r.id = ?",
            (refinement_id,),
        ).fetchone()
        votes = [
            {"user": v["name"], "user_id": v["user_id"], "agree": bool(v["agree"]), "comment": v["comment"]}
            for v in db.execute(
                "SELECT v.*, u.name FROM votes v JOIN users u ON u.id = v.user_id "
                "WHERE v.refinement_id = ? ORDER BY v.created_at",
                (refinement_id,),
            )
        ]
        proposals = [
            {
                "id": p["id"],
                "author": p["name"],
                "author_id": p["author_id"],
                "text": p["text"],
                "comment": p["comment"],
                "status": p["status"],
            }
            for p in db.execute(
                "SELECT p.*, u.name FROM proposals p JOIN users u ON u.id = p.author_id "
                "WHERE p.refinement_id = ? ORDER BY p.id",
                (refinement_id,),
            )
        ]
        mine = row["author_id"] == viewer["id"]
        voted = any(v["user_id"] == viewer["id"] for v in votes)
        open_for_me = row["status"] == "pending" and not mine and viewer["role"] == "medic"
        return {
            "id": row["id"],
            "question": row["question"],
            "history": json.loads(row["history"]),
            "model_answer": row["model_answer"],
            "text": row["text"],
            "language": row["language"],
            "author": row["author_name"],
            "author_id": row["author_id"],
            "status": row["status"],
            "parent_id": row["parent_id"],
            "created_at": row["created_at"],
            "decided_at": row["decided_at"],
            "confirmations": sum(v["agree"] for v in votes),
            "required": self._required(db),
            "votes": votes,
            "proposals": proposals,
            "mine": mine,
            "can_vote": open_for_me and not voted,
            "can_propose": open_for_me
            and not any(p["author_id"] == viewer["id"] and p["status"] == "pending" for p in proposals),
        }

    # ── сообщения в личном кабинете ───────────────────────
    @staticmethod
    def _notify(db, user_id, kind, refinement_id=None, proposal_id=None, actor_id=None) -> None:
        db.execute(
            "INSERT INTO notifications (user_id, kind, refinement_id, proposal_id, actor_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, kind, refinement_id, proposal_id, actor_id, time.time()),
        )

    def notifications(self, user: dict, limit: int = 100) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT n.*, a.name AS actor, r.question, r.text, r.status AS refinement_status, "
                "p.text AS proposal_text, p.comment AS proposal_comment, p.status AS proposal_status "
                "FROM notifications n LEFT JOIN users a ON a.id = n.actor_id "
                "LEFT JOIN refinements r ON r.id = n.refinement_id LEFT JOIN proposals p ON p.id = n.proposal_id "
                "WHERE n.user_id = ? ORDER BY n.id DESC LIMIT ?",
                (user["id"], limit),
            ).fetchall()
            out = []
            for n in rows:
                item = {key: n[key] for key in n.keys() if key not in ("user_id", "actor_id", "read_at")}
                item["read"] = n["read_at"] is not None
                if n["kind"] == "refinement_rejected":
                    vote = db.execute(
                        "SELECT comment FROM votes WHERE refinement_id = ? AND agree = 0", (n["refinement_id"],)
                    ).fetchone()
                    item["comment"] = vote["comment"] if vote else ""
                out.append(item)
            return out

    def mark_read(self, user: dict) -> None:
        with self._db() as db:
            db.execute(
                "UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
                (time.time(), user["id"]),
            )

    # ── журнал активности ─────────────────────────────────
    @staticmethod
    def _decided(db, refinement_id: int, kind: str) -> None:
        """Решение по уточнению — в журнал в ту же транзакцию: дата решения
        в самой записи уточнения перезаписывается при уходе в архив."""
        question = db.execute("SELECT question FROM refinements WHERE id = ?", (refinement_id,)).fetchone()
        db.execute(
            "INSERT INTO events (created_at, kind, question, refinement_id) VALUES (?, ?, ?, ?)",
            (time.time(), kind, question["question"] if question else "", refinement_id),
        )

    def log_event(
        self,
        kind: str,
        *,
        user_id: int | None = None,
        login: str = "",
        question: str = "",
        language: str = "",
        followup: bool = False,
        status: str = "",
        error: str = "",
        first_ms: float | None = None,
        total_ms: float | None = None,
        ip: str = "",
        location: str = "",
    ) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO events (created_at, kind, user_id, login, question, language, followup, status, error, "
                "first_ms, total_ms, ip, location) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (time.time(), kind, user_id or None, login[:64], question, language[:8], int(followup), status,
                 error[:200], first_ms, total_ms, ip[:64], location[:200]),
            )

    # ── история консультаций ──────────────────────────────
    @staticmethod
    def _conversation(row, with_items: bool = False) -> dict:
        view = {
            "id": row["id"],
            "title": row["title"],
            "language": row["language"],
            "turns": row["turns"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if with_items:
            view["items"] = json.loads(row["items"])
        return view

    @staticmethod
    def _turns(items: list[dict]) -> int:
        return sum(1 for item in items if item.get("role") == "user" and not item.get("local"))

    def list_conversations(self, user_id: int, limit: int = 500) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT id, title, language, turns, created_at, updated_at FROM conversations "
                "WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            )
            return [self._conversation(r) for r in rows]

    def get_conversation(self, user_id: int, conversation_id: int) -> dict:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
            ).fetchone()
        # Чужой диалог неотличим от несуществующего: так не угадать чужие номера.
        if row is None:
            raise _error(404, "not_found", "Диалог не найден")
        return self._conversation(row, with_items=True)

    def save_conversation(
        self, user_id: int, conversation_id: int | None, *, title: str, language: str, items: list[dict]
    ) -> dict:
        title = " ".join(title.split())[:300] or "…"
        now = time.time()
        payload = json.dumps(items, ensure_ascii=False)
        with self._db() as db:
            if conversation_id is None:
                cursor = db.execute(
                    "INSERT INTO conversations (user_id, title, language, items, turns, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, title, language[:8], payload, self._turns(items), now, now),
                )
                conversation_id = cursor.lastrowid
            else:
                cursor = db.execute(
                    "UPDATE conversations SET title = ?, language = ?, items = ?, turns = ?, updated_at = ? "
                    "WHERE id = ? AND user_id = ?",
                    (title, language[:8], payload, self._turns(items), now, conversation_id, user_id),
                )
                if cursor.rowcount == 0:
                    raise _error(404, "not_found", "Диалог не найден")
            row = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return self._conversation(row)

    def delete_conversation(self, user_id: int, conversation_id: int) -> None:
        with self._db() as db:
            cursor = db.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
            )
        if cursor.rowcount == 0:
            raise _error(404, "not_found", "Диалог не найден")

    @staticmethod
    def _day_expr(column: str) -> str:
        # Сутки — по часам администратора: сдвиг приходит из браузера.
        return f"date({column} + :shift, 'unixepoch')"

    def activity_days(self, tz_minutes: int = 0, days: int = 90) -> list[dict]:
        """Сводка по дням, новые сверху: входы, вопросы по людям, время ответа, сбои, уточнения."""
        params = {"shift": tz_minutes * 60, "since": time.time() - days * 86400}
        out: dict[str, dict] = {}

        def day(key: str) -> dict:
            return out.setdefault(key, {
                "day": key, "users": set(), "logins": 0, "failed_logins": 0, "questions": 0, "per_user": {},
                "answer_ms": None, "first_ms": None, "errors": 0, "stopped": 0, "verified": 0, "refused": 0,
                "places": {}, "refinements": 0, "accepted": 0, "rejected": 0, "votes_agree": 0, "votes_disagree": 0, "proposals": 0,
            })

        with self._db() as db:
            names = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM users")}
            for r in db.execute(
                f"SELECT {self._day_expr('created_at')} AS d, kind, user_id, status, COUNT(*) AS n FROM events "
                "WHERE created_at >= :since GROUP BY d, kind, user_id, status",
                params,
            ):
                item = day(r["d"])
                if r["user_id"] and r["kind"] in ("login", "question"):
                    item["users"].add(r["user_id"])
                if r["kind"] == "login":
                    item["logins"] += r["n"]
                elif r["kind"] == "login_failed":
                    item["failed_logins"] += r["n"]
                elif r["kind"] == "error":
                    item["errors"] += r["n"]
                elif r["kind"] == "refinement_accepted":
                    item["accepted"] += r["n"]
                elif r["kind"] == "refinement_rejected":
                    item["rejected"] += r["n"]
                elif r["kind"] == "question":
                    item["questions"] += r["n"]
                    who = names.get(r["user_id"], "—")
                    item["per_user"][who] = item["per_user"].get(who, 0) + r["n"]
                    if r["status"] in ("error", "stopped", "verified", "refused"):
                        item[{"error": "errors"}.get(r["status"], r["status"])] += r["n"]
            # Откуда входили: локация (или IP, если её нет) и сколько раз.
            for r in db.execute(
                f"SELECT {self._day_expr('created_at')} AS d, user_id, ip, location, COUNT(*) AS n FROM events "
                "WHERE created_at >= :since AND kind = 'login' GROUP BY d, user_id, ip, location",
                params,
            ):
                place = (r["location"] or r["ip"] or "—", names.get(r["user_id"], "—"))
                places = day(r["d"])["places"]
                entry = places.setdefault(place, {"ips": set(), "logins": 0})
                entry["ips"].add(r["ip"])
                entry["logins"] += r["n"]
            # Среднее время — по завершённым ответам: оборванные и сбойные его исказят.
            for r in db.execute(
                f"SELECT {self._day_expr('created_at')} AS d, AVG(total_ms) AS total, AVG(first_ms) AS first "
                "FROM events WHERE created_at >= :since AND kind = 'question' "
                "AND status IN ('answered', 'refused', 'verified') GROUP BY d",
                params,
            ):
                item = day(r["d"])
                item["answer_ms"] = None if r["total"] is None else round(r["total"])
                item["first_ms"] = None if r["first"] is None else round(r["first"])
            for r in db.execute(
                f"SELECT {self._day_expr('created_at')} AS d, author_id, COUNT(*) AS n FROM refinements "
                "WHERE created_at >= :since GROUP BY d, author_id",
                params,
            ):
                item = day(r["d"])
                item["refinements"] += r["n"]
                item["users"].add(r["author_id"])
            for r in db.execute(
                f"SELECT {self._day_expr('created_at')} AS d, user_id, agree, COUNT(*) AS n FROM votes "
                "WHERE created_at >= :since GROUP BY d, user_id, agree",
                params,
            ):
                item = day(r["d"])
                item["votes_agree" if r["agree"] else "votes_disagree"] += r["n"]
                item["users"].add(r["user_id"])
            for r in db.execute(
                f"SELECT {self._day_expr('created_at')} AS d, COUNT(*) AS n FROM proposals "
                "WHERE created_at >= :since GROUP BY d",
                params,
            ):
                day(r["d"])["proposals"] += r["n"]
        rows = sorted(out.values(), key=lambda item: item["day"], reverse=True)
        for item in rows:
            item["users"] = len(item["users"])
            item["places"] = [
                {"place": place, "user": user, "logins": v["logins"], "ips": sorted(i for i in v["ips"] if i)}
                for (place, user), v in sorted(item["places"].items(), key=lambda kv: (kv[0][1], kv[0][0]))
            ]
            item["per_user"] = [
                {"name": name, "questions": n}
                for name, n in sorted(item["per_user"].items(), key=lambda kv: (-kv[1], kv[0]))
            ]
        return rows

    def activity_day(self, day: str, tz_minutes: int = 0) -> list[dict]:
        """Все события одних суток по порядку: кто, когда, что спросил, сколько ждал ответа."""
        try:
            start = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(minutes=tz_minutes))).timestamp()
        except ValueError as exc:
            raise _error(422, "validation_error", "Дата в формате ГГГГ-ММ-ДД") from exc
        window = {"start": start, "end": start + 86400}
        items: list[dict] = []
        with self._db() as db:
            for r in db.execute(
                "SELECT e.*, u.name FROM events e LEFT JOIN users u ON u.id = e.user_id "
                "WHERE e.created_at >= :start AND e.created_at < :end",
                window,
            ):
                items.append({
                    "time": r["created_at"],
                    "kind": r["kind"],
                    "user": r["name"] or r["login"] or "",
                    "question": r["question"],
                    "language": r["language"],
                    "followup": bool(r["followup"]),
                    "status": r["status"],
                    "error": r["error"],
                    "first_ms": r["first_ms"],
                    "total_ms": r["total_ms"],
                    "refinement_id": r["refinement_id"],
                    "ip": r["ip"],
                    "location": r["location"],
                })
            for r in db.execute(
                "SELECT r.id, r.question, r.text, r.created_at, r.parent_id, u.name FROM refinements r "
                "JOIN users u ON u.id = r.author_id WHERE r.created_at >= :start AND r.created_at < :end",
                window,
            ):
                items.append({
                    "time": r["created_at"], "kind": "refinement", "user": r["name"], "question": r["question"],
                    "text": r["text"], "refinement_id": r["id"], "status": "replacement" if r["parent_id"] else "",
                })
            for r in db.execute(
                "SELECT v.*, u.name, r.question FROM votes v JOIN users u ON u.id = v.user_id "
                "JOIN refinements r ON r.id = v.refinement_id WHERE v.created_at >= :start AND v.created_at < :end",
                window,
            ):
                items.append({
                    "time": r["created_at"], "kind": "vote", "user": r["name"], "question": r["question"],
                    "status": "agree" if r["agree"] else "disagree", "text": r["comment"],
                    "refinement_id": r["refinement_id"],
                })
            for r in db.execute(
                "SELECT p.*, u.name, r.question FROM proposals p JOIN users u ON u.id = p.author_id "
                "JOIN refinements r ON r.id = p.refinement_id WHERE p.created_at >= :start AND p.created_at < :end",
                window,
            ):
                items.append({
                    "time": r["created_at"], "kind": "proposal", "user": r["name"], "question": r["question"],
                    "text": r["text"], "refinement_id": r["refinement_id"],
                })
        items.sort(key=lambda item: item["time"])
        return items

    # ── принятые ответы: выдача и выгрузка ────────────────
    def accepted_for_matching(self) -> list[dict]:
        """Принятые ответы на самостоятельные вопросы (без предыстории диалога)."""
        with self._db() as db:
            rows = db.execute(
                "SELECT id, question, question_norm, text, embedding, embedding_model, decided_at FROM refinements "
                "WHERE status = 'accepted' AND history = '[]' ORDER BY decided_at DESC"
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "question": r["question"],
                    "question_norm": r["question_norm"],
                    "text": r["text"],
                    "embedding": None if r["embedding"] is None else np.frombuffer(r["embedding"], dtype=np.float32),
                    "embedding_model": r["embedding_model"],
                    "decided_at": r["decided_at"],
                    "confirmations": db.execute(
                        "SELECT COUNT(*) FROM votes WHERE refinement_id = ? AND agree = 1", (r["id"],)
                    ).fetchone()[0],
                }
                for r in rows
            ]

    def export_rows(self) -> list[dict]:
        """Принятые пары «вопрос — ответ» в формате диалога для дообучения."""
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM refinements WHERE status = 'accepted' ORDER BY decided_at"
            ).fetchall()
            return [
                {
                    "messages": [
                        *json.loads(r["history"]),
                        {"role": "user", "content": r["question"]},
                        {"role": "assistant", "content": r["text"]},
                    ],
                    "meta": {
                        "refinement_id": r["id"],
                        "language": r["language"],
                        "accepted_at": r["decided_at"],
                        "model_answer": r["model_answer"],
                    },
                }
                for r in rows
            ]
