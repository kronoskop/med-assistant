"""IP посетителя и примерная локация по нему — для журнала активности.

Локация берётся из офлайн-базы DB-IP Lite (формат MMDB, совместим с GeoIP2):
IP медиков никуда не отправляются. Базы нет — локация просто пустая.
Базу скачивает tools/setup_demo.sh; её лицензия (CC BY 4.0) требует указать
источник, подпись есть на странице «Активность».
"""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache
from pathlib import Path

from fastapi import Request

from app.settings import get_settings

logger = logging.getLogger("app.startup")

# Tailscale раздаёт адреса устройств из CGNAT-диапазона.
_TAILSCALE = ipaddress.ip_network("100.64.0.0/10")


def client_ip(request: Request) -> str:
    """Адрес посетителя. За Tailscale Funnel соединение приходит с 127.0.0.1,
    а настоящий адрес — в X-Forwarded-For. Заголовку верим, только если
    соединение локальное: снаружи его может подставить кто угодно."""
    peer = request.client.host if request.client else ""
    if _is_loopback(peer):
        forwarded = request.headers.get("x-forwarded-for", "")
        # Первый адрес — клиент, остальные — прокси по пути.
        first = forwarded.split(",")[0].strip()
        if _valid(first):
            return first
    return peer


def _valid(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return False
    return True


def _is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


@lru_cache(maxsize=2)
def _reader(path: str):
    if not path or not Path(path).is_file():
        return None
    try:
        import maxminddb

        return maxminddb.open_database(path)
    except Exception as exc:  # noqa: BLE001 — без базы журнал работает, только без локации
        logger.error("база локаций по IP не открылась (%s): %s", path, exc)
        return None


def _name(node: dict | None, lang: str = "ru") -> str:
    names = (node or {}).get("names") or {}
    return names.get(lang) or names.get("en") or ""


def locate(ip: str, reader=None) -> str:
    """«Ташкент, Ташкент, Узбекистан» или пометка для внутренних адресов."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if address.is_loopback:
        return "этот компьютер"
    if address.version == 4 and address in _TAILSCALE:
        return "сеть Tailscale"
    if address.is_private or address.is_link_local:
        return "локальная сеть"
    reader = reader if reader is not None else _reader(get_settings().geoip_db)
    if reader is None:
        return ""
    try:
        record = reader.get(ip) or {}
    except Exception:  # noqa: BLE001
        return ""
    nodes = [record.get("city"), (record.get("subdivisions") or [None])[0], record.get("country")]
    shown: list[str] = []
    keys: set[str] = set()
    for node in nodes:
        # Область с тем же именем, что и город («Ташкент, Ташкент») не повторяем;
        # сравнение по-английски: русское имя есть не у всех записей.
        key = _name(node, "en") or _name(node)
        if key and key not in keys:
            keys.add(key)
            shown.append(_name(node))
    return ", ".join(shown)


def visitor(request: Request) -> dict:
    """Поля журнала: адрес и локация."""
    ip = client_ip(request)
    return {"ip": ip, "location": locate(ip)}
