import json

from app.corpus import index as index_module
from app.corpus.chunks import Fragment
from app.corpus.index import FRAGMENTS_CACHE, corpus_signature
from app.corpus.manifest import Document, Edition, EvidenceLevel


def _document(sha: str = "abc") -> Document:
    return Document(
        id="doc",
        title="Стандарт",
        origin="МЗ РУз",
        level=EvidenceLevel.BASE,
        revision="2026",
        editions=(Edition("ru", "https://example.invalid/d.pdf", "d.pdf", sha),),
    )


def _fragment() -> Fragment:
    return Fragment(
        id="doc:ru:1:0",
        document_id="doc",
        language="ru",
        page=1,
        ordinal=0,
        section="1",
        text="Текст фрагмента.",
        kind="prose",
    )


def test_signature_changes_when_a_document_changes():
    before = corpus_signature([_document("abc")])
    after = corpus_signature([_document("xyz")])
    assert before != after, "подмена документа не меняет отпечаток корпуса"


def test_signature_changes_when_chunking_changes(monkeypatch):
    before = corpus_signature([_document()])
    monkeypatch.setattr(index_module, "TARGET_CHARS", index_module.TARGET_CHARS + 100)
    assert corpus_signature([_document()]) != before, "правила нарезки не влияют на отпечаток"


def test_cache_is_used_when_the_signature_matches(tmp_path):
    signature = corpus_signature([_document()])
    payload = {"signature": signature, "fragments": [_fragment().__dict__]}
    (tmp_path / FRAGMENTS_CACHE).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert [f.id for f in index_module._read_cache(tmp_path, signature)] == ["doc:ru:1:0"]


def test_stale_cache_is_ignored(tmp_path):
    payload = {"signature": "старый-отпечаток", "fragments": [_fragment().__dict__]}
    (tmp_path / FRAGMENTS_CACHE).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert index_module._read_cache(tmp_path, "новый-отпечаток") is None


def test_cache_with_an_outdated_fragment_shape_is_ignored(tmp_path):
    """Формат фрагмента изменился — разбор должен пойти заново, а не упасть."""
    payload = {"signature": "s", "fragments": [{"id": "x", "неизвестное_поле": 1}]}
    (tmp_path / FRAGMENTS_CACHE).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert index_module._read_cache(tmp_path, "s") is None


def test_broken_cache_is_ignored(tmp_path):
    (tmp_path / FRAGMENTS_CACHE).write_text("{не json", encoding="utf-8")
    assert index_module._read_cache(tmp_path, "s") is None


def test_missing_cache_is_not_an_error(tmp_path):
    assert index_module._read_cache(tmp_path, "s") is None
