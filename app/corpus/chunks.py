"""Разбиение документов на фрагменты.

Фрагмент несёт координаты — документ, язык, страницу и раздел, — потому что
сноска должна приводить врача в место, а не в файл целиком.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.corpus.extract import Page

# Заголовок раздела: «4.2 Название», «IV. Название». Нужен, чтобы у фрагмента
# была человеческая координата помимо номера страницы.
_SECTION = re.compile(r"^\s*(\d+(?:\.\d+)*\.?|[IVX]+\.)\s+(\S.{2,80})$")

TARGET_CHARS = 900
OVERLAP_CHARS = 150
MIN_CHARS = 120


@dataclass(frozen=True)
class Fragment:
    id: str
    document_id: str
    language: str
    page: int
    ordinal: int
    section: str | None
    text: str

    @property
    def location(self) -> str:
        place = f"с. {self.page}"
        if self.section:
            place += f", разд. {self.section}"
        return place


def split_document(document_id: str, language: str, pages: list[Page]) -> list[Fragment]:
    fragments: list[Fragment] = []
    section: str | None = None
    for page in pages:
        for ordinal, (text, section) in enumerate(_split_page(page.text, section)):
            if len(text) < MIN_CHARS:
                continue
            fragments.append(
                Fragment(
                    id=f"{document_id}:{language}:{page.number}:{ordinal}",
                    document_id=document_id,
                    language=language,
                    page=page.number,
                    ordinal=ordinal,
                    section=section,
                    text=text,
                )
            )
    return fragments


def _split_page(text: str, section: str | None) -> list[tuple[str, str | None]]:
    """Режет страницу по абзацам до целевого размера, отслеживая текущий раздел."""
    out: list[tuple[str, str | None]] = []
    buffer: list[str] = []
    size = 0
    for paragraph in (p.strip() for p in text.split("\n") if p.strip()):
        heading = _heading(paragraph)
        if heading:
            section = heading
        if size and size + len(paragraph) > TARGET_CHARS:
            out.append(("\n".join(buffer), section))
            tail = "\n".join(buffer)[-OVERLAP_CHARS:]
            buffer = [tail] if tail else []
            size = len(tail)
        buffer.append(paragraph)
        size += len(paragraph) + 1
    if buffer:
        out.append(("\n".join(buffer), section))
    return out


def _heading(line: str) -> str | None:
    match = _SECTION.match(line)
    if not match:
        return None
    return match.group(1).rstrip(".")
