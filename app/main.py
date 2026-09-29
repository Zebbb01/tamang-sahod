"""TamangSahod web app: four payroll calculators and a question box.

Everything the owner types arrives in a POST body, so amounts and questions never
land in URLs, access logs or analytics.
"""

import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import calc, search
from app.extract import extract

HERE = Path(__file__).resolve().parent
SOURCES = tomllib.loads((calc.DATA / "sources.toml").read_text(encoding="utf-8"))

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals.update(
    goatcounter=os.environ.get("GOATCOUNTER_CODE", ""),
    sources=SOURCES,
    peso=lambda d: f"₱{d:,.2f}",
)


@dataclass
class Field:
    name: str
    label: str
    kind: str  # money, number, date, month, select, yesno, check
    hint: str = ""
    default: str = ""
    more: bool = False  # tucked under "More options"
    options: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Form:
    title: str
    blurb: str
    fields: list[Field]


DAY_OPTIONS = [
    ("auto", "Look it up from the date"),
    ("regular", "Regular holiday"),
    ("special", "Special (non-working) day"),
    ("special_working", "Special (working) day"),
    ("double_regular", "Double regular holiday"),
    ("double_special", "Double special (non-working) day"),
    ("ordinary", "Ordinary working day"),
]

FORMS = {
    "thirteenth": Form("13th month pay", "One-twelfth of the basic salary earned this year. Due by 24 December.", [
        Field("monthly_salary", "Monthly basic salary", "money", "Basic pay only, without overtime or allowances."),
        Field("months_worked", "Months worked this year", "number", "Use 5.5 for five and a half months.", "12"),
        Field("unpaid_absences", "Unpaid absences this year", "money", "Pesos deducted for leave without pay.", "0", more=True),
        Field("total_basic", "Total basic salary earned this year", "money",
              "If you know it, this is used instead of the monthly salary.", more=True),
    ]),
    "holiday": Form("Holiday and rest-day pay", "Pay for one day of work, or one unworked holiday.", [
        Field("daily_rate", "Daily rate", "money"),
        Field("date", "Date", "date", "2026 dates are matched to Proclamation 1006."),
        Field("day_type", "Day type", "select", default="auto", options=DAY_OPTIONS),
        Field("worked", "Did the employee work that day?", "yesno", "A full 8-hour shift.", "yes"),
        Field("rest_day", "It was the employee's rest day", "check"),
        Field("ot_hours", "Overtime hours beyond 8", "number", default="0"),
        Field("qualified", "At work or on paid leave on the last workday before?", "yesno",
              "Only matters for an unworked regular holiday.", "yes", more=True),
        Field("small_retail_service", "Retail or service business with fewer than 10 workers", "check",
              "These are exempt from holiday pay (Labor Code Art. 94).", more=True),
    ]),
    "final": Form("Final pay", "What is owed when someone resigns or is let go. Release within 30 days.", [
        Field("unpaid_salary", "Salary earned but not yet paid", "money", default="0"),
        Field("monthly_salary", "Monthly basic salary", "money", "Used for the pro-rated 13th month pay."),
        Field("months_worked", "Months worked this year", "number", "Up to the last day of work.", "0"),
        Field("daily_rate", "Daily rate", "money", "Used to convert unused leave to cash."),
        Field("leave_days", "Unused leave days", "number", "Service incentive leave, plus any company leave you convert.", "0"),
        Field("unpaid_absences", "Unpaid absences this year", "money", default="0", more=True),
        Field("total_basic", "Total basic salary earned this year", "money",
              "If you know it, this is used instead of the monthly salary.", more=True),
        Field("other", "Other amounts owed", "money", "Anything your contract or policy adds.", "0", more=True),
    ]),
    "contributions": Form("SSS, PhilHealth, Pag-IBIG", "Monthly shares to deduct and to pay as employer.", [
        Field("monthly_salary", "Monthly salary", "money"),
        Field("month", "Month", "month"),
    ]),
}


def money(values: dict, name: str, label: str, required: bool = True) -> Decimal | None:
    raw = values.get(name, "").replace("₱", "").replace(",", "").strip()
    if not raw:
        if required:
            raise ValueError(f"Enter the {label.lower()}.")
        return None
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"{label} must be a number.") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} must be zero or more.")
    return amount


def compute(topic: str, v: dict) -> tuple[calc.Result, str]:
    """Run the calculator for a submitted form. Returns the result and its heading."""
    if topic == "thirteenth":
        months = money(v, "months_worked", "Months worked")
        total = money(v, "total_basic", "Total basic salary", required=False)
        if total is None:
            total = calc.basic_earned(money(v, "monthly_salary", "Monthly basic salary"), months,
                                      money(v, "unpaid_absences", "Unpaid absences", required=False) or 0)
        return calc.thirteenth_month(total, months), "13th month pay"

    if topic == "holiday":
        day_type, heading, notes = v.get("day_type", "auto"), "Pay for the day", []
        try:
            on = date.fromisoformat(v["date"]) if v.get("date") else None
        except ValueError:
            raise ValueError("Enter the date as YYYY-MM-DD.") from None
        if day_type == "auto":
            if on is None:
                raise ValueError("Enter the date, or choose the day type.")
            found = calc.day_type_on(on)
            day_type, name = found or ("ordinary", "")
            heading = f"{name}, {on:%d %B %Y}" if name else f"{on:%d %B %Y}"
            if not found:
                notes.append("Not a holiday in the 2026 list. Eid'l Fitr, Eid'l Adha and holidays declared "
                             "later are not listed: choose the day type if it applies.")
        elif on:
            heading = f"{on:%d %B %Y}"
        result = calc.holiday_pay(
            money(v, "daily_rate", "Daily rate"), day_type,
            worked=v.get("worked", "yes") == "yes",
            rest_day="rest_day" in v,
            ot_hours=money(v, "ot_hours", "Overtime hours", required=False) or Decimal(0),
            qualified=v.get("qualified", "yes") == "yes",
            small_retail_service="small_retail_service" in v,
        )
        result.notes = notes + result.notes
        if on and on.year == 2026:
            result.sources += ["dole-la-12-25", "proclamation-1006-s-2025"]
        return result, f"{heading} ({calc.DAY_TYPES[day_type]})"

    if topic == "final":
        months = money(v, "months_worked", "Months worked")
        total = money(v, "total_basic", "Total basic salary", required=False)
        if total is None:
            total = calc.basic_earned(money(v, "monthly_salary", "Monthly basic salary", required=False) or Decimal(0),
                                      months, money(v, "unpaid_absences", "Unpaid absences", required=False) or 0)
        result = calc.final_pay(
            unpaid_salary=money(v, "unpaid_salary", "Salary not yet paid", required=False) or Decimal(0),
            basic_earned_this_year=total,
            months_worked=months,
            leave_days=money(v, "leave_days", "Unused leave days", required=False) or Decimal(0),
            daily_rate=money(v, "daily_rate", "Daily rate", required=False) or Decimal(0),
            other=money(v, "other", "Other amounts", required=False) or Decimal(0),
        )
        return result, "Final pay"

    month = v.get("month") or f"{date.today():%Y-%m}"
    try:
        on = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise ValueError("Enter the month as YYYY-MM.") from None
    return calc.contributions(money(v, "monthly_salary", "Monthly salary"), on), f"Contributions for {on:%B %Y}"


def form_values(topic: str, given: dict | None = None) -> dict:
    values = {f.name: f.default for f in FORMS[topic].fields}
    if topic == "contributions":
        values["month"] = f"{date.today():%Y-%m}"
    values.update(given or {})
    return values


def render(request: Request, name: str, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, name, context)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "home.html", forms=FORMS)


@app.get("/calc/{topic}", response_class=HTMLResponse)
def calculator(request: Request, topic: str):
    if topic not in FORMS:
        return RedirectResponse("/", status_code=303)
    return render(request, "calc.html", topic=topic, form=FORMS[topic], values=form_values(topic))


@app.post("/calc/{topic}", response_class=HTMLResponse)
async def calculate(request: Request, topic: str):
    if topic not in FORMS:
        return RedirectResponse("/", status_code=303)
    submitted = {k: str(v) for k, v in (await request.form()).items()}
    values = form_values(topic, submitted)
    for f in FORMS[topic].fields:  # unticked checkboxes are absent from the POST
        if f.kind == "check" and f.name not in submitted:
            values.pop(f.name, None)
    try:
        result, heading = compute(topic, values)
    except (ValueError, calc.NotCovered) as e:
        return render(request, "calc.html", topic=topic, form=FORMS[topic], values=values, error=str(e))
    return render(request, "calc.html", topic=topic, form=FORMS[topic], values=values, result=result, heading=heading)


def as_form_values(topic: str, fields: dict) -> dict:
    """Extracted fields (typed) to form strings."""
    out = {}
    kinds = {f.name: f.kind for f in FORMS[topic].fields}
    for name, value in fields.items():
        if name not in kinds:
            continue
        if kinds[name] == "yesno":
            out[name] = "yes" if value else "no"
        elif kinds[name] == "check":
            if value:
                out[name] = "on"
        else:
            out[name] = value.isoformat() if isinstance(value, date) else f"{value}"
    return out


@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    question = str((await request.form()).get("q", "")).strip()[:500]
    if not question:
        return RedirectResponse("/", status_code=303)
    try:
        passages, similarity = search.search(question)
    except Exception:  # index missing or broken: the calculators still work
        passages, similarity = [], 0.0
    covered = similarity >= search.MIN_SIMILARITY
    found = extract(question)
    if found:
        topic, fields = found
        values = form_values(topic, as_form_values(topic, fields))
        return render(request, "calc.html", topic=topic, form=FORMS[topic], values=values,
                      question=question, passages=passages if covered else [])
    topics = list(dict.fromkeys(search.topic_of(p) for p in passages))[:2] if covered else []
    return render(request, "answer.html", question=question, passages=passages if covered else [],
                  topics=topics, forms=FORMS)


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request):
    return render(request, "sources.html")


@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"
