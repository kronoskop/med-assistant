"""Эмбеддинги внутри сервиса: проверка качества модели и защита от индекса,
собранного другой моделью. Настоящая модель не грузится — подменяется."""

import json
import sys
import types

import numpy as np
import pytest

from app.corpus import embed
from app.corpus import index as index_module
from app.corpus.chunks import Fragment
from app.schemas import AppError
from app.settings import Settings


class FakeModel:
    """Вектор — счётчик «смысловых» слов: близкое по теме совпадает, чужое нет."""

    WORDS = ("анемия", "гемоглобин", "кесарево", "плод")

    def __init__(self, name, device=None, local_files_only=False):
        FakeModel.loaded.append((name, local_files_only))
        if local_files_only and FakeModel.cache_empty:
            raise OSError("нет в кеше")

    def encode(self, texts, **kwargs):
        rows = []
        for text in texts:
            low = text.lower()
            rows.append([float(low.count(word[:5])) for word in self.WORDS] + [0.1])
        return np.asarray(rows)


@pytest.fixture
def fake_st(monkeypatch):
    FakeModel.loaded = []
    FakeModel.cache_empty = False
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setattr(embed, "_models", {})
    return FakeModel


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_local_backend_is_the_default_and_never_calls_lmstudio(fake_st, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("эмбеддинг ушёл в сеть")

    monkeypatch.setattr(embed, "_shared_client", no_network)
    vectors = embed.embed_texts(["анемия"], _settings())
    assert vectors.shape == (1, 5)
    assert np.isclose(np.linalg.norm(vectors[0]), 1.0)


def test_model_loads_from_cache_first_and_downloads_only_once(fake_st):
    fake_st.cache_empty = True
    settings = _settings()
    embed.embed_texts(["а"], settings)
    embed.embed_texts(["б"], settings)
    assert fake_st.loaded == [
        ("intfloat/multilingual-e5-small", True),
        ("intfloat/multilingual-e5-small", False),
    ]


def test_quality_check_passes_a_model_that_tells_topics_apart(fake_st):
    related, unrelated = embed.check_quality(_settings())
    assert related > unrelated


def test_quality_check_rejects_a_model_that_ranks_unrelated_higher(fake_st, monkeypatch):
    # Как сборка e5 в LM Studio: чужая фраза ближе, чем фраза по теме.
    def broken(texts, settings, *, prefix="", client=None):
        if prefix == settings.embedding_query_prefix:
            return np.asarray([[1.0, 0.0]])
        return embed.normalize(np.asarray([[0.934, 0.357], [0.96, 0.28]]))

    monkeypatch.setattr(embed, "embed_texts", broken)
    with pytest.raises(AppError) as error:
        embed.check_quality(_settings())
    assert error.value.code == "embedding_broken"


def _fragment() -> Fragment:
    return Fragment(id="mz-777:ru:1:0", document_id="mz-777", language="ru", page=1, ordinal=0, section=None, text="Анемия")


def test_index_remembers_its_embedding_model(tmp_path):
    settings = _settings(corpus_dir=str(tmp_path))
    index_module.save([_fragment()], np.ones((1, 3), dtype=np.float32), tmp_path, embedding=embed.model_id(settings))
    assert json.loads((tmp_path / "index.json").read_text())["embedding"] == "local:intfloat/multilingual-e5-small"
    assert not index_module.load(settings, root=tmp_path).is_empty


def test_index_of_another_model_is_not_searched(tmp_path, caplog):
    index_module.save([_fragment()], np.ones((1, 3), dtype=np.float32), tmp_path, embedding="lmstudio:text-embedding-multilingual-e5-small")
    corpus = index_module.load(_settings(corpus_dir=str(tmp_path)), root=tmp_path)
    assert corpus.is_empty, "поиск по векторам другой модели был бы случайным"
    assert "пересоберите индекс" in caplog.text


def test_index_without_model_mark_is_rebuilt(tmp_path):
    index_module.save([_fragment()], np.ones((1, 3), dtype=np.float32), tmp_path)
    assert index_module.load(_settings(corpus_dir=str(tmp_path)), root=tmp_path).is_empty
