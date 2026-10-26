"""Performance metrics of an equity curve, pure Python: return, CAGR, drawdown, Sharpe.

Used by ``kronos_strategy_backtest.py`` so the numbers are the same whether or not quantstats
(which only draws the optional HTML tear sheet) is installed. Returns are simple per-bar returns;
the annualization factor is the number of bars per calendar year actually in the data, so daily
stock bars (~252/year), daily crypto bars (365) and intraday bars all annualize correctly.
"""

from __future__ import annotations

import math
from datetime import datetime
from itertools import pairwise
from typing import Any, Sequence

SECONDS_PER_YEAR = 365.25 * 86400


def years_between(first: datetime, last: datetime) -> float:
    return (last - first).total_seconds() / SECONDS_PER_YEAR


def bar_returns(equity: Sequence[float]) -> list[float]:
    return [b / a - 1.0 for a, b in pairwise(equity) if a]


def cagr(equity: Sequence[float], years: float) -> float | None:
    if years <= 0 or not equity or equity[0] <= 0 or equity[-1] <= 0:
        return None
    return (equity[-1] / equity[0]) ** (1.0 / years) - 1.0


def max_drawdown(equity: Sequence[float]) -> float:
    """The worst fall from a running peak, as a negative fraction (0.0 = never below a peak)."""
    peak, worst = float("-inf"), 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def sharpe(returns: Sequence[float], per_year: float) -> float | None:
    """Annualized mean / standard deviation of per-bar returns (risk-free rate 0)."""
    if len(returns) < 2 or per_year <= 0:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    if variance <= 0:
        return None
    return mean / math.sqrt(variance) * math.sqrt(per_year)


def summarize(stamps: Sequence[datetime], equity: Sequence[float]) -> dict[str, Any]:
    """Total return, CAGR, max drawdown (percent) and Sharpe of an equity curve."""
    years = years_between(stamps[0], stamps[-1]) if len(stamps) > 1 else 0.0
    per_year = (len(stamps) - 1) / years if years > 0 else 0.0
    growth = cagr(equity, years)
    ratio = sharpe(bar_returns(equity), per_year)
    return {
        "total_return_pct": round((equity[-1] / equity[0] - 1.0) * 100.0, 2),
        "cagr_pct": round(growth * 100.0, 2) if growth is not None else None,
        "max_drawdown_pct": round(max_drawdown(equity) * 100.0, 2),
        "sharpe": round(ratio, 2) if ratio is not None else None,
        "bars_per_year": round(per_year, 1),
    }
