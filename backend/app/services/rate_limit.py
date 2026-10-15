"""
In-process rate limiting (roadmap R2 / RA1.3).

Four limiters live here, each scoped to a different threat:

1. `chat_limiter` — caps `POST /api/chat/message` per client IP to prevent a
   runaway authenticated loop from burning paid LLM credits (R2.1-adjacent).
   Adversary model: a bug, not a botnet. Tunable via `CHAT_RATE_LIMIT_*` env vars.

2. `auth_failure_limiter` — caps bearer-token failures (401s from auth middleware)
   per client IP. Adversary model: credential-stuffing bots. Goal: make a brute-
   force attempt slow and visible in the log before it succeeds (RA1.3).
   Tunable via `AUTH_FAILURE_LIMIT_PER_MINUTE` / `AUTH_FAILURE_BURST`.

3. `login_failure_limiter` — caps `POST /oauth/login` password failures per client
   IP. Adversary model: brute-force against the single-user OAuth login page.
   Tunable via `LOGIN_FAILURE_LIMIT_PER_MINUTE` / `LOGIN_FAILURE_BURST`.

4. `public_limiter` — caps `GET /api/public/deals` per client IP (R9.3). Adversary
   model: scraping/hammering of the one deliberately public data endpoint.
   Tunable via `PUBLIC_RATE_LIMIT_PER_MINUTE` / `PUBLIC_RATE_LIMIT_BURST`.

All limiters are deliberately **not** security boundaries alone — they are
visibility and throttling aids. `app/middleware/auth.py` is the boundary.

Single-process by design (CLAUDE.md §4.6 / design_decisions D4/E8/INV-9): the
bucket state lives in memory. If Anton ever grows a second worker these — like
the scrape lock — need DB-level coordination; that is out of scope until a
scheduler exists (R4.1), and is labelled here rather than solved silently.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


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

    def is_full(self, t: float) -> bool:
        """True when the bucket would be at `capacity` at time `t` (refilled to `t`).
        A full bucket is indistinguishable from a fresh one, so the keyed limiter
        may evict it without changing any later decision."""
        with self._lock:
            self._refill(t)
            return self._tokens >= self.capacity


class KeyedRateLimiter:
    """
    One `TokenBucket` per key (e.g. client IP), created lazily on first use so
    each client gets its own allowance.

    The dict is capped at `max_keys` (R9.1): the public deals page puts the key
    space on the open internet, so an unbounded dict would be a memory-growth
    vector. When a new key arrives at the cap, buckets that are full are swept
    out — a full bucket is indistinguishable from a fresh one, so evicting it
    changes no future decision. Throttled buckets are never evicted: resetting an
    abusive client's bucket would hand it a free burst. If every bucket is
    throttled the sweep frees nothing and the new key is still admitted, so the
    cap is soft in that pathological case (logged as a WARNING).
    """

    def __init__(self, *, capacity: float, refill_per_s: float,
                 now: Callable[[], float] = time.monotonic,
                 max_keys: int = 10_000):
        self._capacity = capacity
        self._refill_per_s = refill_per_s
        self._now = now
        self._max_keys = max_keys
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buckets)

    def take(self, key: str, tokens: float = 1.0) -> RateLimitResult:
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self._max_keys:
                    self._evict_full_buckets()
                bucket = TokenBucket(
                    capacity=self._capacity,
                    refill_per_s=self._refill_per_s,
                    now=self._now,
                )
                self._buckets[key] = bucket
        return bucket.take(tokens)

    def _evict_full_buckets(self) -> None:
        """Drop every full bucket. Caller holds `self._lock`.

        Runs only when a new key arrives at the cap. The scan is O(n) over at
        most `max_keys` entries — a labelled full pass, acceptable at personal
        scale. It is NOT amortised: if every bucket stays throttled, each new key
        at the cap repeats the scan (still bounded by `max_keys`). The sanctioned
        escape if that ever budgets badly is an LRU/time-indexed structure, not a
        larger cap."""
        now = self._now()
        for key in [k for k, b in self._buckets.items() if b.is_full(now)]:
            del self._buckets[key]
        if len(self._buckets) >= self._max_keys:
            logger.warning(
                "rate limiter at cap (%d keys, max_keys=%d) with no full buckets "
                "to evict; admitting new key over the soft cap",
                len(self._buckets), self._max_keys,
            )


def _max_keys() -> int:
    """Per-limiter key cap (R9.1). Tune via `RATE_LIMIT_MAX_KEYS`; default 10000
    comfortably exceeds any real client population for this app."""
    return int(os.getenv("RATE_LIMIT_MAX_KEYS", "10000"))


def _build_chat_limiter() -> KeyedRateLimiter:
    """The chat-endpoint limiter, configured from the environment at import.

    Default 20 requests/minute with a burst of 20: a human sends a handful of
    chat turns per minute, so 20/min is generous for real use and a hard stop for
    a runaway loop (which does hundreds). Tune via `CHAT_RATE_LIMIT_PER_MINUTE`
    (sustained rate) and `CHAT_RATE_LIMIT_BURST` (bucket capacity)."""
    per_min = float(os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "20"))
    burst = float(os.getenv("CHAT_RATE_LIMIT_BURST", str(per_min)))
    return KeyedRateLimiter(capacity=burst, refill_per_s=per_min / 60.0,
                            max_keys=_max_keys())


def _build_auth_failure_limiter() -> KeyedRateLimiter:
    """Per-IP limiter for bearer-token 401 failures (RA1.3).

    Default: 10 failures allowed in a burst, refilling at 10/minute (one every
    6 seconds). A legitimate client should never fail auth more than once; this
    allows a handful of mis-configured retries while throttling a brute-force
    attempt to 1 test/6 seconds after the initial burst is exhausted.
    Tune via `AUTH_FAILURE_LIMIT_PER_MINUTE` / `AUTH_FAILURE_BURST`."""
    per_min = float(os.getenv("AUTH_FAILURE_LIMIT_PER_MINUTE", "10"))
    burst = float(os.getenv("AUTH_FAILURE_BURST", str(per_min)))
    return KeyedRateLimiter(capacity=burst, refill_per_s=per_min / 60.0,
                            max_keys=_max_keys())


def _build_login_failure_limiter() -> KeyedRateLimiter:
    """Per-IP limiter for OAuth login-page password failures (RA1.3).

    Default: 5 failures allowed in a burst, refilling at 5/minute. A legitimate
    user never fails the password more than once or twice; this stops a brute-
    force against the single-user login page. Tune via
    `LOGIN_FAILURE_LIMIT_PER_MINUTE` / `LOGIN_FAILURE_BURST`."""
    per_min = float(os.getenv("LOGIN_FAILURE_LIMIT_PER_MINUTE", "5"))
    burst = float(os.getenv("LOGIN_FAILURE_BURST", str(per_min)))
    return KeyedRateLimiter(capacity=burst, refill_per_s=per_min / 60.0,
                            max_keys=_max_keys())


def _build_public_limiter() -> KeyedRateLimiter:
    """Per-IP limiter for the public deals endpoint (R9.3).

    Default 60 requests/minute with a burst of 60: the page is cached for 5
    minutes by browsers, so a human never gets near this; it only bites a
    scraper loop. Tune via `PUBLIC_RATE_LIMIT_PER_MINUTE` / `PUBLIC_RATE_LIMIT_BURST`."""
    per_min = float(os.getenv("PUBLIC_RATE_LIMIT_PER_MINUTE", "60"))
    burst = float(os.getenv("PUBLIC_RATE_LIMIT_BURST", str(per_min)))
    return KeyedRateLimiter(capacity=burst, refill_per_s=per_min / 60.0,
                            max_keys=_max_keys())


# Module singletons. Tests build their own instances with an injected clock
# rather than poking these (avoids inter-test state leakage).
chat_limiter = _build_chat_limiter()
auth_failure_limiter = _build_auth_failure_limiter()
login_failure_limiter = _build_login_failure_limiter()
public_limiter = _build_public_limiter()
