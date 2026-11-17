"""Вход, сеансы и проверка ролей."""

from __future__ import annotations

import logging
import secrets
import threading
import time
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, Request

from app.review.store import Store
from app.schemas import AppError
from app.settings import get_settings

COOKIE = "med_session"
logger = logging.getLogger("app.startup")


@lru_cache(maxsize=4)
def _store(path: str) -> Store:
    return Store(path)


def get_store() -> Store:
    return _store(str(Path(get_settings().data_dir) / "review.sqlite3"))


def ensure_first_admin(store: Store) -> None:
    """Первый администратор появляется при установке: остальных заводит он.

    Пароль берётся из ADMIN_PASSWORD; если он не задан, создаётся случайный и
    один раз печатается в журнал запуска.
    """
    if store.has_users():
        return
    settings = get_settings()
    password = settings.admin_password or secrets.token_urlsafe(9)
    store.create_user(settings.admin_login, "Администратор", "admin", password)
    if settings.admin_password:
        logger.warning("создан администратор «%s» с паролем из ADMIN_PASSWORD", settings.admin_login)
    else:
        logger.warning(
            "создан администратор «%s», временный пароль: %s — смените его после входа",
            settings.admin_login,
            password,
        )


# Гость для режима без авторизации (замеры, тесты API): прав медика у него нет.
GUEST = {"id": 0, "login": "", "name": "", "role": "observer", "active": True}


def current_user(request: Request, store: Store = Depends(get_store)) -> dict:
    user = store.session_user(request.cookies.get(COOKIE, ""))
    if user is not None:
        return user
    if not get_settings().auth_required:
        return GUEST
    raise AppError(401, "unauthorized", "Войдите в систему")


def require_medic(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "medic":
        raise AppError(403, "forbidden", "Доступно только медикам")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise AppError(403, "forbidden", "Доступно только администратору")
    return user


class LoginThrottle:
    """Пять неверных паролей подряд — минута паузы для этого логина."""

    LIMIT, PAUSE = 5, 60.0

    def __init__(self) -> None:
        self._fails: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(login: str) -> str:
        # Тот же вид, в каком логин ищется в базе: иначе « admin», «admin » и т. д.
        # давали бы по пять попыток каждый.
        return login.strip().casefold()

    def check(self, login: str) -> None:
        with self._lock:
            count, since = self._fails.get(self._key(login), (0, 0.0))
            if count >= self.LIMIT and time.monotonic() - since < self.PAUSE:
                raise AppError(429, "too_many_attempts", "Слишком много попыток. Повторите через минуту")

    def record(self, login: str, ok: bool) -> None:
        key = self._key(login)
        with self._lock:
            if ok:
                self._fails.pop(key, None)
                return
            count, since = self._fails.get(key, (0, 0.0))
            if count >= self.LIMIT and time.monotonic() - since >= self.PAUSE:
                count = 0
            self._fails[key] = (count + 1, time.monotonic())
            if len(self._fails) > 10_000:
                # Чистим только остывшие записи: полная очистка снимала бы паузу
                # с логина, который сейчас перебирают.
                now = time.monotonic()
                self._fails = {
                    k: v for k, v in self._fails.items() if now - v[1] < self.PAUSE
                }


throttle = LoginThrottle()
