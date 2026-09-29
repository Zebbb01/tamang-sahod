"""Measure the AI parts against the SMART targets.

    python -m evals.run            retrieval + not-covered decision (needs the index)
    python -m evals.run extract    question-to-form extraction (needs GROQ_API_KEY)

Exits non-zero when a target is missed, so CI fails on a regression.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (HERE / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def retrieval() -> bool:
    from app import search

    rows = load("retrieval.jsonl")
    results = [(row, *search.search(row["q"])) for row in rows]
    in_scope = [(row, passages, sim) for row, passages, sim in results if row.get("expect")]
    out_scope = [(row, sim) for row, _, sim in results if not row.get("expect")]

    misses = []
    for row, passages, _ in in_scope:
        if not any(p["source"] == src and title in p["title"] for p in passages for src, title in row["expect"]):
            misses.append((row["q"], [p["title"] for p in passages]))
    hit_rate = 1 - len(misses) / len(in_scope)

    print("threshold  in-scope kept  out-of-scope refused")
    for t in [x / 100 for x in range(30, 75, 5)]:
        kept = sum(sim >= t for _, _, sim in in_scope)
        refused = sum(sim < t for _, sim in out_scope)
        mark = "  <- current" if abs(t - search.MIN_SIMILARITY) < 1e-9 else ""
        print(f"  {t:.2f}      {kept:>2}/{len(in_scope)}          {refused:>2}/{len(out_scope)}{mark}")

    kept = sum(sim >= search.MIN_SIMILARITY for _, _, sim in in_scope)
    refused = sum(sim < search.MIN_SIMILARITY for _, sim in out_scope)
    print(f"\nRetrieval hit@3: {hit_rate:.0%} ({len(in_scope) - len(misses)}/{len(in_scope)})  target >= 90%")
    print(f"In-scope answered: {kept}/{len(in_scope)}")
    print(f"Out-of-scope refused: {refused}/{len(out_scope)}  target >= {len(out_scope) - 1}/{len(out_scope)}")
    for q, titles in misses:
        print(f"  MISS {q}\n       got: {titles}")
    for row, sim in out_scope:
        if sim >= search.MIN_SIMILARITY:
            print(f"  ANSWERED OUT-OF-SCOPE ({sim:.2f}) {row['q']}")
    return hit_rate >= 0.9 and refused >= len(out_scope) - 1


def extraction() -> bool:
    from app.extract import extract

    rows = load("extract.jsonl")
    right = 0
    for row in rows:
        got = extract(row["q"])
        topic, fields = got if got else ("none", {})
        expected = {k: Decimal(v) if isinstance(v, str) and v.replace(".", "").isdigit() else v
                    for k, v in row["fields"].items()}
        found = {k: str(v) if k == "date" else v for k, v in fields.items() if k in expected}
        ok = topic == row["topic"] and found == expected
        right += ok
        if not ok:
            print(f"  WRONG {row['q']}\n        got {topic} {fields}")
    print(f"Extraction: {right}/{len(rows)} ({right / len(rows):.0%})  target >= 90%")
    return right / len(rows) >= 0.9


if __name__ == "__main__":
    ok = extraction() if sys.argv[1:] == ["extract"] else retrieval()
    sys.exit(0 if ok else 1)
