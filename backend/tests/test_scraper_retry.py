"""
Tests for R4.2 per-request retry logic in BaseScraper._fetch_with_requests.

The retry wrapper should:
- Return the response on first-attempt success (no extra calls).
- Retry up to _RETRY_ATTEMPTS times on RequestException, then return None.
- Return the response if a retry succeeds after initial failure(s).
"""
from unittest.mock import MagicMock, patch, call
import requests

from app.scrapers.base_scraper import BaseScraper


class _ConcreteScraper(BaseScraper):
    """Minimal concrete subclass for testing base-class HTTP behaviour."""

    retailer_name = "Test"

    def search_products(self, brand, model):  # pragma: no cover
        return []

    def get_product_details(self, url):  # pragma: no cover
        return None


def _scraper():
    return _ConcreteScraper("Test", "https://example.com")


def test_success_on_first_attempt(monkeypatch):
    scraper = _scraper()
    mock_resp = MagicMock()
    mock_resp.text = "<html>ok</html>"
    mock_resp.raise_for_status = MagicMock()
    scraper.session.get = MagicMock(return_value=mock_resp)

    with patch("time.sleep"):
        result = scraper._fetch_with_requests("https://example.com/p")

    assert result == "<html>ok</html>"
    assert scraper.session.get.call_count == 1


def test_retries_on_failure_and_succeeds(monkeypatch):
    """First call raises, second returns successfully."""
    scraper = _scraper()
    good_resp = MagicMock()
    good_resp.text = "<html>ok</html>"
    good_resp.raise_for_status = MagicMock()

    scraper.session.get = MagicMock(
        side_effect=[requests.RequestException("timeout"), good_resp]
    )

    with patch("time.sleep"):
        result = scraper._fetch_with_requests("https://example.com/p")

    assert result == "<html>ok</html>"
    assert scraper.session.get.call_count == 2


def test_exhausts_retries_and_returns_none():
    """All attempts fail → None."""
    scraper = _scraper()
    scraper.session.get = MagicMock(
        side_effect=requests.RequestException("timeout")
    )

    with patch("time.sleep"):
        result = scraper._fetch_with_requests("https://example.com/p")

    assert result is None
    assert scraper.session.get.call_count == scraper._RETRY_ATTEMPTS + 1


def test_http_error_status_also_retried():
    """raise_for_status raises HTTPError (a RequestException subclass) → retried."""
    scraper = _scraper()
    bad_resp = MagicMock()
    bad_resp.raise_for_status = MagicMock(
        side_effect=requests.HTTPError("503 Service Unavailable")
    )
    scraper.session.get = MagicMock(return_value=bad_resp)

    with patch("time.sleep"):
        result = scraper._fetch_with_requests("https://example.com/p")

    assert result is None
    assert scraper.session.get.call_count == scraper._RETRY_ATTEMPTS + 1
