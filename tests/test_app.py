import re

import pytest
from fastapi.testclient import TestClient

from app import main


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
    page = client.post("/calc/holiday", data={"daily_rate": "800", "date": "30-12-2026", "day_type": "auto"}).text
    assert "Enter the date as YYYY-MM-DD." in page


def test_question_prefills_form_when_extraction_succeeds(client, monkeypatch):
    from decimal import Decimal
    monkeypatch.setattr(main, "extract", lambda q: ("holiday", {"daily_rate": Decimal("645"), "worked": True}))
    monkeypatch.setattr(main.search, "search", lambda q: ([], 0.0))
    page = client.post("/ask", data={"q": "Pumasok siya noong Dec 30, 645 ang daily"}).text
    assert 'value="645"' in page
    assert "Pumasok siya noong Dec 30" in page
    assert "Check each field" in page


def test_question_without_index_or_llm_is_not_covered(client, monkeypatch):
    monkeypatch.setattr(main, "extract", lambda q: None)

    def broken(q):
        raise RuntimeError("no index")

    monkeypatch.setattr(main.search, "search", broken)
    page = client.post("/ask", data={"q": "How do I register with DTI?"}).text
    assert "Not covered yet" in page
    assert "1349" in page


def test_health(client):
    assert client.get("/health").text == "ok"
