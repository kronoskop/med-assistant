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


def _pdf(text_lines: list[str]) -> bytes:
    """Минимальный PDF с текстом: без внешних библиотек, только для разбора."""
    stream = "BT /F1 12 Tf 50 750 Td 14 TL " + " ".join(f"({line}) '" for line in text_lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = "%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")


def test_parallel_parsing_gives_the_same_fragments(tmp_path):
    from app.corpus.manifest import load
    from app.corpus.store import MANIFEST_PATH, edition_path
    from app.settings import Settings

    documents = [d for d in load(MANIFEST_PATH) if d.level is EvidenceLevel.BASE][:3]
    for n, document in enumerate(documents):
        edition = document.local_editions[0]
        path = edition_path(tmp_path, document, edition)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"Document {n} line {i} about protocol care and dosing details" for i in range(30)]
        path.write_bytes(_pdf(lines))

    settings = Settings(_env_file=None, corpus_dir=str(tmp_path))
    serial, _ = index_module.build(settings, root=tmp_path, use_cache=False, workers=1)
    parallel, _ = index_module.build(settings, root=tmp_path, use_cache=False, workers=2)
    assert serial, "тестовые PDF не дали фрагментов"
    assert [f.id for f in parallel] == [f.id for f in serial]
    assert {f.document_id for f in serial} == {d.id for d in documents}


def test_vectors_are_reused_only_for_the_same_fragments_and_model(tmp_path):
    import numpy as np

    from app.corpus.chunks import Fragment
    from app.corpus.index import index_is_current, save, vectors_fingerprint

    frags = [Fragment("d:ru:1:0", "d", "ru", 1, 0, None, "текст")]
    mark = vectors_fingerprint(frags, "local:e5", "passage: ")
    assert not index_is_current(tmp_path, mark)
    save(frags, np.zeros((1, 3), dtype=np.float32), tmp_path, embedding="local:e5", fingerprint=mark)
    assert index_is_current(tmp_path, mark)
    assert not index_is_current(tmp_path, vectors_fingerprint(frags, "local:other", "passage: "))
    changed = [Fragment("d:ru:1:0", "d", "ru", 1, 0, None, "другой текст")]
    assert not index_is_current(tmp_path, vectors_fingerprint(changed, "local:e5", "passage: "))
