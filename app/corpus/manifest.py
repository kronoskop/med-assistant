"""Манифест корпуса: что за документ, откуда он и какого он уровня.

Сами файлы в репозиторий не попадают — в git живёт только описание, по
которому корпус воспроизводится на другой машине.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class EvidenceLevel(str, Enum):
    """Уровень доказательности документа.

    Основа — обязательные к применению документы учреждения: только они
    подтверждают конкретные утверждения ответа. Подкрепление — международные
    и справочные документы: ориентир, который при расхождении уступает основе.
    """

    BASE = "base"
    SUPPORT = "support"


@dataclass(frozen=True)
class Edition:
    """Языковая редакция документа: тот же документ, другой язык.

    `filename` есть только у редакций, которые скачиваются и разбиваются на
    фрагменты. Документы подкрепления показываются ссылкой и цитат не дают,
    поэтому для них достаточно адреса.
    """

    language: str
    url: str
    filename: str | None = None
    sha256: str | None = None

    @property
    def is_local(self) -> bool:
        return self.filename is not None

    def to_dict(self) -> dict:
        data: dict = {"language": self.language, "url": self.url}
        if self.filename:
            data["filename"] = self.filename
        if self.sha256:
            data["sha256"] = self.sha256
        return data


@dataclass(frozen=True)
class Document:
    """Документ корпуса. Русская и узбекская редакции — один документ."""

    id: str
    title: str
    origin: str
    level: EvidenceLevel
    revision: str
    editions: tuple[Edition, ...] = field(default_factory=tuple)

    def edition(self, language: str) -> Edition | None:
        for item in self.editions:
            if item.language == language:
                return item
        return None

    @property
    def local_editions(self) -> tuple[Edition, ...]:
        """Редакции, которые скачиваются: только они дают фрагменты."""
        return tuple(item for item in self.editions if item.is_local)

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(item.language for item in self.editions)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "origin": self.origin,
            "level": self.level.value,
            "revision": self.revision,
            "editions": [item.to_dict() for item in self.editions],
        }


def load(path: Path) -> list[Document]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [_document(entry) for entry in raw["documents"]]


def dump(documents: list[Document], path: Path) -> None:
    payload = {"documents": [document.to_dict() for document in documents]}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _document(entry: dict) -> Document:
    for key in ("id", "title", "origin", "level", "revision", "editions"):
        if key not in entry:
            raise ValueError(f"в записи манифеста нет поля {key!r}: {entry.get('id', entry)!r}")
    if not entry["editions"]:
        raise ValueError(f"документ {entry['id']!r} без языковых редакций")
    return Document(
        id=entry["id"],
        title=entry["title"],
        origin=entry["origin"],
        level=EvidenceLevel(entry["level"]),
        revision=entry["revision"],
        editions=tuple(
            Edition(
                language=item["language"],
                url=item["url"],
                filename=item.get("filename"),
                sha256=item.get("sha256"),
            )
            for item in entry["editions"]
        ),
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
