"""Turn a payroll question into a calculator topic and pre-filled fields.

Optional: runs only when GROQ_API_KEY is set. The model's reply is untrusted input —
`parse` keeps only known topics and values that pass the same range checks the forms
use. The model never computes an amount; the owner checks every field before Compute.
"""

import json
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from app.calc import DAY_TYPES

URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

PROMPT = """You turn a Philippine payroll question into JSON for a calculator. Today is {today}.
Reply with JSON only: {{"topic": "...", "fields": {{...}}}}
topic is one of: "thirteenth" (13th month pay), "holiday" (holiday, rest day or special day pay),
"final" (final pay / last pay after resigning or being let go), "contributions" (SSS, PhilHealth,
Pag-IBIG), or "none" for anything else (taxes, separation pay, loans, leave rules, other topics).
Fields, filled only when the question states them:
- thirteenth: monthly_salary, months_worked (0-12), unpaid_absences, total_basic
- holiday: daily_rate, date (YYYY-MM-DD), day_type (regular, special, special_working,
  double_regular, double_special, ordinary), worked (true/false), rest_day (true/false), ot_hours
- final: unpaid_salary, monthly_salary, months_worked, daily_rate, leave_days, other
- contributions: monthly_salary, month (YYYY-MM)
Amounts are pesos as plain numbers. Never invent a value the question does not give.
Questions may be in English, Filipino or Taglish."""


def _number(value) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        d = Decimal(re.sub(r"PHP|Php|[₱,\s]", "", str(value)))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _range(low: int, high: int):
    return lambda v: d if (d := _number(v)) is not None and low <= d <= high else None


def _money(value) -> Decimal | None:
    d = _number(value)
    return d if d is not None and d >= 0 else None


def _flag(value) -> bool | None:
    return value if isinstance(value, bool) else None


def _date(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _month(value) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value) else None


def _day_type(value) -> str | None:
    return value if value in DAY_TYPES else None


MONTHS = _range(0, 12)
FIELDS = {
    "thirteenth": {"monthly_salary": _money, "months_worked": MONTHS, "unpaid_absences": _money, "total_basic": _money},
    "holiday": {"daily_rate": _money, "date": _date, "day_type": _day_type, "worked": _flag,
                "rest_day": _flag, "ot_hours": _range(0, 16)},
    "final": {"unpaid_salary": _money, "monthly_salary": _money, "months_worked": MONTHS, "daily_rate": _money,
              "leave_days": _range(0, 365), "other": _money, "total_basic": _money, "unpaid_absences": _money},
    "contributions": {"monthly_salary": _money, "month": _month},
}


def parse(raw: str) -> tuple[str, dict] | None:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("topic") not in FIELDS:
        return None
    topic = data["topic"]
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    clean = {}
    for name, value in fields.items():
        check = FIELDS[topic].get(name)
        if check and (valid := check(value)) is not None:
            clean[name] = valid
    return topic, clean


def extract(question: str) -> tuple[str, dict] | None:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    try:
        response = httpx.post(URL, timeout=8, headers={"Authorization": f"Bearer {key}"}, json={
            "model": MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": PROMPT.format(today=date.today().isoformat())},
                {"role": "user", "content": question[:500]},
            ],
        })
        response.raise_for_status()
        return parse(response.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None  # search and the tiles still work without it
