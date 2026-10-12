# TamangSahod

**Live:** https://zebbb01--tamang-sahod-web.modal.run (the first visit after a quiet spell takes about 5 seconds to wake)

Payroll answers for Philippine micro-businesses. An owner asks in English or Taglish, or
opens one of five calculators, and gets the exact peso amount together with the official
rule it follows, quoted word for word.

## The problem

Owners of businesses with 1–20 staff run payroll by hand or in Excel. What a worker is
owed on a holiday, in 13th month pay, in final pay, or in SSS, PhilHealth and Pag-IBIG
contributions is spread across DOLE advisories, a Presidential Decree and three agencies'
circulars that change every year. Owners guess. A wrong guess underpays a worker or ends in
a DOLE complaint.

## What it does

- **Salary for the year:** yearly and monthly pay from an hourly or daily rate, using DOLE's
  equivalent-monthly-rate factors (305 or 313 paid days for a 6-day week, 253 or 261 for 5).
- **13th month pay:** one-twelfth of basic salary earned, pro-rated for part years.
- **Holiday and rest-day pay:** every 2026 day type from Proclamation 1006, with overtime,
  rest days, and the exemption for small retail and service businesses.
- **Final pay:** unpaid salary, pro-rated 13th month and unused leave converted to cash.
- **SSS, PhilHealth, Pag-IBIG:** employee and employer shares for a monthly salary.
- **Ask a question:** returns the matching rule passages, or pre-fills a calculator for the
  owner to check. Anything outside these five topics gets "not covered" and the DOLE
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
| Calculators vs official worked examples | 100% | all pass (`pytest`, 74 tests) |
| Right rule in top 3 results | ≥ 90% | 96% (44/46) |
| Out-of-scope questions refused | ≥ 19/20 | 20/20 |
| In-scope questions answered, not refused | — | 41/46 |
| Question-to-form extraction | ≥ 90% | not yet run: needs `GROQ_API_KEY` |
| Running cost | ₱0 | Modal Starter without a card: $1 of compute a month |

Measured 12 October 2026 with `python -m evals.run`, locally and in CI. Two caveats. The 46 in-scope and 20
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

**Modal**, from `modal_app.py`:

```
uv run modal token new                 # once: approve in the browser
uv run modal deploy modal_app.py
```

The image installs the locked dependencies and builds the search index at build time; there
is no database. Without a card, the Starter plan gives $1 of compute a month, so the app runs
on half a CPU and scales to zero two minutes after the last request: roughly 30 warm hours a
month, after which it stops until the next month. Measured on 12 October 2026: 4.7 s to wake,
6.8 s for the first question after waking (the embedding model loads), under a second after
that. The `Dockerfile` serves the same app on any container host.

## Known limits

- Salary for the year is an estimate from DOLE's paid-day factors; it leaves out overtime,
  premiums, 13th month pay and deductions.
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
