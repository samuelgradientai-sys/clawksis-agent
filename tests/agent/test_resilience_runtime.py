"""Tests for the process-global resilience runtime + the rate-limit chokepoint."""

import types

import pytest

import agent.chat_completion_helpers as cch
import agent.credential_pool as cp
from agent.resilience.runtime import (
    get_circuit_breaker,
    get_rate_limiter,
    install_resilience_runtime,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_runtime():
    reset_for_tests()
    yield
    reset_for_tests()


def test_disabled_by_default():
    install_resilience_runtime({})
    assert get_rate_limiter() is None
    assert get_circuit_breaker() is None


def test_enables_limiter_and_breaker_from_config():
    install_resilience_runtime({
        "resilience": {
            "rate_limits": {"enabled": True, "providers": {"p": {"rpm": 10}}},
            "circuit_breaker": {"enabled": True, "failure_threshold": 2},
        }
    })
    assert get_rate_limiter() is not None
    breaker = get_circuit_breaker()
    assert breaker is not None and breaker.enabled is True


def test_install_sets_and_clears_adaptive_cooldown():
    install_resilience_runtime({"resilience": {"adaptive_cooldown": {"enabled": True}}})
    assert cp._adaptive_cfg is not None
    # Reinstall with adaptive off -> the pool's adaptive cooldown is cleared.
    install_resilience_runtime({"resilience": {}}, force=True)
    assert cp._adaptive_cfg is None


def test_install_idempotent_without_force():
    install_resilience_runtime({"resilience": {"rate_limits": {"enabled": True}}})
    first = get_rate_limiter()
    # Second call (different config) is ignored without force.
    install_resilience_runtime({"resilience": {}})
    assert get_rate_limiter() is first


def test_apply_rate_limit_calls_acquire_when_enabled(monkeypatch):
    install_resilience_runtime({
        "resilience": {
            "rate_limits": {"enabled": True, "providers": {"p": {"tpm": 1000}}}
        }
    })
    limiter = get_rate_limiter()
    assert limiter is not None
    calls = []
    monkeypatch.setattr(
        limiter,
        "acquire",
        lambda provider, est=0, **kw: calls.append((provider, est)) or 0.0,
    )
    monkeypatch.setattr(cch, "estimate_request_context_tokens", lambda kw: 123)
    agent = types.SimpleNamespace(
        provider="p", _interrupt_requested=False, _buffer_status=lambda *a, **k: None
    )
    cch._apply_rate_limit(agent, {"messages": []})
    assert calls == [("p", 123)]


def test_apply_rate_limit_noop_when_disabled():
    install_resilience_runtime({"resilience": {}})
    agent = types.SimpleNamespace(
        provider="p", _interrupt_requested=False, _buffer_status=lambda *a, **k: None
    )
    # Must not raise and must not throttle (limiter is None).
    cch._apply_rate_limit(agent, {"messages": []})


def test_apply_rate_limit_never_raises(monkeypatch):
    # Even if the limiter blows up, the request path must be unaffected.
    install_resilience_runtime({
        "resilience": {"rate_limits": {"enabled": True, "providers": {"p": {"rpm": 1}}}}
    })
    limiter = get_rate_limiter()

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(limiter, "acquire", _boom)
    agent = types.SimpleNamespace(
        provider="p", _interrupt_requested=False, _buffer_status=lambda *a, **k: None
    )
    cch._apply_rate_limit(agent, {"messages": []})  # swallowed
