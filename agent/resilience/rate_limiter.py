"""Preemptive per-provider token-bucket rate limiter.

Throttles *before* a request is sent so we stay under the provider's advertised
RPM/TPM instead of learning the limit by hitting a 429. Caps come from the
parsed ``x-ratelimit-*`` headers when present (``rate_limit_tracker``), else from
static per-provider config caps. Sync (the API call path is sync, run in a
worker thread) and the wait is **interruptible** so a throttle never makes the
gateway look dead, with a hard ceiling so a misconfigured cap can't stall it.

Opt-in: a limiter constructed with ``enabled=False`` — or for a provider with no
known cap — returns immediately from :meth:`acquire`.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Mapping

from agent.rate_limit_tracker import RateLimitState

# Token-bucket dimensions are per-minute (RPM / TPM); the window is 60s.
_WINDOW_SECONDS = 60.0
_SLEEP_SLICE = 0.2


class _TokenBucket:
    """A leaky/token bucket allowing transient debt (tokens may go negative).

    Debt naturally throttles subsequent calls until refill catches up, which
    correctly handles a single request larger than the per-minute capacity.
    """

    __slots__ = ("capacity", "refill_per_sec", "tokens", "_last")

    def __init__(self, capacity: float, now: float) -> None:
        self.capacity = max(0.0, capacity)
        self.refill_per_sec = self.capacity / _WINDOW_SECONDS if self.capacity else 0.0
        self.tokens = self.capacity
        self._last = now

    def set_capacity(self, capacity: float, now: float) -> None:
        capacity = max(0.0, capacity)
        # Preserve the current "used" fraction loosely: clamp tokens to the new cap.
        self.capacity = capacity
        self.refill_per_sec = capacity / _WINDOW_SECONDS if capacity else 0.0
        if self.tokens > capacity:
            self.tokens = capacity
        self._last = now

    def _refill(self, now: float) -> None:
        if self.refill_per_sec <= 0:
            return
        elapsed = now - self._last
        if elapsed <= 0:
            return
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        self._last = now

    def time_until(self, need: float, now: float) -> float:
        """Seconds until ``need`` tokens are available (0 if available now)."""
        self._refill(now)
        if self.refill_per_sec <= 0:
            return 0.0  # no cap -> never throttle
        if self.tokens >= need:
            return 0.0
        return (need - self.tokens) / self.refill_per_sec

    def consume(self, need: float, now: float) -> None:
        self._refill(now)
        self.tokens -= need  # may go negative (debt)


class ProviderRateLimiter:
    def __init__(
        self,
        *,
        enabled: bool = True,
        static_limits: Mapping[str, Mapping[str, int]] | None = None,
        use_response_headers: bool = True,
        max_wait_seconds: float = 60.0,
    ) -> None:
        self._enabled = bool(enabled)
        self._use_headers = bool(use_response_headers)
        self._max_wait = max(0.0, float(max_wait_seconds))
        # provider -> (rpm, tpm)
        self._caps: dict[str, tuple[float, float]] = {}
        if static_limits:
            for prov, caps in static_limits.items():
                rpm = float(caps.get("rpm", 0) or 0)
                tpm = float(caps.get("tpm", 0) or 0)
                if rpm > 0 or tpm > 0:
                    self._caps[str(prov)] = (rpm, tpm)
        # provider -> (req_bucket, tok_bucket)
        self._buckets: dict[str, tuple[_TokenBucket, _TokenBucket]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def update_from_headers(self, provider: str, state: RateLimitState | None) -> None:
        """Seed/refresh a provider's caps from parsed rate-limit headers.

        Only trusts the headers when the provider matches and the limits are
        positive; otherwise leaves any static caps in place.
        """
        if not self._enabled or not self._use_headers or state is None:
            return
        if not state.has_data:
            return
        rpm = float(getattr(state.requests_min, "limit", 0) or 0)
        tpm = float(getattr(state.tokens_min, "limit", 0) or 0)
        if rpm <= 0 and tpm <= 0:
            return
        now = time.monotonic()
        with self._lock:
            prev = self._caps.get(provider, (0.0, 0.0))
            self._caps[provider] = (rpm or prev[0], tpm or prev[1])
            req_cap, tok_cap = self._caps[provider]
            buckets = self._buckets.get(provider)
            if buckets is None:
                self._buckets[provider] = (
                    _TokenBucket(req_cap, now),
                    _TokenBucket(tok_cap, now),
                )
            else:
                buckets[0].set_capacity(req_cap, now)
                buckets[1].set_capacity(tok_cap, now)

    def _ensure_buckets(
        self, provider: str, now: float
    ) -> tuple[_TokenBucket, _TokenBucket] | None:
        caps = self._caps.get(provider)
        if not caps:
            return None
        buckets = self._buckets.get(provider)
        if buckets is None:
            buckets = (_TokenBucket(caps[0], now), _TokenBucket(caps[1], now))
            self._buckets[provider] = buckets
        return buckets

    def acquire(
        self,
        provider: str,
        est_tokens: int = 0,
        *,
        should_interrupt: Callable[[], bool] | None = None,
        on_wait: Callable[[float], None] | None = None,
    ) -> float:
        """Block until a request to ``provider`` fits under its RPM/TPM.

        Returns the number of seconds actually waited (0.0 if no throttle).
        No-op (returns 0.0) when disabled or the provider has no known cap.
        """
        if not self._enabled:
            return 0.0
        need_tok = float(max(0, est_tokens))
        with self._lock:
            now = time.monotonic()
            buckets = self._ensure_buckets(provider, now)
            if buckets is None:
                return 0.0
            req_bucket, tok_bucket = buckets
            wait = max(
                req_bucket.time_until(1.0, now),
                tok_bucket.time_until(need_tok, now),
            )
            if wait <= 0:
                req_bucket.consume(1.0, now)
                tok_bucket.consume(need_tok, now)
                return 0.0
            wait = min(wait, self._max_wait)

        # Sleep OUTSIDE the lock so other providers aren't blocked.
        if on_wait is not None:
            try:
                on_wait(wait)
            except Exception:
                pass
        waited = 0.0
        deadline = time.monotonic() + wait
        while True:
            if should_interrupt is not None:
                try:
                    if should_interrupt():
                        break
                except Exception:
                    pass
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(_SLEEP_SLICE, remaining))
            waited += min(_SLEEP_SLICE, remaining)

        # Consume after waiting (best-effort; debt model self-corrects).
        with self._lock:
            now = time.monotonic()
            buckets = self._ensure_buckets(provider, now)
            if buckets is not None:
                buckets[0].consume(1.0, now)
                buckets[1].consume(need_tok, now)
        return waited

    def reset(self) -> None:
        """Drop all bucket state (tests)."""
        with self._lock:
            self._buckets.clear()
