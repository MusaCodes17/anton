"""
Scraper registry — maps retailer names to scraper instances.

Bespoke subclasses take priority over dynamically-built generic scrapers.
Dynamic scrapers are built from the retailer row's platform + scraper_config
for retailers that don't have a hand-written subclass.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Retailer
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.the_last_hunt import TheLastHuntScraper
from app.scrapers.jd_sports import JDSportsScraper
from app.scrapers.altitude_sports import AltitudeSportsScraper
from app.scrapers.boutique_endurance import BoutiqueEnduranceScraper
from app.scrapers.le_coureur import LeCoureurScraper
from app.scrapers.blacktoe_running import BlackToeRunningScraper
from app.scrapers.forerunners import ForeRunnersScraper
from app.scrapers.enroute_run import EnRouteRunScraper
from app.scrapers.sail import SailScraper
from app.scrapers.shopify_scraper import ShopifyScraper
from app.scrapers.algolia_scraper import AlgoliaScraper

logger = logging.getLogger(__name__)

# Keyed by retailer.name as stored in the DB (see seed_data.py).
# Values are classes — instantiated lazily by build_registry().
BESPOKE_SCRAPERS: dict[str, type[BaseScraper]] = {
    'The Last Hunt': TheLastHuntScraper,
    'JD Sports Canada': JDSportsScraper,
    'Altitude Sports': AltitudeSportsScraper,
    'Boutique Endurance': BoutiqueEnduranceScraper,
    'Le Coureur': LeCoureurScraper,
    'BlackToe Running': BlackToeRunningScraper,
    'ForeRunners': ForeRunnersScraper,
    'En Route Run': EnRouteRunScraper,
    'SAIL': SailScraper,
}


def build_dynamic_scraper(retailer: Retailer) -> Optional[BaseScraper]:
    """
    Build a generic ShopifyScraper/AlgoliaScraper instance straight from a
    Retailer row's platform + scraper_config — no subclass file needed.

    Used for retailers that don't have one of the hand-written subclasses.
    Returns None for platform="custom" or if Algolia credentials are missing.
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


def get_scraper(retailer: Retailer) -> Optional[BaseScraper]:
    """
    Return a scraper for the given retailer: bespoke subclass by name first,
    else a dynamically-built generic scraper by platform, else None.
    """
    cls = BESPOKE_SCRAPERS.get(retailer.name)
    if cls is not None:
        return cls()
    return build_dynamic_scraper(retailer)


def build_registry(db: Session) -> dict[str, BaseScraper]:
    """
    Build the full name→scraper map for all scrapable retailers.

    Bespoke scrapers are instantiated for every known name. Dynamic scrapers
    are built from the DB for any shopify/algolia retailer not already covered.
    Rebuilt from the DB on every construction, so newly-created retailers get
    a working scraper immediately without any extra in-memory registry.
    """
    registry: dict[str, BaseScraper] = {
        name: cls() for name, cls in BESPOKE_SCRAPERS.items()
    }

    dynamic_candidates = db.query(Retailer).filter(
        Retailer.platform.in_(["shopify", "algolia"])
    ).all()

    for retailer in dynamic_candidates:
        if retailer.name in registry:
            continue
        scraper = build_dynamic_scraper(retailer)
        if scraper:
            registry[retailer.name] = scraper

    return registry
