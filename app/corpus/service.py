"""Отбор фрагментов под вопрос врача.

Здесь же живёт разделение уровней: подтверждать утверждения может только
основа, документы подкрепления идут отдельным списком.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.corpus.index import Corpus, Hit, load
from app.corpus.manifest import Document
from app.settings import Settings, get_settings


class Grounding(str, Enum):
    GROUNDED = "grounded"          # нашлись фрагменты основы
    EMPTY_CORPUS = "empty_corpus"  # корпус не собран
    NO_MATCH = "no_match"          # по вопросу ничего не нашлось
    SUPPORT_ONLY = "support_only"  # есть только подкрепление


@dataclass(frozen=True)
class Retrieval:
    status: Grounding
    hits: tuple[Hit, ...] = ()
    support: tuple[Document, ...] = field(default=())

    @property
    def is_grounded(self) -> bool:
        return self.status is Grounding.GROUNDED


# Корпус читается с диска один раз на каталог: Settings не хешируется,
# да и ключ здесь по смыслу — каталог, а не весь конфиг.
_CACHE: dict[str, Corpus] = {}


def _corpus(settings: Settings) -> Corpus:
    key = settings.corpus_dir
    if key not in _CACHE:
        _CACHE[key] = load(settings)
    return _CACHE[key]


def reset_corpus_cache() -> None:
    _CACHE.clear()


def retrieve(question: str, settings: Settings | None = None, *, corpus: Corpus | None = None) -> Retrieval:
    settings = settings or get_settings()
    corpus = corpus if corpus is not None else _corpus(settings)
    if corpus.is_empty:
        return Retrieval(Grounding.EMPTY_CORPUS)

    from app.corpus.embed import embed_query  # локальный импорт: сеть только когда есть что искать

    vectors = embed_query(question, settings)
    hits = tuple(
        corpus.search(vectors[0], top_k=settings.retrieval_top_k, min_score=settings.retrieval_min_score)
    )
    support = tuple(corpus.support_documents())
    if hits:
        return Retrieval(Grounding.GROUNDED, hits, support)
    if support:
        return Retrieval(Grounding.SUPPORT_ONLY, (), support)
    return Retrieval(Grounding.NO_MATCH)


def render_fragments(hits: tuple[Hit, ...]) -> str:
    """Фрагменты в том виде, в каком их видит модель: с идентификатором,
    по которому потом сверяется ссылка.

    Текст таблицы модели не показывается: извлечение расплющивает её в
    неразборчивую строку, и модель переписывает этот мусор в ответ. Вместо
    текста — пометка, что там таблица; врач откроет её по ссылке.
    """
    blocks = []
    for hit in hits:
        fragment = hit.fragment
        body = (
            "Таблица. Её содержимое не приводится — сошлись на неё и отправь врача к документу."
            if fragment.is_table
            else fragment.text
        )
        blocks.append(
            f"[{fragment.id}] {hit.document.title} — {fragment.location}\n{body}"
        )
    return "\n\n".join(blocks)


class Retriever:
    """Отбор фрагментов как зависимость: в тестах подменяется целиком."""

    def __call__(self, question: str) -> Retrieval:
        return retrieve(question)


def get_retriever() -> Retriever:
    return Retriever()
