"""
Champs Sports Canada scraper rules (Foot Locker SSR storefront).

Pure helpers plus one tiny markup snippet per price shape. No full-page HTML
fixtures (CLAUDE.md §10: retailer DOMs are verified live via the dry-run). The rules:
  - whole-word model matching, numbers included, brand verified from the name;
  - women's listings never match a men's watch;
  - sale blocks read as (current, original) whatever the markup order;
  - the bespoke registration takes the retailer out of the onboarding queue;
  - a row named differently (production's "Champs Sports") still resolves by host.
"""
import pytest
from bs4 import BeautifulSoup

from app.models.models import Retailer
from app.scrapers.champs_sports import ChampsSportsScraper, _price_pair, name_matches
from app.scrapers.registry import BESPOKE_SCRAPERS, bespoke_class_for, build_registry, get_scraper
from app.services.onboarding import retailers_needing_onboarding


def test_name_matches_is_whole_word_with_brand():
    assert name_matches("Nike Air Zoom Pegasus 42  - Men's", "Nike", "Pegasus 42")
    assert not name_matches("Nike Air Zoom Pegasus 42  - Men's", "Nike", "Pegasus 4")
    assert not name_matches("Nike Air Zoom Pegasus 42  - Men's", "Adidas", "Pegasus 42")


def test_name_matches_excludes_womens_unless_watched():
    assert not name_matches("Nike Air Zoom Pegasus 42  - Women's", "Nike", "Pegasus 42")
    assert name_matches("Nike Pegasus Women's 42", "Nike", "Pegasus Women's 42")


def test_name_matches_hyphen_splits():
    assert name_matches("Asics Gel-Kayano 31 - Men's", "Asics", "Gel Kayano 31")


def _block(markup: str):
    return BeautifulSoup(f'<div data-testid="ProductPrice">{markup}</div>', "html.parser").div


def test_regular_price_has_no_original():
    block = _block('<span>$180.00</span>')
    assert _price_pair(block) == (180.0, None)


def test_sale_price_reads_as_current_and_original_in_either_order():
    sale = ('<span data-testid="Sale"><span>This item is on sale. Price dropped from '
            '$270.00 to $189.99</span><span aria-hidden="true">$189.99</span>'
            '<span aria-hidden="true">$270.00</span></span>')
    assert _price_pair(_block(sale)) == (189.99, 270.0)
    flipped = sale.replace('$189.99</span><span aria-hidden="true">$270.00', '$270.00</span><span aria-hidden="true">$189.99')
    assert _price_pair(_block(flipped)) == (189.99, 270.0)


def test_missing_price_block_is_none():
    assert _price_pair(None) == (None, None)


def test_registered_and_out_of_onboarding_queue(db):
    assert BESPOKE_SCRAPERS["Champs Sports Canada"] is ChampsSportsScraper
    db.add(Retailer(name="Champs Sports Canada", base_url="https://www.champssports.ca",
                    platform="custom", is_active=True, scraping_enabled=False))
    db.commit()
    assert "Champs Sports Canada" not in [r["name"] for r in retailers_needing_onboarding(db)]


def test_differently_named_row_resolves_by_host(db):
    # Production's row: added through the UI as "Champs Sports", URL with a
    # trailing slash. Name lookup misses; the host must still find the scraper.
    db.add(Retailer(name="Champs Sports", base_url="https://www.champssports.ca/",
                    platform="custom", is_active=True, scraping_enabled=True))
    db.commit()
    row = db.query(Retailer).filter_by(name="Champs Sports").one()
    assert bespoke_class_for(row) is ChampsSportsScraper
    assert isinstance(get_scraper(row), ChampsSportsScraper)
    assert isinstance(build_registry(db)["Champs Sports"], ChampsSportsScraper)
    assert "Champs Sports" not in [r["name"] for r in retailers_needing_onboarding(db)]


def test_unknown_host_is_not_matched(db):
    row = Retailer(name="Foot Locker", base_url="https://www.footlocker.ca/",
                   platform="custom", is_active=True)
    assert bespoke_class_for(row) is None
    assert get_scraper(row) is None


_MATCHING_TILE = ('<div data-testid="ProductCardV3"><a data-productcard=\'{"name": "Nike Vomero 18 - Men&#39;s"}\' '
                  'href="/en/product/x/1.html"></a><div data-testid="ProductPrice"><span>$190.00</span></div></div>')


def test_page_with_no_tiles_raises_with_title(monkeypatch):
    scraper = ChampsSportsScraper()
    html = "<html><head><title>Please wait - Queue</title></head><body>waiting</body></html>"
    monkeypatch.setattr(scraper, "fetch_page", lambda url, use_browser=False: html)
    with pytest.raises(ValueError, match="Please wait - Queue"):
        scraper.search_products("Nike", "Vomero 18")


def test_no_page_returned_raises(monkeypatch):
    scraper = ChampsSportsScraper()
    monkeypatch.setattr(scraper, "fetch_page", lambda url, use_browser=False: None)
    with pytest.raises(ValueError):
        scraper.search_products("Nike", "Vomero 18")


def test_tiles_that_do_not_match_return_empty_without_raising(monkeypatch):
    scraper = ChampsSportsScraper()
    html = _MATCHING_TILE.replace("Vomero 18", "Pegasus 41")
    monkeypatch.setattr(scraper, "fetch_page", lambda url, use_browser=False: html)
    assert scraper.search_products("Nike", "Vomero 18") == []


def test_matching_tile_returns_one_result(monkeypatch):
    scraper = ChampsSportsScraper()
    monkeypatch.setattr(scraper, "fetch_page", lambda url, use_browser=False: _MATCHING_TILE)
    results = scraper.search_products("Nike", "Vomero 18")
    assert len(results) == 1
    assert results[0]["price"] == 190.0
    assert results[0]["product_url"].endswith("/en/product/x/1.html")
