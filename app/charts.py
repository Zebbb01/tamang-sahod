"""Chart geometry for the cost-of-a-worker result. The page draws it as plain HTML bars
sized in percent (no chart library, no JavaScript); amounts stay Decimal, only the
geometry is float."""

import calendar
import math
from decimal import Decimal

SERIES = (
    ("salary", "Salary"),
    ("employer", "Employer share of SSS, PhilHealth, Pag-IBIG"),
    ("thirteenth", "13th month pay"),
)


def nice_ticks(top: float) -> list[float]:
    """Round axis ticks from 0 to at least `top`, about five steps of 1, 2, 2.5 or 5 × 10ⁿ."""
    raw = float(top) / 5
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    return [step * i for i in range(math.ceil(float(top) / step) + 1)]


def compact(amount: float) -> str:
    """25000 -> 25K, 1200000 -> 1.2M, for axis ticks and the peak label."""
    amount = float(amount)
    for size, suffix in ((1_000_000, "M"), (1_000, "K")):
        if amount >= size:
            return f"{round(amount / size, 1):g}{suffix}"
    return f"{amount:g}"


def cost_chart(months: list[dict]) -> dict:
    """Twelve stacked columns (Jan-Dec), the share of the year by series, and the y-axis."""
    by_month = {m["month"].month: m for m in months}
    ticks = nice_ticks(max(sum(m[k] for k, _ in SERIES) for m in months))
    top = ticks[-1]
    columns = []
    for n in range(1, 13):
        m = by_month.get(n)
        segments = [(k, label, m[k], round(float(m[k]) * 100 / top, 2)) for k, label in SERIES if m and m[k]]
        columns.append({"label": calendar.month_abbr[n], "total": sum((s[2] for s in segments), Decimal(0)),
                        "segments": segments, "height": round(sum(s[3] for s in segments), 2)})
    totals = {k: sum((m[k] for m in months), Decimal(0)) for k, _ in SERIES}
    grand = sum(totals.values())
    return {
        "columns": columns,
        "peak": max(range(12), key=lambda i: columns[i]["total"]),
        "share": [(k, label, totals[k], float(totals[k] * 100 / grand)) for k, label in SERIES if totals[k]],
        "ticks": [(compact(t), round(t * 100 / top, 2)) for t in ticks],
    }
