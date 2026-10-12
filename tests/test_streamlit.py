"""Streamlit front end, driven headless with Streamlit's AppTest."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app import forms, search

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


@pytest.fixture
def at(monkeypatch):
    monkeypatch.setattr(search, "build", lambda: None)  # never download the model in tests
    return AppTest.from_file(APP, default_timeout=60).run()


def compute(at):
    next(b for b in at.button if b.label == "Compute").click().run()
    return " ".join(m.value for m in at.markdown)


def test_thirteenth_month(at):
    at.text_input(key="thirteenth.monthly_salary").input("15,910.83")
    at.text_input(key="thirteenth.unpaid_absences").input("6710")
    assert "₱15,351.66" in compute(at)


def test_holiday_uses_2026_list(at):
    at.radio(key="topic").set_value("holiday").run()
    at.text_input(key="holiday.daily_rate").input("800")
    at.date_input(key="holiday.date").set_value(date(2026, 12, 30))
    page = compute(at)
    assert "₱1,600.00" in page
    assert "Rizal Day" in page


def test_bad_input_is_explained(at):
    at.radio(key="topic").set_value("holiday").run()
    at.text_input(key="holiday.daily_rate").input("abc")
    at.date_input(key="holiday.date").set_value(date(2026, 12, 30))
    compute(at)
    assert at.error[0].value == "Daily rate must be a number."


def ask(at, question):
    at.text_area(key="question").input(question)
    next(b for b in at.button if b.label == "Ask").click().run()


def test_question_prefills_calculator(at, monkeypatch):
    monkeypatch.setattr(forms, "extract", lambda q: ("holiday", {"daily_rate": Decimal("645"), "worked": True}))
    monkeypatch.setattr(search, "search", lambda q: ([], 0.0))
    ask(at, "Pumasok siya noong Dec 30, 645 ang daily")
    assert at.radio(key="topic").value == "holiday"
    assert at.text_input(key="holiday.daily_rate").value == "645"
    assert "Check each field" in at.info[0].value


def test_question_outside_scope_is_not_covered(at, monkeypatch):
    monkeypatch.setattr(forms, "extract", lambda q: None)
    monkeypatch.setattr(search, "search", lambda q: ([], 0.0))
    ask(at, "How do I register with DTI?")
    assert "Not covered yet" in at.warning[0].value
    assert "1349" in at.warning[0].value
