"""
Scraper registry — maps retailer names to scraper instances.

Bespoke subclasses take priority over dynamically-built generic scrapers.
Dynamic scrapers are built from the retailer row's platform + scraper_config
for retailers that don't have a hand-written subclass.
"""
import logging
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

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
from app.scrapers.boutique_courir import BoutiqueCourirScraper
from app.scrapers.champs_sports import ChampsSportsScraper
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
    'Boutique Courir': BoutiqueCourirScraper,
    'Champs Sports Canada': ChampsSportsScraper,
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


def _host(url: Optional[str]) -> str:
    """Bare host of a URL, lower-cased, without a leading 'www.'."""
    host = (urlparse(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


@lru_cache(maxsize=1)
def _bespoke_by_host() -> dict[str, type[BaseScraper]]:
    """Host -> bespoke class, read from each subclass's own base_url.

    Construction is cheap (a requests.Session, no network, no browser), and it
    keeps the scraper file as the one place the host is written down.
    """
    return {_host(cls().base_url): cls for cls in BESPOKE_SCRAPERS.values()}


def bespoke_class_for(retailer: Retailer) -> Optional[type[BaseScraper]]:
    """The hand-written scraper for a retailer row: by exact name, else by host.

    The name key alone is fragile: a retailer added through the UI or the
    onboarding flow gets whatever name was typed. Production's Champs row is
    "Champs Sports" while the code says "Champs Sports Canada", and the
    mismatch made every scrape fail with "No scraper implemented". The site's
    host is what the scraper is actually written against, so it is the
    fallback key.
    """
    cls = BESPOKE_SCRAPERS.get(retailer.name)
    if cls is not None:
        return cls
    host = _host(retailer.base_url)
    return _bespoke_by_host().get(host) if host else None


def get_scraper(retailer: Retailer) -> Optional[BaseScraper]:
    """
    Return a scraper for the given retailer: bespoke subclass by name or host
    first, else a dynamically-built generic scraper by platform, else None.
    """
    cls = bespoke_class_for(retailer)
    if cls is not None:
        return cls()
    return build_dynamic_scraper(retailer)


def build_registry(db: Session) -> dict[str, BaseScraper]:
    """
    Build the full name→scraper map for all scrapable retailers.

    Bespoke scrapers are instantiated for every known name, then for any DB
    row whose name differs but whose host matches a bespoke scraper (see
    bespoke_class_for). Dynamic scrapers are built from the DB for any
    shopify/algolia retailer not already covered.
    Rebuilt from the DB on every construction, so newly-created retailers get
    a working scraper immediately without any extra in-memory registry.
    """
    registry: dict[str, BaseScraper] = {
        name: cls() for name, cls in BESPOKE_SCRAPERS.items()
    }

    for retailer in db.query(Retailer).all():
        if retailer.name in registry:
            continue
        scraper = get_scraper(retailer)
        if scraper:
            registry[retailer.name] = scraper

    return registry
