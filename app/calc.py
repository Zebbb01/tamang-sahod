"""Payroll calculators. Money is Decimal, rounded to the centavo (half-up) per amount.

Rates and holiday dates live in data/*.toml with their sources. A date outside every
verified period raises NotCovered instead of reusing an old rate.
"""

import tomllib
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
RATES = tomllib.loads((DATA / "rates.toml").read_text(encoding="utf-8"))
HOLIDAYS = {y["year"]: y for y in tomllib.loads((DATA / "holidays.toml").read_text(encoding="utf-8"))["year"]}

ZERO = Decimal(0)
AGENCY = {"sss": "SSS", "philhealth": "PhilHealth", "pagibig": "Pag-IBIG"}

# Share of the daily wage for the first 8 hours worked, by (day type, rest day).
# DOLE-BWC Handbook 2024, "Guide Computations for Holiday Pay, Premium Pay, Overtime Pay".
WORKED = {
    ("ordinary", False): "1", ("ordinary", True): "1.3",
    ("special", False): "1.3", ("special", True): "1.5",
    ("double_special", False): "1.5", ("double_special", True): "1.95",
    ("regular", False): "2", ("regular", True): "2.6",
    ("double_regular", False): "3", ("double_regular", True): "3.9",
}
# Unworked days that are still paid, to employees present or on paid leave the workday before.
UNWORKED = {"regular": "1", "double_regular": "2"}
DAY_TYPES = {
    "regular": "regular holiday",
    "double_regular": "double regular holiday",
    "special": "special (non-working) day",
    "double_special": "double special (non-working) day",
    "special_working": "special (working) day",
    "ordinary": "ordinary working day",
}


# Paid days in a year by work schedule, as (special days paid, special days unpaid).
# DOLE-BWC Handbook 2024, "Computation of the Estimated Equivalent Monthly Rate", pp. 20-21.
PAID_DAYS = {
    "six": ("313", "305"),
    "five": ("261", "253"),
    "everyday": ("395", "395"),
    "monthly": ("365", "365"),
}
SCHEDULES = {
    "six": "Daily-paid, 6 days a week",
    "five": "Daily-paid, 5 days a week",
    "everyday": "Daily-paid, works every day including rest days and holidays",
    "monthly": "Monthly-paid (paid for every day of the month)",
}


class NotCovered(Exception):
    """No verified rate period or holiday list covers the date asked about."""


@dataclass
class Result:
    total: Decimal
    lines: list[tuple[str, Decimal]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    parts: dict[str, Decimal] = field(default_factory=dict)
    months: list[dict] = field(default_factory=list)  # month-by-month amounts, for the charts


def peso(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), ROUND_HALF_UP)


def pct(share: Decimal) -> str:
    return f"{(share * 100).normalize():f}%"


def _check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _period(kind: str, on: date) -> dict:
    for p in RATES[kind]:
        if p["from"] <= on <= p["to"]:
            return {k: Decimal(v) if isinstance(v, str) and k != "source" else v for k, v in p.items()}
    loaded = "; ".join(f"{p['from']:%b %Y} to {p['to']:%b %Y}" for p in RATES[kind])
    raise NotCovered(f"No verified {AGENCY[kind]} rates for {on:%B %Y} yet (loaded: {loaded}).")


# --- 13th month pay (PD 851) ---

def basic_earned(monthly: Decimal, months: Decimal, unpaid_absences: Decimal = ZERO) -> Decimal:
    _check(monthly >= 0 and unpaid_absences >= 0, "Amounts cannot be negative.")
    _check(0 <= months <= 12, "Months worked must be between 0 and 12.")
    total = monthly * months - unpaid_absences
    _check(total >= 0, "Unpaid absences are more than the salary earned.")
    return peso(total)


def thirteenth_month(total_basic: Decimal, months_worked: Decimal) -> Result:
    _check(total_basic >= 0, "Basic salary earned cannot be negative.")
    _check(0 <= months_worked <= 12, "Months worked must be between 0 and 12.")
    sources = ["pd-851", "dole-handbook-2024"]
    if months_worked < 1:
        return Result(ZERO, notes=["Not required: the employee worked less than one month this year."], sources=sources)
    amount = peso(total_basic / 12)
    return Result(
        amount,
        lines=[("Basic salary earned this year", peso(total_basic)), ("13th month pay (÷ 12)", amount)],
        notes=[
            "Pay on or before 24 December.",
            "Basic salary leaves out overtime, premium, night differential, holiday pay, allowances "
            "and COLA, unless your policy treats them as part of basic pay.",
        ],
        sources=sources,
    )


# --- Holiday and premium pay (Labor Code Arts. 87, 93, 94) ---

def day_type_on(d: date) -> tuple[str, str] | None:
    year = HOLIDAYS.get(d.year)
    if year is None:
        raise NotCovered(f"No official holiday list loaded for {d.year}. Choose the day type yourself.")
    for day in year["days"]:
        if day["date"] == d:
            return day["type"], day["name"]
    return None


def holiday_pay(
    daily_rate: Decimal,
    day_type: str,
    worked: bool,
    rest_day: bool = False,
    ot_hours: Decimal = ZERO,
    qualified: bool = True,
    small_retail_service: bool = False,
) -> Result:
    _check(day_type in DAY_TYPES, "Unknown day type.")
    _check(daily_rate > 0, "Daily rate must be more than ₱0.")
    _check(0 <= ot_hours <= 16, "Overtime hours must be between 0 and 16.")
    notes, effective = [], day_type
    if day_type == "special_working":
        effective = "ordinary"
        notes.append("A special (working) day is paid as an ordinary working day.")
    if small_retail_service and day_type in UNWORKED:
        effective = "ordinary"
        notes.append(
            "Holiday pay does not cover retail or service businesses that regularly employ fewer than "
            "10 workers (Labor Code Art. 94), so this is paid as an ordinary day. The rest-day premium "
            "still applies. Paying the holiday rate anyway is allowed."
        )
    result = Result(ZERO, notes=notes, sources=["dole-handbook-2024"])

    if not worked:
        share = Decimal(UNWORKED.get(effective, "0"))
        if share and not qualified:
            share = ZERO
            notes.append("Not due: the employee was absent without pay on the last workday before the holiday.")
        elif not share:
            notes.append("No pay is required for an unworked day of this type, unless your policy or contract gives it.")
        result.total = peso(daily_rate * share)
        result.lines.append((f"Unworked {DAY_TYPES[day_type]} ({pct(share)} of daily rate)", result.total))
        return result

    share = Decimal(WORKED[(effective, rest_day)])
    ot_share = share * (Decimal("1.25") if (effective, rest_day) == ("ordinary", False) else Decimal("1.3"))
    day = peso(daily_rate * share)
    result.lines.append((f"First 8 hours ({pct(share)} of daily rate)", day))
    result.total = day
    if ot_hours:
        ot = peso(daily_rate / 8 * ot_share * ot_hours)
        result.lines.append((f"Overtime, {ot_hours.normalize():f} h ({pct(ot_share)} of hourly rate)", ot))
        result.total += ot
    return result


# --- Government contributions ---

def sss(comp: Decimal, on: date) -> dict:
    _check(comp >= 0, "Salary cannot be negative.")
    p = _period("sss", on)
    step = p["msc_step"]
    msc = p["msc_min"] + step * ((comp - p["msc_min"] + step / 2) // step)
    msc = min(max(msc, p["msc_min"]), p["msc_max"])
    ec = p["ec_low"] if msc < p["ec_threshold"] else p["ec_high"]
    return {"msc": msc, "er": peso(msc * p["er_rate"] + ec), "ee": peso(msc * p["ee_rate"]), "source": p["source"]}


def philhealth(salary: Decimal, on: date) -> dict:
    _check(salary >= 0, "Salary cannot be negative.")
    p = _period("philhealth", on)
    premium = peso(min(max(salary, p["floor"]), p["ceiling"]) * p["rate"])
    ee = peso(premium / 2)
    return {"ee": ee, "er": premium - ee, "source": p["source"]}


def pagibig(salary: Decimal, on: date) -> dict:
    _check(salary >= 0, "Salary cannot be negative.")
    p = _period("pagibig", on)
    fund = min(salary, p["fund_salary_cap"])
    ee_rate = p["ee_rate_low"] if salary <= p["low_salary"] else p["ee_rate"]
    return {"ee": peso(fund * ee_rate), "er": peso(fund * p["er_rate"]), "source": p["source"]}


def contributions(salary: Decimal, on: date) -> Result:
    result = Result(ZERO, notes=[
        "SSS counts total monthly pay; PhilHealth counts basic salary only. If this employee earns "
        "commissions or taxable allowances, the SSS share may be higher.",
    ])
    employee = employer = ZERO
    for kind, fn in (("sss", sss), ("philhealth", philhealth), ("pagibig", pagibig)):
        r = fn(salary, on)
        result.lines += [(f"{AGENCY[kind]}: deduct from employee", r["ee"]), (f"{AGENCY[kind]}: employer share", r["er"])]
        result.sources.append(r["source"])
        employee += r["ee"]
        employer += r["er"]
    result.parts = {"employee": employee, "employer": employer}
    result.total = employee + employer
    return result


# --- Final pay (DOLE Labor Advisory 06-20) ---

def final_pay(
    unpaid_salary: Decimal,
    basic_earned_this_year: Decimal,
    months_worked: Decimal,
    leave_days: Decimal,
    daily_rate: Decimal,
    other: Decimal = ZERO,
) -> Result:
    _check(unpaid_salary >= 0 and other >= 0 and daily_rate >= 0, "Amounts cannot be negative.")
    _check(0 <= leave_days <= 365, "Unused leave must be between 0 and 365 days.")
    _check(not leave_days or daily_rate > 0, "Enter the daily rate to convert unused leave to cash.")
    thirteenth = thirteenth_month(basic_earned_this_year, months_worked)
    lines = [
        ("Unpaid salary", peso(unpaid_salary)),
        ("Pro-rated 13th month pay", thirteenth.total),
        (f"Unused leave, {leave_days.normalize():f} days × daily rate", peso(daily_rate * leave_days)),
    ]
    if other:
        lines.append(("Other amounts owed", peso(other)))
    notes = [
        "Release within 30 days of separation, unless your policy is more favourable.",
        "Before lawful deductions and tax. Separation pay is not included.",
        "Service incentive leave is 5 days a year after one year of service, and is not required if "
        "you regularly employ fewer than 10 workers.",
    ]
    return Result(
        sum((a for _, a in lines), ZERO),
        lines=lines,
        notes=notes + [n for n in thirteenth.notes if n.startswith("Not required")],
        sources=["dole-la-06-20", "pd-851", "dole-handbook-2024"],
    )


# --- Salary for the year (DOLE equivalent-monthly-rate factors) ---

def salary(
    daily_rate: Decimal,
    schedule: str,
    special_days_paid: bool = False,
    unpaid_absences: Decimal = ZERO,
) -> Result:
    _check(schedule in PAID_DAYS, "Unknown work schedule.")
    _check(daily_rate > 0, "Daily rate must be more than ₱0.")
    _check(0 <= unpaid_absences <= 366, "Unpaid absences must be between 0 and 366 days.")
    days = Decimal(PAID_DAYS[schedule][0 if special_days_paid else 1])
    yearly = peso(daily_rate * days)
    lines = [("Daily rate", peso(daily_rate)), (f"Yearly pay, {days} paid days × daily rate", yearly)]
    absences = peso(daily_rate * unpaid_absences)
    if unpaid_absences:
        lines.append((f"Less {unpaid_absences.normalize():f} unpaid absence days", absences))
    lines.append(("Monthly equivalent (÷ 12)", peso(yearly / 12)))
    notes = [f"Estimate using DOLE's equivalent-monthly-rate factor: {days} paid days a year for "
             f"{SCHEDULES[schedule].lower()}."]
    if schedule in ("six", "five") and not special_days_paid:
        notes.append("Special (non-working) days are counted as unpaid (no work, no pay). "
                     "If your company pays them, tick that option.")
    notes += [
        "Leaves out overtime, holiday and rest-day premiums, night differential, 13th month pay, "
        "and deductions such as tax and contributions.",
        "The real number of paid days shifts a little with each year's holidays.",
    ]
    return Result(yearly - absences, lines=lines, notes=notes, sources=["dole-handbook-2024"])


# --- Cost of a worker to the employer (salary, employer shares, 13th month) ---

def worker_cost(monthly: Decimal, start: date) -> Result:
    """What one worker costs the owner from the start month through December."""
    _check(monthly > 0, "Monthly salary must be more than ₱0.")
    monthly = peso(monthly)
    months, sources, employee = [], [], ZERO
    for m in range(start.month, 13):
        c = contributions(monthly, date(start.year, m, 1))
        months.append({"month": date(start.year, m, 1), "salary": monthly, "employer": c.parts["employer"],
                       "thirteenth": ZERO})
        employee += c.parts["employee"]
        sources = c.sources
    worked = Decimal(len(months))
    months[-1]["thirteenth"] = thirteenth_month(basic_earned(monthly, worked), worked).total
    totals = {k: sum((m[k] for m in months), ZERO) for k in ("salary", "employer", "thirteenth")}
    total = sum(totals.values(), ZERO)
    return Result(
        total,
        lines=[
            (f"Salary, {worked} months × ₱{monthly:,.2f}", totals["salary"]),
            ("Employer share: SSS, PhilHealth, Pag-IBIG", totals["employer"]),
            ("13th month pay, due by 24 December", totals["thirteenth"]),
            ("Average a month", peso(total / worked)),
        ],
        notes=[
            f"The worker's own share of the contributions, ₱{employee:,.2f} this year, is deducted from "
            "their salary, so it is not an added cost.",
            "Assumes the same salary every month. Overtime, holiday premiums, night differential, "
            "service incentive leave and benefits your policy adds are not included.",
            "13th month pay is one-twelfth of the salary earned this year.",
        ],
        sources=sources + ["pd-851", "dole-handbook-2024"],
        months=months,
    )
