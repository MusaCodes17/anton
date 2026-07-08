"""
In-process rate limiting — the R2.1-adjacent throttle (roadmap R2, SECURITY_PASS_PLAN §6).

R2.1 stopped *anonymous* LLM spend (a bearer token now gates `/api`). It does
**not** stop an *authenticated* client — the SPA with a retry bug, a user's own
script, a runaway agent loop — from hammering `POST /api/chat/message` and
burning the owner's paid Anthropic/OpenAI/Gemini credits. This module is that
backstop: a token-bucket limiter that caps the request rate per client.

Deliberately **not** a security boundary — `app/middleware/auth.py` is. Under the
single-user LAN threat model the realistic adversary is a *bug*, not a botnet, so
this bounds accidental spend and loops, not a hostile flood.

Single-process by design (CLAUDE.md §4.6 / design_decisions D4/E5): the bucket
state lives in memory, exactly like the scrape lock and the SSE state. If Anton
ever grows a second worker this — like the scrape lock — needs DB-level
coordination; that is out of scope until a scheduler exists (R4.1), and is
labelled here rather than solved silently.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class RateLimitResult:
    """Outcome of one `take()`. `retry_after_s` is the wait until the next token
    would be available (0.0 when the request was allowed)."""
    allowed: bool
    retry_after_s: float


class TokenBucket:
    """
    A classic token bucket: `capacity` tokens, refilled at `refill_per_s`
    tokens/second, one token spent per request. Bursts up to `capacity` are
    allowed; the sustained rate is capped at `refill_per_s`.

    Thread-safe — FastAPI may run the enforcing dependency in a threadpool
    worker, and the same bucket can be hit concurrently. `now` is injectable so
    tests drive time deterministically instead of sleeping.
    """

    def __init__(self, *, capacity: float, refill_per_s: float,
                 now: Callable[[], float] = time.monotonic):
        self.capacity = float(capacity)
        self.refill_per_s = float(refill_per_s)
        self._now = now
        self._tokens = float(capacity)
        self._updated = now()
        self._lock = threading.Lock()

    def _refill(self, t: float) -> None:
        elapsed = t - self._updated
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_s)
            self._updated = t

    def take(self, tokens: float = 1.0) -> RateLimitResult:
        """Spend `tokens` if available; otherwise deny with the wait until enough
        have refilled. Never blocks — it reports, the caller decides (429)."""
        with self._lock:
            self._refill(self._now())
            if self._tokens >= tokens:
                self._tokens -= tokens
                return RateLimitResult(True, 0.0)
            deficit = tokens - self._tokens
            retry = deficit / self.refill_per_s if self.refill_per_s > 0 else float("inf")
            return RateLimitResult(False, retry)


class KeyedRateLimiter:
    """
    One `TokenBucket` per key (e.g. client IP), created lazily on first use so
    each client gets its own allowance. At single-user LAN scale the key space is
    a handful of devices, so a plain dict under a lock is right — no eviction
    policy is needed (bounded by the owner's device count). If this were ever
    exposed to an open network the unbounded dict would need capping; it isn't.
    """

    def __init__(self, *, capacity: float, refill_per_s: float,
                 now: Callable[[], float] = time.monotonic):
        self._capacity = capacity
        self._refill_per_s = refill_per_s
        self._now = now
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def take(self, key: str, tokens: float = 1.0) -> RateLimitResult:
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(
                    capacity=self._capacity,
                    refill_per_s=self._refill_per_s,
                    now=self._now,
                )
                self._buckets[key] = bucket
        return bucket.take(tokens)


def _build_chat_limiter() -> KeyedRateLimiter:
    """The chat-endpoint limiter, configured from the environment at import.

    Default 20 requests/minute with a burst of 20: a human sends a handful of
    chat turns per minute, so 20/min is generous for real use and a hard stop for
    a runaway loop (which does hundreds). Tune via `CHAT_RATE_LIMIT_PER_MINUTE`
    (sustained rate) and `CHAT_RATE_LIMIT_BURST` (bucket capacity)."""
    per_min = float(os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "20"))
    burst = float(os.getenv("CHAT_RATE_LIMIT_BURST", str(per_min)))
    return KeyedRateLimiter(capacity=burst, refill_per_s=per_min / 60.0)


# Module singleton wired into routers/chat.py. Tests build their own instances
# with an injected clock rather than poking this one.
chat_limiter = _build_chat_limiter()
