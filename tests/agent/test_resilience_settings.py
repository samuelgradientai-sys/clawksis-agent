"""Tests for agent.resilience settings parsing (opt-in, defensive)."""

from agent.resilience import ResilienceSettings, get_resilience_settings


def test_none_config_all_disabled():
    s = get_resilience_settings(None)
    assert isinstance(s, ResilienceSettings)
    assert s.any_enabled is False
    assert s.circuit_breaker.enabled is False
    assert s.rate_limits.enabled is False
    assert s.adaptive_cooldown.enabled is False
    assert s.auto_restore_primary is False
    assert s.durable_turns.enabled is False


def test_missing_block_all_disabled():
    assert get_resilience_settings({"other": 1}).any_enabled is False


def test_garbage_block_all_disabled():
    assert get_resilience_settings({"resilience": "nope"}).any_enabled is False
    assert get_resilience_settings({"resilience": 123}).any_enabled is False


def test_partial_block_parsed_with_defaults():
    s = get_resilience_settings({
        "resilience": {
            "circuit_breaker": {"enabled": True, "failure_threshold": 5},
            "auto_restore_primary": True,
        }
    })
    assert s.circuit_breaker.enabled is True
    assert s.circuit_breaker.failure_threshold == 5
    assert s.circuit_breaker.cooldown_seconds == 60.0  # default kept
    assert s.auto_restore_primary is True
    assert s.rate_limits.enabled is False
    assert s.any_enabled is True


def test_rate_limit_providers_parsed():
    s = get_resilience_settings({
        "resilience": {
            "rate_limits": {
                "enabled": True,
                "providers": {
                    "anthropic": {"rpm": 50, "tpm": 40000},
                    "bad": "nope",  # ignored
                },
                "use_response_headers": False,
            }
        }
    })
    assert s.rate_limits.enabled is True
    assert s.rate_limits.use_response_headers is False
    assert s.rate_limits.providers["anthropic"] == {"rpm": 50, "tpm": 40000}
    assert "bad" not in s.rate_limits.providers


def test_threshold_floor_and_bad_types():
    s = get_resilience_settings({
        "resilience": {
            "circuit_breaker": {
                "enabled": "yes",
                "failure_threshold": 0,  # floored to 1
                "cooldown_seconds": "abc",  # default 60
            }
        }
    })
    assert s.circuit_breaker.enabled is True
    assert s.circuit_breaker.failure_threshold == 1
    assert s.circuit_breaker.cooldown_seconds == 60.0
