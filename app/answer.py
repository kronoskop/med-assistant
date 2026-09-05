"""Сборка ответа чата: отбор фрагментов, проверка ссылок, отказ при пустоте.

Здесь проходит граница доверия: модель заявляет источники, а подтверждаются
только те, что действительно были отобраны.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.corpus.index import Hit
from app.corpus.service import Grounding, Retrieval
from app.prompt import REFUSAL_EMPTY_CORPUS, REFUSAL_NO_MATCH
from app.schemas import SourceFragment, SupportDocument


@dataclass(frozen=True)
class Grounded:
    retrieval: Retrieval
    fragments_prompt: str


def refusal_text(status: Grounding) -> str:
    return REFUSAL_EMPTY_CORPUS if status is Grounding.EMPTY_CORPUS else REFUSAL_NO_MATCH


def confirmed_sources(claimed: tuple[str, ...] | list[str], hits: tuple[Hit, ...]) -> list[SourceFragment]:
    """Оставляет только те ссылки, что указывают на реально отобранные фрагменты.

    Модель охотно ссылается на правдоподобные, но не существовавшие фрагменты;
    без этой сверки продукт получил бы фальшивую трассируемость.
    """
    by_id = {hit.fragment.id: hit for hit in hits}
    sources: list[SourceFragment] = []
    seen: set[str] = set()
    for raw in claimed:
        hit = by_id.get(str(raw).strip())
        if hit is None or hit.fragment.id in seen:
            continue
        seen.add(hit.fragment.id)
        sources.append(
            SourceFragment(
                id=hit.fragment.id,
                document_id=hit.document.id,
                document_title=hit.document.title,
                origin=hit.document.origin,
                revision=hit.document.revision,
                language=hit.fragment.language,
                location=hit.fragment.location,
                text=hit.fragment.text,
            )
        )
    return sources


def support_documents(retrieval: Retrieval) -> list[SupportDocument]:
    out: list[SupportDocument] = []
    for document in retrieval.support:
        edition = document.editions[0]
        out.append(
            SupportDocument(
                document_id=document.id,
                title=document.title,
                origin=document.origin,
                revision=document.revision,
                url=edition.url,
            )
        )
    return out


def last_question(messages) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


# Ссылка внутри ответа: [document:язык:страница:порядок]
_MARKER = re.compile(r"\[([^\[\]]+:[^\[\]]+:\d+:\d+)\]")


def weave_citations(text: str, hits: tuple[Hit, ...]) -> tuple[str, list[SourceFragment]]:
    """Заменяет идентификаторы в тексте на номера сносок.

    В ответе остаются только ссылки на реально отобранные фрагменты: выдуманный
    идентификатор вычёркивается вместе со скобками, иначе врач увидел бы сноску,
    ведущую в никуда. Нумерация — по первому появлению в тексте, чтобы номер
    сноски совпадал с порядком чтения.
    """
    by_id = {hit.fragment.id: hit for hit in hits}
    order: list[str] = []

    def replace(match: re.Match[str]) -> str:
        fragment_id = match.group(1)
        if fragment_id not in by_id:
            return ""  # ссылка в никуда: убираем вместе со скобками
        if fragment_id not in order:
            order.append(fragment_id)
        return f"[{order.index(fragment_id) + 1}]"

    woven = _MARKER.sub(replace, text)
    woven = re.sub(r" +([.,;:])", r"\1", woven)
    woven = re.sub(r"[ \t]{2,}", " ", woven).strip()
    return woven, confirmed_sources(order, hits)
