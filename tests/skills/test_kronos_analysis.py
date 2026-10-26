"""Behaviour contracts for the Kronos analysis helpers (``finance/kronos``).

``kronos_indicators.py``: indicator math against hand-computed values, the rule-based signal
(bullish / bearish / neutral with reasons) and its CLI. ``kronos_risk.py``: position sizing,
ATR stops and targets, the caps from the trading limits and today's ledger, the goals' risk
profile, and that it never writes config or ledger. Pure Python, no network.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "skills" / "finance" / "kronos" / "scripts"
)


def _load(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # siblings import each other by these names
    spec.loader.exec_module(module)
    return module


kc = _load("_kronos_common")
trade = _load("etoro_trade")
ind = _load("kronos_indicators")
risk = _load("kronos_risk")

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=kc.UTC)


def _bars(closes, volumes=None, spread=1.0):
    start = datetime(2026, 1, 5)
    volumes = volumes or [1000.0] * len(closes)
    return [
        kc.Bar(start + timedelta(days=i), c, c + spread, c - spread, c, v)
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


def _csv(path: Path, bars) -> Path:
    lines = ["timestamps,open,high,low,close,volume"]
    lines += [
        f"{b.ts.isoformat()},{b.open},{b.high},{b.low},{b.close},{b.volume}"
        for b in bars
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ── Indicator math ──


def test_moving_averages_match_hand_computed_values():
    assert ind.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]
    # EMA(3): alpha 0.5, seeded with the SMA of the first 3 values.
    assert ind.ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]
    assert ind.ema([2, 2, 2, 10], 3)[-1] == pytest.approx(6.0)
    assert ind.ema([1, 2], 3) == [None, None]


def test_rsi_extremes_and_balance():
    assert ind.rsi([float(i) for i in range(30)])[-1] == 100.0
    assert ind.rsi([float(30 - i) for i in range(30)])[-1] == pytest.approx(0.0)
    zigzag = [100.0 + (1 if i % 2 else 0) for i in range(41)]
    assert ind.rsi(zigzag)[-1] == pytest.approx(50.0, abs=3.0)
    assert ind.rsi([1.0] * 10)[-1] is None  # not enough data yet


def test_flat_prices_give_zero_momentum_and_a_collapsed_band():
    flat = [50.0] * 60
    line, signal, hist = ind.macd(flat)
    assert line[-1] == pytest.approx(0.0) and hist[-1] == pytest.approx(0.0)
    assert line[24] is None and line[25] is not None and signal[33] is not None
    mid, upper, lower = ind.bollinger(flat)
    assert mid[-1] == upper[-1] == lower[-1] == 50.0


def test_atr_volume_and_swing_levels():
    bars = _bars([100.0] * 30, spread=1.0)  # every bar ranges 2.0
    assert ind.atr(bars)[-1] == pytest.approx(2.0)
    rising_volume = _bars([100.0] * 40, volumes=[100.0] * 30 + [300.0] * 10)
    assert ind.volume_ratio(rising_volume) == pytest.approx(3.0)
    valley = [110 - i for i in range(10)] + [100 + i for i in range(10)]
    lows, _highs = ind.swing_levels(_bars([float(c) for c in valley], spread=0.5))
    assert lows == [99.5]  # the valley's low, confirmed by 3 bars on each side


# ── Signal ──


# A wavy trend whose last 10 bars trade on double volume.
WAVE = [0.3 * i + 4 * math.sin(i / 4) for i in range(260)]
LOUD_END = [1000.0] * 250 + [2000.0] * 10


def test_an_uptrend_on_rising_volume_reads_bullish_with_reasons():
    result = ind.analyze(_bars([100.0 + w for w in WAVE], LOUD_END))
    assert result["signal"] == "bullish" and result["score"] >= 3
    assert any("above its 50-bar average" in r for r in result["reasons"])
    assert any("above the 200-bar average" in r for r in result["reasons"])
    assert any("buyers" in r for r in result["reasons"])
    values = result["indicators"]
    assert values["support"] and all(s < values["close"] for s in values["support"])
    assert values["resistance"] and all(
        r > values["close"] for r in values["resistance"]
    )


def test_a_downtrend_on_rising_volume_reads_bearish():
    result = ind.analyze(_bars([300.0 - w for w in WAVE], LOUD_END))
    assert result["signal"] == "bearish" and result["score"] <= -3
    assert any("below its 50-bar average" in r for r in result["reasons"])
    assert any("sellers" in r for r in result["reasons"])


def test_heavy_volume_on_a_rising_price_counts_for_buyers():
    closes = [100.0] * 40 + [100.0 + i for i in range(1, 11)]
    volumes = [100.0] * 40 + [400.0] * 10
    reasons = ind.analyze(_bars(closes, volumes))["reasons"]
    assert any("volume is" in r and "buyers" in r for r in reasons)


def test_too_little_history_is_a_clear_error():
    with pytest.raises(kc.SkillError, match="at least 35"):
        ind.analyze(_bars([100.0] * 20))


def test_indicators_cli_reads_a_file_and_prints_json(tmp_path, capsys):
    csv = _csv(tmp_path / "aapl.csv", _bars([100.0 + i for i in range(80)]))
    assert ind.main(["--input", str(csv), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["signal"] in {"bullish", "bearish", "neutral"} and out["reasons"]
    assert out["bars"] == 80 and out["interval"] == "1 day"


# ── Risk ──

LIMITS = {"max_order_usd": 100.0, "usd_left_today": 300.0, "buys_left_today": 5}


def test_position_size_risks_the_chosen_share_of_the_account():
    plan = risk.plan_position(
        account_size=10_000,
        risk_pct=1.0,
        entry=100.0,
        stop=95.0,
        rr=2.0,
        limits={**LIMITS, "max_order_usd": 5000.0, "usd_left_today": 5000.0},
    )
    # $100 at risk / $5 per unit = 20 units = $2,000.
    assert plan["suggested_amount_usd"] == 2000.0 and plan["binding_cap"] == "risk"
    assert plan["units"] == 20.0 and plan["max_loss_usd"] == 100.0
    assert plan["take_profit"] == 110.0 and plan["stop_distance_pct"] == 5.0


def test_the_trading_limits_cap_the_size():
    plan = risk.plan_position(
        account_size=10_000, risk_pct=1.0, entry=100.0, stop=95.0, rr=2.0, limits=LIMITS
    )
    assert (
        plan["suggested_amount_usd"] == 100.0 and plan["binding_cap"] == "max_order_usd"
    )
    assert plan["max_loss_usd"] == 5.0
    none_left = risk.plan_position(
        account_size=10_000,
        risk_pct=1.0,
        entry=100.0,
        stop=95.0,
        rr=2.0,
        limits={**LIMITS, "buys_left_today": 0},
    )
    assert none_left["suggested_amount_usd"] == 0.0
    assert none_left["binding_cap"] == "buys_left_today"


def test_stops_must_sit_below_the_entry():
    with pytest.raises(kc.SkillError, match="below the entry"):
        risk.plan_position(
            account_size=1000,
            risk_pct=1.0,
            entry=100.0,
            stop=100.0,
            rr=2.0,
            limits=LIMITS,
        )


def test_risk_cli_uses_goals_atr_and_todays_ledger_without_writing(tmp_path, capsys):
    config = tmp_path / "config.yaml"
    config.write_text(
        "skills:\n  config:\n    kronos:\n      trading:\n        enabled: true\n"
        "        max_order_usd: 1000\n      goals:\n        risk: alto\n",
        encoding="utf-8",
    )
    ledger = tmp_path / "kronos" / "trades.jsonl"
    trade.append_ledger(
        {
            "id": "a",
            "ts": NOW.isoformat(),
            "action": "open",
            "account": "demo",
            "amount": 250.0,
            "status": "filled",
        },
        ledger,
    )
    before = (config.read_text(encoding="utf-8"), ledger.read_text(encoding="utf-8"))
    csv = _csv(tmp_path / "aapl.csv", _bars([100.0] * 40, spread=1.0))  # ATR 2.0
    deps = risk.RiskDeps(config_path=config, ledger=ledger, now=lambda: NOW)
    assert (
        risk.main(["--account-size", "10000", "--input", str(csv), "--json"], deps) == 0
    )
    out = json.loads(capsys.readouterr().out)
    assert out["risk_profile"] == "high" and out["risk_pct"] == 2.0
    assert out["stop_loss"] == 96.0 and out["take_profit"] == 108.0  # 2 ATR, 2:1
    # Ready to paste into etoro_trade.py buy, which sends the stop and target with the order.
    buy = trade.build_parser().parse_args(
        ["buy", "AAPL", "--reason", "x", *out["buy_args"].split()]
    )
    assert (buy.amount, buy.stop, buy.target) == (50.0, 96.0, 108.0)
    assert (
        out["suggested_amount_usd"] == 50.0 and out["binding_cap"] == "usd_left_today"
    )
    assert (
        config.read_text(encoding="utf-8"),
        ledger.read_text(encoding="utf-8"),
    ) == before


def test_risk_cli_without_a_stop_or_bars_explains_what_it_needs(tmp_path, capsys):
    deps = risk.RiskDeps(
        config_path=tmp_path / "missing.yaml", ledger=tmp_path / "t.jsonl"
    )
    assert risk.main(["--account-size", "1000", "--entry", "50"], deps) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "--stop" in out["hint"]
