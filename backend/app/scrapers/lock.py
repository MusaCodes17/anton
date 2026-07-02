"""
Scrape lock primitives — prevent concurrent overlapping scrapes.

Scraping a full catalog easily takes 20-30+ minutes (47 shoes x up to 9
retailers, each request rate-limited with a sleep). The REST endpoints are
synchronous, so a frontend client that times out waiting (see ScrapeButton)
and retries — or two people clicking "Run scan" — would otherwise stack
unbounded concurrent full-catalog scrapes on top of each other with no
coordination, which is what actually produces "scraping forever": each
pass slows every other one down via shared rate limits and none of them
ever appear to finish. This lock makes that a clean, fast rejection
instead, across every entry point (REST + the MCP trigger_scrape tool).
"""
import threading
from contextlib import contextmanager

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
