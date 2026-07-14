"""
Tests for D7: kids/junior shoe filter and youth-size exclusion.

D7a — composite kids filter (BaseScraper.is_kids_shoe + search_products_filtered):
  - Listings whose kids-ness lives only in the product URL handle are caught even
    when the title looks adult (Shopify handle pattern).
  - Listings with an adult-looking name AND adult-looking URL pass through.

D7b — youth-size exclusion (ShopifyScraper._is_youth_size + get_product_details):
  - Variants with Y/C-suffix labels (e.g. "6Y", "4.5C") are excluded from both
    sizes_available and the price pool.
  - A product whose ONLY available variants are youth sizes produces price=None
    (so record_price skips it and no deal is created).
  - Adult variants on the same product are unaffected.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.scrapers.base_scraper import BaseScraper
from app.scrapers.shopify_scraper import ShopifyScraper


# ── D7a: composite kids filter ────────────────────────────────────────────────

@pytest.mark.parametrize("texts,expected", [
    # Kids keyword in name only — caught.
    (["Nike Air Max Kids", None], True),
    # Kids keyword in URL only — caught (D7a fix).
    ([None, "https://jdsports.ca/products/adidas-ultraboost-kids"], True),
    # Kids keyword in neither — passes through.
    (["Nike Air Max 90", "https://jdsports.ca/products/nike-air-max-90"], False),
    # "Grade School" in name — caught.
    (["Nike Revolution Grade School", None], True),
    # "GS" token in name — caught.
    (["Air Force 1 (GS)", None], True),
    # "youth" in URL path — caught.
    ([None, "https://example.com/products/new-balance-fresh-foam-youth"], True),
    # "Junior" in name — caught.
    (["Asics GT-2000 Junior", None], True),
    # Plural "juniors" in a JD Sports URL slug — caught (D7 plural gap, 2026-07-14).
    ([None, "https://jdsports.ca/products/adidas-juniors-adizero-evo-sl-dash-grey"], True),
    ([None, "https://jdsports.ca/products/nike-juniors-pegasus-42-white-black"], True),
    # Plural "kids" possessive-ish slug still caught.
    ([None, "https://jdsports.ca/products/nike-juniors-pegasus"], True),
    # "juniorx" (no boundary, s? must not over-match into an unrelated token) — passes.
    (["Adizero Juniorx Edition", None], False),
    # Adult name + adult URL — passes.
    (["adidas Adizero Boston 13", "https://jdsports.ca/products/adidas-adizero-boston-13"], False),
    # Empty strings treated as absent.
    (["", ""], False),
    # None values treated as absent.
    ([None, None], False),
])
def test_is_kids_shoe_composite(texts, expected):
    assert BaseScraper.is_kids_shoe(*texts) is expected


class _StubShopifyScraper(ShopifyScraper):
    """ShopifyScraper subclass that intercepts _get_json to return fixture data."""

    def __init__(self, products_fixture, details_fixture=None):
        super().__init__(retailer_name="TestShop", base_url="https://test.example")
        self._products_fixture = products_fixture
        self._details_fixture = details_fixture

    def search_products(self, brand, model):
        return list(self._products_fixture)

    def _get_json(self, url):
        return self._details_fixture


def test_search_products_filtered_catches_kids_in_url():
    """D7a: a result whose kids-ness is only in the URL must be filtered out."""
    fixture = [
        {"product_url": "https://test.example/products/nike-zoom-fly-kids", "name": "Nike Zoom Fly 5"},
        {"product_url": "https://test.example/products/nike-zoom-fly-5", "name": "Nike Zoom Fly 5"},
    ]
    scraper = _StubShopifyScraper(fixture)
    results = scraper.search_products_filtered("Nike", "Zoom Fly 5")

    assert len(results) == 1
    assert results[0]["product_url"] == "https://test.example/products/nike-zoom-fly-5"


def test_search_products_filtered_passes_adult_listing():
    """D7a: a listing with adult name and adult URL must not be filtered."""
    fixture = [
        {"product_url": "https://test.example/products/adidas-adizero-boston-13", "name": "adidas Adizero Boston 13"},
    ]
    scraper = _StubShopifyScraper(fixture)
    results = scraper.search_products_filtered("adidas", "Adizero Boston 13")

    assert len(results) == 1


# ── D7b: youth-size exclusion ────────────────────────────────────────────────

@pytest.mark.parametrize("label,expected", [
    ("6Y", True),
    ("4.5Y", True),
    ("10y", True),       # case-insensitive
    ("6C", True),
    ("4.5C", True),
    ("8c", True),        # lowercase C
    ("10", False),       # plain adult size
    ("10.5", False),
    ("11 US", False),    # no Y/C suffix
    ("", False),
    ("Color: Black", False),  # must not false-positive on leading digit
])
def test_is_youth_size(label, expected):
    assert ShopifyScraper._is_youth_size(label) is expected


def _make_product_data(variants):
    """Helper: build a minimal Shopify .js product dict."""
    return {
        "title": "Nike Vaporfly 3",
        "vendor": "Nike",
        "available": True,
        "featured_image": None,
        "options": [{"name": "Size", "position": 1, "values": []}],
        "variants": variants,
    }


def _variant(label, price_cents, compare_cents=None, available=True):
    return {
        "option1": label,
        "price": price_cents,
        "compare_at_price": compare_cents,
        "available": available,
    }


def test_youth_sizes_excluded_from_sizes_available():
    """D7b: Y-suffix variants must not appear in sizes_available."""
    scraper = _StubShopifyScraper(
        products_fixture=[],
        details_fixture=_make_product_data([
            _variant("8", 17000),
            _variant("9", 17000),
            _variant("6Y", 8900),   # youth — must be excluded
            _variant("4.5Y", 7900), # youth — must be excluded
        ]),
    )
    details = scraper.get_product_details("https://test.example/products/nike-vaporfly-3")
    assert details is not None
    assert "6" not in details["sizes_available"]   # stripped "6Y" must not appear
    assert "4.5" not in details["sizes_available"]
    assert "8" in details["sizes_available"]
    assert "9" in details["sizes_available"]


def test_youth_only_product_has_no_price():
    """D7b: a product whose only available variants are youth sizes must return
    price=None so record_price skips it and no deal is created."""
    scraper = _StubShopifyScraper(
        products_fixture=[],
        details_fixture=_make_product_data([
            _variant("6Y", 8900),
            _variant("4.5Y", 7900),
        ]),
    )
    details = scraper.get_product_details("https://test.example/products/nike-vaporfly-3")
    assert details is not None
    assert details["price"] is None
    assert details["sizes_available"] == []


def test_youth_variant_price_does_not_set_adult_deal_price():
    """D7b: cheapest available variant is a youth size — price must reflect
    the adult variant, not the cheaper youth one."""
    scraper = _StubShopifyScraper(
        products_fixture=[],
        details_fixture=_make_product_data([
            _variant("10", 17000),   # adult, $170
            _variant("5Y", 8900),    # youth, $89 — must be excluded from price pool
        ]),
    )
    details = scraper.get_product_details("https://test.example/products/nike-vaporfly-3")
    assert details is not None
    # Price must be the adult-size price, not the youth-size bargain.
    assert details["price"] == 170.00
    assert "5" not in details["sizes_available"]
    assert "10" in details["sizes_available"]
