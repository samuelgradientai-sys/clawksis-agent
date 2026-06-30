"""Tests for the preemptive per-provider token-bucket rate limiter."""

import agent.resilience.rate_limiter as rl_mod
from agent.rate_limit_tracker import RateLimitBucket, RateLimitState
from agent.resilience.rate_limiter import ProviderRateLimiter


class _Clock:
    """Fake monotonic clock; sleep() advances it (no real delay)."""

    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def _patch_clock(monkeypatch) -> _Clock:
    clock = _Clock()
    monkeypatch.setattr(rl_mod.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(rl_mod.time, "sleep", clock.sleep)
    return clock


def test_disabled_returns_zero(monkeypatch):
    _patch_clock(monkeypatch)
    rl = ProviderRateLimiter(enabled=False, static_limits={"p": {"rpm": 1}})
    assert rl.acquire("p", 10) == 0.0


def test_no_cap_provider_returns_zero(monkeypatch):
    _patch_clock(monkeypatch)
    rl = ProviderRateLimiter(enabled=True, static_limits={})
    assert rl.acquire("unknown", 10) == 0.0


def test_token_cap_forces_wait(monkeypatch):
    clock = _patch_clock(monkeypatch)
    # tpm=60 -> token capacity 60, refill 1 tok/sec. rpm absent -> no req throttle.
    rl = ProviderRateLimiter(
        enabled=True, static_limits={"p": {"tpm": 60}}, max_wait_seconds=120
    )
    # First call drains the 60-token bucket.
    assert rl.acquire("p", 60) == 0.0
    # Second call needs 60 more; refill is 1/sec -> ~60s wait.
    waited = rl.acquire("p", 60)
    assert 59.0 <= waited <= 61.0
    assert clock.t >= 1060.0  # clock advanced via fake sleep


def test_max_wait_ceiling(monkeypatch):
    _patch_clock(monkeypatch)
    rl = ProviderRateLimiter(
        enabled=True, static_limits={"p": {"tpm": 60}}, max_wait_seconds=5
    )
    rl.acquire("p", 60)  # drain
    waited = rl.acquire("p", 600)  # would need 600s, capped at 5
    assert waited <= 5.5


def test_request_cap_forces_wait(monkeypatch):
    _patch_clock(monkeypatch)
    # rpm=60 -> 60 request capacity, refill 1/sec.
    rl = ProviderRateLimiter(
        enabled=True, static_limits={"p": {"rpm": 60}}, max_wait_seconds=120
    )
    for _ in range(60):
        assert rl.acquire("p", 0) == 0.0  # drain the request bucket
    waited = rl.acquire("p", 0)  # 61st request must wait ~1s
    assert 0.5 <= waited <= 1.5


def test_interrupt_breaks_wait(monkeypatch):
    _patch_clock(monkeypatch)
    rl = ProviderRateLimiter(
        enabled=True, static_limits={"p": {"tpm": 60}}, max_wait_seconds=120
    )
    rl.acquire("p", 60)  # drain
    waited = rl.acquire("p", 60, should_interrupt=lambda: True)
    assert waited == 0.0  # interrupted immediately


def test_update_from_headers_sets_cap(monkeypatch):
    _patch_clock(monkeypatch)
    rl = ProviderRateLimiter(enabled=True, static_limits={}, use_response_headers=True)
    # No cap yet -> no throttle.
    assert rl.acquire("anthropic", 1000) == 0.0
    state = RateLimitState(
        tokens_min=RateLimitBucket(limit=60, remaining=0, reset_seconds=60),
        captured_at=1.0,
        provider="anthropic",
    )
    rl.update_from_headers("anthropic", state)
    rl.acquire("anthropic", 60)  # drain to ~0
    waited = rl.acquire("anthropic", 60)
    assert waited > 0.0  # now throttles from header-derived cap


def test_on_wait_callback(monkeypatch):
    _patch_clock(monkeypatch)
    rl = ProviderRateLimiter(
        enabled=True, static_limits={"p": {"tpm": 60}}, max_wait_seconds=120
    )
    rl.acquire("p", 60)
    seen = []
    rl.acquire("p", 60, on_wait=lambda w: seen.append(w))
    assert seen and seen[0] > 0.0
