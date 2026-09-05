"""Извлечение текста из PDF корпуса.

Возвращает страницы, а не сплошной текст: место в документе нужно, чтобы
сноска приводила врача к разделу, а не к сорокастраничному файлу.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

# Буквы кириллицы и латиницы. Если их доля в извлечённом тексте мала,
# перед нами скан или сломанная кодировка, а не читаемый текст.
_LETTERS = re.compile(r"[a-zA-Zа-яА-ЯёЁʻʼґєіїўқғҳ]")
_WHITESPACE = re.compile(r"[ \t ]+")
_BREAKS = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class Page:
    number: int  # с единицы, как видит человек
    text: str


def read_pages(path: Path) -> list[Page]:
    reader = PdfReader(str(path))
    pages: list[Page] = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append(Page(number=index, text=normalize(page.extract_text() or "")))
    return pages


def normalize(text: str) -> str:
    text = text.replace("­", "").replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BREAKS.sub("\n\n", text).strip()


def readable_ratio(text: str) -> float:
    """Доля букв среди непробельных символов: мера читаемости извлечения."""
    dense = [ch for ch in text if not ch.isspace()]
    if not dense:
        return 0.0
    return len(_LETTERS.findall(text)) / len(dense)


def is_readable(text: str, *, min_chars: int = 200, min_ratio: float = 0.5) -> bool:
    return len(text) >= min_chars and readable_ratio(text) >= min_ratio
