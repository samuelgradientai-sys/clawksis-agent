"""Per-provider circuit breaker.

Mirrors the MCP-server breaker in ``tools/mcp_tool.py`` (consecutive-failure
count + open/half-open/closed state machine), but keyed by an arbitrary string
(``provider`` or ``provider:credential_id``) and used by the agent's retry loop
to **fast-fail to a fallback provider** instead of burning the whole retry
budget on a provider that keeps rate-limiting/erroring.

State machine (per key):
  * **closed**    — failure count below threshold; calls go through.
  * **open**      — threshold reached and within cooldown; ``is_open`` returns
                    True so the caller short-circuits to fallback.
  * **half-open** — cooldown elapsed; ``is_open`` returns False so the next call
                    is a probe. Probe success → ``record_success`` closes it;
                    probe failure → ``record_failure`` re-arms the cooldown.

In-process and lock-guarded: gateway turns run in worker threads that all hit
the same provider quotas, so a single process-global breaker is correct (and a
restart resetting it is fine). Opt-in: a breaker constructed with
``enabled=False`` is a no-op (``record_*`` do nothing, ``is_open`` is False).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


def make_key(provider: str | None, credential_id: str | None = None) -> str:
    """Build a breaker key from the active provider (+ optional credential id)."""
    prov = (provider or "unknown").strip() or "unknown"
    if credential_id:
        return f"{prov}:{credential_id}"
    return prov


@dataclass
class _BreakerState:
    consecutive_failures: int = 0
    opened_at: float = 0.0  # time.monotonic() when opened; 0.0 = never opened


class ProviderCircuitBreaker:
    """A registry of per-key circuit breakers (thread-safe)."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        enabled: bool = True,
    ) -> None:
        self._threshold = max(1, int(failure_threshold))
        self._cooldown = max(0.0, float(cooldown_seconds))
        self._enabled = bool(enabled)
        self._states: dict[str, _BreakerState] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_failure(self, key: str) -> None:
        """Count a transient failure for ``key``; (re)arm cooldown at threshold."""
        if not self._enabled:
            return
        with self._lock:
            st = self._states.setdefault(key, _BreakerState())
            st.consecutive_failures += 1
            if st.consecutive_failures >= self._threshold:
                # Stamp (or re-stamp, for a failed half-open probe) the open time.
                st.opened_at = time.monotonic()

    def record_success(self, key: str) -> None:
        """Fully close the breaker for ``key`` on any unambiguous success."""
        if not self._enabled:
            return
        with self._lock:
            self._states[key] = _BreakerState()

    def is_open(self, key: str) -> bool:
        """True when the breaker is open AND still within its cooldown.

        Returns False when closed, when below threshold, or when the cooldown
        has elapsed (half-open — the caller should let one probe through).
        """
        if not self._enabled:
            return False
        with self._lock:
            st = self._states.get(key)
            if st is None or st.opened_at == 0.0:
                return False
            if st.consecutive_failures < self._threshold:
                return False
            if (time.monotonic() - st.opened_at) >= self._cooldown:
                return False  # half-open: allow a probe
            return True

    def state(self, key: str) -> str:
        """Return ``"closed"`` | ``"open"`` | ``"half-open"`` (observability/tests)."""
        if not self._enabled:
            return "closed"
        with self._lock:
            st = self._states.get(key)
            if (
                st is None
                or st.opened_at == 0.0
                or st.consecutive_failures < self._threshold
            ):
                return "closed"
            if (time.monotonic() - st.opened_at) >= self._cooldown:
                return "half-open"
            return "open"

    def reset(self, key: str | None = None) -> None:
        """Clear one key (or all). Used on manual recovery and in tests."""
        with self._lock:
            if key is None:
                self._states.clear()
            else:
                self._states.pop(key, None)
