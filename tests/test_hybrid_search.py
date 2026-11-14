"""Гибридный поиск: слова достают абзац с конкретикой, который векторы
пропускают; переранжирование меняет порядок, но не состав фрагментов."""

import numpy as np

from app.corpus import service
from app.corpus.chunks import Fragment
from app.corpus.index import Corpus
from app.corpus.lexical import LexicalIndex, fuse, tokens
from app.settings import Settings
from tests.conftest import make_hit


def test_tokens_cut_endings_and_drop_stop_words():
    assert tokens("Анемия у беременных и беременности, 110 г/л") == [
        "анемия",
        "береме",
        "береме",
        "110",
        "г",
        "л",
    ]
    assert tokens("Homiladorlikda oʻtkir anemiya") == ["homila", "otkir", "anemiy"]


def test_bm25_prefers_the_fragment_with_the_exact_terms():
    index = LexicalIndex(
        [
            "Общие сведения об анемии.",
            "Анемия у беременных: гемоглобин ниже 110 г/л.",
            "Кесарево сечение.",
        ]
    )
    scores = index.scores("порог гемоглобина 110 при анемии у беременных")
    assert int(np.argmax(scores)) == 1
    assert scores[2] == 0


def test_fusion_lifts_a_fragment_found_by_words():
    vector = np.array([0.9, 0.8, 0.1, 0.7])
    lexical = np.array([0.0, 0.0, 5.0, 0.0])
    order = fuse(vector, lexical, depth=4)
    assert order[:2] == [2, 0], "найденное по слову встаёт рядом с лучшим по смыслу"


def _corpus() -> Corpus:
    hit = make_hit()
    texts = [
        "Общие положения ведения беременности.",
        "Анемия: гемоглобин ниже 110 г/л у беременных.",
        "Роды.",
    ]
    fragments = [
        Fragment(f"doc:ru:1:{i}", "doc", "ru", 1, i, None, t)
        for i, t in enumerate(texts)
    ]
    vectors = np.array([[1.0, 0.0], [0.6, 0.8], [0.9, 0.1]], dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    return Corpus([hit.document], fragments, vectors)


def test_hybrid_search_finds_what_vectors_rank_low(monkeypatch):
    monkeypatch.setattr(
        "app.corpus.embed.embed_query",
        lambda q, s: np.array([[1.0, 0.0]], dtype=np.float32),
    )
    question = "гемоглобин 110 анемия"
    vector_only = service.retrieve(
        question, Settings(_env_file=None, retrieval_top_k=1), corpus=_corpus()
    )
    hybrid = service.retrieve(
        question,
        Settings(_env_file=None, retrieval_top_k=1, retrieval_mode="hybrid"),
        corpus=_corpus(),
    )
    assert vector_only.hits[0].fragment.ordinal == 0
    assert hybrid.hits[0].fragment.ordinal == 1


def test_reranker_order_is_kept(monkeypatch):
    monkeypatch.setattr(
        "app.corpus.embed.embed_query",
        lambda q, s: np.array([[1.0, 0.0]], dtype=np.float32),
    )
    monkeypatch.setattr(
        "app.corpus.rerank.rerank",
        lambda q, texts, name: [1.0 if "Роды" in t else 0.0 for t in texts],
    )
    settings = Settings(_env_file=None, retrieval_top_k=2, reranker_model="fake")
    hits = service.retrieve("вопрос", settings, corpus=_corpus()).hits
    assert hits[0].fragment.text == "Роды."
