"""Tests for the OPT-IN adaptive 429 cooldown in the credential pool.

When disabled (the default) the static EXHAUSTED_TTL_* constants apply, i.e.
legacy behavior is unchanged.
"""

import time as _time

import pytest

import agent.credential_pool as cp
from agent.credential_pool import (
    EXHAUSTED_TTL_429_SECONDS,
    STATUS_EXHAUSTED,
    CredentialPool,
    PooledCredential,
    _exhausted_until,
    set_adaptive_cooldown,
)
from agent.resilience import AdaptiveCooldownSettings


@pytest.fixture(autouse=True)
def _reset_adaptive():
    # Module-global: ensure no leak between tests.
    set_adaptive_cooldown(None)
    yield
    set_adaptive_cooldown(None)


def _entry(**kw) -> PooledCredential:
    base = dict(
        provider="openai",
        id="k1",
        label="k1",
        auth_type="api_key",
        priority=0,
        source="manual",
        access_token="sk-x",
    )
    base.update(kw)
    return PooledCredential(**base)


def test_disabled_uses_static_429_ttl():
    e = _entry(
        last_status=STATUS_EXHAUSTED,
        last_status_at=1000.0,
        last_error_code=429,
        extra={"consecutive_429": 5},
    )
    # Disabled (default) -> static 1h regardless of the counter.
    assert _exhausted_until(e) == 1000.0 + EXHAUSTED_TTL_429_SECONDS


def test_adaptive_grows_with_consecutive_and_caps():
    set_adaptive_cooldown(
        AdaptiveCooldownSettings(enabled=True, base_seconds=60, max_seconds=3600)
    )

    def ttl(n: int) -> float:
        e = _entry(
            last_status=STATUS_EXHAUSTED,
            last_status_at=1000.0,
            last_error_code=429,
            extra={"consecutive_429": n},
        )
        return _exhausted_until(e) - 1000.0

    # base * 2^(n-1) + jitter (jitter <= 0.5 * delay).
    assert 60 <= ttl(1) <= 90
    assert 120 <= ttl(2) <= 180
    assert 240 <= ttl(3) <= 360
    # Caps at max_seconds (soft cap: + up to 0.5*cap jitter).
    assert 3600 <= ttl(20) <= 5400


def test_provider_reset_at_still_wins():
    set_adaptive_cooldown(AdaptiveCooldownSettings(enabled=True))
    reset_at = _time.time() + 999
    e = _entry(
        last_status=STATUS_EXHAUSTED,
        last_status_at=1000.0,
        last_error_code=429,
        last_error_reset_at=reset_at,
        extra={"consecutive_429": 9},
    )
    assert _exhausted_until(e) == reset_at


def test_non_429_uses_static_even_when_enabled():
    set_adaptive_cooldown(AdaptiveCooldownSettings(enabled=True))
    e = _entry(last_status=STATUS_EXHAUSTED, last_status_at=1000.0, last_error_code=402)
    assert _exhausted_until(e) == 1000.0 + cp._exhausted_ttl(402)


def test_mark_exhausted_escalates_then_resets(monkeypatch):
    set_adaptive_cooldown(
        AdaptiveCooldownSettings(enabled=True, base_seconds=60, max_seconds=3600)
    )
    clock = {"t": 1000.0}
    monkeypatch.setattr(cp.time, "time", lambda: clock["t"])

    e0 = _entry()
    pool = CredentialPool("openai", [e0])
    monkeypatch.setattr(pool, "_persist", lambda *a, **k: None)

    u1 = pool._mark_exhausted(e0, 429)
    assert u1.extra["consecutive_429"] == 1

    u2 = pool._mark_exhausted(u1, 429)  # within window -> escalate
    assert u2.extra["consecutive_429"] == 2

    clock["t"] += 4000  # > max_seconds window -> isolated, reset
    u3 = pool._mark_exhausted(u2, 429)
    assert u3.extra["consecutive_429"] == 1


def test_mark_exhausted_no_extra_mutation_when_disabled(monkeypatch):
    # Disabled: _mark_exhausted must not inject the adaptive counter at all.
    e0 = _entry()
    pool = CredentialPool("openai", [e0])
    monkeypatch.setattr(pool, "_persist", lambda *a, **k: None)
    u1 = pool._mark_exhausted(e0, 429)
    assert "consecutive_429" not in (u1.extra or {})
