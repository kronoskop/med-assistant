"""Индекс корпуса: фрагменты и их представления рядом с документами.

Корпус измеряется сотнями фрагментов, поэтому отбор — полный перебор
косинусной близости. Специализированная векторная база на таком объёме
ничего не даёт, а сложности добавляет.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from app.corpus import manifest as manifest_module
from app.corpus.chunks import Fragment, split_document
from app.corpus.extract import read_pages
from app.corpus.manifest import Document, EvidenceLevel
from app.corpus.store import MANIFEST_PATH, edition_path
from app.settings import Settings

INDEX_FILE = "index.json"
VECTORS_FILE = "vectors.npy"


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


def build(settings: Settings, *, root: Path | None = None) -> tuple[list[Fragment], list[Document]]:
    """Собирает фрагменты из скачанных документов основы."""
    root = root or Path(settings.corpus_dir)
    documents = manifest_module.load(MANIFEST_PATH)
    fragments: list[Fragment] = []
    for document in documents:
        if document.level is not EvidenceLevel.BASE:
            continue  # подкрепление показывается ссылкой и фрагментов не даёт
        for edition in document.local_editions:
            path = edition_path(root, document, edition)
            if not path.exists():
                continue
            fragments.extend(split_document(document.id, edition.language, read_pages(path)))
    return fragments, documents


def save(fragments: list[Fragment], vectors: np.ndarray, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / INDEX_FILE).write_text(
        json.dumps({"fragments": [asdict(f) for f in fragments]}, ensure_ascii=False),
        encoding="utf-8",
    )
    np.save(root / VECTORS_FILE, vectors)


def load(settings: Settings, *, root: Path | None = None) -> Corpus:
    root = root or Path(settings.corpus_dir)
    documents = manifest_module.load(MANIFEST_PATH)
    index_path, vectors_path = root / INDEX_FILE, root / VECTORS_FILE
    if not index_path.exists() or not vectors_path.exists():
        return Corpus(documents, [], np.zeros((0, 0), dtype=np.float32))
    raw = json.loads(index_path.read_text(encoding="utf-8"))
    fragments = [Fragment(**item) for item in raw["fragments"]]
    return Corpus(documents, fragments, np.load(vectors_path))
