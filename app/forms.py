"""The calculator forms and the question flow behind the FastAPI app (app/main.py).
Values arrive as strings, the way a form submits them."""

import calendar
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app import calc, search
from app.extract import extract

SOURCES = tomllib.loads((calc.DATA / "sources.toml").read_text(encoding="utf-8"))


@dataclass
class Field:
    name: str
    label: str
    # money, number, text: a typed box. segmented: 2-3 choices side by side. yesno: segmented
    # Yes/No. cards: up to ~7 choices with a hint each. holiday: chips for the holidays ahead
    # plus "Other date". month: chips for this year's months. switch: on/off.
    kind: str
    hint: str = ""
    default: str = ""
    step: str = ""  # the numbered section it sits in; "" means "More options"
    options: list[tuple[str, ...]] = field(default_factory=list)  # (value, label[, hint])
    show_if: tuple[str, str] | None = None  # shown only while that field has that value


@dataclass
class Form:
    title: str
    blurb: str
    verb: str  # the button
    fields: list[Field]


DAY_OPTIONS = [
    ("auto", "From the date", "Uses the 2026 holiday list"),
    ("regular", "Regular holiday", "200% if worked, 100% if not"),
    ("special", "Special (non-working) day", "130% if worked, no work no pay"),
    ("special_working", "Special (working) day", "Paid as an ordinary day"),
    ("double_regular", "Double regular holiday", "300% if worked, 200% if not"),
    ("double_special", "Double special (non-working) day", "150% if worked"),
    ("ordinary", "Ordinary working day", "100%, overtime 125%"),
]
SCHEDULE_OPTIONS = [
    ("six", "6 days a week", "Daily-paid · 305 paid days a year, 313 if special days are paid"),
    ("five", "5 days a week", "Daily-paid · 253 paid days a year, 261 if special days are paid"),
    ("everyday", "Every day", "Daily-paid, including rest days and holidays · 395 days"),
    ("monthly", "Monthly-paid", "Paid for every day of the month · 365 days"),
]

FORMS = {
    "salary": Form("Salary for the year", "Yearly and monthly pay from an hourly or daily rate, by DOLE's factors.",
                   "Compute salary", [
        Field("rate", "Rate", "money", step="Pay"),
        Field("rate_per", "Paid per", "segmented", default="day", step="Pay", options=[("day", "Day"), ("hour", "Hour")]),
        Field("hours_per_day", "Hours a day", "number", default="8", step="Pay", show_if=("rate_per", "hour")),
        Field("schedule", "Work schedule", "cards", default="six", step="Schedule", options=SCHEDULE_OPTIONS),
        Field("unpaid_absences", "Unpaid absences this year (days)", "number", default="0", step="Adjustments"),
        Field("special_days_paid", "Special (non-working) days are paid", "switch",
              "Turn on if your company pays them even when nobody works.", step="Adjustments"),
    ]),
    "thirteenth": Form("13th month pay", "One-twelfth of the basic salary earned this year. Due by 24 December.",
                       "Compute 13th month pay", [
        Field("monthly_salary", "Monthly basic salary", "money", "Basic pay only, without overtime or allowances.", step="Pay"),
        Field("months_worked", "Months worked this year", "number", "Use 5.5 for five and a half months.", "12", step="Pay"),
        Field("unpaid_absences", "Unpaid absences this year", "money", "Pesos deducted for leave without pay.", "0",
              step="Adjustments"),
        Field("total_basic", "Total basic salary earned this year", "money",
              "If you know it, this is used instead of the monthly salary."),
    ]),
    "holiday": Form("Holiday and rest-day pay", "Pay for one day of work, or one unworked holiday.",
                    "Compute pay for the day", [
        Field("date", "Which day?", "holiday", step="Day"),
        Field("other_date", "Other date", "text", "Type it like Dec 30 or 2026-12-30.", step="Day",
              show_if=("date", "other")),
        Field("daily_rate", "Daily rate", "money", step="Pay"),
        Field("worked", "Did the employee work that day?", "yesno", "A full 8-hour shift.", "yes", step="Work"),
        Field("qualified", "At work or on paid leave on the last workday before?", "yesno",
              "Needed for holiday pay on an unworked regular holiday.", "yes", step="Work", show_if=("worked", "no")),
        Field("rest_day", "It was the employee's rest day", "switch", step="Work"),
        Field("ot_hours", "Overtime hours beyond 8", "number", default="0", step="Work", show_if=("worked", "yes")),
        Field("day_type", "Day type", "cards", default="auto", options=DAY_OPTIONS),
        Field("small_retail_service", "Retail or service business with fewer than 10 workers", "switch",
              "These are exempt from holiday pay (Labor Code Art. 94)."),
    ]),
    "final": Form("Final pay", "What is owed when someone resigns or is let go. Release within 30 days.",
                  "Compute final pay", [
        Field("unpaid_salary", "Salary earned but not yet paid", "money", default="0", step="Pay owed"),
        Field("monthly_salary", "Monthly basic salary", "money", "Used for the pro-rated 13th month pay.", step="Pay owed"),
        Field("months_worked", "Months worked this year", "number", "Up to the last day of work.", "0", step="Pay owed"),
        Field("daily_rate", "Daily rate", "money", "Used to convert unused leave to cash.", step="Leave"),
        Field("leave_days", "Unused leave days", "number", "Service incentive leave, plus any company leave you convert.",
              "0", step="Leave"),
        Field("unpaid_absences", "Unpaid absences this year", "money", default="0"),
        Field("total_basic", "Total basic salary earned this year", "money",
              "If you know it, this is used instead of the monthly salary."),
        Field("other", "Other amounts owed", "money", "Anything your contract or policy adds.", "0"),
    ]),
    "contributions": Form("SSS, PhilHealth, Pag-IBIG", "Monthly shares to deduct and to pay as employer.",
                          "Compute contributions", [
        Field("monthly_salary", "Monthly salary", "money", step="Salary"),
        Field("month", "Which month is this for?", "month", step="Month"),
    ]),
}


def steps(form: Form) -> list[tuple[str, list[Field]]]:
    """The numbered sections of a form, in order; fields without a step go under More options."""
    grouped: dict[str, list[Field]] = {}
    for f in form.fields:
        if f.step:
            grouped.setdefault(f.step, []).append(f)
    return list(grouped.items())


def holiday_choices(today: date | None = None) -> list[tuple[str, str, str, str]]:
    """(ISO date, "Nov 30", name, day type) for this year's listed holidays from today on."""
    today = today or date.today()
    days = calc.HOLIDAYS.get(today.year, {}).get("days", [])
    return [(d["date"].isoformat(), f"{d['date']:%b} {d['date'].day}", d["name"], d["type"])
            for d in days if d["date"] >= today]


def month_choices(today: date | None = None) -> list[tuple[str, str]]:
    year = (today or date.today()).year
    return [(f"{year}-{m:02d}", calendar.month_abbr[m]) for m in range(1, 13)]


def parse_date(text: str, today: date | None = None) -> date:
    """Read a date the way people type it: 2026-12-30, Dec 30, 30 Dec, 30/12/2026, 12/30/2026.
    Without a year, this year. Day and month both 12 or under: month first, as on PH forms."""
    year = (today or date.today()).year
    text = re.sub(r"\s+", " ", text.strip().replace(",", ""))
    numeric = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if numeric:
        a, b, y = map(int, numeric.groups())
        month, day = (b, a) if a > 12 else (a, b)
        try:
            return date(y, month, day)
        except ValueError:
            pass
    else:
        for fmt in ("%Y-%m-%d", "%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"):
            for candidate in (text, f"{text} {year}"):
                try:
                    return datetime.strptime(candidate, fmt).date()
                except ValueError:
                    continue
    raise ValueError("Enter the date like Dec 30 or 2026-12-30.")


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
    A switch counts as on when its value is non-empty."""
    if topic == "salary":
        rate = money(v, "rate", "Rate")
        if v.get("rate_per", "day") == "hour":
            hours = money(v, "hours_per_day", "Hours a day")
            if not 0 < hours <= 24:
                raise ValueError("Hours a day must be between 1 and 24.")
            rate = calc.peso(rate * hours)
        return calc.salary(
            rate, v.get("schedule", "six"),
            special_days_paid=bool(v.get("special_days_paid")),
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
        raw = v.get("other_date", "") if v.get("date") == "other" else v.get("date", "")
        on = parse_date(raw) if raw.strip() else None
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
            rest_day=bool(v.get("rest_day")),
            ot_hours=money(v, "ot_hours", "Overtime hours", required=False) or Decimal(0),
            qualified=v.get("qualified", "yes") == "yes",
            small_retail_service=bool(v.get("small_retail_service")),
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
    if topic == "holiday":  # a date that is not one of the chips goes in the "Other date" box
        chips = {value for value, *_ in holiday_choices()}
        if values.get("date") and values["date"] not in chips | {"other"}:
            values["other_date"], values["date"] = values["date"], "other"
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
        elif kinds[name] == "switch":
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
