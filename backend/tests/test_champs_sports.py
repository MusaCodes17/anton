"""
Champs Sports Canada scraper rules (Foot Locker SSR storefront).

Pure helpers plus one tiny markup snippet per price shape. No full-page HTML
fixtures (CLAUDE.md §10: retailer DOMs are verified live via the dry-run). The rules:
  - whole-word model matching, numbers included, brand verified from the name;
  - women's listings never match a men's watch;
  - sale blocks read as (current, original) whatever the markup order;
  - the bespoke registration takes the retailer out of the onboarding queue.
"""
from bs4 import BeautifulSoup

from app.models.models import Retailer
from app.scrapers.champs_sports import ChampsSportsScraper, _price_pair, name_matches
from app.scrapers.registry import BESPOKE_SCRAPERS
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
