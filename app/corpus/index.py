"""Индекс корпуса: фрагменты и их представления рядом с документами.

Корпус измеряется сотнями фрагментов, поэтому отбор — полный перебор
косинусной близости. Специализированная векторная база на таком объёме
ничего не даёт, а сложности добавляет.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from app.corpus import manifest as manifest_module
from app.corpus.chunks import (
    MIN_CHARS,
    OVERLAP_CHARS,
    TABLE_SHARE,
    TARGET_CHARS,
    Fragment,
    split_document,
)
from app.corpus.extract import read_pages
from app.corpus.manifest import Document, EvidenceLevel
from app.corpus.store import MANIFEST_PATH, edition_path
from app.settings import Settings

logger = logging.getLogger("app.corpus")

INDEX_FILE = "index.json"
VECTORS_FILE = "vectors.npy"
FRAGMENTS_CACHE = "fragments.json"


@dataclass(frozen=True)
class Hit:
    fragment: Fragment
    document: Document
    score: float


class Corpus:
    """Документы корпуса плюс отбор фрагментов под вопрос."""

    def __init__(self, documents: list[Document], fragments: list[Fragment], vectors: np.ndarray) -> None:
        self.documents = {document.id: document for document in documents}
        self.fragments = fragments
        self.vectors = vectors

    @property
    def is_empty(self) -> bool:
        return not self.fragments

    def support_documents(self) -> list[Document]:
        return [d for d in self.documents.values() if d.level is EvidenceLevel.SUPPORT]

    def search(self, query_vector: np.ndarray, *, top_k: int, min_score: float) -> list[Hit]:
        if self.is_empty or self.vectors.size == 0:
            return []
        scores = self.vectors @ query_vector
        order = np.argsort(-scores)[:top_k]
        hits: list[Hit] = []
        for position in order:
            score = float(scores[position])
            if score < min_score:
                continue
            fragment = self.fragments[int(position)]
            hits.append(Hit(fragment, self.documents[fragment.document_id], score))
        return hits


def build(
    settings: Settings,
    *,
    root: Path | None = None,
    use_cache: bool = True,
    workers: int = 1,
) -> tuple[list[Fragment], list[Document]]:
    """Собирает фрагменты из скачанных документов основы.

    Разбор идёт послойно, чтобы отличить таблицу от прозы, и на сотне PDF
    занимает часы. Результат кешируется: пока состав корпуса и параметры
    разбиения не изменились, повторная сборка — чтение одного файла.
    """
    root = root or Path(settings.corpus_dir)
    documents = manifest_module.load(MANIFEST_PATH)
    signature = corpus_signature(documents)

    if use_cache:
        cached = _read_cache(root, signature)
        if cached is not None:
            return cached, documents

    jobs = [
        (document.id, edition.language, str(path))
        for document in documents
        if document.level is EvidenceLevel.BASE  # подкрепление показывается ссылкой и фрагментов не даёт
        for edition in document.local_editions
        if (path := edition_path(root, document, edition)).exists()
    ]
    fragments: list[Fragment] = []
    if workers > 1 and len(jobs) > 1:
        # Разбор PDF упирается в процессор, а документы независимы: каждый
        # разбирается в своём процессе. Порядок фрагментов сохраняется.
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=workers) as pool:
            for part in pool.map(_split_file, jobs):
                fragments.extend(part)
    else:
        for job in jobs:
            fragments.extend(_split_file(job))

    _write_cache(root, signature, fragments)
    return fragments, documents


def _split_file(job: tuple[str, str, str]) -> list[Fragment]:
    document_id, language, path = job
    return split_document(document_id, language, read_pages(Path(path)))


def corpus_signature(documents: list[Document]) -> str:
    """Отпечаток состава корпуса и параметров разбиения.

    Меняется состав документов или правила нарезки — кеш перестаёт подходить
    и разбор выполняется заново.
    """
    parts = [
        f"{document.id}:{edition.language}:{edition.sha256 or edition.filename}"
        for document in documents
        if document.level is EvidenceLevel.BASE
        for edition in document.local_editions
    ]
    parts.append(f"chunks:{TARGET_CHARS}:{OVERLAP_CHARS}:{MIN_CHARS}:{TABLE_SHARE}")
    return hashlib.sha256("|".join(sorted(parts)).encode("utf-8")).hexdigest()


def _read_cache(root: Path, signature: str) -> list[Fragment] | None:
    path = root / FRAGMENTS_CACHE
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if raw.get("signature") != signature:
        return None
    try:
        return [Fragment(**item) for item in raw["fragments"]]
    except TypeError:
        return None  # формат фрагмента изменился — разберём заново


def _write_cache(root: Path, signature: str, fragments: list[Fragment]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / FRAGMENTS_CACHE).write_text(
        json.dumps(
            {"signature": signature, "fragments": [asdict(f) for f in fragments]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def vectors_fingerprint(fragments: list[Fragment], embedding: str, prefix: str = "") -> str:
    """Отпечаток того, из чего посчитаны векторы: тексты фрагментов, модель и
    префикс. Совпал — пересчитывать нечего."""
    digest = hashlib.sha256(f"{embedding}|{prefix}".encode())
    for fragment in fragments:
        digest.update(b"\0" + fragment.id.encode() + b"\0" + fragment.text.encode())
    return digest.hexdigest()


def index_is_current(root: Path, fingerprint: str) -> bool:
    index_path, vectors_path = root / INDEX_FILE, root / VECTORS_FILE
    if not index_path.exists() or not vectors_path.exists():
        return False
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return raw.get("fingerprint") == fingerprint


def save(
    fragments: list[Fragment],
    vectors: np.ndarray,
    root: Path,
    embedding: str | None = None,
    fingerprint: str | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload: dict = {"fragments": [asdict(f) for f in fragments]}
    if embedding:
        payload["embedding"] = embedding
    if fingerprint:
        payload["fingerprint"] = fingerprint
    (root / INDEX_FILE).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    np.save(root / VECTORS_FILE, vectors)


def load(settings: Settings, *, root: Path | None = None) -> Corpus:
    root = root or Path(settings.corpus_dir)
    documents = manifest_module.load(MANIFEST_PATH)
    index_path, vectors_path = root / INDEX_FILE, root / VECTORS_FILE
    if not index_path.exists() or not vectors_path.exists():
        return Corpus(documents, [], np.zeros((0, 0), dtype=np.float32))
    raw = json.loads(index_path.read_text(encoding="utf-8"))
    from app.corpus.embed import model_id

    built_with, expected = raw.get("embedding"), model_id(settings)
    if built_with != expected:
        # Векторы другой модели несравнимы с вопросом: поиск по ним случаен.
        # Лучше честный отказ «документы недоступны», чем ответ не по теме.
        logger.error(
            "индекс собран моделью %s, а вопросы считаются %s: пересоберите индекс "
            "(uv run python tools/build_corpus.py)",
            built_with or "неизвестной",
            expected,
        )
        return Corpus(documents, [], np.zeros((0, 0), dtype=np.float32))
    fragments = [Fragment(**item) for item in raw["fragments"]]
    return Corpus(documents, fragments, np.load(vectors_path))
