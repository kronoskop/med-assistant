"""Отбор фрагментов под вопрос врача.

Здесь же живёт разделение уровней: подтверждать утверждения может только
основа, документы подкрепления идут отдельным списком.
"""

from __future__ import annotations

import logging
import re
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

    from app.corpus.embed import (
        embed_query,  # локальный импорт: сеть только когда есть что искать
    )

    vectors = embed_query(question, settings)
    pool = max(settings.retrieval_top_k * 4, settings.rerank_candidates if settings.reranker_model else 0)
    if settings.retrieval_mode == "hybrid":
        candidates = corpus.search_hybrid(question, vectors[0], top_k=pool)
    else:
        candidates = corpus.search(vectors[0], top_k=pool, min_score=settings.retrieval_min_score)
    if settings.reranker_model and candidates:
        candidates = _reranked(question, candidates, settings.reranker_model)
    hits = tuple(_prefer_prose(candidates, settings.retrieval_top_k, settings.retrieval_max_tables))
    support = tuple(corpus.support_documents())
    if hits:
        return Retrieval(Grounding.GROUNDED, hits, support)
    if support:
        return Retrieval(Grounding.SUPPORT_ONLY, (), support)
    return Retrieval(Grounding.NO_MATCH)


def _reranked(question: str, candidates: list[Hit], model: str) -> list[Hit]:
    from app.corpus.rerank import rerank

    try:
        scores = rerank(question, [h.fragment.text for h in candidates], model)
    except Exception as exc:  # noqa: BLE001 — без переранжирования ответ хуже, но он есть
        logging.getLogger("app.corpus").error("переранжирование не сработало: %s", type(exc).__name__)
        return candidates
    paired = sorted(zip(scores, range(len(candidates))), key=lambda p: -p[0])
    return [candidates[i] for _, i in paired]


def _prefer_prose(candidates: list[Hit], top_k: int, max_tables: int) -> list[Hit]:
    """Проза вперёд, таблиц не больше нескольких.

    Содержимое таблицы модели не показывается, поэтому набор из одних таблиц
    оставляет её без материала: ответ вырождается в «смотрите таблицу».
    Таблицы остаются в выдаче — на них можно сослаться, — но не вытесняют
    фрагменты, по которым можно ответить по существу.
    """
    prose = [h for h in candidates if not h.fragment.is_table]
    tables = [h for h in candidates if h.fragment.is_table]
    chosen = prose[:top_k]
    room = max(top_k - len(chosen), 0) + min(max_tables, top_k)
    chosen += tables[: min(max_tables, room)]
    # Порядок кандидатов уже лучший из доступных (косинус, слияние или
    # переранжирование): сохраняем его, а не пересортировываем по косинусу.
    position = {id(h): i for i, h in enumerate(candidates)}
    chosen.sort(key=lambda h: position[id(h)])
    return chosen[: top_k + max_tables]


def render_fragments(hits: tuple[Hit, ...]) -> str:
    """Фрагменты в том виде, в каком их видит модель: с идентификатором,
    по которому потом сверяется ссылка.

    Фрагменты пронумерованы: номер модель ставит как ссылку, сервер переводит
    его обратно в идентификатор (`app.answer.numbered_to_ids`).

    Текст таблицы модели не показывается: извлечение расплющивает её в
    неразборчивую строку, и модель переписывает этот мусор в ответ. Вместо
    текста — пометка, что там таблица; врач откроет её по ссылке.
    """
    blocks = []
    for number, hit in enumerate(hits, start=1):
        fragment = hit.fragment
        body = (
            "Здесь таблица, её содержимое не приводится. Отвечай по остальным фрагментам; "
            "на таблицу можно сослаться дополнительно."
            if fragment.is_table
            else fragment.text
        )
        blocks.append(
            f"[{number}] {hit.document.title} — {fragment.location}\n{body}"
        )
    return "\n\n".join(blocks)


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_MIN_SENTENCE = 25


def attribute(text: str, hits: tuple[Hit, ...], settings: Settings | None = None) -> tuple[list[str], float]:
    """Запасные сноски, когда модель не поставила ни одной ссылки.

    Каждое предложение ответа сравнивается с отобранными фрагментами прозы
    (текст таблиц модель не видела); сноской становится ближайший фрагмент,
    если близость не ниже порога. Возвращает идентификаторы и лучшую близость
    — по ней подбирают порог. Пустой список — ответ ни на что не опирается.
    """
    settings = settings or get_settings()
    if settings.attribution_min_score <= 0:
        return [], 0.0
    sentences = [s.strip() for s in _SENTENCE_END.split(text) if len(s.strip()) >= _MIN_SENTENCE]
    prose = [hit for hit in hits if not hit.fragment.is_table]
    if not sentences or not prose:
        return [], 0.0

    from app.corpus.embed import embed_texts

    claims = embed_texts(sentences, settings, prefix=settings.embedding_query_prefix)
    passages = _passage_vectors(prose, settings)
    scores = claims @ passages.T
    ids: list[str] = []
    for row in scores:
        best = int(row.argmax())
        fragment_id = prose[best].fragment.id
        if row[best] >= settings.attribution_min_score and fragment_id not in ids:
            ids.append(fragment_id)
    return ids, round(float(scores.max()), 3)


_ID_MARKER = re.compile(r"\[([^\[\]]+:[^\[\]]+:\d+:\d+)\]")


def citation_support(text: str, hits: tuple[Hit, ...], settings: Settings | None = None) -> float | None:
    """Насколько предложения со ссылками модели близки к фрагментам, на которые
    ссылаются: лучшая близость пары «предложение — его фрагмент».

    Ссылка сама по себе не доказывает опору: на посторонний вопрос модель
    может написать стих и сослаться на протокол. Ниже порога
    `citation_min_support` ответ не считается опирающимся на документы.
    None — сравнить нечего (ссылки только на таблицы или без текста рядом).
    """
    settings = settings or get_settings()
    by_id = {hit.fragment.id: hit for hit in hits if not hit.fragment.is_table}
    # Ссылка, поставленная после точки («…г/л. [2]»), отрезается в отдельный
    # кусок — она относится к предыдущему предложению.
    sentences: list[tuple[str, list[str]]] = []
    for piece in _SENTENCE_END.split(text):
        ids = [i for i in _ID_MARKER.findall(piece) if i in by_id]
        plain = _ID_MARKER.sub("", piece).strip(" .,;:")
        if len(plain) < _MIN_SENTENCE and sentences:
            sentences[-1][1].extend(ids)
        else:
            sentences.append((plain, ids))
    pairs = [
        (plain, by_id[i])
        for plain, ids in sentences
        if len(plain) >= _MIN_SENTENCE
        for i in dict.fromkeys(ids)
    ]
    if not pairs:
        return None

    from app.corpus.embed import embed_texts

    # Предложение со ссылками на два фрагмента встречается в парах дважды:
    # каждое предложение считается один раз.
    plains = list(dict.fromkeys(plain for plain, _ in pairs))
    vectors = embed_texts(plains, settings, prefix=settings.embedding_query_prefix)
    claims = vectors[[plains.index(plain) for plain, _ in pairs]]
    passages = _passage_vectors([hit for _, hit in pairs], settings)
    return round(float((claims * passages).sum(axis=1).max()), 3)


def _passage_vectors(hits: list[Hit], settings: Settings):
    """Векторы фрагментов: из индекса, если отбор их приложил, иначе — расчёт.

    В индексе они посчитаны той же моделью и с тем же префиксом passage
    (`index.load` не открывает индекс другой модели), так что пересчёт дал бы
    те же числа ценой прогона модели на каждый вопрос.
    """
    import numpy as np

    if hits and all(hit.vector is not None for hit in hits):
        return np.stack([hit.vector for hit in hits])
    from app.corpus.embed import embed_passages

    return embed_passages([hit.fragment.text for hit in hits], settings)


class Retriever:
    """Отбор фрагментов как зависимость: в тестах подменяется целиком."""

    def __call__(self, question: str) -> Retrieval:
        return retrieve(question)

    def attribute(self, text: str, hits: tuple[Hit, ...]) -> tuple[list[str], float]:
        return attribute(text, hits)

    def citation_support(self, text: str, hits: tuple[Hit, ...]) -> float | None:
        return citation_support(text, hits)


def get_retriever() -> Retriever:
    return Retriever()
