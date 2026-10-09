"""
Boutique Courir scraper rules (WooCommerce, French-formatted prices).

Pure helpers only — no HTML fixtures (CLAUDE.md §10: retailer DOMs are
verified live via the dry-run, not pinned in tests). The rules:
  - French prices parse correctly (BaseScraper.parse_price would not);
  - model matching is whole-word, numbers included;
  - the search query drops the numbers WordPress search trips on;
  - the bespoke registration takes the retailer out of the onboarding queue.
"""
import pytest

from app.models.models import Retailer
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.boutique_courir import BoutiqueCourirScraper, _parse_fr_price, title_matches
from app.scrapers.registry import BESPOKE_SCRAPERS
from app.services.onboarding import retailers_needing_onboarding


@pytest.mark.parametrize("text,expected", [
    ("189,99 $", 189.99),
    ("189,99 $", 189.99),
    ("1 299,99 $", 1299.99),
    ("1 299,99 $", 1299.99),
    ("180 $", 180.0),
    ("", None),
    (None, None),
])
def test_parse_fr_price(text, expected):
    assert _parse_fr_price(text) == expected


def test_base_parse_price_would_misread_french_prices():
    # The reason _parse_fr_price exists: the shared parser drops the comma.
    assert BaseScraper.parse_price(None, "189,99 $") == 18999.0


@pytest.mark.parametrize("title,model,ok", [
    ("Novablast 5 • H", "Novablast 5", True),
    ("Novablast 5 EKIDEN • F", "Novablast 5", True),   # edition of the same model
    ("Novablast 6 • F", "Novablast 5", False),
    ("Clifton 10 • H", "Clifton 1", False),            # whole-word numbers
    ("Clifton 10 • H", "Clifton 10", True),
    ("GEL-Nimbus 27 • F", "Gel Nimbus 27", True),      # hyphen splits
    ("GEL-Nimbus 28 • H", "Gel-Nimbus 27", False),
    ("Lacets Lock Laces", "", False),
])
def test_title_matches(title, model, ok):
    assert title_matches(title, model) is ok


@pytest.mark.parametrize("model,query", [
    ("Clifton 10", "clifton"),
    ("Gel-Nimbus 27", "gel nimbus"),
    ("Novablast 5", "novablast"),
    ("1080", "1080"),  # all-numeric model falls back to itself
])
def test_search_query_drops_numbers(model, query):
    assert BoutiqueCourirScraper._search_query(model) == query


def test_registered_and_out_of_onboarding_queue(db):
    assert BESPOKE_SCRAPERS["Boutique Courir"] is BoutiqueCourirScraper
    db.add(Retailer(name="Boutique Courir", base_url="https://boutiquecourir.com",
                    platform="custom", is_active=True, scraping_enabled=False))
    db.commit()
    assert "Boutique Courir" not in [r["name"] for r in retailers_needing_onboarding(db)]
