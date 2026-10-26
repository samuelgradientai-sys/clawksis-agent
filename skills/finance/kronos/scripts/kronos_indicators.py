#!/usr/bin/env python3
"""Technical indicators and a plain-language signal summary (no model needed).

Computes SMA 20/50/200, EMA 12/26, MACD (12, 26, 9), RSI 14 (Wilder), Bollinger bands (20, 2),
ATR 14 (Wilder), the volume trend (last 10 bars vs the previous 30) and swing-based support and
resistance from the same OHLCV bars Kronos forecasts from (CSV/JSON file or read-only eToro
candles). Each rule adds or removes a point with a one-line reason; the total gives
bullish (>= +2), bearish (<= -2) or neutral. Pure Python: runs under any python3.

Indicators describe the past, not the future: use them to confirm or veto a Kronos forecast,
never as a trade signal on their own (references/trading-playbook.md).

Usage:
  kronos_indicators.py --etoro AAPL --interval OneDay [--count 300] [--format text|json]
  kronos_indicators.py --input prices.csv [--json]
"""

from __future__ import annotations

import argparse
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any, Callable, Sequence

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_common import (
    Bar,
    SkillError,
    describe_step,
    dump_json,
    infer_step,
    run_cli,
)
from kronos_forecast import add_data_args, load_input

MIN_BARS = 35  # MACD needs 26 + 9 bars
DEFAULT_COUNT = 300
NOTE = (
    "Indicators describe past prices, not the future; combine them with the forecast and its "
    "track record. Not financial advice."
)

Series = list[float | None]


# ── Indicator math (lists aligned with the input; None until enough data) ──


def sma(values: Sequence[float], n: int) -> Series:
    out: Series = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= n:
            total -= values[i - n]
        if i >= n - 1:
            out[i] = total / n
    return out


def ema(values: Sequence[float], n: int) -> Series:
    """Exponential average seeded with the simple average of the first *n* values."""
    out: Series = [None] * len(values)
    if len(values) < n:
        return out
    alpha = 2.0 / (n + 1)
    current = sum(values[:n]) / n
    out[n - 1] = current
    for i in range(n, len(values)):
        current = alpha * values[i] + (1 - alpha) * current
        out[i] = current
    return out


def _wilder(values: Sequence[float], n: int, start: int) -> Series:
    """Wilder smoothing of *values*; the first average covers values[start : start + n]."""
    out: Series = [None] * len(values)
    if len(values) < start + n:
        return out
    current = sum(values[start : start + n]) / n
    out[start + n - 1] = current
    for i in range(start + n, len(values)):
        current = (current * (n - 1) + values[i]) / n
        out[i] = current
    return out


def rsi(closes: Sequence[float], n: int = 14) -> Series:
    gains = [0.0] + [max(b - a, 0.0) for a, b in pairwise(closes)]
    losses = [0.0] + [max(a - b, 0.0) for a, b in pairwise(closes)]
    avg_gain, avg_loss = _wilder(gains, n, 1), _wilder(losses, n, 1)
    out: Series = [None] * len(closes)
    for i, (gain, loss) in enumerate(zip(avg_gain, avg_loss)):
        if gain is None or loss is None:
            continue
        out[i] = 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)
    return out


def macd(
    closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[Series, Series, Series]:
    fast_ema, slow_ema = ema(closes, fast), ema(closes, slow)
    line: Series = [
        f - s if f is not None and s is not None else None
        for f, s in zip(fast_ema, slow_ema)
    ]
    first = next((i for i, v in enumerate(line) if v is not None), len(line))
    tail = ema([v for v in line[first:] if v is not None], signal)
    signal_line: Series = [None] * first + tail
    hist: Series = [
        m - s if m is not None and s is not None else None
        for m, s in zip(line, signal_line)
    ]
    return line, signal_line, hist


def bollinger(
    closes: Sequence[float], n: int = 20, k: float = 2.0
) -> tuple[Series, Series, Series]:
    mid = sma(closes, n)
    upper: Series = [None] * len(closes)
    lower: Series = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        window = closes[i - n + 1 : i + 1]
        mean = mid[i] or 0.0
        deviation = (sum((x - mean) ** 2 for x in window) / n) ** 0.5
        upper[i], lower[i] = mean + k * deviation, mean - k * deviation
    return mid, upper, lower


def atr(bars: Sequence[Bar], n: int = 14) -> Series:
    ranges = [bars[0].high - bars[0].low] + [
        max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close))
        for a, b in pairwise(bars)
    ]
    return _wilder(ranges, n, 1)


def volume_ratio(bars: Sequence[Bar], short: int = 10, long: int = 30) -> float | None:
    volumes = [b.volume for b in bars if b.volume is not None]
    if len(volumes) < short + long or len(volumes) != len(bars):
        return None
    recent = sum(volumes[-short:]) / short
    before = sum(volumes[-short - long : -short]) / long
    return recent / before if before > 0 else None


def swing_levels(
    bars: Sequence[Bar], lookback: int = 120, wing: int = 3
) -> tuple[list[float], list[float]]:
    """(swing lows, swing highs) confirmed by *wing* bars on each side, newest window."""
    window = list(bars[-lookback:])
    lows, highs = [], []
    for i in range(wing, len(window) - wing):
        around = window[i - wing : i + wing + 1]
        if window[i].low == min(b.low for b in around):
            lows.append(window[i].low)
        if window[i].high == max(b.high for b in around):
            highs.append(window[i].high)
    return sorted(set(lows)), sorted(set(highs))


# ── Signal ──


def _last(series: Series, back: int = 0) -> float | None:
    index = len(series) - 1 - back
    return series[index] if index >= 0 else None


def _crossed(a: Series, b: Series, within: int) -> int:
    """+1 when *a* crossed above *b* in the last *within* bars, -1 below, 0 otherwise."""
    for back in range(within):
        now_a, now_b = _last(a, back), _last(b, back)
        then_a, then_b = _last(a, back + 1), _last(b, back + 1)
        if None in (now_a, now_b, then_a, then_b):
            return 0
        if then_a <= then_b and now_a > now_b:
            return 1
        if then_a >= then_b and now_a < now_b:
            return -1
    return 0


def _trend(s: dict[str, Any]) -> tuple[int, str] | None:
    if s["sma50"] is None:
        return None
    if s["close"] > s["sma50"]:
        return 1, "price is above its 50-bar average (uptrend)"
    return -1, "price is below its 50-bar average (downtrend)"


def _long_trend(s: dict[str, Any]) -> tuple[int, str] | None:
    if s["sma50"] is None or s["sma200"] is None:
        return None
    if s["sma50"] > s["sma200"]:
        return 1, "50-bar average is above the 200-bar average (long-term uptrend)"
    return -1, "50-bar average is below the 200-bar average (long-term downtrend)"


def _cross(s: dict[str, Any]) -> tuple[int, str] | None:
    if s["sma_cross"] > 0:
        return 1, "20-bar average just crossed above the 50-bar average"
    if s["sma_cross"] < 0:
        return -1, "20-bar average just crossed below the 50-bar average"
    return None


def _momentum(s: dict[str, Any]) -> tuple[int, str] | None:
    hist = s["macd_hist"]
    if hist is None:
        return None
    fresh = " (fresh crossover)" if s["macd_cross"] else ""
    if hist > 0:
        return 1, f"MACD is above its signal line: momentum up{fresh}"
    return -1, f"MACD is below its signal line: momentum down{fresh}"


def _rsi_rule(s: dict[str, Any]) -> tuple[int, str] | None:
    value = s["rsi14"]
    if value is None:
        return None
    if value < 30:
        return 1, f"RSI {value:.0f}: oversold, a bounce is possible"
    if value > 70:
        return -1, f"RSI {value:.0f}: overbought, pullback risk"
    return 0, f"RSI {value:.0f}: neither overbought nor oversold"


def _bands(s: dict[str, Any]) -> tuple[int, str] | None:
    if s["bb_upper"] is None:
        return None
    if s["close"] > s["bb_upper"]:
        return -1, "price is above the upper Bollinger band (stretched)"
    if s["close"] < s["bb_lower"]:
        return 1, "price is below the lower Bollinger band (stretched down)"
    return None


def _volume(s: dict[str, Any]) -> tuple[int, str] | None:
    ratio, move = s["volume_ratio"], s["change_10_pct"]
    if ratio is None or ratio < 1.5 or move is None:
        return None
    if move > 0:
        return 1, f"volume is {ratio:.1f}x its average on a rising price (buyers)"
    return -1, f"volume is {ratio:.1f}x its average on a falling price (sellers)"


RULES: tuple[Callable[[dict[str, Any]], tuple[int, str] | None], ...] = (
    _trend,
    _long_trend,
    _cross,
    _momentum,
    _rsi_rule,
    _bands,
    _volume,
)


def _nearest(levels: list[float], close: float, below: bool) -> list[float]:
    picked = [x for x in levels if (x < close if below else x > close)]
    picked.sort(key=lambda x: abs(close - x))
    return picked[:3]


def snapshot(bars: Sequence[Bar]) -> dict[str, Any]:
    """Latest value of every indicator plus support/resistance."""
    if len(bars) < MIN_BARS:
        raise SkillError(
            f"Only {len(bars)} bars; indicators need at least {MIN_BARS} (ideally 200+).",
            hint="Fetch more history (--count) or use a shorter interval.",
        )
    closes = [b.close for b in bars]
    close = closes[-1]
    line, signal_line, hist = macd(closes)
    mid, upper, lower = bollinger(closes)
    sma20, sma50 = sma(closes, 20), sma(closes, 50)
    atr14 = _last(atr(bars))
    lows, highs = swing_levels(bars)
    width = (_last(upper) or 0.0) - (_last(lower) or 0.0)
    return {
        "close": close,
        "sma20": _last(sma20),
        "sma50": _last(sma50),
        "sma200": _last(sma(closes, 200)),
        "ema12": _last(ema(closes, 12)),
        "ema26": _last(ema(closes, 26)),
        "rsi14": _last(rsi(closes)),
        "macd": _last(line),
        "macd_signal": _last(signal_line),
        "macd_hist": _last(hist),
        "macd_cross": _crossed(line, signal_line, 3),
        "sma_cross": _crossed(sma20, sma50, 5),
        "bb_mid": _last(mid),
        "bb_upper": _last(upper),
        "bb_lower": _last(lower),
        "bb_pct_b": (close - (_last(lower) or 0.0)) / width if width > 0 else None,
        "atr14": atr14,
        "atr_pct": atr14 / close * 100.0 if atr14 is not None and close else None,
        "volume_ratio": volume_ratio(bars),
        "change_10_pct": (close - closes[-11]) / closes[-11] * 100.0
        if len(closes) > 10 and closes[-11]
        else None,
        "support": _nearest(lows, close, below=True)
        or [min(b.low for b in bars[-120:])],
        "resistance": _nearest(highs, close, below=False)
        or [max(b.high for b in bars[-120:])],
    }


def analyze(bars: Sequence[Bar]) -> dict[str, Any]:
    values = snapshot(bars)
    score, reasons = 0, []
    for rule in RULES:
        verdict = rule(values)
        if verdict is None:
            continue
        points, reason = verdict
        score += points
        reasons.append(reason)
    signal = "bullish" if score >= 2 else "bearish" if score <= -2 else "neutral"
    return {"signal": signal, "score": score, "reasons": reasons, "indicators": values}


# ── CLI ──


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Technical indicators and a signal summary."
    )
    add_data_args(parser)
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help="eToro bars to fetch (max 1000)",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--json",
        dest="format",
        action="store_const",
        const="json",
        help="--format json",
    )
    return parser


def _fmt(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def render_text(result: dict[str, Any]) -> str:
    v = result["indicators"]
    label = result.get("symbol") or Path(str(result.get("input", "series"))).stem
    volume = (
        f"volume x{v['volume_ratio']:.1f} vs average"
        if v["volume_ratio"]
        else "volume n/a"
    )
    lines = [
        f"{label}: {result['bars']} x {result['interval']} bars, last close "
        f"{_fmt(v['close'], 4)} at {result['last_timestamp']}",
        f"signal: {result['signal'].upper()} (score {result['score']:+d})",
        *(f"- {reason}" for reason in result["reasons"]),
        f"RSI14 {_fmt(v['rsi14'], 1)} · MACD hist {_fmt(v['macd_hist'], 4)} · ATR14 "
        f"{_fmt(v['atr14'], 4)} ({_fmt(v['atr_pct'], 1)}% of price) · Bollinger %B "
        f"{_fmt(v['bb_pct_b'])} · {volume}",
        f"support {', '.join(_fmt(x) for x in v['support'])} · resistance "
        f"{', '.join(_fmt(x) for x in v['resistance'])}",
        *(f"warning: {w}" for w in result["warnings"]),
        result["note"],
    ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    bars, meta, warnings = load_input(args, max(MIN_BARS, min(args.count, 1000)))
    result = {
        "ok": True,
        **meta,
        "bars": len(bars),
        "interval": describe_step(infer_step([b.ts for b in bars])),
        "last_timestamp": bars[-1].ts.isoformat(),
        **analyze(bars),
        "warnings": warnings,
        "note": NOTE,
    }
    print(render_text(result) if args.format == "text" else dump_json(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_cli(lambda: run(args))


if __name__ == "__main__":
    sys.exit(main())
