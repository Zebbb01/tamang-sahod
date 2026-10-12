"""The four calculator forms and the question flow, shared by both front ends
(FastAPI in app/main.py, Streamlit in streamlit_app.py). Values arrive as strings,
the way a form submits them."""

import tomllib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app import calc, search
from app.extract import extract

SOURCES = tomllib.loads((calc.DATA / "sources.toml").read_text(encoding="utf-8"))


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
    "salary": Form("Salary for the year", "Yearly and monthly pay from an hourly or daily rate, by DOLE's factors.", [
        Field("rate", "Rate", "money"),
        Field("rate_per", "Paid per", "select", default="day", options=[("day", "Day"), ("hour", "Hour")]),
        Field("hours_per_day", "Hours a day", "number", "Used when paid per hour.", "8"),
        Field("schedule", "Work schedule", "select", default="six", options=list(calc.SCHEDULES.items())),
        Field("unpaid_absences", "Unpaid absences this year (days)", "number", default="0"),
        Field("special_days_paid", "Special (non-working) days are paid", "check",
              "Tick if your company pays them even when nobody works.", more=True),
    ]),
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
    """Run the calculator for a submitted form. Returns the result and its heading.
    A checkbox counts as ticked when its name is present in `v`."""
    if topic == "salary":
        rate = money(v, "rate", "Rate")
        if v.get("rate_per", "day") == "hour":
            hours = money(v, "hours_per_day", "Hours a day")
            if not 0 < hours <= 24:
                raise ValueError("Hours a day must be between 1 and 24.")
            rate = calc.peso(rate * hours)
        return calc.salary(
            rate, v.get("schedule", "six"),
            special_days_paid="special_days_paid" in v,
            unpaid_absences=money(v, "unpaid_absences", "Unpaid absences", required=False) or Decimal(0),
        ), "Salary for the year"

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


@dataclass
class Answer:
    topic: str | None = None       # a calculator to pre-fill, when the LLM found one
    values: dict = field(default_factory=dict)
    passages: list[dict] = field(default_factory=list)  # empty means "not covered"
    topics: list[str] = field(default_factory=list)     # calculators to suggest


def answer(question: str) -> Answer:
    try:
        passages, similarity = search.search(question)
    except Exception:  # index missing or broken: the calculators still work
        passages, similarity = [], 0.0
    if similarity < search.MIN_SIMILARITY:
        passages = []
    found = extract(question)
    if found:
        topic, fields = found
        return Answer(topic, form_values(topic, as_form_values(topic, fields)), passages)
    return Answer(passages=passages, topics=list(dict.fromkeys(search.topic_of(p) for p in passages))[:2])
