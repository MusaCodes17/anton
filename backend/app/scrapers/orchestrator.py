"""
ScrapeOrchestrator — coordinates per-shoe/per-retailer scraping and deal
qualification, delegating all persistence to DealStore and all scraper
instantiation to the registry.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.models import Retailer, ScrapeRun, Shoe
from app.scrapers.deal_store import DealStore
from app.scrapers.registry import build_registry

logger = logging.getLogger(__name__)

# Joined per-item error strings are truncated before they land in
# ScrapeRun.error — the column is a human-readable summary, not a log sink.
_SCRAPE_ERROR_MAX = 2000


class ScrapeOrchestrator:
    def __init__(
        self,
        db: Session,
        registry: Optional[Dict] = None,
        store: Optional[DealStore] = None,
    ):
        self.db = db
        self.scrapers = registry if registry is not None else build_registry(db)
        self.store = store if store is not None else DealStore(db)

    def scrape_retailer_for_shoe(self, shoe: Shoe, retailer: Retailer) -> Dict:
        """
        Scrape a specific retailer for a specific shoe and persist results.

        Deal-qualification rule: a "deal" is any price strictly below the
        shoe's CURRENT MSRP (read fresh this scrape, so MSRP edits take effect
        immediately). "On sale" now means "below list price" — the retailer's
        own compare-at/original price is ignored for qualification. Shoes
        without an MSRP can't produce deals (nothing to measure against).

        URLs seen this scrape are tracked so orphaned deals can be retired after
        the loop (see _deactivate_orphaned_deals comment below).
        """
        logger.info(f"Scraping {retailer.name} for {shoe.brand} {shoe.model}")

        results = {
            'products_found': 0,
            'prices_recorded': 0,
            'deals_found': 0,
            'errors': [],
        }

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
            #
            # We track TWO sets: `fetched_urls` (products whose detail fetch
            # succeeded) and `searched_urls` (every URL the search returned,
            # whether or not its detail fetch succeeded). Orphan retirement runs
            # against the *union* — a product that appeared in search must never
            # be orphaned merely because its detail fetch failed this scrape
            # (H2/B10: a transient per-product detail timeout is routine and must
            # not extinguish a live deal). Search and detail URLs share the
            # `/products/<handle>` shape across the Shopify and En Route scrapers,
            # so the union matches correctly.
            fetched_urls = set()
            searched_urls = {
                p['product_url'] for p in products if p.get('product_url')
            }
            for product in products:
                try:
                    details = scraper.get_product_details(product['product_url'])
                    if not details:
                        continue

                    fetched_urls.add(details['product_url'])

                    # We no longer track one exact size — "available" now means at
                    # least one size of this model is in stock.
                    size_available = bool(details.get('sizes_available')) or details.get('in_stock', False)
                    sizes_available = details.get('sizes_available') or None
                    image_url = details.get('image_url')
                    colorway = details.get('colorway')

                    price_recorded = self.store.record_price(
                        shoe=shoe,
                        retailer=retailer,
                        product_url=details['product_url'],
                        price=details['price'],
                        original_price=details.get('original_price'),
                        in_stock=details['in_stock'],
                        size_available=size_available,
                        sizes_available=sizes_available,
                        image_url=image_url,
                        colorway=colorway,
                    )

                    if price_recorded:
                        results['prices_recorded'] += 1

                        # A "deal" is any price strictly below the shoe's
                        # CURRENT MSRP (read fresh this scrape, so MSRP edits
                        # take effect immediately). The retailer's own
                        # compare-at/original price no longer matters. A shoe
                        # with no MSRP can't qualify — nothing to measure against.
                        below_msrp = (
                            shoe.msrp is not None
                            and details['price']
                            and details['price'] < shoe.msrp
                        )
                        if below_msrp:
                            deal_created = self.store.upsert_deal(
                                shoe=shoe,
                                retailer=retailer,
                                price=details['price'],
                                product_url=details['product_url'],
                                in_stock=details['in_stock'] and size_available,
                                sizes_available=sizes_available,
                                image_url=image_url,
                                colorway=colorway,
                            )
                            if deal_created:
                                results['deals_found'] += 1
                                logger.info(
                                    f"🎉 Deal found! {shoe.brand} {shoe.model} at {retailer.name}: "
                                    f"${details['price']} (msrp: ${shoe.msrp})"
                                )
                        else:
                            # Price is at/above MSRP (or MSRP was just raised, or
                            # is unset) — retire any stale deal so the UI reflects
                            # reality.
                            self.store.deactivate_deal(shoe, retailer, details['product_url'])

                except Exception as e:
                    error_msg = f"Error processing product: {str(e)}"
                    logger.warning(error_msg)
                    results['errors'].append(error_msg)

            # Retire deals whose product_url wasn't found at all this scrape
            # (distinct from deactivate_deal above, which only fires for URLs
            # that WERE re-scraped but rose above target). Without this,
            # renaming a shoe (e.g. "Magic Speed 4" -> "Magic Speed 5") leaves
            # the old model's deal active forever, since the new search never
            # revisits the old URL to notice it should be retired. Retire against
            # the union of fetched + searched URLs so a failed detail fetch on a
            # still-listed product can't orphan its live deal (H2/B10).
            self.store.deactivate_orphaned_deals(
                shoe, retailer, fetched_urls | searched_urls
            )

            retailer.last_scraped_at = datetime.now(timezone.utc)
            self.db.commit()

        except Exception as e:
            error_msg = f"Error in scraper for {retailer.name}: {str(e)}"
            logger.error(error_msg)
            results['errors'].append(error_msg)

        return results

    def scrape_retailer(
        self, retailer: Retailer, shoes: List[Shoe], *, trigger: Optional[str] = None
    ) -> Dict:
        """
        Scrape one retailer across a list of shoes, recording a ScrapeRun
        observability row (R2.5) — the **single sanctioned write path** for
        `scrape_runs`. This is the per-retailer, full-catalog unit that answers
        "is this retailer quietly broken?"; the SSE-driven background flow and
        the synchronous POST /scrape/retailer/{id} endpoint both go through it.

        The run is stamped "running" and committed immediately so an in-flight
        (or crashed-mid-scrape) attempt is visible, then finalized to
        "success"/"error" once the shoe list is exhausted. Per-shoe failures are
        isolated (one shoe's error never aborts the retailer) and summarized
        into ScrapeRun.error — matching the skip-and-continue rule for batch
        loops (CLAUDE.md §7).

        Args:
            retailer: the retailer to scrape (caller has confirmed it's active
                and scraping-enabled).
            shoes: the shoes to search for at this retailer.
            trigger: how the scrape was kicked off ("background" | "manual");
                stamped on the run for later attribution.

        Returns the aggregate counts for this retailer (products_found,
        prices_recorded, deals_found, shoes_scraped, errors).
        """
        run = ScrapeRun(retailer_id=retailer.id, status="running", trigger=trigger)
        self.db.add(run)
        self.db.commit()  # persist "running" up front — visible while in flight

        agg = {
            'shoes_scraped': 0,
            'products_found': 0,
            'prices_recorded': 0,
            'deals_found': 0,
            'errors': [],
        }

        for shoe in shoes:
            try:
                r = self.scrape_retailer_for_shoe(shoe, retailer)
                agg['shoes_scraped'] += 1
                agg['products_found'] += r.get('products_found', 0)
                agg['prices_recorded'] += r.get('prices_recorded', 0)
                agg['deals_found'] += r.get('deals_found', 0)
                if r.get('errors'):
                    agg['errors'].extend(r['errors'])
            except Exception as e:
                # scrape_retailer_for_shoe catches its own errors, so this is a
                # belt-and-suspenders guard — one shoe never wedges the run.
                msg = f"{shoe.brand} {shoe.model}: {e}"
                logger.error(f"[{retailer.name}] {msg}")
                agg['errors'].append(msg)

        run.finished_at = datetime.now(timezone.utc)
        run.status = "error" if agg['errors'] else "success"
        run.shoes_scraped = agg['shoes_scraped']
        run.products_found = agg['products_found']
        run.prices_recorded = agg['prices_recorded']
        run.deals_found = agg['deals_found']
        run.error = ("; ".join(agg['errors'])[:_SCRAPE_ERROR_MAX]) or None
        retailer.last_scraped_at = run.finished_at
        self.db.commit()

        return agg

    def scrape_shoe(self, shoe_id: int, retailer_ids: Optional[List[int]] = None) -> Dict:
        """
        Scrape prices for a specific shoe across retailers.

        Args:
            shoe_id: ID of shoe to scrape.
            retailer_ids: Optional list of retailer IDs to scrape (if None, scrape all active).
        """
        shoe = self.db.query(Shoe).filter(Shoe.id == shoe_id).first()
        if not shoe:
            return {'success': False, 'error': f'Shoe with ID {shoe_id} not found'}
        if not shoe.is_active:
            return {'success': False, 'error': f'Shoe {shoe.brand} {shoe.model} is not active'}

        logger.info(f"Scraping prices for {shoe.brand} {shoe.model} (msrp ${shoe.msrp})")

        query = self.db.query(Retailer).filter(
            Retailer.is_active == True, Retailer.scraping_enabled == True
        )
        if retailer_ids:
            query = query.filter(Retailer.id.in_(retailer_ids))
        retailers = query.all()

        results = {
            'shoe': f'{shoe.brand} {shoe.model}',
            'retailers_scraped': 0,
            'products_found': 0,
            'prices_recorded': 0,
            'deals_found': 0,
            'errors': [],
        }

        for retailer in retailers:
            try:
                r = self.scrape_retailer_for_shoe(shoe, retailer)
                results['retailers_scraped'] += 1
                results['products_found'] += r.get('products_found', 0)
                results['prices_recorded'] += r.get('prices_recorded', 0)
                results['deals_found'] += r.get('deals_found', 0)
                if r.get('errors'):
                    results['errors'].extend(r['errors'])
            except Exception as e:
                error_msg = f"Error scraping {retailer.name}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)

        return results

    def scrape_all_shoes(self, retailer_ids: Optional[List[int]] = None) -> Dict:
        """Scrape all active shoes across all retailers."""
        active_shoes = self.db.query(Shoe).filter(Shoe.is_active == True).all()
        logger.info(f"Starting scrape for {len(active_shoes)} active shoes")

        aggregated = {
            'total_shoes': len(active_shoes),
            'total_retailers_scraped': 0,
            'total_products_found': 0,
            'total_prices_recorded': 0,
            'total_deals_found': 0,
            'promo_codes_found': 0,
            'errors': [],
        }

        # Detect site-wide discount codes first so deals can reference them.
        try:
            promo_summary = self.detect_all_promo_codes()
            aggregated['promo_codes_found'] = promo_summary['codes_found']
            aggregated['errors'].extend(promo_summary['errors'])
        except Exception as e:
            logger.error(f"Promo detection failed: {e}")
            aggregated['errors'].append(f"Promo detection failed: {str(e)}")

        for shoe in active_shoes:
            results = self.scrape_shoe(shoe.id, retailer_ids)
            aggregated['total_retailers_scraped'] += results.get('retailers_scraped', 0)
            aggregated['total_products_found'] += results.get('products_found', 0)
            aggregated['total_prices_recorded'] += results.get('prices_recorded', 0)
            aggregated['total_deals_found'] += results.get('deals_found', 0)
            if results.get('errors'):
                aggregated['errors'].extend(results['errors'])

        return aggregated

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
                if self.store.upsert_promo_code(retailer, c):
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
                continue

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
