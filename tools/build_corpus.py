"""Наполнить корпус и собрать индекс одной командой.

Скачивает документы по манифесту, сверяет контрольные суммы, разбирает PDF
параллельно на всех ядрах и считает эмбеддинги в LM Studio. Повторный запуск
ничего не скачивает и не разбирает заново, если корпус не менялся.

    uv run python tools/build_corpus.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.corpus.embed import embed_passages  # noqa: E402
from app.corpus.index import build, save  # noqa: E402
from app.corpus.manifest import load  # noqa: E402
import httpx  # noqa: E402

from app.corpus.store import MANIFEST_PATH, fetch_edition  # noqa: E402
from app.settings import get_settings  # noqa: E402


def main() -> int:
    settings = get_settings()
    root = Path(settings.corpus_dir)
    if not root.is_absolute():
        root = ROOT / root

    started = time.perf_counter()
    print("Скачиваю документы…", flush=True)
    results, failed = [], []
    with httpx.Client(headers={"User-Agent": "CliniCompass corpus fetcher"}) as client:
        for document in load(MANIFEST_PATH):
            for edition in document.local_editions:
                try:
                    results.append(fetch_edition(root, document, edition, client=client))
                except httpx.HTTPError as exc:
                    # Один недоступный файл не должен останавливать сборку:
                    # индекс соберётся из остальных, а пропуск виден в сводке.
                    failed.append(f"{document.id} ({edition.language}): {type(exc).__name__}")
    bad = [r for r in results if r.matched is False]
    fresh = sum(1 for r in results if r.downloaded)
    print(f"  файлов: {len(results)}, скачано сейчас: {fresh}, не скачалось: {len(failed)}")
    for line in failed:
        print(f"  НЕ СКАЧАЛСЯ: {line}")
    for r in bad:
        print(f"  НЕ СОВПАЛА КОНТРОЛЬНАЯ СУММА: {r.document_id} ({r.language})")
    if not results:
        print("Ни один документ не скачан: проверьте доступ к интернету.")
        return 1

    workers = max(1, (os.cpu_count() or 2) - 1)
    print(f"Разбираю PDF в {workers} процессах (первый раз долго, потом из кеша)…", flush=True)
    fragments, _ = build(settings, root=root, workers=workers)
    print(f"  фрагментов: {len(fragments)}")

    print("Считаю эмбеддинги в LM Studio…", flush=True)
    vectors = embed_passages([f.text for f in fragments], settings)
    save(fragments, vectors, root)
    print(f"Готово за {time.perf_counter() - started:.0f} с. Индекс: {root}")
    if bad or failed:
        print("Внимание: часть документов пропущена или изменилась на сайте — ответы по ним будут неполными.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
