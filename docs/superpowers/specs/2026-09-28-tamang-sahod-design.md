# TamangSahod — design spec

**Date:** 2026-09-28 · **Status:** design approved in chat; built from this spec the same day.

## 1. Problem

Philippine micro-businesses (1–20 staff) run payroll by hand or in Excel. The rules
that decide what a worker is owed — holiday pay, 13th month pay, final pay and the
three government contributions — are spread across DOLE advisories, a Presidential
Decree, and SSS, PhilHealth and Pag-IBIG circulars that change every year. Owners
guess, and a wrong guess means an underpaid worker or a DOLE complaint.

## 2. Target market

Not a blue ocean and not "everyone": owners of Philippine micro-businesses with
1–20 staff who compute pay themselves. Demand is proven — paid payroll software
exists (Sprout, Salarium) and HR Facebook groups ask these exact questions daily.
The builder's edge is money-correctness practice from ProfitView, which has no
payroll module, so the two do not overlap.

## 3. Goal (SMART)

- **Specific:** a free, mobile-first web app. An owner asks a payroll question in
  English or Taglish, or opens one of four calculators, and gets the exact peso
  amount with the official rule it follows. Four topics only.
- **Measurable:**
  - Calculators match 100% of the worked examples taken from official sources.
  - Retrieval puts the right source in the top 3 for ≥ 90% of the eval questions
    (at least half written in Taglish).
  - Out-of-scope questions get "not covered", never a guess, on ≥ 19 of 20 probes.
  - Question-to-form extraction is right on ≥ 90% of its eval set.
  - Running cost ₱0 per month, apart from a few pesos of image storage (see §5).
  - 30 distinct visitors complete a calculation in the 2 weeks after launch.
- **Achievable:** one Python service, free tiers only, four topics.
- **Relevant:** owners compute these every payday; for the builder it is a
  published, measured AI project in the Python/vector-search space.
- **Time-bound:** code built 28 Sep 2026. Private beta with 5 owners, then public
  launch by **15 Nov 2026**, ahead of the 13th-month deadline (24 Dec). Users are
  counted until 29 Nov 2026.

## 4. Scope

**In v1:** 13th month pay · holiday pay (2026 day types) · final pay · SSS,
PhilHealth and Pag-IBIG monthly contributions.

**Not in v1 (parked):** separation pay, night-shift differential, ordinary-day
overtime, withholding tax, payslips, accounts or login, kasambahay and OFW
contribution rules, monthly-paid holiday factors, a Filipino-language UI, any link
to ProfitView.

## 5. How it works

**Screens.** Home has one question box and four tiles. A tile opens a short form.
A question either pre-fills that form (the owner checks the fields, then taps
Compute) or, when no calculator fits, shows the top rule passages quoted word for
word with their source. Out-of-scope questions get "Not covered yet" and the DOLE
hotline 1349. Results show the amount first, then the breakdown, then the rule,
source and effective date, labelled "Guide, not legal advice".

**One Python service.** FastAPI with server-rendered Jinja2 pages and plain HTML
forms — almost no JavaScript, so it loads fast on cheap phones and prepaid data.

**Calculators.** Pure functions using `Decimal`, rounded to the centavo, half-up.
Rates live in `data/rates.toml`, each period carrying its effective dates and
source. The rate is picked by the pay date; if no loaded period covers the
date, the calculator refuses rather than reuse an old rate.

**Vector search.** LanceDB, embedded in the app image, built at deploy time from
source text committed under `data/corpus/`. Hybrid search (vector + full-text,
reciprocal-rank fusion), so both "magkano holiday pay" and "Article 94" land.
Embeddings come from an open multilingual model run on CPU through `fastembed`;
the model is chosen by the retrieval eval. A question is "not covered" when its
best passage scores below a tuned threshold, or when it sits closer to one of a
short list of neighbouring topics the app does not answer (minimum wage, loans,
deductions, tax, separation pay...) than to any passage.

*Changed from the chat design:* Supabase pgvector was dropped. The Supabase
organisation is on the free plan (2 active projects) and already holds
ProfitView's production and test databases; a third project would block restoring
the test database ProfitView's CI needs. An embedded index also removes the
free-tier pause, a keep-alive dependency and a database secret.

**LLM (optional, free tier).** Only turns a question into `{topic, fields}` JSON,
validated before use. It never computes and never writes rule text. If it is
unset, down or out of quota, the question box falls back to search and the tiles
keep working. Provider rule: a free tier whose terms do not train on inputs.

**Hosting.** Google Cloud Run, deployed from the `Dockerfile` by Cloud Build on
every push to `main`: region `asia-east1`, 2 GiB memory, 1 CPU, 0–2 instances,
public access. The free tier (180k vCPU-seconds, 360k GiB-seconds and 2M requests a
month, priced at Tier 1 rates) covers this traffic; the image is larger than
Artifact Registry's free 0.5 GB, which costs a few pesos a month.

*Changed from the chat design (29 Sep 2026):* Hugging Face now requires a paid plan
for Docker Spaces. Free 512 MB hosts (Render, Koyeb) cannot hold the app, which uses
about 1.1 GB once the embedding model is loaded, and the dependencies exceed
Vercel's 250 MB Python function limit. Cloud Run scales to zero instead of
sleeping, so the keep-awake workflow was removed.

## 6. Privacy and safety

- No login. Salaries and form values are never stored or logged.
- Visitor and "Was this right?" counts go to GoatCounter (cookieless, free) as
  page paths only — no amounts, no question text.
- Every result names its source and effective date and says it is a guide.
- Coverage exemptions are asked, not assumed (e.g. retail/service businesses with
  fewer than 10 workers are exempt from holiday pay and service incentive leave).

## 7. Failure handling

| Situation | Behaviour |
| --- | --- |
| Invalid input (negative pay, >24 hours) | Form re-shown with the field's message |
| No rate period covers the date | Refuse, name the missing period |
| LLM unset, down or quota exhausted | Search + tiles only; no error page |
| LLM returns invalid JSON or unknown topic | Treated as no extraction |
| Best search score below threshold | "Not covered yet" + DOLE hotline |

## 8. Proof

- `pytest`: calculators against official worked examples, rate selection, form
  validation, page smoke tests.
- `evals/`: retrieval (hit@3), out-of-scope probes, extraction. Retrieval and
  out-of-scope run in CI; extraction runs on demand (it calls the LLM).
- The README publishes the latest eval numbers.

## 9. Sources

Official PDFs are kept under `data/sources/`; `data/sources.toml` records each
one's URL, retrieval date and provenance, and drives the site's Sources page.
DOLE's servers refuse scripted downloads (HTTP 403 behind a bot check); where a
DOLE PDF could not be fetched, the source record says so and says which copy was
used instead.

## 10. Risks

- **Rules change mid-year** (new advisory or circular): dated rate periods, and
  refusal outside them.
- **Free tiers change**: the LLM is optional; nothing else depends on a paid tier.
- **Wrong answer harms a worker**: official-example tests, owner-confirmed inputs,
  source on every result.
- **Cloud Run needs a card on the billing account**: cap it with a budget alert and
  a maximum of 2 instances. A cold start after a quiet spell takes about 10 seconds.

## 11. Done when

Status 2026-09-29: the first two items passed in GitHub Actions (58 tests;
hit@3 95%, out-of-scope 20/20).

- [x] Four calculators pass every official worked example in CI.
- [x] Retrieval hit@3 ≥ 90% and out-of-scope ≥ 19/20, published in the README.
- [ ] Extraction ≥ 90%, or the LLM left off and that stated in the README.
- [ ] Live on Cloud Run with a budget alert set; cold start measured.
- [ ] First month's bill checked: nothing beyond image storage.
- [ ] No amount or question text in logs or analytics (checked by test).
- [ ] Private beta with 5 owners done; their findings fixed or parked.
- [ ] Public launch posts in 2 Facebook groups by 15 Nov 2026.
- [ ] Visitor count reported on 29 Nov 2026, whether or not it reaches 30.
