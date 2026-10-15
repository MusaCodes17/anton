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


# --- R9.1: key-space cap -----------------------------------------------------

from app.services import rate_limit as rate_limit_module  # noqa: E402


def test_bucket_is_full_reports_refilled_state():
    clock = _Clock()
    bucket = TokenBucket(capacity=2, refill_per_s=1.0, now=clock)
    assert bucket.is_full(clock.t) is True
    bucket.take(); bucket.take()
    assert bucket.is_full(clock.t) is False
    clock.advance(2.0)                         # 2 tokens back, capacity reached
    assert bucket.is_full(clock.t) is True


def test_keyed_limiter_stays_bounded_when_keys_refill_to_full():
    # 50 one-shot clients at a cap of 5. Each bucket is spent, then the clock
    # advances enough to refill it, so it is full and evictable at the next sweep.
    clock = _Clock()
    limiter = KeyedRateLimiter(capacity=1, refill_per_s=1.0, now=clock, max_keys=5)
    for i in range(50):
        assert limiter.take(f"10.0.0.{i}").allowed is True
        clock.advance(1.0)
        assert len(limiter) <= 5 + 1
    assert len(limiter) <= 5 + 1


def test_throttled_key_survives_eviction_sweep(caplog):
    # `hot` is drained and the clock is frozen, so it stays throttled. New keys are
    # created full (tokens=0 spends nothing) so each sweep has something to evict —
    # the sweep must drop those and keep `hot`, or an abusive client gets a free reset.
    clock = _Clock()
    limiter = KeyedRateLimiter(capacity=1, refill_per_s=1.0, now=clock, max_keys=3)
    assert limiter.take("hot").allowed is True
    assert limiter.take("hot").allowed is False
    for i in range(20):
        assert limiter.take(f"new-{i}", tokens=0).allowed is True
    assert len(limiter) <= 3 + 1
    assert limiter.take("hot").allowed is False


def test_all_throttled_at_cap_admits_new_key_soft_cap(caplog):
    clock = _Clock()
    limiter = KeyedRateLimiter(capacity=1, refill_per_s=1.0, now=clock, max_keys=2)
    for key in ("a", "b"):
        assert limiter.take(key).allowed is True
        assert limiter.take(key).allowed is False      # both throttled, none evictable
    with caplog.at_level("WARNING", logger=rate_limit_module.__name__):
        result = limiter.take("c")
    assert result.allowed is True                      # new key still served
    assert len(limiter) == 2 + 1                       # soft cap: one over
    assert any("rate limiter at cap" in r.getMessage() for r in caplog.records)


def test_max_keys_env_tunable(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_MAX_KEYS", raising=False)
    assert rate_limit_module._max_keys() == 10_000
    monkeypatch.setenv("RATE_LIMIT_MAX_KEYS", "7")
    assert rate_limit_module._max_keys() == 7


# --- R9.5: peek does not spend (global login ceiling) ------------------------

def test_peek_does_not_spend_tokens():
    clock = _Clock()
    bucket = TokenBucket(capacity=1, refill_per_s=1.0, now=clock)
    assert bucket.peek().allowed is True
    assert bucket.peek().allowed is True          # still there: peek spent nothing
    assert bucket.take().allowed is True          # the one token is intact
    assert bucket.take().allowed is False


def test_peek_reports_retry_when_empty():
    clock = _Clock()
    bucket = TokenBucket(capacity=1, refill_per_s=0.5, now=clock)
    assert bucket.take().allowed is True
    result = bucket.peek()
    assert result.allowed is False
    assert result.retry_after_s == pytest.approx(2.0)   # 1 token at 0.5/s
    clock.advance(2.0)
    assert bucket.peek().allowed is True
