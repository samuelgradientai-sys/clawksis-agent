"""Tests for the per-provider circuit breaker (mirror of the MCP breaker)."""

import agent.resilience.circuit_breaker as cb_mod
from agent.resilience.circuit_breaker import ProviderCircuitBreaker, make_key


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t


def test_make_key():
    assert make_key("openai") == "openai"
    assert make_key("openai", "cred1") == "openai:cred1"
    assert make_key(None) == "unknown"


def test_closed_until_threshold():
    b = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=60)
    assert b.is_open("p") is False
    b.record_failure("p")
    b.record_failure("p")
    assert b.state("p") == "closed"
    assert b.is_open("p") is False


def test_opens_at_threshold_and_short_circuits():
    b = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=60)
    for _ in range(3):
        b.record_failure("p")
    assert b.state("p") == "open"
    assert b.is_open("p") is True


def test_half_open_after_cooldown_then_close_on_success(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(cb_mod.time, "monotonic", clock.monotonic)
    b = ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=30)
    b.record_failure("p")
    b.record_failure("p")
    assert b.is_open("p") is True  # open within cooldown
    clock.t += 31  # cooldown elapsed
    assert b.state("p") == "half-open"
    assert b.is_open("p") is False  # probe allowed
    b.record_success("p")  # probe succeeded
    assert b.state("p") == "closed"


def test_half_open_probe_failure_rearms(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(cb_mod.time, "monotonic", clock.monotonic)
    b = ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=30)
    b.record_failure("p")
    b.record_failure("p")
    clock.t += 31
    assert b.is_open("p") is False  # half-open
    b.record_failure("p")  # probe failed -> re-arm
    assert b.is_open("p") is True
    assert b.state("p") == "open"


def test_success_resets_count():
    b = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=60)
    b.record_failure("p")
    b.record_failure("p")
    b.record_success("p")
    b.record_failure("p")
    assert b.state("p") == "closed"  # count restarted from 0


def test_disabled_is_noop():
    b = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=60, enabled=False)
    b.record_failure("p")
    b.record_failure("p")
    assert b.is_open("p") is False
    assert b.state("p") == "closed"


def test_keys_isolated():
    b = ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    b.record_failure("a")
    b.record_failure("a")
    assert b.is_open("a") is True
    assert b.is_open("b") is False
