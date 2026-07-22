"""Opt-in resilience layer for provider failures (429 / rate limits / outages).

This package adds *production-grade robustness* on top of the existing retry +
credential-rotation + provider-failover machinery (``agent/conversation_loop.py``,
``agent/credential_pool.py``, ``agent/retry_utils.py``). Everything here is
**opt-in** and gated behind the ``resilience`` config block — when the block is
absent or every flag is off, these helpers are no-ops and the agent behaves
byte-for-byte as before.

Components:
  * :mod:`agent.resilience.circuit_breaker` — per-provider circuit breaker that
    fast-fails to a fallback provider instead of burning the retry budget on a
    provider that keeps erroring (mirrors the MCP breaker in ``tools/mcp_tool``).
  * :mod:`agent.resilience.rate_limiter` — preemptive per-provider token bucket
    that throttles *before* hitting a 429, using the provider's advertised
    RPM/TPM (parsed ``x-ratelimit-*`` headers, else static config caps).
  * :mod:`agent.resilience.pending_journal` — durable journal of in-flight
    turns so heavy tasks survive a process crash and auto-resume on restart
    (``tui_gateway`` only; the ``gateway`` package already has its own resume).

``get_resilience_settings(config)`` parses the config block once into a frozen
dataclass; it tolerates a missing/partial/garbage block and returns an
all-disabled instance in that case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = [
    "CircuitBreakerSettings",
    "RateLimitSettings",
    "AdaptiveCooldownSettings",
    "DurableTurnsSettings",
    "ResilienceSettings",
    "get_resilience_settings",
]


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    try:
        return bool(value)
    except Exception:
        return default


def _as_int(value: Any, default: int, *, minimum: int | None = None) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and out < minimum:
        return minimum
    return out


def _as_float(value: Any, default: float, *, minimum: float | None = None) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and out < minimum:
        return minimum
    return out


@dataclass(frozen=True)
class CircuitBreakerSettings:
    enabled: bool = False
    failure_threshold: int = 3
    cooldown_seconds: float = 60.0


@dataclass(frozen=True)
class RateLimitSettings:
    enabled: bool = False
    # Per-provider static caps, e.g. {"anthropic": {"rpm": 50, "tpm": 40000}}.
    # Headers override these when ``use_response_headers`` is true and present.
    providers: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    use_response_headers: bool = True
    # Hard ceiling on any single throttle wait so a misconfigured cap can never
    # stall the agent indefinitely.
    max_wait_seconds: float = 60.0


@dataclass(frozen=True)
class AdaptiveCooldownSettings:
    enabled: bool = False
    base_seconds: float = 60.0
    max_seconds: float = 3600.0


@dataclass(frozen=True)
class DurableTurnsSettings:
    enabled: bool = False
    freshness_seconds: float = 3600.0


@dataclass(frozen=True)
class ResilienceSettings:
    circuit_breaker: CircuitBreakerSettings = field(
        default_factory=CircuitBreakerSettings
    )
    rate_limits: RateLimitSettings = field(default_factory=RateLimitSettings)
    adaptive_cooldown: AdaptiveCooldownSettings = field(
        default_factory=AdaptiveCooldownSettings
    )
    durable_turns: DurableTurnsSettings = field(default_factory=DurableTurnsSettings)

    # NOTE: auto-restore to the primary provider is NOT a setting here — it is a
    # built-in, always-on behavior. ``run_conversation`` calls
    # ``_restore_primary_runtime()`` at the top of every turn (cooldown-aware),
    # so once the primary recovers the agent returns to it automatically.

    @property
    def any_enabled(self) -> bool:
        return (
            self.circuit_breaker.enabled
            or self.rate_limits.enabled
            or self.adaptive_cooldown.enabled
            or self.durable_turns.enabled
        )


def _parse_providers(raw: Any) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    if not isinstance(raw, Mapping):
        return out
    for name, caps in raw.items():
        if not isinstance(caps, Mapping):
            continue
        entry: dict[str, int] = {}
        for k in ("rpm", "tpm"):
            if k in caps:
                entry[k] = _as_int(caps.get(k), 0, minimum=0)
        out[str(name)] = entry
    return out


def get_resilience_settings(config: Mapping[str, Any] | None) -> ResilienceSettings:
    """Parse the ``resilience`` config block into a frozen settings object.

    Defensive: a missing/partial/garbage block yields an all-disabled instance,
    so callers can unconditionally consult the result without branching on shape.
    """
    block: Any = None
    if isinstance(config, Mapping):
        block = config.get("resilience")
    if not isinstance(block, Mapping):
        return ResilienceSettings()

    cb_raw = block.get("circuit_breaker")
    cb = CircuitBreakerSettings()
    if isinstance(cb_raw, Mapping):
        cb = CircuitBreakerSettings(
            enabled=_as_bool(cb_raw.get("enabled"), False),
            failure_threshold=_as_int(cb_raw.get("failure_threshold"), 3, minimum=1),
            cooldown_seconds=_as_float(
                cb_raw.get("cooldown_seconds"), 60.0, minimum=0.0
            ),
        )

    rl_raw = block.get("rate_limits")
    rl = RateLimitSettings()
    if isinstance(rl_raw, Mapping):
        rl = RateLimitSettings(
            enabled=_as_bool(rl_raw.get("enabled"), False),
            providers=_parse_providers(rl_raw.get("providers")),
            use_response_headers=_as_bool(rl_raw.get("use_response_headers"), True),
            max_wait_seconds=_as_float(
                rl_raw.get("max_wait_seconds"), 60.0, minimum=0.0
            ),
        )

    ac_raw = block.get("adaptive_cooldown")
    ac = AdaptiveCooldownSettings()
    if isinstance(ac_raw, Mapping):
        ac = AdaptiveCooldownSettings(
            enabled=_as_bool(ac_raw.get("enabled"), False),
            base_seconds=_as_float(ac_raw.get("base_seconds"), 60.0, minimum=0.0),
            max_seconds=_as_float(ac_raw.get("max_seconds"), 3600.0, minimum=0.0),
        )

    dt_raw = block.get("durable_turns")
    dt = DurableTurnsSettings()
    if isinstance(dt_raw, Mapping):
        dt = DurableTurnsSettings(
            enabled=_as_bool(dt_raw.get("enabled"), False),
            freshness_seconds=_as_float(
                dt_raw.get("freshness_seconds"), 3600.0, minimum=0.0
            ),
        )

    return ResilienceSettings(
        circuit_breaker=cb,
        rate_limits=rl,
        adaptive_cooldown=ac,
        durable_turns=dt,
    )
