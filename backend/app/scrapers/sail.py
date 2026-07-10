"""
SAIL scraper — SearchSpring-based API.

SAIL (sail.ca) runs on Magento 2 with SearchSpring as the search/catalogue
layer. The public SearchSpring API (site ID s8zq1c, no auth required) returns
price, MSRP, stock status, and absolute product URLs in a single JSON request
— no browser, no CSS selector fragility.
"""
import logging
import re
import time
from typing import Dict, List, Optional

from app.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

_SS_URL = "https://api.searchspring.net/api/search/search.json"
_SAIL_SITE_ID = "s8zq1c"

# Trailing numeric SKU appended to SAIL URL slugs: /en/<words>-<id>
_TRAILING_SKU_RE = re.compile(r'-\d+$')


class SailScraper(BaseScraper):
    """Scraper for SAIL (sail.ca) via the public SearchSpring search API."""

    def __init__(self):
        super().__init__(
            retailer_name="SAIL",
            base_url="https://www.sail.ca/en/",
            config={"use_browser": False},
        )

    # ----- SearchSpring plumbing -----------------------------------------------

    def _ss_query(self, query: str, page_size: int = 20) -> List[Dict]:
        """Query the SearchSpring API; returns the results list (empty on failure)."""
        params = {
            "siteId": _SAIL_SITE_ID,
            "q": query,
            "resultsFormat": "native",
            "pageSize": page_size,
        }
        try:
            resp = self.session.get(_SS_URL, params=params, timeout=15)
            resp.raise_for_status()
            time.sleep(1)
            return resp.json().get("results", [])
        except Exception as e:
            logger.error(f"[{self.retailer_name}] SearchSpring query failed for '{query}': {e}")
            return []

    # ----- Result parsing ------------------------------------------------------

    @staticmethod
    def _to_float(value: Optional[str]) -> Optional[float]:
        try:
            return round(float(value), 2) if value else None
        except (TypeError, ValueError):
            return None

    def _parse_result(self, result: Dict) -> Optional[Dict]:
        url = result.get("url")
        if not url:
            return None
        return {
            "product_url": url,
            "name": result.get("name", ""),
            "brand": result.get("brand", ""),
            "price": self._to_float(result.get("price")),
            "original_price": self._to_float(result.get("msrp") or result.get("regular_price")),
            "in_stock": result.get("saleable") == "1",
            "sizes_available": [],
            "image_url": result.get("imageUrl"),
        }

    @staticmethod
    def _matches(name: str, brand: str, model: str) -> bool:
        """True if every significant token of the model appears in the product name."""
        name_l = name.lower()
        tokens = [t for t in model.lower().split() if t]
        if not tokens:
            return brand.lower() in name_l
        return all(t in name_l for t in tokens)

    # ----- Public API ----------------------------------------------------------

    def search_products(self, brand: str, model: str) -> List[Dict]:
        """Search SAIL's SearchSpring index for products matching brand + model."""
        logger.info(f"[{self.retailer_name}] Searching for {brand} {model}")
        results = self._ss_query(f"{brand} {model}")
        parsed = []
        for r in results:
            if not self._matches(r.get("name", ""), brand, model):
                continue
            p = self._parse_result(r)
            if p and not any(x["product_url"] == p["product_url"] for x in parsed):
                parsed.append(p)
        self.log_scrape_attempt(brand, model, len(parsed))
        return parsed

    def get_product_details(self, product_url: str) -> Optional[Dict]:
        """
        Refresh a single product by re-querying with the URL slug as search terms.

        SearchSpring has no single-product lookup by URL; we search with the
        slug words (minus the trailing numeric SKU) and match by exact URL.
        """
        slug = product_url.rstrip("/").split("/")[-1]
        query = _TRAILING_SKU_RE.sub("", slug).replace("-", " ")
        for r in self._ss_query(query):
            if r.get("url") == product_url:
                return self._parse_result(r)
        logger.info(f"[{self.retailer_name}] No exact URL match for {product_url}")
        return None
