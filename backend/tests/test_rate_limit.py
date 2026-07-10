"""
Tests for the chat rate limiter (`services.rate_limit`) and the router
dependency that enforces it. The bucket is driven by an injected clock so time
is deterministic (no sleeps); the dependency test asserts the 429 + Retry-After
contract that stops an authenticated-but-looping client burning LLM credits.
"""
import types

import pytest
from fastapi import HTTPException

from app.routers import chat as chat_router
from app.services.rate_limit import KeyedRateLimiter, TokenBucket


class _Clock:
    """A hand-cranked monotonic clock for deterministic refill tests."""
    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_bucket_allows_up_to_capacity_then_denies():
    clock = _Clock()
    bucket = TokenBucket(capacity=3, refill_per_s=1.0, now=clock)
    assert [bucket.take().allowed for _ in range(3)] == [True, True, True]
    denied = bucket.take()
    assert denied.allowed is False
    # empty bucket, 1 token/s → ~1s until the next token
    assert denied.retry_after_s == pytest.approx(1.0)


def test_bucket_refills_over_time():
    clock = _Clock()
    bucket = TokenBucket(capacity=2, refill_per_s=2.0, now=clock)
    bucket.take(); bucket.take()               # drain
    assert bucket.take().allowed is False
    clock.advance(0.5)                         # 0.5s * 2/s = 1 token
    assert bucket.take().allowed is True
    assert bucket.take().allowed is False      # only one refilled
    clock.advance(10)                          # long wait caps at capacity, not beyond
    assert [bucket.take().allowed for _ in range(3)] == [True, True, False]


def test_keyed_limiter_isolates_clients():
    clock = _Clock()
    limiter = KeyedRateLimiter(capacity=1, refill_per_s=1.0, now=clock)
    assert limiter.take("10.0.0.1").allowed is True
    assert limiter.take("10.0.0.1").allowed is False   # that client is out
    assert limiter.take("10.0.0.2").allowed is True    # a different client is fresh


def _fake_request(host="10.0.0.9"):
    return types.SimpleNamespace(client=types.SimpleNamespace(host=host))


def test_dependency_raises_429_with_retry_after_when_exhausted(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(
        chat_router, "chat_limiter",
        KeyedRateLimiter(capacity=1, refill_per_s=1.0, now=clock),
    )
    req = _fake_request()
    chat_router.enforce_chat_rate_limit(req)  # first call: allowed, no raise
    with pytest.raises(HTTPException) as exc:
        chat_router.enforce_chat_rate_limit(req)  # second: over the limit
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "1"


def test_dependency_missing_client_uses_stable_key(monkeypatch):
    # request.client can be None (e.g. some ASGI test transports) — the key falls
    # back to a constant so the limiter still functions instead of crashing.
    monkeypatch.setattr(
        chat_router, "chat_limiter",
        KeyedRateLimiter(capacity=1, refill_per_s=1.0),
    )
    req = types.SimpleNamespace(client=None)
    chat_router.enforce_chat_rate_limit(req)
    with pytest.raises(HTTPException):
        chat_router.enforce_chat_rate_limit(req)
