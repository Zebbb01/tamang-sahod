"""What an owner does in the browser. Amounts use the 2026 rates; from January 2027 these
fail until data/rates.toml is re-verified, which is the point."""

import pytest
from playwright.sync_api import Page, expect

from app.forms import FORMS


@pytest.mark.parametrize("topic", list(FORMS))
def test_each_calculator_opens_from_home(page: Page, topic):
    page.goto("/")
    page.get_by_role("link", name=FORMS[topic].title).click()
    expect(page.get_by_role("heading", level=1)).to_have_text(FORMS[topic].title)


def test_cost_of_a_worker_shows_the_year_as_charts(page: Page):
    page.goto("/calc/cost")
    page.get_by_label("Rate").fill("20,000")
    page.get_by_role("button", name="Compute the cost").click()

    expect(page.locator(".amount")).to_have_text("₱292,760.00")
    expect(page.locator(".col")).to_have_count(12)
    expect(page.locator(".col").last).to_have_attribute("title", "Dec 2026: ₱42,730.00")
    page.get_by_text("Month by month").click()
    expect(page.get_by_role("row")).to_have_count(13)  # header + January to December


def test_cost_from_a_daily_rate_fits_a_phone(page: Page):
    page.set_viewport_size({"width": 360, "height": 800})
    page.goto("/calc/cost")
    page.get_by_role("radio", name="Day").check()
    expect(page.get_by_text("6 days a week")).to_be_visible()  # schedule shows only for a daily rate
    page.get_by_label("Rate").fill("645")
    page.get_by_role("radio", name="Nov").check()
    page.get_by_role("button", name="Compute the cost").click()

    expect(page.get_by_text("₱16,393.75 a month")).to_be_visible()
    expect(page.locator(".col").nth(9)).to_have_attribute("title", "Oct 2026: not on payroll")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
