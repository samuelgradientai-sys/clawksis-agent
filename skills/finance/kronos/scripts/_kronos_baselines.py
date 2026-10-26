"""Classical forecast baseline for the honesty checks: exponential smoothing (ETS) on closes.

Kronos only "adds value" when it beats both "repeat the last close" and this baseline. The
forecaster is statsforecast's AutoETS (Apache-2.0; installed in the skill venv by
``kronos_setup.py`` when it can be), which picks the error/trend form by AICc. Without it, a
built-in additive Holt fit stands in: simple exponential smoothing or a damped trend, whichever
grid-searched setting has the smallest one-step-ahead squared error on the window. The result
always says which engine produced it. Stdlib only unless statsforecast is importable.
"""

from __future__ import annotations

import itertools
from typing import Callable, Sequence

ENGINE_AUTOETS = "statsforecast AutoETS"
ENGINE_BUILTIN = "built-in Holt (statsforecast not installed)"
ALPHAS = (0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)
BETAS = (0.05, 0.1, 0.2)
PHIS = (0.8, 0.9, 0.98)

Forecaster = Callable[[Sequence[float], int], list[float]]


def _one_step_sse(
    series: Sequence[float], alpha: float, beta: float, phi: float
) -> tuple[float, float, float]:
    """(sum of squared one-step errors, final level, final trend) of an additive Holt fit."""
    level, trend = series[0], (series[1] - series[0]) if beta else 0.0
    sse = 0.0
    for value in series[1:]:
        predicted = level + phi * trend
        error = value - predicted
        sse += error * error
        new_level = predicted + alpha * error
        trend = phi * trend + beta * (new_level - level - phi * trend) if beta else 0.0
        level = new_level
    return sse, level, trend


def holt_forecast(series: Sequence[float], horizon: int) -> list[float]:
    """Best of SES and damped-trend Holt by one-step SSE, projected *horizon* steps."""
    values = [float(v) for v in series]
    if len(values) < 3:
        return [values[-1]] * horizon
    grid = [(a, 0.0, 1.0) for a in ALPHAS] + list(
        itertools.product(ALPHAS, BETAS, PHIS)
    )
    _sse, level, trend, phi = min(
        (*_one_step_sse(values, a, b, p), p) for a, b, p in grid
    )
    out, damp = [], 0.0
    for step in range(1, horizon + 1):
        damp += phi**step
        out.append(level + damp * trend)
    return out


def _autoets() -> Forecaster | None:
    try:
        import numpy as np
        from statsforecast.models import AutoETS
    except ImportError:
        return None

    def forecast(series: Sequence[float], horizon: int) -> list[float]:
        result = AutoETS(season_length=1).forecast(
            y=np.asarray(series, dtype=float), h=horizon
        )
        return [float(v) for v in result["mean"]]

    return forecast


def ets_forecasts(
    windows: Sequence[Sequence[float]], horizon: int
) -> tuple[list[list[float]], str]:
    """One *horizon*-step close forecast per window, and the engine that produced them."""
    autoets = _autoets()
    if autoets is None:
        return [holt_forecast(w, horizon) for w in windows], ENGINE_BUILTIN
    out, unfit = [], 0
    for window in windows:
        try:
            out.append(autoets(window, horizon))
        except (ValueError, ArithmeticError):
            # No ETS form could be fitted to this window.
            out.append(holt_forecast(window, horizon))
            unfit += 1
    if unfit:
        return out, f"{ENGINE_AUTOETS} (built-in Holt for {unfit} window(s))"
    return out, ENGINE_AUTOETS
