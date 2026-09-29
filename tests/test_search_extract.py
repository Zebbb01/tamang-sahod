from datetime import date
from decimal import Decimal as D

from app.extract import parse
from app.search import load_corpus, rrf, topic_of


# --- corpus and fusion (no model needed) ---

def test_corpus_passages_carry_source_and_location():
    rows = load_corpus()
    assert len(rows) >= 40
    holiday = next(r for r in rows if r["title"] == "Holiday pay (Labor Code Art. 94) — B. Coverage")
    assert holiday["source"] == "dole-handbook-2024"
    assert holiday["where"] == "p. 26"
    assert "less than ten workers" in holiday["text"]


def test_rrf_rewards_agreement_between_rankings():
    assert rrf([["a", "b", "c"], ["c", "a"]])[:2] == ["a", "c"]


def test_topic_of_passage():
    assert topic_of({"source": "sss-ci-2024-006", "title": "x"}) == "contributions"
    assert topic_of({"source": "dole-handbook-2024", "title": "13th month pay (PD 851) — C. Amount"}) == "thirteenth"
    assert topic_of({"source": "dole-handbook-2024", "title": "Service incentive leave (Labor Code Art. 95) — D. Conversion"}) == "final"
    assert topic_of({"source": "dole-handbook-2024", "title": "Premium pay (Labor Code Arts. 91-93) — D. Premium Pay Rates"}) == "holiday"


# --- LLM output is untrusted: only known topics and valid values survive ---

def test_parse_keeps_valid_fields():
    got = parse('{"topic": "holiday", "fields": {"daily_rate": "₱645", "date": "2026-12-30", "worked": true, "ot_hours": 2}}')
    assert got == ("holiday", {"daily_rate": D("645"), "date": date(2026, 12, 30), "worked": True, "ot_hours": D("2")})


def test_parse_drops_unknown_and_invalid_values():
    got = parse('{"topic": "thirteenth", "fields": {"monthly_salary": "-5", "months_worked": "abc", "password": "x", "total_basic": "120,000"}}')
    assert got == ("thirteenth", {"total_basic": D("120000")})


def test_parse_rejects_unknown_topic_and_bad_json():
    assert parse('{"topic": "separation", "fields": {}}') is None
    assert parse('{"topic": "none"}') is None
    assert parse("not json") is None
