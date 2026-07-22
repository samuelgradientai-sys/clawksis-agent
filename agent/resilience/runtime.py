"""Process-global resilience runtime.

Builds the rate limiter + circuit breaker from the ``resilience`` config block
(default OFF) and installs the adaptive 429 cooldown into the credential pool.
Install is idempotent and process-wide: provider rate limits / breaker state
must be shared across all concurrent gateway turns (each turn is its own agent
but they hit the same provider quotas), so a per-agent instance would be wrong.

Everything is opt-in: when the config flags are off (the default), the getters
return ``None`` and callers skip the resilience path entirely.
"""

from __future__ import annotations

import threading
from typing import Any, Mapping, Optional

from agent.resilience import ResilienceSettings, get_resilience_settings
from agent.resilience.circuit_breaker import ProviderCircuitBreaker
from agent.resilience.rate_limiter import ProviderRateLimiter

_lock = threading.Lock()
_installed = False
_settings = ResilienceSettings()
_limiter: Optional[ProviderRateLimiter] = None
_breaker: Optional[ProviderCircuitBreaker] = None


def install_resilience_runtime(
    config: Mapping[str, Any] | None = None, *, force: bool = False
) -> ResilienceSettings:
    """Build the runtime from ``config`` (loaded lazily when omitted).

    Idempotent: only the first call (or ``force=True``) does work; later calls
    return the cached settings. Safe to call from every agent build.
    """
    global _installed, _settings, _limiter, _breaker
    with _lock:
        if _installed and not force:
            return _settings

        cfg = config
        if cfg is None:
            try:
                from clawk_cli.config import load_config

                cfg = load_config()
            except Exception:
                cfg = None

        settings = get_resilience_settings(cfg)
        _settings = settings

        _limiter = (
            ProviderRateLimiter(
                enabled=True,
                static_limits=settings.rate_limits.providers,
                use_response_headers=settings.rate_limits.use_response_headers,
                max_wait_seconds=settings.rate_limits.max_wait_seconds,
            )
            if settings.rate_limits.enabled
            else None
        )

        _breaker = (
            ProviderCircuitBreaker(
                failure_threshold=settings.circuit_breaker.failure_threshold,
                cooldown_seconds=settings.circuit_breaker.cooldown_seconds,
                enabled=True,
            )
            if settings.circuit_breaker.enabled
            else None
        )

        # Install (or clear) the adaptive 429 cooldown in the credential pool.
        try:
            from agent import credential_pool

            credential_pool.set_adaptive_cooldown(settings.adaptive_cooldown)
        except Exception:
            pass

        _installed = True
        return settings


def _ensure() -> None:
    if not _installed:
        install_resilience_runtime()


def get_rate_limiter() -> Optional[ProviderRateLimiter]:
    _ensure()
    return _limiter


def get_circuit_breaker() -> Optional[ProviderCircuitBreaker]:
    _ensure()
    return _breaker


def get_settings() -> ResilienceSettings:
    _ensure()
    return _settings


def reset_for_tests() -> None:
    """Forget the installed runtime (test isolation)."""
    global _installed, _settings, _limiter, _breaker
    with _lock:
        _installed = False
        _settings = ResilienceSettings()
        _limiter = None
        _breaker = None
    try:
        from agent import credential_pool

        credential_pool.set_adaptive_cooldown(None)
    except Exception:
        pass
