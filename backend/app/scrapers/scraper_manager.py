"""
Scraper Manager - Orchestrates scraping operations and database storage
"""
import logging
import threading
from contextlib import contextmanager
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.models import Shoe, Retailer, PriceRecord, Deal, PromoCode
from app.scrapers.the_last_hunt import TheLastHuntScraper
from app.scrapers.jd_sports import JDSportsScraper
from app.scrapers.altitude_sports import AltitudeSportsScraper
from app.scrapers.boutique_endurance import BoutiqueEnduranceScraper
from app.scrapers.le_coureur import LeCoureurScraper
from app.scrapers.blacktoe_running import BlackToeRunningScraper
from app.scrapers.forerunners import ForeRunnersScraper
from app.scrapers.enroute_run import EnRouteRunScraper
from app.scrapers.shopify_scraper import ShopifyScraper
from app.scrapers.algolia_scraper import AlgoliaScraper

logger = logging.getLogger(__name__)

# Scraping a full catalog easily takes 20-30+ minutes (47 shoes x up to 9
# retailers, each request rate-limited with a sleep). The REST endpoints are
# synchronous, so a frontend client that times out waiting (see ScrapeButton)
# and retries — or two people clicking "Run scan" — would otherwise stack
# unbounded concurrent full-catalog scrapes on top of each other with no
# coordination, which is what actually produces "scraping forever": each
# pass slows every other one down via shared rate limits and none of them
# ever appear to finish. This lock makes that a clean, fast rejection
# instead, across every entry point (REST + the MCP trigger_scrape tool).
_scrape_lock = threading.Lock()


class ScrapeInProgressError(Exception):
    """Raised when a scrape is requested while one is already running."""


@contextmanager
def scrape_guard():
    if not _scrape_lock.acquire(blocking=False):
        raise ScrapeInProgressError(
            "A scrape is already in progress. Wait for it to finish before starting another."
        )
    try:
        yield
    finally:
        _scrape_lock.release()


def try_acquire_scrape_lock() -> bool:
    """
    Non-blocking acquire for callers that can't use the `scrape_guard()`
    context manager because the work outlives the function that starts it
    (the background scrape job — see app/scrape_runner.py — is scheduled via
    BackgroundTasks and runs after the request that kicked it off has
    already returned). The caller is responsible for calling
    `release_scrape_lock()` exactly once when that work finishes.
    """
    return _scrape_lock.acquire(blocking=False)


def release_scrape_lock() -> None:
    _scrape_lock.release()


def is_scrape_running() -> bool:
    """Non-blocking check — True if a scrape of any kind currently holds the lock."""
    return _scrape_lock.locked()


def build_dynamic_scraper(retailer: Retailer):
    """
    Build a generic ShopifyScraper/AlgoliaScraper instance straight from a
    Retailer row's platform + scraper_config — no subclass file needed.

    Used for retailers that don't have one of the hand-written subclasses
    (the_last_hunt.py, jd_sports.py, etc). Returns None for platform="custom"
    or if Algolia credentials are missing/invalid.
    """
    cfg = retailer.scraper_config or {}

    if retailer.platform == "shopify":
        return ShopifyScraper(
            retailer_name=retailer.name,
            base_url=retailer.base_url,
            config={"use_browser": False},
        )

    if retailer.platform == "algolia":
        required = ("algolia_app_id", "algolia_api_key", "algolia_index")
        if not all(cfg.get(k) for k in required):
            logger.warning(
                f"Retailer '{retailer.name}' is platform=algolia but missing "
                f"credentials in scraper_config; no scraper built."
            )
            return None
        return AlgoliaScraper(
            retailer_name=retailer.name,
            base_url=retailer.base_url,
            app_id=cfg["algolia_app_id"],
            api_key=cfg["algolia_api_key"],
            index=cfg["algolia_index"],
            product_path=cfg.get("algolia_product_path", "/p/"),
        )

    return None


class ScraperManager:
    """
    Manages scraping operations across multiple retailers
    Handles database storage of results
    """

    def __init__(self, db: Session):
        self.db = db
        # Keyed by retailer.name as stored in the DB (see seed_data.py).
        # These bespoke subclasses take priority over dynamically-built ones
        # below (names are unique, so this only matters as a tie-break rule).
        self.scrapers = {
            'The Last Hunt': TheLastHuntScraper(),
            'JD Sports Canada': JDSportsScraper(),
            'Altitude Sports': AltitudeSportsScraper(),
            'Boutique Endurance': BoutiqueEnduranceScraper(),
            'Le Coureur': LeCoureurScraper(),
            'BlackToe Running': BlackToeRunningScraper(),
            'ForeRunners': ForeRunnersScraper(),
            'En Route Run': EnRouteRunScraper(),
        }
        self._register_dynamic_scrapers()

    def _register_dynamic_scrapers(self):
        """
        Supplement the static dict with generic scrapers built from any
        retailer row whose platform is shopify/algolia and doesn't already
        have a hardcoded subclass. Rebuilt from the DB on every ScraperManager
        construction, so newly-created retailers get a working scraper
        immediately and it survives application restarts without any extra
        in-memory registry to persist.
        """
        dynamic_candidates = self.db.query(Retailer).filter(
            Retailer.platform.in_(["shopify", "algolia"])
        ).all()

        for retailer in dynamic_candidates:
            if retailer.name in self.scrapers:
                continue
            scraper = build_dynamic_scraper(retailer)
            if scraper:
                self.scrapers[retailer.name] = scraper

    def scrape_shoe(self, shoe_id: int, retailer_ids: Optional[List[int]] = None) -> Dict:
        """
        Scrape prices for a specific shoe across retailers
        
        Args:
            shoe_id: ID of shoe to scrape
            retailer_ids: Optional list of retailer IDs to scrape (if None, scrape all active)
            
        Returns:
            Dictionary with scraping results
        """
        # Get shoe from database
        shoe = self.db.query(Shoe).filter(Shoe.id == shoe_id).first()
        
        if not shoe:
            return {
                'success': False,
                'error': f'Shoe with ID {shoe_id} not found'
            }
        
        if not shoe.is_active:
            return {
                'success': False,
                'error': f'Shoe {shoe.brand} {shoe.model} is not active'
            }
        
        logger.info(f"Scraping prices for {shoe.brand} {shoe.model} (target ${shoe.target_price})")
        
        # Get retailers to scrape
        query = self.db.query(Retailer).filter(Retailer.is_active == True, Retailer.scraping_enabled == True)
        
        if retailer_ids:
            query = query.filter(Retailer.id.in_(retailer_ids))
        
        retailers = query.all()
        
        results = {
            'shoe': f'{shoe.brand} {shoe.model}',
            'retailers_scraped': 0,
            'products_found': 0,
            'prices_recorded': 0,
            'deals_found': 0,
            'errors': []
        }
        
        for retailer in retailers:
            try:
                retailer_results = self._scrape_retailer_for_shoe(shoe, retailer)
                
                results['retailers_scraped'] += 1
                results['products_found'] += retailer_results.get('products_found', 0)
                results['prices_recorded'] += retailer_results.get('prices_recorded', 0)
                results['deals_found'] += retailer_results.get('deals_found', 0)
                
                if retailer_results.get('errors'):
                    results['errors'].extend(retailer_results['errors'])
                
            except Exception as e:
                error_msg = f"Error scraping {retailer.name}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        return results
    
    def _scrape_retailer_for_shoe(self, shoe: Shoe, retailer: Retailer) -> Dict:
        """
        Scrape a specific retailer for a specific shoe
        """
        logger.info(f"Scraping {retailer.name} for {shoe.brand} {shoe.model}")
        
        results = {
            'products_found': 0,
            'prices_recorded': 0,
            'deals_found': 0,
            'errors': []
        }
        
        # Get appropriate scraper
        scraper = self.scrapers.get(retailer.name)
        
        if not scraper:
            error_msg = f"No scraper implemented for {retailer.name}"
            logger.warning(error_msg)
            results['errors'].append(error_msg)
            return results
        
        try:
            # Search for products (kids/junior listings filtered out before
            # anything from this search is ever recorded — see
            # BaseScraper.search_products_filtered)
            products = scraper.search_products_filtered(shoe.brand, shoe.model)
            results['products_found'] = len(products)
            
            if not products:
                logger.info(f"No products found on {retailer.name} for {shoe.brand} {shoe.model}")
                return results
            
            # Process each product found. URLs seen this scrape are tracked so
            # we can retire deals whose product_url no longer comes back at all
            # (e.g. the shoe's model name was edited and the retailer search now
            # resolves to a different product page) — see cleanup below.
            seen_urls = set()
            for product in products:
                try:
                    # Get detailed product info
                    details = scraper.get_product_details(product['product_url'])

                    if not details:
                        continue

                    seen_urls.add(details['product_url'])

                    # We no longer track one exact size — "available" now means at
                    # least one size of this model is in stock.
                    size_available = bool(details.get('sizes_available')) or details.get('in_stock', False)
                    sizes_available = details.get('sizes_available') or None
                    image_url = details.get('image_url')
                    colorway = details.get('colorway')

                    # Record price
                    price_recorded = self._record_price(
                        shoe=shoe,
                        retailer=retailer,
                        product_url=details['product_url'],
                        price=details['price'],
                        original_price=details.get('original_price'),
                        in_stock=details['in_stock'],
                        size_available=size_available,
                        sizes_available=sizes_available,
                        image_url=image_url,
                        colorway=colorway
                    )

                    if price_recorded:
                        results['prices_recorded'] += 1

                        # A "deal" requires both: the retailer is actually marking the
                        # item down from its own original price, AND that sale price is
                        # at/below the shoe's CURRENT target_price (read fresh this scrape,
                        # so target edits take effect immediately). Hitting your target at
                        # full price (no original_price, or original_price <= price) is not
                        # a deal — e.g. Adios Pro 4 at BlackToe sits at $300 full price with
                        # no compare_at_price, which used to falsely qualify when target was $300.
                        original_price = details.get('original_price')
                        on_sale = original_price is not None and original_price > details['price']
                        if details['price'] and on_sale and details['price'] <= shoe.target_price:
                            deal_created = self._create_deal(
                                shoe=shoe,
                                retailer=retailer,
                                price=details['price'],
                                product_url=details['product_url'],
                                in_stock=details['in_stock'] and size_available,
                                sizes_available=sizes_available,
                                image_url=image_url,
                                colorway=colorway
                            )

                            if deal_created:
                                results['deals_found'] += 1
                                logger.info(
                                    f"🎉 Deal found! {shoe.brand} {shoe.model} at {retailer.name}: "
                                    f"${details['price']} (target: ${shoe.target_price})"
                                )
                        else:
                            # Price is above target (or target was just raised) —
                            # retire any stale deal so the UI reflects reality.
                            self._deactivate_deal(shoe, retailer, details['product_url'])
                
                except Exception as e:
                    error_msg = f"Error processing product: {str(e)}"
                    logger.warning(error_msg)
                    results['errors'].append(error_msg)

            # Retire deals whose product_url wasn't found at all this scrape
            # (distinct from _deactivate_deal above, which only fires for URLs
            # that WERE re-scraped but rose above target). Without this, renaming
            # a shoe (e.g. "Magic Speed 4" -> "Magic Speed 5") leaves the old
            # model's deal active forever, since the new search never revisits
            # the old URL to notice it should be retired.
            self._deactivate_orphaned_deals(shoe, retailer, seen_urls)

            # Update retailer's last scraped timestamp
            retailer.last_scraped_at = datetime.utcnow()
            self.db.commit()
            
        except Exception as e:
            error_msg = f"Error in scraper for {retailer.name}: {str(e)}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
        
        return results
    
    def _record_price(self, shoe: Shoe, retailer: Retailer, product_url: str,
                     price: Optional[float], original_price: Optional[float],
                     in_stock: bool, size_available: bool,
                     sizes_available: Optional[list] = None,
                     image_url: Optional[str] = None, colorway: Optional[str] = None) -> bool:
        """
        Record a price in the database
        """
        if not price:
            logger.warning(f"No price found for {product_url}")
            return False

        try:
            price_record = PriceRecord(
                shoe_id=shoe.id,
                retailer_id=retailer.id,
                product_url=product_url,
                price=price,
                original_price=original_price,
                in_stock=in_stock,
                size_available=size_available,
                sizes_available=sizes_available,
                image_url=image_url,
                colorway=colorway
            )
            
            self.db.add(price_record)
            self.db.commit()
            
            logger.info(f"Recorded price: ${price} for {shoe.brand} {shoe.model} at {retailer.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error recording price: {e}")
            self.db.rollback()
            return False
    
    def _create_deal(self, shoe: Shoe, retailer: Retailer, price: float,
                    product_url: str, in_stock: bool,
                    sizes_available: Optional[list] = None,
                    image_url: Optional[str] = None, colorway: Optional[str] = None) -> bool:
        """
        Create a deal when price is at or below target
        """
        try:
            # Calculate savings
            savings_amount = shoe.target_price - price
            savings_percent = (savings_amount / shoe.target_price) * 100

            # Check if deal already exists
            existing_deal = self.db.query(Deal).filter(
                Deal.shoe_id == shoe.id,
                Deal.retailer_id == retailer.id,
                Deal.is_active == True,
                Deal.product_url == product_url
            ).first()

            if existing_deal:
                # Always refresh image/colorway/sizes when we have them (older
                # deals predate this data and would otherwise stay blank/stale).
                if image_url:
                    existing_deal.image_url = image_url
                if colorway:
                    existing_deal.colorway = colorway
                existing_deal.sizes_available = sizes_available
                # Refresh price/savings if the scraped price OR the shoe's
                # target_price changed since the deal was created. Recomputing
                # against the current target_price is what makes target edits
                # "stick" on existing deals.
                if (existing_deal.current_price != price
                        or existing_deal.target_price != shoe.target_price):
                    existing_deal.current_price = price
                    existing_deal.target_price = shoe.target_price
                    existing_deal.savings_amount = savings_amount
                    existing_deal.savings_percent = savings_percent
                    existing_deal.in_stock = in_stock
                    logger.info(f"Updated existing deal (price ${price}, target ${shoe.target_price})")
                self.db.commit()
                return False  # Not a new deal
            
            # Create new deal
            deal = Deal(
                shoe_id=shoe.id,
                retailer_id=retailer.id,
                current_price=price,
                target_price=shoe.target_price,
                savings_amount=savings_amount,
                savings_percent=savings_percent,
                product_url=product_url,
                in_stock=in_stock,
                sizes_available=sizes_available,
                image_url=image_url,
                colorway=colorway,
                is_active=True
            )
            
            self.db.add(deal)
            self.db.commit()
            
            logger.info(
                f"Created deal: {shoe.brand} {shoe.model} at {retailer.name} - "
                f"${price} (save {savings_percent:.1f}%)"
            )
            return True
            
        except Exception as e:
            logger.error(f"Error creating deal: {e}")
            self.db.rollback()
            return False

    def _deactivate_deal(self, shoe: Shoe, retailer: Retailer, product_url: str) -> bool:
        """
        Retire an active deal that no longer qualifies (price rose above target,
        or the target_price was lowered below the current price).

        Returns True if a deal was deactivated.
        """
        try:
            deal = self.db.query(Deal).filter(
                Deal.shoe_id == shoe.id,
                Deal.retailer_id == retailer.id,
                Deal.product_url == product_url,
                Deal.is_active == True,
            ).first()

            if not deal:
                return False

            deal.is_active = False
            self.db.commit()
            logger.info(
                f"Deactivated stale deal: {shoe.brand} {shoe.model} at {retailer.name} "
                f"(no longer <= target ${shoe.target_price})"
            )
            return True
        except Exception as e:
            logger.error(f"Error deactivating deal: {e}")
            self.db.rollback()
            return False

    def _deactivate_orphaned_deals(self, shoe: Shoe, retailer: Retailer, seen_urls: set) -> int:
        """
        Retire active deals for this shoe+retailer whose product_url wasn't
        among the URLs just scraped. Called once per retailer after a
        successful (non-empty) search, so a transient empty response can't
        wipe out deals — only a real search that came back with different
        URLs than what's on file (most commonly: the shoe's brand/model was
        edited, so the search now resolves a different product page).

        Returns the number of deals deactivated.
        """
        if not seen_urls:
            return 0

        try:
            stale = self.db.query(Deal).filter(
                Deal.shoe_id == shoe.id,
                Deal.retailer_id == retailer.id,
                Deal.is_active == True,
                ~Deal.product_url.in_(seen_urls),
            ).all()

            for deal in stale:
                deal.is_active = False
                logger.info(
                    f"Deactivated orphaned deal: {shoe.brand} {shoe.model} at {retailer.name} "
                    f"({deal.product_url} no longer matches this shoe's search)"
                )

            if stale:
                self.db.commit()
            return len(stale)
        except Exception as e:
            logger.error(f"Error deactivating orphaned deals: {e}")
            self.db.rollback()
            return 0

    def detect_promo_codes_for_retailer(self, retailer: Retailer) -> Dict:
        """
        Scan a retailer's site for discount codes and upsert them.

        Returns {'found': int, 'new': int, 'errors': [...]}.
        """
        result = {'found': 0, 'new': 0, 'errors': []}

        scraper = self.scrapers.get(retailer.name)
        if not scraper:
            result['errors'].append(f"No scraper implemented for {retailer.name}")
            return result

        try:
            codes = scraper.scrape_promo_codes()
            result['found'] = len(codes)
            for c in codes:
                if self._upsert_promo_code(retailer, c):
                    result['new'] += 1
        except Exception as e:
            msg = f"Error detecting promo codes for {retailer.name}: {str(e)}"
            logger.error(msg)
            result['errors'].append(msg)

        return result

    def detect_all_promo_codes(self) -> Dict:
        """Detect promo codes across all active, scraping-enabled retailers."""
        retailers = self.db.query(Retailer).filter(
            Retailer.is_active == True, Retailer.scraping_enabled == True
        ).all()

        agg = {'retailers_scanned': 0, 'codes_found': 0, 'new_codes': 0, 'errors': []}
        for retailer in retailers:
            r = self.detect_promo_codes_for_retailer(retailer)
            agg['retailers_scanned'] += 1
            agg['codes_found'] += r['found']
            agg['new_codes'] += r['new']
            agg['errors'].extend(r['errors'])
        return agg

    def _upsert_promo_code(self, retailer: Retailer, data: Dict) -> bool:
        """
        Insert a newly-detected code, or refresh an existing one.

        Returns True if a new code row was created. Manually-added codes are
        never overwritten by scraped data.
        """
        try:
            existing = self.db.query(PromoCode).filter(
                PromoCode.retailer_id == retailer.id,
                PromoCode.code == data['code'],
            ).first()

            now = datetime.utcnow()
            if existing:
                existing.last_seen_at = now
                existing.is_active = True
                if existing.source != 'manual':
                    existing.description = data.get('description') or existing.description
                    if data.get('discount_percent') is not None:
                        existing.discount_percent = data['discount_percent']
                    existing.source_url = data.get('source_url') or existing.source_url
                self.db.commit()
                return False

            promo = PromoCode(
                retailer_id=retailer.id,
                code=data['code'],
                description=data.get('description'),
                discount_percent=data.get('discount_percent'),
                discount_amount=data.get('discount_amount'),
                source='scraped',
                source_url=data.get('source_url'),
                is_active=True,
                last_seen_at=now,
            )
            self.db.add(promo)
            self.db.commit()
            logger.info(f"🏷️  New promo code for {retailer.name}: {data['code']}")
            return True
        except Exception as e:
            logger.error(f"Error upserting promo code: {e}")
            self.db.rollback()
            return False

    def test_shoe_scrapability(self, brand: str, model: str) -> Dict:
        """
        Dry-run a brand+model search across every active, scraping-enabled
        retailer WITHOUT writing to the database (no PriceRecord, no Deal).

        Used to validate naming before a shoe is saved (or to re-check one
        that was added by hand in seed_data.py).
        """
        retailers = self.db.query(Retailer).filter(
            Retailer.is_active == True, Retailer.scraping_enabled == True
        ).all()

        results = []
        total_found = 0
        retailers_found = 0

        for retailer in retailers:
            scraper = self.scrapers.get(retailer.name)
            if not scraper:
                continue  # no scraper implemented for this retailer yet

            entry = {'retailer': retailer.name}
            try:
                products = scraper.search_products_filtered(brand, model)
            except Exception as e:
                logger.warning(f"[{retailer.name}] scrapability test error: {e}")
                entry.update(status='error', products_found=0, error=str(e))
                results.append(entry)
                continue

            if not products:
                entry.update(
                    status='not_found',
                    products_found=0,
                    suggestion=(
                        "No matches — try a shorter or differently-formatted "
                        "model name (drop size/edition suffixes, check spelling)."
                    ),
                )
                results.append(entry)
                continue

            sample_price = products[0].get('price')
            sizes = products[0].get('sizes_available') or []
            if not sizes:
                # Shopify's search step doesn't return sizes — only the
                # per-product detail call does.
                try:
                    details = scraper.get_product_details(products[0]['product_url'])
                    if details:
                        sample_price = details.get('price', sample_price)
                        sizes = details.get('sizes_available') or []
                except Exception as e:
                    logger.warning(f"[{retailer.name}] detail lookup failed during test: {e}")

            entry.update(
                status='success',
                products_found=len(products),
                sample_price=sample_price,
                sizes=sizes,
            )
            total_found += len(products)
            retailers_found += 1
            results.append(entry)

        return {
            'shoe': f'{brand} {model}',
            'scrapeable': retailers_found > 0,
            'results': results,
            'total_found': total_found,
            'retailers_tested': len(results),
            'retailers_found': retailers_found,
            'recommendation': 'proceed' if retailers_found > 0 else 'modify_name',
        }

    def scrape_all_shoes(self, retailer_ids: Optional[List[int]] = None) -> Dict:
        """
        Scrape all active shoes across all retailers

        Args:
            retailer_ids: Optional list of retailer IDs to scrape

        Returns:
            Dictionary with aggregated results
        """
        active_shoes = self.db.query(Shoe).filter(Shoe.is_active == True).all()

        logger.info(f"Starting scrape for {len(active_shoes)} active shoes")

        aggregated_results = {
            'total_shoes': len(active_shoes),
            'total_retailers_scraped': 0,
            'total_products_found': 0,
            'total_prices_recorded': 0,
            'total_deals_found': 0,
            'promo_codes_found': 0,
            'errors': []
        }

        # Detect site-wide discount codes first so deals can reference them.
        try:
            promo_summary = self.detect_all_promo_codes()
            aggregated_results['promo_codes_found'] = promo_summary['codes_found']
            aggregated_results['errors'].extend(promo_summary['errors'])
        except Exception as e:
            logger.error(f"Promo detection failed: {e}")
            aggregated_results['errors'].append(f"Promo detection failed: {str(e)}")

        for shoe in active_shoes:
            results = self.scrape_shoe(shoe.id, retailer_ids)
            
            aggregated_results['total_retailers_scraped'] += results.get('retailers_scraped', 0)
            aggregated_results['total_products_found'] += results.get('products_found', 0)
            aggregated_results['total_prices_recorded'] += results.get('prices_recorded', 0)
            aggregated_results['total_deals_found'] += results.get('deals_found', 0)
            
            if results.get('errors'):
                aggregated_results['errors'].extend(results['errors'])
        
        return aggregated_results
