import re

import pytest
from fastapi.testclient import TestClient

from app import forms, main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(main.templates.env.globals, "goatcounter", "demo")
    return TestClient(main.app)


def test_home_shows_question_box_and_four_calculators(client):
    page = client.get("/").text
    assert 'name="q"' in page
    for form in main.FORMS.values():
        assert form.title in page


def test_holiday_result_uses_2026_list(client):
    page = client.post("/calc/holiday", data={
        "daily_rate": "800", "date": "2026-12-30", "day_type": "auto", "worked": "yes", "ot_hours": "0",
    }).text
    assert "Rizal Day" in page
    assert "₱1,600.00" in page
    assert "Labor Advisory No. 12-25" in page  # the 2026 pay rules are cited


def test_thirteenth_month_result(client):
    page = client.post("/calc/thirteenth", data={
        "monthly_salary": "15,910.83", "months_worked": "12", "unpaid_absences": "6710",
    }).text
    assert "₱15,351.66" in page


def test_bad_input_is_explained_on_the_form(client):
    page = client.post("/calc/holiday", data={"daily_rate": "abc", "day_type": "regular", "worked": "yes"}).text
    assert "Daily rate must be a number." in page
    assert 'value="abc"' in page  # what they typed is kept


def test_unverified_period_is_refused(client):
    page = client.post("/calc/contributions", data={"monthly_salary": "20000", "month": "2027-01"}).text
    assert "No verified SSS rates for January 2027" in page


def test_amounts_never_reach_urls_or_analytics(client):
    page = client.post("/calc/holiday", data={
        "daily_rate": "777", "day_type": "regular", "worked": "yes", "ot_hours": "0",
    }).text
    assert "₱1,554.00" in page
    forms = re.findall(r"<form[^>]*>", page)
    assert forms and all('method="post"' in f for f in forms)
    tracked = re.findall(r'goatcounter = \{path: "([^"]*)"', page)
    assert tracked == ["/result/holiday"]


def test_malformed_date_is_explained(client):
    page = client.post("/calc/holiday", data={
        "daily_rate": "800", "date": "other", "other_date": "sometime", "day_type": "auto"}).text
    assert "Enter the date like Dec 30 or 2026-12-30." in page


@pytest.mark.parametrize("typed", ["Dec 30", "30 Dec 2026", "30/12/2026", "2026-12-30"])
def test_typed_date_finds_the_holiday(client, typed):
    page = client.post("/calc/holiday", data={
        "daily_rate": "800", "date": "other", "other_date": typed, "day_type": "auto", "worked": "yes"}).text
    assert "Rizal Day" in page
    assert "₱1,600.00" in page


@pytest.mark.parametrize("topic", list(main.FORMS))
def test_no_native_dropdowns_or_calendars(client, topic):
    page = client.get(f"/calc/{topic}").text
    assert "<select" not in page
    assert 'type="date"' not in page and 'type="month"' not in page


def test_fields_that_do_not_apply_are_marked_conditional(client):
    page = client.get("/calc/salary").text
    assert 'data-show-if="hours_per_day"' in page
    assert '[name="rate_per"][value="hour"]:checked' in page


def test_result_placeholder_before_compute(client):
    assert "Your result appears here" in client.get("/calc/salary").text


def test_example_question_chip_asks_it(client, monkeypatch):
    monkeypatch.setattr(forms, "extract", lambda q: None)
    monkeypatch.setattr(forms.search, "search", lambda q: ([], 0.0))
    page = client.post("/ask", data={"q": "", "example": "Magkano ang 13th month ng nag-resign?"}).text
    assert "Magkano ang 13th month ng nag-resign?" in page


def test_question_prefills_form_when_extraction_succeeds(client, monkeypatch):
    from decimal import Decimal
    monkeypatch.setattr(forms, "extract", lambda q: ("holiday", {"daily_rate": Decimal("645"), "worked": True}))
    monkeypatch.setattr(forms.search, "search", lambda q: ([], 0.0))
    page = client.post("/ask", data={"q": "Pumasok siya noong Dec 30, 645 ang daily"}).text
    assert 'value="645"' in page
    assert "Pumasok siya noong Dec 30" in page
    assert "Check each field" in page


def test_question_without_index_or_llm_is_not_covered(client, monkeypatch):
    monkeypatch.setattr(forms, "extract", lambda q: None)

    def broken(q):
        raise RuntimeError("no index")

    monkeypatch.setattr(forms.search, "search", broken)
    page = client.post("/ask", data={"q": "How do I register with DTI?"}).text
    assert "Not covered yet" in page
    assert "1349" in page


def test_health(client):
    assert client.get("/health").text == "ok"


def test_salary_from_hourly_rate(client):
    page = client.post("/calc/salary", data={
        "rate": "919.54", "rate_per": "hour", "hours_per_day": "8", "schedule": "six", "unpaid_absences": "5",
    }).text
    assert "₱2,206,896.00" in page
    assert "₱7,356.32" in page  # the daily rate it worked from


def test_switch_left_off_counts_as_off():
    # Regression: an empty switch value once counted as "on" (313 days instead of 305).
    result, _ = forms.compute("salary", forms.form_values("salary", {"rate": "500"}))
    assert result.total == 500 * 305


def test_cost_of_a_worker_charts_each_month(client):
    page = client.post("/calc/cost", data={"rate": "20,000", "rate_per": "month", "month": "2026-01"}).text
    assert "₱292,760.00" in page             # 240,000 salary + 32,760 employer share + 20,000 13th month
    assert "Jan 2026: ₱22,730.00" in page    # a month: salary + employer share
    assert "Dec 2026: ₱42,730.00" in page    # December adds the 13th month pay
    assert "Month by month" in page          # the table view of the chart


def test_cost_from_a_daily_rate_uses_dole_paid_days(client):
    page = client.post("/calc/cost", data={
        "rate": "645", "rate_per": "day", "schedule": "six", "month": "2026-01"}).text
    assert "₱16,393.75" in page  # ₱645 × 305 paid days ÷ 12


def test_cost_before_hiring_month_shows_empty_columns(client):
    page = client.post("/calc/cost", data={"rate": "20000", "rate_per": "month", "month": "2026-11"}).text
    assert "Oct 2026: not on payroll" in page
    assert "₱48,793.33" in page
