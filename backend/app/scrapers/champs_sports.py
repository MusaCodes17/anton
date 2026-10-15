"""
Champs Sports Canada scraper (champssports.ca)

Foot Locker's Canadian banner. Probed 2026-10-15 (S05 add-retailer):

- Not Shopify (`/products.json` returns the HTML storefront) and not Algolia,
  so this is a bespoke scraper keyed by name in `registry.BESPOKE_SCRAPERS`.
- Search (`/en/search?query=<q>`) is server-rendered: each result is a
  `[data-testid=ProductCardV3]` carrying the name (in `data-productcard` JSON),
  the URL and the price. No XHR, no browser needed.
- robots.txt disallows `*currentPage=*`, so pagination is off-limits; we read
  page 1 only. Queries for a specific model ("Pegasus 42") fill page 1 with
  the model's colourways, and matching is local, so a broad query just yields
  more candidates to filter.
- Prices: a `data-testid=Sale` block holds the sale and the original price as
  two plain `$` spans; a regular listing holds one. We take the lower value as
  the current price and the higher as the original, so the order in the markup
  does not matter.
- Product pages carry a `ProductGroup` JSON-LD (`#productLdJson`) whose
  `hasVariant` entries are colourways with an `offers.price` and availability.
  Sizes are not in the JSON-LD; they are the `Size: X` buttons inside
  `ProductDetailsSizesV3`. Disabled size buttons are treated as sold out.
- A Queue-it waiting room script is on every page. We saw no queue at probe
  time. If one ever intercepts a request, the search returns no tiles and the
  scrape records zero results rather than a stale or invented price.
"""
import json
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from app.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# A money span's whole text: "$180.00", "$1,299.99", "C$180". Anchored so that
# the screen-reader sentence ("Price dropped from $270.00 to $189.99") is not
# mistaken for a price.
_MONEY_RE = re.compile(r"^C?\$\s?[\d,]+(?:\.\d{2})?$")
_SIZE_LABEL_PREFIX = "Size: "
_SIZE_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_OUT_OF_STOCK_RE = re.compile(r"out of stock|sold out", re.IGNORECASE)


def _tokens(text: str) -> List[str]:
    """Lower-cased word tokens; hyphens split ('Gel-Nimbus' -> gel, nimbus)."""
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", (text or "").lower().replace("-", " "))


def name_matches(name: str, brand: str, model: str) -> bool:
    """Every brand and model token appears as a whole word in the listing name.

    Whole-word, numbers included, so 'Pegasus 4' does not match 'Pegasus 42'.
    Champs listing names carry the brand ("Nike Air Zoom Pegasus 42 - Men's"),
    so the brand is verifiable here, unlike on some WordPress stores.

    Women's listings are excluded unless the watched model itself says women:
    a women's price is not a men's deal (different last, different size scale),
    and the deals engine would otherwise read it as the cheapest offer.
    """
    wanted = _tokens(brand) + _tokens(model)
    have = set(_tokens(name))
    if "women" in have and "women" not in wanted:
        return False
    return bool(wanted) and all(t in have for t in wanted)


def _money_values(scope) -> List[float]:
    """Every `$` amount rendered as a standalone span under `scope`, in order."""
    values = []
    for span in scope.find_all("span"):
        text = span.get_text(strip=True)
        if _MONEY_RE.match(text):
            values.append(float(text.replace("C", "").replace("$", "").replace(",", "").strip()))
    return values


def _price_pair(block) -> tuple[Optional[float], Optional[float]]:
    """(current, original) from a ProductPrice block; original is None unless discounted.

    Sale blocks hold two amounts (sale and original). Taking min/max keeps this
    independent of which one the markup lists first.
    """
    if block is None:
        return None, None
    sale = block.select_one('[data-testid="Sale"]')
    values = _money_values(sale or block)
    if not values:
        return None, None
    current, high = min(values), max(values)
    return current, (high if high > current else None)


class ChampsSportsScraper(BaseScraper):
    """Scraper for Champs Sports Canada (champssports.ca) — Foot Locker SSR storefront."""

    def __init__(self):
        super().__init__(
            retailer_name="Champs Sports Canada",
            base_url="https://www.champssports.ca",
            config={"use_browser": False},
        )

    # ----- search --------------------------------------------------------------

    def _parse_cards(self, html_text: str, brand: str, model: str) -> List[Dict]:
        soup = BeautifulSoup(html_text, "html.parser")
        results = []
        for card in soup.select('[data-testid="ProductCardV3"]'):
            link = card.select_one("a[data-productcard]")
            if link is None or not link.get("href"):
                continue
            try:
                meta = json.loads(link["data-productcard"])
            except (TypeError, json.JSONDecodeError):
                continue
            name = meta.get("name") or ""
            if not name_matches(name, brand, model):
                continue
            current, original = _price_pair(card.select_one('[data-testid="ProductPrice"]'))
            if current is None:
                continue
            img = card.select_one("img")
            results.append({
                "product_url": urljoin(self.base_url, link["href"]),
                "name": name,
                "price": current,
                "original_price": original,
                "in_stock": not _OUT_OF_STOCK_RE.search(card.get_text(" ", strip=True)),
                "sizes_available": [],  # filled in by get_product_details
                "image_url": img.get("src") if img else None,
                "colorway": None,
            })
        return results

    def search_products(self, brand: str, model: str) -> List[Dict]:
        query = " ".join(_tokens(model)) or model
        url = f"{self.base_url}/en/search?query={quote_plus(query)}"
        logger.info(f"[{self.retailer_name}] Searching: {url}")
        html_text = self.fetch_page(url, use_browser=False)
        results = self._parse_cards(html_text, brand, model) if html_text else []
        self.log_scrape_attempt(brand, model, len(results))
        return results

    # ----- product page --------------------------------------------------------

    @staticmethod
    def _product_ld(soup: BeautifulSoup) -> Optional[Dict]:
        script = soup.select_one('script#productLdJson')
        if script is None:
            return None
        try:
            data = json.loads(script.string or "")
        except (TypeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _chosen_variant(variants: List[Dict], url_sku: Optional[str]) -> Optional[Dict]:
        """The colourway whose SKU is in the URL, else the cheapest in-stock one."""
        if not variants:
            return None
        if url_sku:
            for v in variants:
                if str(v.get("sku")) == url_sku:
                    return v
        in_stock = [v for v in variants if "InStock" in str((v.get("offers") or {}).get("availability", ""))]
        pool = in_stock or variants
        return min(pool, key=lambda v: float((v.get("offers") or {}).get("price") or 0))

    @staticmethod
    def _sizes(soup: BeautifulSoup) -> List[str]:
        """Sizes with an enabled button. Disabled buttons are sold out, not absent."""
        panel = soup.select_one('[data-testid="ProductDetailsSizesV3"]')
        if panel is None:
            return []
        sizes: List[str] = []
        for btn in panel.select('[data-testid="CTAButton"][aria-label^="Size: "]'):
            if btn.has_attr("disabled"):
                continue
            label = btn["aria-label"][len(_SIZE_LABEL_PREFIX):]
            m = _SIZE_NUMBER_RE.search(label)
            if m and m.group(0) not in sizes:
                sizes.append(m.group(0))
        return sorted(sizes, key=float)

    def get_product_details(self, product_url: str) -> Optional[Dict]:
        html_text = self.fetch_page(product_url, use_browser=False)
        if not html_text:
            return None
        soup = BeautifulSoup(html_text, "html.parser")
        ld = self._product_ld(soup)
        if ld is None:
            logger.warning(f"[{self.retailer_name}] No productLdJson on {product_url}")
            return None

        url_sku_match = re.search(r"/(\d+)\.html", product_url)
        variant = self._chosen_variant(ld.get("hasVariant") or [], url_sku_match.group(1) if url_sku_match else None)
        offers = (variant or {}).get("offers") or {}

        # The rendered price block is what a shopper sees; prefer it over the
        # JSON-LD offer, which can lag a sale.
        price, original_price = _price_pair(soup.select_one('[data-testid="ProductPrice"]'))
        if price is None:
            try:
                price = float(offers.get("price")) if offers.get("price") is not None else None
            except (TypeError, ValueError):
                price = None

        sizes = self._sizes(soup)
        if soup.select_one('[data-testid="ProductDetailsSizesV3"]') is not None:
            in_stock = bool(sizes)
        else:
            in_stock = "InStock" in str(offers.get("availability", ""))

        image = ld.get("image")
        if isinstance(image, list):
            image = image[0] if image else None

        return {
            "product_url": product_url,
            "name": ld.get("name") or "",
            "brand": ((ld.get("brand") or {}).get("name") if isinstance(ld.get("brand"), dict) else "") or "",
            "price": price,
            "original_price": original_price,
            "in_stock": in_stock,
            "sizes_available": sizes,
            "image_url": image,
            "colorway": (variant or {}).get("color"),
        }
