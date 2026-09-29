# TamangSahod

Payroll answers for Philippine micro-businesses. An owner asks in English or Taglish, or
opens one of four calculators, and gets the exact peso amount together with the official
rule it follows, quoted word for word.

## The problem

Owners of businesses with 1–20 staff run payroll by hand or in Excel. What a worker is
owed on a holiday, in 13th month pay, in final pay, or in SSS, PhilHealth and Pag-IBIG
contributions is spread across DOLE advisories, a Presidential Decree and three agencies'
circulars that change every year. Owners guess. A wrong guess underpays a worker or ends in
a DOLE complaint.

## What it does

- **13th month pay:** one-twelfth of basic salary earned, pro-rated for part years.
- **Holiday and rest-day pay:** every 2026 day type from Proclamation 1006, with overtime,
  rest days, and the exemption for small retail and service businesses.
- **Final pay:** unpaid salary, pro-rated 13th month and unused leave converted to cash.
- **SSS, PhilHealth, Pag-IBIG:** employee and employer shares for a monthly salary.
- **Ask a question:** returns the matching rule passages, or pre-fills a calculator for the
  owner to check. Anything outside these four topics gets "not covered" and the DOLE
  hotline, never a guess.

## How it works

```
question ─┬─> multilingual embeddings ─> LanceDB (vector + full-text, rank fusion)
          │        └─> not-covered check ─> quoted rule passages, or "not covered"
          │
          └─> LLM, optional ─> {topic, fields} ─> validated ─> pre-filled form
                                                                  │ owner checks
                                                                  v
                          Python calculator (Decimal, dated rate tables) ─> amount + rule + source
```

**The AI never does the math.** Language models are good at reading "pumasok siya noong
Dec 30, 645 ang daily" and bad at arithmetic, so the model only fills in a form. The owner
confirms every field, and tested code computes the pesos. The model's reply is treated as
untrusted input: unknown topics, fields and out-of-range values are dropped.

**Rates are data with an expiry.** Every rate lives in `data/rates.toml` with its source
and the last date it was verified. A pay date outside every verified period is refused
("No verified SSS rates for January 2027 yet"), never computed with an old rate.

**Everything the owner types travels in a POST body**, so amounts and questions never land
in URLs, access logs or analytics. Nothing is stored.

## Measured

| Measure | Target | Result |
| --- | --- | --- |
| Calculators vs official worked examples | 100% | all pass (`pytest`, 58 tests) |
| Right rule in top 3 results | ≥ 90% | 95% (41/43) |
| Out-of-scope questions refused | ≥ 19/20 | 20/20 |
| In-scope questions answered, not refused | — | 39/43 |
| Question-to-form extraction | ≥ 90% | not yet run: needs `GROQ_API_KEY` |
| Running cost | ₱0 | Cloud Run free tier; image storage past 0.5 GB costs a few pesos a month |

Measured 29 September 2026 with `python -m evals.run`, locally and in CI. Two caveats. The 43 in-scope and 20
out-of-scope questions are a seed set written by the builder, half in Taglish; real
questions from the beta will replace them. And the list of not-covered topics was written
after seeing which probes slipped through, so 20/20 is optimistic until it is re-measured on
questions it has not seen.

Worked examples come from the DOLE-BWC Handbook on Workers' Statutory Monetary Benefits
(₱184,219.96 ÷ 12 = ₱15,351.66; 5.833 days × ₱610 = ₱3,558.13), the SSS 2025 contribution
table, PhilHealth Advisory 2025-0002, Pag-IBIG Circular 460 and DOLE Labor Advisory 12-25. Every source, with where
it was fetched from, is listed in `data/sources.toml` and on the site's Sources page.

## Run it locally

```
uv sync
uv run python -m app.search            # downloads the embedding model (~220 MB), builds the index
uv run uvicorn app.main:app --reload   # http://127.0.0.1:8000
uv run pytest
uv run python -m evals.run             # retrieval and not-covered evals
uv run python -m evals.run extract     # extraction eval, needs GROQ_API_KEY
```

Optional settings: `GROQ_API_KEY` (question-to-form), `GROQ_MODEL` (default
`openai/gpt-oss-20b`), `GOATCOUNTER_CODE` (cookieless visit counts).

## Deploy

Google Cloud Run, continuously deployed from this repository's `Dockerfile` by Cloud Build.
The image builds the search index at build time and needs no database. Service settings:
region `asia-east1` (Tier 1 pricing, close to the Philippines), 2 GiB memory (the app uses
about 1.1 GB once the model is loaded), 1 CPU, minimum 0 and maximum 2 instances, public
access. It scales to zero, so the first visit after a quiet spell waits about 10 seconds.

## Known limits

- Holiday pay assumes a daily-paid employee on a full 8-hour shift. Part-day holiday work,
  night-shift differential and monthly-paid factors are not covered.
- Final pay leaves out separation pay, deductions and tax.
- Contributions cover regular employees only, not kasambahay, OFWs or the self-employed,
  and one salary figure is used for both the SSS and PhilHealth bases.
- Rates are verified through 31 December 2026. PhilHealth's 2026 figures rest on a
  Philippine Information Agency report; the 2026 advisory itself was not located.
- Only the 2026 holiday list is loaded, and Eid'l Fitr and Eid'l Adha are proclaimed
  separately, so the owner picks those day types by hand.
- DOLE's servers refuse scripted downloads. The two labor advisories were downloaded by
  hand in a browser; the handbook copy came from a law-firm mirror of the same edition.
- Retrieval uses a small multilingual model; larger ones have not been compared yet.

A guide, not legal advice. Design and goals: `docs/superpowers/specs/2026-09-28-tamang-sahod-design.md`.
