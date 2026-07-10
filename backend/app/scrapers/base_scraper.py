"""
Base scraper class with common functionality for all retailers
"""
import time
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Browser, Page
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Abstract base class for all retailer scrapers
    
    Provides common functionality:
    - HTTP requests with retries
    - Browser automation with Playwright
    - Rate limiting
    - Error handling
    - Price parsing
    """
    
    # Keywords (case-insensitive) that mark a listing as a kids/junior shoe.
    # Short/ambiguous ones (jr, gs, ps, td) are bounded by \b on both sides
    # so they only match as standalone tokens (e.g. "Jr." or "(GS)" or
    # "- GS"), never as a substring inside an unrelated model name/code.
    _KIDS_SHOE_KEYWORDS = (
        "junior", "jr", "kids", "kid", "grade school", "gs", "preschool",
        "ps", "toddler", "td", "infant", "youth", "children", "child",
        "little kids", "big kids",
    )
    _KIDS_SHOE_RE = re.compile(
        r'\b(?:' + '|'.join(re.escape(k) for k in _KIDS_SHOE_KEYWORDS) + r')\b',
        re.IGNORECASE,
    )

    @classmethod
    def is_kids_shoe(cls, text: Optional[str]) -> bool:
        """True if a product name/title/URL looks like a kids/junior listing."""
        if not text:
            return False
        return bool(cls._KIDS_SHOE_RE.search(text))

    def search_products_filtered(self, brand: str, model: str) -> List[Dict]:
        """
        Wraps the abstract search_products() with a kids/junior-shoe filter.
        Defined once, here, so every scraper subclass — existing and any
        added later — gets it automatically without having to remember to
        filter itself. Callers that persist results to the database
        (ScrapeOrchestrator) should call this instead of search_products()
        directly; dry-run/test paths may use either.
        """
        results = self.search_products(brand, model)
        filtered = [r for r in results if not self.is_kids_shoe(r.get('name'))]
        skipped = len(results) - len(filtered)
        if skipped:
            logger.info(
                f"[{self.retailer_name}] Filtered out {skipped} kids/junior shoe result(s) "
                f"for '{brand} {model}'"
            )
        return filtered

    def __init__(self, retailer_name: str, base_url: str, config: dict = None):
        self.retailer_name = retailer_name
        self.base_url = base_url
        self.config = config or {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
    def fetch_page(self, url: str, use_browser: bool = False) -> Optional[str]:
        """
        Fetch page content using requests or Playwright
        
        Args:
            url: URL to fetch
            use_browser: Whether to use headless browser (for JS-heavy sites)
            
        Returns:
            HTML content or None if failed
        """
        try:
            if use_browser:
                return self._fetch_with_browser(url)
            else:
                return self._fetch_with_requests(url)
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    # Retry budget for transient HTTP failures (R4.2).
    # _RETRY_ATTEMPTS is the number of *additional* attempts after the first.
    # _RETRY_DELAY_S is the wait between attempts — also serves as politeness.
    _RETRY_ATTEMPTS = 2
    _RETRY_DELAY_S = 2

    def _fetch_with_requests(self, url: str) -> Optional[str]:
        """
        Fetch page using requests library, with up to _RETRY_ATTEMPTS retries
        on transient RequestException (timeout, connection reset, 5xx).

        Rate-limit sleep (2 s) is placed after a successful response; retries
        wait _RETRY_DELAY_S before the next attempt so we don't hammer a site
        that is momentarily overloaded.
        """
        last_exc = None
        for attempt in range(self._RETRY_ATTEMPTS + 1):
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                time.sleep(2)  # be polite after every successful fetch
                return response.text
            except requests.RequestException as e:
                last_exc = e
                if attempt < self._RETRY_ATTEMPTS:
                    logger.warning(
                        f"[{self.retailer_name}] Fetch attempt {attempt + 1} failed "
                        f"for {url}: {e}; retrying in {self._RETRY_DELAY_S}s"
                    )
                    time.sleep(self._RETRY_DELAY_S)
        logger.error(f"[{self.retailer_name}] Request error for {url} after "
                     f"{self._RETRY_ATTEMPTS + 1} attempts: {last_exc}")
        return None
    
    def _fetch_with_browser(self, url: str) -> Optional[str]:
        """Fetch page using Playwright (for JavaScript-heavy sites)"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until='networkidle')
                
                # Wait a bit for dynamic content
                page.wait_for_timeout(2000)
                
                content = page.content()
                browser.close()
                
                # Rate limiting
                time.sleep(3)
                
                return content
        except Exception as e:
            logger.error(f"Browser error for {url}: {e}")
            return None
    
    def parse_price(self, price_text: str) -> Optional[float]:
        """
        Extract numeric price from text
        
        Examples:
            "$199.99" -> 199.99
            "C$249.50" -> 249.50
            "Was $300 Now $199" -> 199.00
        """
        if not price_text:
            return None
        
        try:
            # Remove common currency symbols and text
            cleaned = price_text.replace('C$', '').replace('$', '').replace('CAD', '')
            cleaned = cleaned.replace(',', '').strip()
            
            # Extract first number that looks like a price
            # This handles cases like "Was $300 Now $199"
            match = re.search(r'(\d+\.?\d*)', cleaned)
            if match:
                return float(match.group(1))
            
            return None
        except (ValueError, AttributeError) as e:
            logger.warning(f"Could not parse price from '{price_text}': {e}")
            return None
    
    def extract_numeric_size(self, size_text: str) -> Optional[str]:
        """
        Extract shoe size from text
        
        Examples:
            "Size 10.5" -> "10.5"
            "US 11" -> "11"
            "10.5 US" -> "10.5"
        """
        if not size_text:
            return None
        
        # Look for size patterns like 10, 10.5, 11
        match = re.search(r'(\d+\.?\d*)', size_text)
        if match:
            return match.group(1)
        
        return None
    
    def is_in_stock(self, html: str, soup: BeautifulSoup) -> bool:
        """
        Check if product is in stock
        
        Args:
            html: Raw HTML content
            soup: BeautifulSoup object
            
        Returns:
            True if in stock, False otherwise
        """
        # Common out-of-stock indicators
        out_of_stock_phrases = [
            'out of stock',
            'sold out',
            'unavailable',
            'not available',
            'épuisé',  # French for sold out
            'non disponible'
        ]
        
        html_lower = html.lower()
        
        for phrase in out_of_stock_phrases:
            if phrase in html_lower:
                return False
        
        return True
    
    # Keyword (case-insensitive) immediately preceding a code token. The code
    # itself is captured case-sensitively so we don't grab lowercase prose.
    _PROMO_CODE_RE = re.compile(
        r'(?i:promo\s*code|coupon\s*code|discount\s*code|use\s*code|enter\s*code|'
        r'with\s*code|coupon|promo|code)\s*[:\-]?\s*[\'"“]?([A-Z0-9][A-Z0-9\-]{2,24})'
    )
    # "Extra 20% off", "20% off", "save 20%", French "20% de rabais".
    _PERCENT_RE = re.compile(
        r'(\d{1,2})\s*%\s*(?:off|discount|rabais)', re.IGNORECASE
    )

    def get_homepage_url(self) -> str:
        """URL to scan for site-wide promo codes (overridable per retailer)."""
        return self.base_url

    def get_promo_page_urls(self) -> List[str]:
        """
        URLs to check for site-wide promo codes (R4.4).

        Default: the homepage only. Subclasses can override to append
        additional pages (sale pages, promotions pages, etc.) so the
        coupon hunter sees more than just the homepage banner.
        """
        return [self.get_homepage_url()]

    @staticmethod
    def _looks_like_code(token: str) -> bool:
        """Filter out prose accidentally captured after the word 'code'."""
        has_digit = any(c.isdigit() for c in token)
        has_alpha = any(c.isalpha() for c in token)
        if has_digit and has_alpha:
            return True  # e.g. 20FOR200, SAVE20
        if has_alpha and not has_digit and len(token) >= 5:
            return True  # e.g. FREESHIP, WELCOME
        return False

    def find_promo_codes(self, html: str) -> List[Dict]:
        """
        Heuristically extract discount codes from page HTML.

        Returns a list of dicts: {code, description, discount_percent}.
        Best-effort — pairs each code with the nearest "% off" mention.
        """
        if not html:
            return []

        soup = BeautifulSoup(html, 'lxml')
        text = soup.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text)

        found = {}
        for match in self._PROMO_CODE_RE.finditer(text):
            code = match.group(1)
            if not self._looks_like_code(code):
                continue

            # Look at a window around the match for a nearby discount + context.
            start = max(0, match.start() - 90)
            end = min(len(text), match.end() + 60)
            window = text[start:end]

            percent = None
            pm = self._PERCENT_RE.search(window)
            if pm:
                percent = float(pm.group(1))

            # Build a tidy description spanning from the discount phrase (or
            # just before the code) through the code itself — the code is the
            # last meaningful token, so we drop trailing nav text after it.
            code_pos = window.find(code)
            desc_end = code_pos + len(code) if code_pos != -1 else len(window)
            if pm and pm.start() < desc_end:
                phrase_start = window.rfind('. ', 0, pm.start())
                desc_start = phrase_start + 2 if phrase_start != -1 else pm.start()
            else:
                desc_start = max(0, desc_end - len(code) - 40)
            description = window[desc_start:desc_end].strip(' .,-|')
            if len(description) > 120:
                description = description[:117].rstrip() + '…'

            # De-dupe by code; keep the variant that found a discount.
            if code not in found or (percent and not found[code].get('discount_percent')):
                found[code] = {
                    'code': code,
                    'description': description,
                    'discount_percent': percent,
                }

        return list(found.values())

    def scrape_promo_codes(self) -> List[Dict]:
        """
        Fetch each URL from get_promo_page_urls() and extract promo codes.

        Results across pages are merged and deduplicated by code — if the same
        code appears on multiple pages, the variant with a discount_percent is
        preferred (gives the LLM a concrete number to work with).
        """
        urls = self.get_promo_page_urls()
        use_browser = self.config.get('use_browser', False)
        merged: Dict[str, Dict] = {}

        for url in urls:
            html = self.fetch_page(url, use_browser=use_browser)
            if not html:
                logger.warning(f"[{self.retailer_name}] Could not fetch {url} for promo codes")
                continue
            for c in self.find_promo_codes(html):
                c['source_url'] = url
                code = c['code']
                # Keep the variant that found a discount_percent.
                if code not in merged or (c.get('discount_percent') and not merged[code].get('discount_percent')):
                    merged[code] = c

        codes = list(merged.values())
        logger.info(f"[{self.retailer_name}] Found {len(codes)} promo code(s) across {len(urls)} page(s)")
        return codes

    # Replica/sort suffixes appended to the base Algolia index name — stripped
    # during rediscovery so we cache the primary index, not a sorted replica.
    _ALGOLIA_REPLICA_SUFFIX_RE = re.compile(
        r'_(bestSeller|newest|price_asc|price_desc|relevance)$'
    )

    def discover_algolia_credentials(self, homepage_url: str, search_selector: str,
                                     query: str = "shoe") -> Optional[Dict]:
        """
        Discover a site's public Algolia credentials by driving its own search.

        Launches headless Playwright, navigates to ``homepage_url``, types ``query``
        into ``search_selector``, and intercepts the resulting requests to
        ``*.algolia.net`` — reading the app id + search key from request headers and
        the index name from the search payload. Returns
        ``{"app_id", "api_key", "index"}`` or ``None``. Never raises.
        """
        creds: Dict[str, str] = {}

        def on_request(req):
            try:
                url = req.url
                if 'algolia.net' not in url.lower():
                    return
                headers = req.headers
                app_id = headers.get('x-algolia-application-id')
                api_key = headers.get('x-algolia-api-key')
                if app_id and 'app_id' not in creds:
                    creds['app_id'] = app_id
                if api_key and 'api_key' not in creds:
                    creds['api_key'] = api_key
                if 'index' not in creds:
                    # Prefer the indexName from the search payload (the base index);
                    # fall back to the /indexes/<name>/ URL segment.
                    names = re.findall(r'"indexName"\s*:\s*"([^"]+)"', req.post_data or '')
                    if not names:
                        m = re.search(r'/indexes/([^/?*]+)', url)
                        names = [m.group(1)] if m else []
                    for name in names:
                        if 'query_suggestions' in name:
                            continue
                        creds['index'] = self._ALGOLIA_REPLICA_SUFFIX_RE.sub('', name)
                        break
            except Exception:
                pass

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.on('request', on_request)
                page.goto(homepage_url, wait_until='domcontentloaded', timeout=40000)
                try:
                    page.wait_for_selector(search_selector, timeout=20000)
                    page.click(search_selector)
                    page.type(search_selector, query, delay=80)
                except Exception as e:
                    logger.warning(f"[{self.retailer_name}] rediscovery: search box not usable: {e}")
                page.wait_for_timeout(5000)
                browser.close()
        except Exception as e:
            logger.error(
                f"[{self.retailer_name}] Algolia rediscovery error at "
                f"{datetime.utcnow().isoformat()}: {e}"
            )
            return None

        if creds.get('app_id') and creds.get('api_key'):
            logger.info(
                f"[{self.retailer_name}] Algolia credential rediscovery succeeded at "
                f"{datetime.utcnow().isoformat()}: app_id={creds['app_id']} "
                f"index={creds.get('index')}"
            )
            return creds

        logger.warning(
            f"[{self.retailer_name}] Algolia rediscovery found no credentials at "
            f"{datetime.utcnow().isoformat()}"
        )
        return None

    @abstractmethod
    def search_products(self, brand: str, model: str) -> List[Dict]:
        """
        Search for products matching brand and model
        
        Must be implemented by each retailer scraper
        
        Returns:
            List of product dictionaries with keys:
                - product_url: str
                - name: str
                - price: float
                - original_price: Optional[float]
                - in_stock: bool
                - sizes_available: List[str]
        """
        pass
    
    @abstractmethod
    def get_product_details(self, product_url: str) -> Optional[Dict]:
        """
        Get detailed information for a specific product
        
        Must be implemented by each retailer scraper
        
        Returns:
            Dictionary with product details or None if failed
        """
        pass
    
    def log_scrape_attempt(self, shoe_brand: str, shoe_model: str, results_count: int):
        """Log scraping attempt for monitoring"""
        logger.info(
            f"[{self.retailer_name}] Scraped {shoe_brand} {shoe_model}: "
            f"Found {results_count} results"
        )
