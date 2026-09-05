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
    kind: str = "prose"  # prose | table

    @property
    def is_table(self) -> bool:
        return self.kind == "table"

    @property
    def location(self) -> str:
        place = f"с. {self.page}"
        if self.section:
            place += f", разд. {self.section}"
        return place


# Фрагмент считается таблицей, когда больше половины его строк размечены
# колонками: цитировать такую расплющенную таблицу бессмысленно, врачу
# показывается ссылка на место в документе.
TABLE_SHARE = 0.5

# Матрица обследований: цепочка одиночных маркеров вроде «+ + + +». Ловит
# таблицы, где строки-переносы размывают долю колонок.
_MARKER_RUN = re.compile(r"(?:[-+–—]\s+){3,}")


def split_document(document_id: str, language: str, pages: list[Page]) -> list[Fragment]:
    fragments: list[Fragment] = []
    section: str | None = None
    for page in pages:
        chunks = _split_lines(page, section) if page.lines else [
            (text, sec, 0.0, 0) for text, sec in _split_page(page.text, section)
        ]
        for ordinal, (text, section, share, columns) in enumerate(chunks):
            table = (share >= TABLE_SHARE and columns >= 2) or bool(_MARKER_RUN.search(text))
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
                    kind="table" if table else "prose",
                )
            )
    return fragments


def _split_lines(page: Page, section: str | None) -> list[tuple[str, str | None, float, int]]:
    """Режет страницу по строкам раскладки, считая долю строк с колонками."""
    out: list[tuple[str, str | None, float, int]] = []
    buffer: list[str] = []
    columns = total = size = 0

    def flush() -> None:
        nonlocal buffer, columns, total, size
        if buffer:
            share = columns / total if total else 0.0
            out.append(("\n".join(buffer), section, share, columns))
        buffer, columns, total, size = [], 0, 0, 0

    for line in page.lines:
        text = line.text.strip()
        if not text:
            continue
        heading = _heading(text)
        if heading:
            section = heading
        if size and size + len(text) > TARGET_CHARS:
            flush()
        buffer.append(text)
        size += len(text) + 1
        total += 1
        columns += line.columns
    flush()
    return out


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
