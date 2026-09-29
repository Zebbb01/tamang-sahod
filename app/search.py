"""Hybrid search over the rule passages in data/corpus/*.md.

Passages are embedded with a multilingual model (so Taglish questions reach English
rules) into an embedded LanceDB index, and the vector ranking is fused with a
full-text ranking (so "Article 94" still lands). Build the index with:

    python -m app.search
"""

import re
from functools import cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
INDEX = DATA / "index"
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# Below this cosine similarity for the best passage, a question is "not covered".
# Tuned on evals/ (2026-09-28): 0.45 refuses 20/20 out-of-scope probes and keeps 37/40
# in-scope; 0.40 keeps 39/40 but refuses only 19/20. A wrong passage misleads more than
# a "not covered" does. Re-run `python -m evals.run` after changing the model or corpus.
MIN_SIMILARITY = 0.45

CONTRIBUTION_SOURCES = {"sss-ci-2024-006", "philhealth-pa-2025-0002", "hdmf-circular-460"}

# Neighbouring topics TamangSahod does not answer. They share words with the covered
# ones ("SSS", "final pay", "wage"), so similarity alone lets them through; a question
# closer to one of these than to every passage is "not covered".
NOT_COVERED = [
    "minimum wage rates by region",
    "registering a business or employees with SSS, PhilHealth or Pag-IBIG, online accounts",
    "SSS, PhilHealth and Pag-IBIG loans, housing loans and benefit claims",
    "deductions from salary: cash advances, loans, uniforms, damages, shortages",
    "income tax and withholding tax on salaries, BIR forms and filing",
    "separation pay, retirement pay, retrenchment",
    "maternity, paternity, solo parent and other special leaves",
    "business registration, DTI, SEC, mayor's permit, licenses",
    "termination, dismissal, resignation notice, labor complaints and cases",
    "night shift differential",
    "payslips, payroll software and spreadsheets",
]


def load_corpus() -> list[dict]:
    """Each '## title | location' heading in a corpus file starts one passage."""
    rows = []
    for path in sorted((DATA / "corpus").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        source = re.search(r"^source: (\S+)$", text, re.M).group(1)
        for block in re.split(r"^## ", text, flags=re.M)[1:]:
            head, _, body = block.partition("\n")
            title, _, where = head.partition(" | ")
            rows.append({
                "id": f"{source}#{len(rows)}",
                "source": source,
                "title": title.strip(),
                "where": where.strip(),
                "text": body.strip(),
            })
    return rows


def topic_of(row: dict) -> str:
    """The calculator a passage belongs with."""
    if row["source"] in CONTRIBUTION_SOURCES:
        return "contributions"
    if row["title"].startswith("13th month"):
        return "thirteenth"
    if row["source"] == "dole-la-06-20" or row["title"].startswith("Service incentive leave"):
        return "final"
    return "holiday"


def rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal-rank fusion: items ranked high in several lists come first."""
    score: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            score[item] = score.get(item, 0) + 1 / (k + rank)
    return sorted(score, key=score.get, reverse=True)


@cache
def _model():
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL, cache_dir=str(DATA / "models"))


def embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().embed(texts)]


@cache
def _table():
    import lancedb

    return lancedb.connect(INDEX).open_table("passages")


@cache
def _not_covered() -> list[list[float]]:
    return embed(NOT_COVERED)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / ((sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5))


def search(query: str, k: int = 3) -> tuple[list[dict], float]:
    """Top k passages, and a relevance score: the best passage's cosine similarity,
    or 0 when the question sits closer to a topic in NOT_COVERED."""
    table = _table()
    vector = embed([query])[0]
    by_vector = table.search(vector).distance_type("cosine").limit(10).to_list()
    words = " ".join(re.findall(r"\w+", query))
    by_text = table.search(words, query_type="fts").limit(10).to_list() if words else []
    rows = {r["id"]: r for r in by_vector + by_text}
    ranked = rrf([[r["id"] for r in by_vector], [r["id"] for r in by_text]])
    similarity = 1 - by_vector[0]["_distance"] if by_vector else 0.0
    if max(_cosine(vector, v) for v in _not_covered()) > similarity:
        similarity = 0.0
    return [rows[i] for i in ranked[:k]], similarity


def build() -> None:
    import lancedb

    rows = load_corpus()
    vectors = embed([f"{r['title']}\n{r['text']}" for r in rows])
    for row, vector in zip(rows, vectors):
        row["vector"] = vector
        row["topic"] = topic_of(row)
        row["doc"] = f"{row['title']} {row['text']}"
    table = lancedb.connect(INDEX).create_table("passages", rows, mode="overwrite")
    table.create_fts_index("doc", replace=True)
    print(f"Indexed {len(rows)} passages into {INDEX}")


if __name__ == "__main__":
    build()
