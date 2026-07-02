"""
Backward-compat shim — re-exports everything that existing importers
(routers/scraping.py, scrape_runner.py, mcp_server.py, test_scraper.py)
expect from this module. The real implementations live in:

  app/scrapers/lock.py        — lock primitives
  app/scrapers/registry.py    — scraper registry + build_dynamic_scraper
  app/scrapers/deal_store.py  — DealStore (all DB writes)
  app/scrapers/orchestrator.py — ScrapeOrchestrator (orchestration logic)

Remove this shim once every importer has been updated to import directly
from those modules.
"""
from app.scrapers.orchestrator import ScrapeOrchestrator as ScraperManager  # noqa: F401
from app.scrapers.lock import (  # noqa: F401
    _scrape_lock,
    ScrapeInProgressError,
    scrape_guard,
    try_acquire_scrape_lock,
    release_scrape_lock,
    is_scrape_running,
)
from app.scrapers.registry import build_dynamic_scraper  # noqa: F401

__all__ = [
    "ScraperManager",
    "_scrape_lock",
    "ScrapeInProgressError",
    "scrape_guard",
    "try_acquire_scrape_lock",
    "release_scrape_lock",
    "is_scrape_running",
    "build_dynamic_scraper",
]
