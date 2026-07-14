"""
Generic Shopify scraper.

Most Canadian shoe retailers (JD Sports, Altitude Sports, etc.) run on Shopify,
which exposes clean JSON endpoints that are far more reliable than scraping
rendered HTML with CSS selectors:

    GET /search/suggest.json?q=<query>&resources[type]=product   -> search results
    GET /products/<handle>.js                                    -> full product + variants

This base class implements search/detail against those endpoints. Retailer
subclasses just supply a name + base_url (see jd_sports.py).
"""
import json
import logging
import re
from typing import List, Dict, Optional
from urllib.parse import quote, urlsplit

from app.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ShopifyScraper(BaseScraper):
    """Scraper for any Shopify-backed storefront."""

    def _get_json(self, url: str) -> Optional[dict]:
        """Fetch a URL and parse it as JSON (Shopify JSON endpoints)."""
        raw = self.fetch_page(url, use_browser=False)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError) as e:
            logger.warning(f"[{self.retailer_name}] Non-JSON response from {url}: {e}")
            return None

    def _handle_from_url(self, product_url: str) -> Optional[str]:
        """Extract the Shopify product handle from a product URL."""
        path = urlsplit(product_url).path
        if '/products/' not in path:
            return None
        handle = path.split('/products/', 1)[1].strip('/')
        # Drop any trailing .js / .json and sub-paths.
        handle = handle.split('/')[0]
        for suffix in ('.js', '.json'):
            if handle.endswith(suffix):
                handle = handle[: -len(suffix)]
        return handle or None

    @staticmethod
    def _matches(title: str, brand: str, model: str) -> bool:
        """True if every significant token of the model appears in the title."""
        title_l = title.lower()
        tokens = [t for t in model.lower().split() if t]
        if not tokens:
            return brand.lower() in title_l
        return all(t in title_l for t in tokens)

    def search_products(self, brand: str, model: str) -> List[Dict]:
        query = f"{brand} {model}".strip()
        url = (
            f"{self.base_url}/search/suggest.json?q={quote(query)}"
            f"&resources[type]=product&resources[limit]=10"
        )
        logger.info(f"[{self.retailer_name}] Searching Shopify: {url}")

        data = self._get_json(url)
        if not data:
            logger.warning(f"[{self.retailer_name}] No search results for '{query}'")
            return []

        try:
            products = data['resources']['results']['products']
        except (KeyError, TypeError):
            logger.warning(f"[{self.retailer_name}] Unexpected suggest.json shape")
            return []

        results = []
        for p in products:
            title = p.get('title', '')
            if not self._matches(title, brand, model):
                continue

            handle = p.get('handle') or self._handle_from_url(p.get('url', ''))
            if not handle:
                continue

            clean_url = f"{self.base_url}/products/{handle}"
            featured = p.get('featured_image')
            featured_url = featured.get('url') if isinstance(featured, dict) else None
            results.append({
                'product_url': clean_url,
                'name': title,
                'price': self.parse_price(str(p.get('price'))),
                'original_price': self.parse_price(str(p.get('compare_at_price_max'))),
                'in_stock': bool(p.get('available', False)),  # pessimistic until detail fetch
                'sizes_available': [],  # filled in by get_product_details
                'image_url': self._norm_url(p.get('image') or featured_url),
                'colorway': self._colorway_from_title(title, brand, model),
            })

        self.log_scrape_attempt(brand, model, len(results))
        return results

    def get_product_details(self, product_url: str) -> Optional[Dict]:
        handle = self._handle_from_url(product_url)
        if not handle:
            logger.warning(f"[{self.retailer_name}] Could not parse handle from {product_url}")
            return None

        url = f"{self.base_url}/products/{handle}.js"
        data = self._get_json(url)
        if not data:
            return None

        # Locate the "Size" option by name so we read the right variant option
        # (products may also have Color/Width options, e.g. "1005 / 6.0 / B").
        size_pos = None
        for opt in data.get('options', []):
            if isinstance(opt, dict) and (opt.get('name') or '').strip().lower() in (
                'size', 'taille', 'pointure', 'shoe size'
            ):
                size_pos = opt.get('position')
                break

        # Derive price and original_price from available variants only.
        # The product-level 'price' field is the min across ALL variants including
        # sold-out ones — reading it would create phantom deals for sold-out sale
        # colorways (e.g. $150 sold-out colorway makes the product appear at $150
        # even though every in-stock colorway is $300 full price).
        sizes_available = []
        available_prices = []
        for v in data.get('variants', []):
            vp = v.get('price')
            vc = v.get('compare_at_price')
            vp_dollars = round(vp / 100.0, 2) if isinstance(vp, (int, float)) else None
            vc_dollars = round(vc / 100.0, 2) if isinstance(vc, (int, float)) and vc else None
            if v.get('available') and vp_dollars is not None:
                available_prices.append((vp_dollars, vc_dollars))
            if not v.get('available'):
                continue
            if size_pos:
                label = v.get(f'option{size_pos}') or ''
            else:
                label = (v.get('title') or '').split('/')[-1].strip()
            size = self.extract_numeric_size(label)
            if size and size not in sizes_available:
                sizes_available.append(size)

        if available_prices:
            # Prefer the cheapest available variant that has a real markdown;
            # fall back to the cheapest available full-price variant.
            sale_variants = [(p, c) for p, c in available_prices if c is not None and c > p]
            if sale_variants:
                price, original_price = min(sale_variants, key=lambda x: x[0])
            else:
                price = min(p for p, _ in available_prices)
                original_price = None
        else:
            price = None
            original_price = None

        return {
            'product_url': f"{self.base_url}/products/{handle}",
            'name': data.get('title', ''),
            'brand': data.get('vendor', ''),
            'price': price,
            'original_price': original_price,
            'in_stock': bool(data.get('available', False)),
            'sizes_available': sorted(sizes_available, key=lambda x: float(x) if x else 0),
            'image_url': self._norm_url(data.get('featured_image')),
            'colorway': self._color_from_options(data),
        }

    @staticmethod
    def _norm_url(url: Optional[str]) -> Optional[str]:
        """Shopify often returns protocol-relative URLs ('//cdn.shopify.com/...')."""
        if not url or not isinstance(url, str):
            return None
        return f"https:{url}" if url.startswith("//") else url

    @staticmethod
    def _color_from_options(data: Dict) -> Optional[str]:
        """Extract the colorway from a product's Color/Colour option values."""
        for opt in data.get('options', []):
            if isinstance(opt, dict) and (opt.get('name') or '').lower() in ('color', 'colour'):
                values = [str(v) for v in (opt.get('values') or []) if v]
                if values:
                    return ", ".join(values)
        return None

    def _colorway_from_title(self, title: str, brand: str, model: str) -> Optional[str]:
        """
        Best-effort colorway from a product title by removing the brand + model
        tokens (Shopify stores the colorway in the title, e.g.
        "adidas Adizero Boston 13 Black / White - Grey" -> "Black / White - Grey").
        """
        if not title:
            return None
        remainder = title
        for token in (brand.split() + model.split()):
            remainder = re.sub(rf'(?i)\b{re.escape(token)}\b', '', remainder)
        remainder = re.sub(r'\s{2,}', ' ', remainder).strip(' -/|,')
        return remainder or None
