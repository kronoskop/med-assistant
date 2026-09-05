"""Хранилище корпуса: файлы на диске, вне git.

В репозитории живёт манифест, здесь — код, который по нему получает файлы
и проверяет, что получен именно тот документ.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from app.corpus.manifest import Document, Edition, sha256

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).parent / "documents.json"


@dataclass(frozen=True)
class FetchResult:
    document_id: str
    language: str
    path: Path
    digest: str
    downloaded: bool
    matched: bool | None  # None — контрольной суммы в манифесте ещё не было


def edition_path(root: Path, document: Document, edition: Edition) -> Path:
    return root / document.id / edition.filename


def fetch_edition(
    root: Path,
    document: Document,
    edition: Edition,
    *,
    client: httpx.Client,
    force: bool = False,
) -> FetchResult:
    target = edition_path(root, document, edition)
    if target.exists() and not force:
        digest = sha256(target.read_bytes())
        return FetchResult(document.id, edition.language, target, digest, False, _matched(edition, digest))

    response = client.get(edition.url, follow_redirects=True, timeout=120)
    response.raise_for_status()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    digest = sha256(response.content)
    return FetchResult(document.id, edition.language, target, digest, True, _matched(edition, digest))


def fetch_all(documents: list[Document], root: Path, *, force: bool = False) -> list[FetchResult]:
    results: list[FetchResult] = []
    headers = {"User-Agent": "CliniCompass corpus fetcher"}
    with httpx.Client(headers=headers) as client:
        for document in documents:
            for edition in document.local_editions:
                results.append(fetch_edition(root, document, edition, client=client, force=force))
    return results


def _matched(edition: Edition, digest: str) -> bool | None:
    if edition.sha256 is None:
        return None
    return edition.sha256 == digest
