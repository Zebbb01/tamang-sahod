"""Chart geometry for the cost-of-a-worker result. Expected figures are hand-computed."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.calc import worker_cost
from app.charts import compact, cost_chart, nice_ticks


@pytest.mark.parametrize("top, ticks", [
    (47000, [0, 10000, 20000, 30000, 40000, 50000]),
    (22730, [0, 5000, 10000, 15000, 20000, 25000]),
    (26063.33, [0, 10000, 20000, 30000]),
    (900, [0, 200, 400, 600, 800, 1000]),
])
def test_ticks_are_round_and_cover_the_tallest_bar(top, ticks):
    assert nice_ticks(top) == ticks


@pytest.mark.parametrize("amount, label", [
    (0, "0"), (500, "500"), (2500, "2.5K"), (25000, "25K"), (26063.33, "26.1K"), (1200000, "1.2M"),
])
def test_compact_labels(amount, label):
    assert compact(amount) == label


@pytest.fixture
def november_hire():
    # ₱20,000 a month from November: 2 × 22,730 a month, plus 3,333.33 13th month in December
    return cost_chart(worker_cost(D("20000"), date(2026, 11, 1)).months)


def test_every_month_of_the_year_has_a_column(november_hire):
    assert [c["label"] for c in november_hire["columns"]] == [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    assert all(not c["segments"] for c in november_hire["columns"][:10])  # not yet hired


def test_december_column_stacks_salary_employer_share_and_13th_month(november_hire):
    dec = november_hire["columns"][-1]
    assert dec["total"] == D("26063.33")
    # Axis tops out at 30,000
    assert [(key, height) for key, _, _, height in dec["segments"]] == [
        ("salary", 66.67), ("employer", 9.10), ("thirteenth", 11.11)]
    assert november_hire["peak"] == 11


def test_share_of_the_year_adds_up(november_hire):
    # 40,000 + 5,460 + 3,333.33 = 48,793.33
    assert [(key, amount, round(pct, 1)) for key, _, amount, pct in november_hire["share"]] == [
        ("salary", D("40000"), 82.0), ("employer", D("5460"), 11.2), ("thirteenth", D("3333.33"), 6.8)]


def test_tick_positions_run_bottom_to_top(november_hire):
    assert november_hire["ticks"] == [("0", 0.0), ("10K", 33.33), ("20K", 66.67), ("30K", 100.0)]
