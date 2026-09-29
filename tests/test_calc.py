"""Calculator tests. Expected figures come from the official sources:
DOLE-BWC Handbook on Workers' Statutory Monetary Benefits (2024 ed.), SSS Circular
2024-006, PhilHealth Advisory 2025-0002, HDMF Circular 460 and Proclamation 1006."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.calc import (
    NotCovered,
    basic_earned,
    contributions,
    day_type_on,
    final_pay,
    holiday_pay,
    pagibig,
    philhealth,
    sss,
    thirteenth_month,
)

OCT_2026 = date(2026, 10, 1)


# --- 13th month (Handbook §13 D: ₱184,219.96 / 12 = ₱15,351.66) ---

def test_basic_earned_matches_handbook_year():
    # 12 months at ₱15,910.83, less 10 + 1 days of leave without pay at ₱610
    assert basic_earned(D("15910.83"), D("12"), D("6710")) == D("184219.96")


def test_thirteenth_month_matches_handbook_example():
    assert thirteenth_month(D("184219.96"), D("12")).total == D("15351.66")


def test_thirteenth_month_not_due_under_one_month():
    r = thirteenth_month(D("10000"), D("0.5"))
    assert r.total == 0
    assert any("less than one month" in n for n in r.notes)


def test_thirteenth_month_rejects_more_than_twelve_months():
    with pytest.raises(ValueError):
        thirteenth_month(D("10000"), D("13"))


# --- Holiday pay (Handbook "Guide Computations", daily rate ₱800, hourly ₱100) ---

@pytest.mark.parametrize("day_type, rest_day, day_pay, ot_2h", [
    ("ordinary", False, "800", "250"),          # 100%, OT 125%
    ("ordinary", True, "1040", "338"),          # 130%, OT 169%
    ("special_working", False, "800", "250"),   # treated as an ordinary day
    ("special", False, "1040", "338"),          # 130%, OT 169%
    ("special", True, "1200", "390"),           # 150%, OT 195%
    ("double_special", False, "1200", "390"),   # 150%, OT 195%
    ("double_special", True, "1560", "507"),    # 195%, OT 253.5%
    ("regular", False, "1600", "520"),          # 200%, OT 260%
    ("regular", True, "2080", "676"),           # 260%, OT 338%
    ("double_regular", False, "2400", "780"),   # 300%, OT 390%
    ("double_regular", True, "3120", "1014"),   # 390%, OT 507%
])
def test_holiday_pay_matches_handbook_guide(day_type, rest_day, day_pay, ot_2h):
    worked = holiday_pay(D("800"), day_type, worked=True, rest_day=rest_day)
    assert worked.total == D(day_pay)
    with_ot = holiday_pay(D("800"), day_type, worked=True, rest_day=rest_day, ot_hours=D("2"))
    assert with_ot.total == D(day_pay) + D(ot_2h)


@pytest.mark.parametrize("day_type, qualified, expected", [
    ("regular", True, "800"),           # 100% if present or on paid leave the workday before
    ("regular", False, "0"),
    ("double_regular", True, "1600"),   # 200%
    ("special", True, "0"),             # no work, no pay
    ("special_working", True, "0"),
])
def test_unworked_day(day_type, qualified, expected):
    assert holiday_pay(D("800"), day_type, worked=False, qualified=qualified).total == D(expected)


def test_small_retail_or_service_is_exempt_from_holiday_pay_only():
    # Holiday Pay coverage excludes retail/service establishments regularly employing
    # fewer than ten workers; Premium Pay coverage has no such exclusion.
    small = dict(small_retail_service=True)
    assert holiday_pay(D("800"), "regular", worked=False, **small).total == 0
    assert holiday_pay(D("800"), "regular", worked=True, **small).total == D("800")
    assert holiday_pay(D("800"), "regular", worked=True, rest_day=True, **small).total == D("1040")
    assert holiday_pay(D("800"), "special", worked=True, **small).total == D("1040")


def test_holiday_pay_rejects_bad_input():
    with pytest.raises(ValueError):
        holiday_pay(D("0"), "regular", worked=True)
    with pytest.raises(ValueError):
        holiday_pay(D("800"), "regular", worked=True, ot_hours=D("17"))
    with pytest.raises(ValueError):
        holiday_pay(D("800"), "birthday", worked=True)


# --- 2026 day types (Proclamation 1006, s. 2025) ---

def test_day_type_lookup():
    assert day_type_on(date(2026, 11, 30)) == ("regular", "Bonifacio Day")
    assert day_type_on(date(2026, 2, 25)) == ("special_working", "EDSA People Power Revolution Anniversary")
    assert day_type_on(date(2026, 11, 2)) == ("special", "All Souls' Day")
    assert day_type_on(date(2026, 10, 15)) is None


def test_day_type_lookup_refuses_year_without_list():
    with pytest.raises(NotCovered):
        day_type_on(date(2027, 1, 1))


# --- SSS (Circular 2024-006 schedule, rows read off the published table) ---

@pytest.mark.parametrize("comp, msc, er, ee", [
    ("4000", "5000", "510", "250"),         # below 5,250
    ("5250", "5500", "560", "275"),
    ("5749.99", "5500", "560", "275"),
    ("14749.99", "14500", "1460", "725"),   # last row with EC ₱10
    ("14750", "15000", "1530", "750"),      # EC becomes ₱30
    ("20250", "20500", "2080", "1025"),     # first row with MPF
    ("34749.99", "34500", "3480", "1725"),
    ("34750", "35000", "3530", "1750"),
    ("100000", "35000", "3530", "1750"),
])
def test_sss_matches_published_table(comp, msc, er, ee):
    r = sss(D(comp), OCT_2026)
    assert (r["msc"], r["er"], r["ee"]) == (D(msc), D(er), D(ee))


def test_sss_refuses_dates_outside_verified_period():
    with pytest.raises(NotCovered):
        sss(D("20000"), date(2024, 12, 1))
    with pytest.raises(NotCovered):
        sss(D("20000"), date(2027, 1, 1))


# --- PhilHealth (Advisory 2025-0002: 5%, floor ₱10,000, ceiling ₱100,000, shared equally) ---

@pytest.mark.parametrize("salary, ee, er", [
    ("8000", "250", "250"),
    ("25000", "625", "625"),
    ("150000", "2500", "2500"),
])
def test_philhealth(salary, ee, er):
    r = philhealth(D(salary), OCT_2026)
    assert (r["ee"], r["er"]) == (D(ee), D(er))


# --- Pag-IBIG (Circular 460: fund salary capped at ₱10,000; 1% employee at ₱1,500 or below) ---

@pytest.mark.parametrize("salary, ee, er", [
    ("1500", "15", "30"),
    ("5000", "100", "100"),
    ("25000", "200", "200"),
])
def test_pagibig(salary, ee, er):
    r = pagibig(D(salary), OCT_2026)
    assert (r["ee"], r["er"]) == (D(ee), D(er))


def test_contributions_total_for_20k_salary():
    r = contributions(D("20000"), OCT_2026)
    # SSS 1,000 + PhilHealth 500 + Pag-IBIG 200 from the employee;
    # SSS 2,030 + PhilHealth 500 + Pag-IBIG 200 from the employer.
    assert r.parts == {"employee": D("1700"), "employer": D("2730")}
    assert r.total == D("4430")


# --- Final pay (Handbook §13 G and §7 D figures combined) ---

def test_final_pay_combines_parts():
    r = final_pay(
        unpaid_salary=D("5000"),
        basic_earned_this_year=D("184219.96"),
        months_worked=D("12"),
        leave_days=D("5.833"),   # Handbook §7 D: 5 days + 2/12 x 5 days
        daily_rate=D("610"),
    )
    assert D("3558.13") in [amount for _, amount in r.lines]   # Handbook §7 D
    assert r.total == D("5000") + D("15351.66") + D("3558.13")
