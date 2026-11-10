"""Замер скорости и качества ассистента на проверочном наборе вопросов.

Два режима:

- `chat` — через работающий сервер, как это видит врач: поток SSE, время до
  первого слова, полное время, привязка к документам, отказ на посторонний
  вопрос. Нужны запущенные LM Studio и `make run`.
- `retrieval` — только отбор фрагментов, в этом же процессе, без генерации:
  попал ли ожидаемый документ в выдачу. Нужны собранный индекс и модель
  эмбеддингов в LM Studio.

Ответы модели в отчёт не пишутся целиком: только длина, признак привязки и
документы сносок. Набор вопросов — черновик, эталон проверяет врач.

    uv run python tools/bench.py chat --url http://127.0.0.1:8000
    uv run python tools/bench.py retrieval
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "eval" / "questions.jsonl"
RESULTS = ROOT / "eval" / "results"


def load_questions(path: Path, lang: str | None, limit: int | None) -> list[dict]:
    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if lang:
        items = [q for q in items if q["lang"] == lang]
    return items[:limit] if limit else items


def chat_once(client: httpx.Client, url: str, question: str) -> dict:
    started = time.perf_counter()
    first: float | None = None
    text = ""
    final: dict = {}
    with client.stream(
        "POST",
        url.rstrip("/") + "/api/v1/chat",
        json={"stream": True, "messages": [{"role": "user", "content": question}]},
    ) as response:
        if response.status_code != 200:
            response.read()
            return {"error": f"HTTP {response.status_code}", "total_ms": _ms(started)}
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            data = json.loads(payload)
            if "text" in data:
                if first is None:
                    first = time.perf_counter()
                text += data["text"]
            elif "sources" in data:
                final = data
    return {
        "first_token_ms": round((first - started) * 1000) if first else None,
        "total_ms": _ms(started),
        "answer_chars": len(text),
        "grounded": bool(final.get("grounded")),
        "source_docs": sorted({s["document_id"] for s in final.get("sources", [])}),
        "questions": len(final.get("questions", [])),
        "conflicts": len(final.get("conflicts", [])),
    }


def run_chat(args) -> list[dict]:
    rows = []
    with httpx.Client(timeout=args.timeout) as client:
        for item in load_questions(args.questions, args.lang, args.limit):
            for attempt in range(args.repeat):
                try:
                    result = chat_once(client, args.url, item["question"])
                except httpx.HTTPError as exc:
                    result = {"error": type(exc).__name__}
                row = {"id": item["id"], "lang": item["lang"], "kind": item["kind"], "attempt": attempt, **result}
                expected = set(item["expected_docs"])
                if item["kind"] == "grounded":
                    row["ok"] = row.get("grounded", False) and bool(expected & set(row.get("source_docs", [])))
                else:
                    row["ok"] = "error" not in row and not row.get("grounded", True)
                rows.append(row)
                _progress(row)
    return rows


def run_retrieval(args) -> list[dict]:
    sys.path.insert(0, str(ROOT))
    from app.corpus.service import retrieve
    from app.settings import get_settings

    settings = get_settings()
    rows = []
    for item in load_questions(args.questions, args.lang, args.limit):
        if item["kind"] != "grounded":
            continue
        started = time.perf_counter()
        retrieval = retrieve(item["question"], settings)
        docs = [hit.document.id for hit in retrieval.hits]
        expected = set(item["expected_docs"])
        rank = next((i + 1 for i, d in enumerate(docs) if d in expected), None)
        row = {
            "id": item["id"],
            "lang": item["lang"],
            "kind": item["kind"],
            "retrieval_ms": _ms(started),
            "rank": rank,
            "ok": rank is not None,
            "top_docs": docs,
        }
        rows.append(row)
        _progress(row)
    return rows


def summarize(rows: list[dict], mode: str) -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["lang"]].append(row)
        groups["все"].append(row)
    lines = []
    if mode == "chat":
        lines.append(f"{'язык':<5} {'n':>3} {'1-е слово p50':>14} {'p90':>7} {'всего p50':>10} {'p90':>7} {'верно':>6} {'ошибки':>7}")
        for lang, items in groups.items():
            first = [r["first_token_ms"] for r in items if r.get("first_token_ms")]
            total = [r["total_ms"] for r in items if "error" not in r]
            ok = sum(1 for r in items if r.get("ok"))
            errors = sum(1 for r in items if "error" in r)
            lines.append(
                f"{lang:<5} {len(items):>3} {_p(first, 50):>14} {_p(first, 90):>7} "
                f"{_p(total, 50):>10} {_p(total, 90):>7} {ok:>3}/{len(items):<3}{errors:>6}"
            )
        lines.append("«верно»: на профильный вопрос есть сноска на ожидаемый документ, на посторонний — отказ. Время в мс.")
    else:
        lines.append(f"{'язык':<5} {'n':>3} {'попал в выдачу':>15} {'на 1-м месте':>13} {'мс p50':>8}")
        for lang, items in groups.items():
            hit = sum(1 for r in items if r["ok"])
            top1 = sum(1 for r in items if r["rank"] == 1)
            ms = [r["retrieval_ms"] for r in items]
            lines.append(f"{lang:<5} {len(items):>3} {hit:>11}/{len(items):<3} {top1:>9}/{len(items):<3} {_p(ms, 50):>8}")
    return "\n".join(lines)


def _p(values: list[float], q: int) -> str:
    if not values:
        return "—"
    if len(values) == 1:
        return str(round(values[0]))
    return str(round(statistics.quantiles(values, n=100, method="inclusive")[q - 1]))


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _progress(row: dict) -> None:
    mark = "ok " if row.get("ok") else "-- "
    detail = row.get("error") or row.get("first_token_ms") or row.get("rank")
    print(f"{mark}{row['id']:<8} {detail}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["chat", "retrieval"])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--lang", choices=["ru", "uz", "en"])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--label", default="", help="подпись прогона в имени файла, например модель")
    args = parser.parse_args()

    rows = run_chat(args) if args.mode == "chat" else run_retrieval(args)
    summary = summarize(rows, args.mode)
    print(summary)

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{args.mode}{'-' + args.label if args.label else ''}"
    (RESULTS / f"{name}.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    (RESULTS / f"{name}.txt").write_text(summary + "\n", encoding="utf-8")
    print(f"\nОтчёт: eval/results/{name}.txt", file=sys.stderr)


if __name__ == "__main__":
    main()
