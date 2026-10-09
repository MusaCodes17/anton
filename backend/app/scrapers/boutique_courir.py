"""
Boutique Courir scraper (boutiquecourir.com)

Independent Quebec running shop on WordPress + WooCommerce (LiteSpeed, no bot
wall). Probed 2026-10-09 (roadmap R7.3 follow-up):

- The WooCommerce Store API is deliberately closed to anonymous callers
  (`/wp-json/wc/store/v1/products` → 401 rest_not_logged_in), so this reads
  the server-rendered HTML instead. robots.txt allows product search
  (it only disallows add-to-cart, plugins and readme paths).
- Search (`/?s=<q>&post_type=product`) is WordPress full-text search: titles
  carry no brand ("Novablast 5 • H", "GEL-Nimbus 27 • F") and numeric terms
  can make it return nothing ("Clifton 10" → 0 results, "Clifton" → both).
  So we search on the model's word tokens only and match locally, requiring
  every model token — numbers included — as a whole word in the title.
  Brand isn't verifiable on the page (heuristic: running-shoe model names
  rarely collide across brands); results are limited to shoe categories so
  laces or accessories can't match.
- Prices are French-formatted ("189,99 $", "1 299,99 $"). BaseScraper's
  parse_price strips commas and would read 18999 — use _parse_fr_price.
- Product pages carry schema.org JSON-LD (current price, availability, image).
  Shoes are listed without sizes (no variations form at probe time), so
  sizes_available is usually []; deals then show size as "unknown" (R6.3).
  A variations form, if one ever appears, is parsed the standard WooCommerce way.
- No product was on sale at probe time (0 of 131 running shoes); expect
  mostly price history, with deals only during promotions.
"""
import html as ihtml
import json
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

MAX_SEARCH_PAGES = 3  # a model search is rarely past page 1 (24/page); bound it anyway

_IN_STOCK = ("InStock", "LimitedAvailability", "OnlineOnly")


def _parse_fr_price(text: Optional[str]) -> Optional[float]:
    """'189,99 $' → 189.99; '1 299,99 $' → 1299.99 (space/nbsp thousands)."""
    if not text:
        return None
    cleaned = re.sub(r"[\s  $]|CAD", "", text)
    m = re.search(r"\d+(?:,\d{1,2})?", cleaned)
    return float(m.group(0).replace(",", ".")) if m else None


def _tokens(text: str) -> List[str]:
    """Lower-cased word tokens; hyphens split ('GEL-Nimbus' → gel, nimbus)."""
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower().replace("-", " "))


def title_matches(title: str, model: str) -> bool:
    """Every token of `model` appears as a whole word in `title`, so
    'Clifton 1' doesn't match 'Clifton 10'."""
    wanted = _tokens(model)
    have = set(_tokens(title))
    return bool(wanted) and all(t in have for t in wanted)


class BoutiqueCourirScraper(BaseScraper):
    """Scraper for Boutique Courir (boutiquecourir.com) — WooCommerce HTML."""

    def __init__(self):
        super().__init__(
            retailer_name="Boutique Courir",
            base_url="https://boutiquecourir.com",
            config={"use_browser": False},
        )

    # ----- search --------------------------------------------------------------

    @staticmethod
    def _search_query(model: str) -> str:
        """Word tokens of the model without the numbers WordPress search trips on."""
        words = [t for t in _tokens(model) if not t[0].isdigit()]
        return " ".join(words) or model

    def _parse_tiles(self, html_text: str, model: str) -> List[Dict]:
        soup = BeautifulSoup(html_text, "html.parser")
        results = []
        for tile in soup.select("li.product"):
            classes = " ".join(tile.get("class") or [])
            if "chaussure" not in classes:  # shoe categories only
                continue
            title_el = tile.select_one(".woocommerce-loop-product__title")
            link = tile.select_one("a[href]")
            if not (title_el and link):
                continue
            title = title_el.get_text(strip=True)
            if not title_matches(title, model):
                continue
            regular = tile.select_one(".price del .amount")
            current = tile.select_one(".price ins .amount") or tile.select_one(".price .amount")
            img = tile.select_one("img")
            results.append({
                "product_url": link["href"],
                "name": title,
                "price": _parse_fr_price(current.get_text() if current else None),
                "original_price": _parse_fr_price(regular.get_text()) if regular else None,
                "in_stock": "outofstock" not in classes,
                "sizes_available": [],  # filled in by get_product_details
                "image_url": img.get("src") if img else None,
                "colorway": None,
            })
        return results

    def search_products(self, brand: str, model: str) -> List[Dict]:
        query = self._search_query(model)
        results: List[Dict] = []
        seen = set()
        for page in range(1, MAX_SEARCH_PAGES + 1):
            path = "/" if page == 1 else f"/page/{page}/"
            url = f"{self.base_url}{path}?s={query.replace(' ', '+')}&post_type=product"
            logger.info(f"[{self.retailer_name}] Searching: {url}")
            html_text = self.fetch_page(url, use_browser=False)
            if not html_text:
                break
            for r in self._parse_tiles(html_text, model):
                if r["product_url"] not in seen:
                    seen.add(r["product_url"])
                    results.append(r)
            if 'class="next page-numbers"' not in html_text:
                break
        self.log_scrape_attempt(brand, model, len(results))
        return results

    # ----- product page --------------------------------------------------------

    @staticmethod
    def _json_ld_product(soup: BeautifulSoup) -> Optional[Dict]:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
            except (TypeError, json.JSONDecodeError):
                continue
            nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
            for node in nodes or []:
                if isinstance(node, dict) and node.get("@type") == "Product":
                    return node
        return None

    def _variations(self, soup: BeautifulSoup) -> List[Dict]:
        """Standard WooCommerce variable-product data, if the page has any."""
        form = soup.select_one("form.variations_form")
        raw = form.get("data-product_variations") if form else None
        if not raw or raw == "false":
            return []
        try:
            return json.loads(ihtml.unescape(raw))
        except json.JSONDecodeError:
            return []

    def get_product_details(self, product_url: str) -> Optional[Dict]:
        html_text = self.fetch_page(product_url, use_browser=False)
        if not html_text:
            return None
        soup = BeautifulSoup(html_text, "html.parser")
        node = self._json_ld_product(soup)
        if node is None:
            logger.warning(f"[{self.retailer_name}] No Product JSON-LD on {product_url}")
            return None

        offers = node.get("offers") or []
        offer = offers[0] if isinstance(offers, list) and offers else (offers if isinstance(offers, dict) else {})
        try:
            price = float(offer.get("price")) if offer.get("price") is not None else None
        except (TypeError, ValueError):
            price = None
        in_stock = str(offer.get("availability", "")).rsplit("/", 1)[-1] in _IN_STOCK

        regular_el = soup.select_one(".summary .price del .amount, p.price del .amount")
        regular = _parse_fr_price(regular_el.get_text()) if regular_el else None
        original_price = regular if regular and price and regular > price else None

        sizes: List[str] = []
        variations = self._variations(soup)
        if variations:
            available = [v for v in variations if v.get("is_in_stock")]
            in_stock = bool(available)
            if available:
                cheapest = min(available, key=lambda v: v.get("display_price") or 0)
                price = cheapest.get("display_price") or price
                reg = cheapest.get("display_regular_price")
                original_price = reg if reg and price and reg > price else None
            for v in available:
                for key, value in (v.get("attributes") or {}).items():
                    if any(k in key for k in ("pointure", "taille", "size")):
                        size = self.extract_numeric_size(str(value).replace("-", "."))
                        if size and size not in sizes:
                            sizes.append(size)

        image = node.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("url")

        return {
            "product_url": product_url,
            "name": node.get("name") or "",
            "brand": "",
            "price": price,
            "original_price": original_price,
            "in_stock": in_stock,
            "sizes_available": sorted(sizes, key=float),
            "image_url": urljoin(self.base_url, image) if image else None,
            "colorway": None,
        }
