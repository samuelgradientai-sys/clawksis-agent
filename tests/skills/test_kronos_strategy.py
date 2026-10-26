"""Behaviour contracts for the playbook replay in ``finance/kronos`` (``kronos_strategy_backtest``).

The replay must enforce exactly what real orders face: the per-order, per-day and per-day-count
limits (``check_limits`` with the user's settings, ``DEFAULTS`` without them), the lesson gate
over the forecasts it made, and the stop/target price check at the fill. Its metrics are pure
Python, its summary feeds the dashboard's "Playbook replays" panel, and the backtest verdicts get
their own panel; both must survive the web server's snapshot normalizer. No network, no model,
no quantstats.
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

from clawk_cli.skill_dashboard_snapshot import read_snapshot

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
metrics = _load("_kronos_metrics")
trade = _load("etoro_trade")
journal = _load("_kronos_journal")
strategy = _load("kronos_strategy_backtest")
dash = _load("kronos_dashboard")


# ── Metrics ──


def test_metrics_match_hand_computed_values():
    assert metrics.max_drawdown([100, 120, 90, 130, 117]) == pytest.approx(-0.25)
    assert metrics.max_drawdown([1, 2, 3]) == 0.0
    assert metrics.cagr([100, 121], 2.0) == pytest.approx(0.10)
    assert metrics.sharpe([0.01] * 10, 252) is None  # no variance, no ratio
    returns = [0.01, -0.01] * 50
    assert metrics.sharpe(returns, 252) == pytest.approx(0.0, abs=1e-9)
    days = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(731)]
    summary = metrics.summarize(days, [100 * 1.21 ** (i / 730.5) for i in range(731)])
    assert summary["cagr_pct"] == pytest.approx(10.0, abs=0.05)
    assert summary["max_drawdown_pct"] == 0.0
    assert summary["bars_per_year"] == pytest.approx(365.25, abs=0.1)


# ── The replay enforces the real guards ──


def _bars(closes, stamps, *, high_pad, low_pad):
    """Bars that open at the previous close; *high_pad*/*low_pad* set how far they reach."""
    out, previous = [], closes[0]
    for stamp, close in zip(stamps, closes):
        opened = previous
        out.append(
            kc.Bar(
                stamp,
                opened,
                max(opened, close) + high_pad,
                min(opened, close) - low_pad,
                close,
                1000.0,
            )
        )
        previous = close
    return out


def _bullish(monkeypatch, atr=1.0):
    def analyze(window):
        close = window[-1].close
        return {
            "signal": "bullish",
            "indicators": {"atr14": atr, "atr_pct": atr / close * 100, "rsi14": 55.0},
        }

    monkeypatch.setattr(strategy, "analyze", analyze)


def _sim(tmp_path, bars, config, *, horizon=3, start=0):
    rules = strategy.Rules(
        account_size=10_000.0,
        risk_pct=1.0,
        atr_mult=2.0,
        rr=2.0,
        max_hold=20,
        fee=0.0,
        horizon=horizon,
    )
    forecasts = {i: bars[i].close + 10.0 for i in range(start, len(bars) - 1)}
    return strategy.Sim(
        bars=bars,
        forecasts=forecasts,
        rules=rules,
        config=config,
        journal=tmp_path / "forecasts.jsonl",
        label="TSLA",
        interval="1 hour",
        cash=10_000.0,
    )


def test_buys_that_would_exceed_the_daily_limit_are_capped_then_refused(
    tmp_path, monkeypatch
):
    _bullish(monkeypatch)
    # Seven hourly bars a day; every buy hits its target within the next bar, so the rules
    # want to buy again on every bar: far more than the limits allow.
    hours = [
        datetime(2026, 10, 26) + timedelta(days=d, hours=14 + h)
        for d in range(3)
        for h in range(7)
    ]
    closes = [100.0 + 0.3 * i for i in range(len(hours))]
    bars = _bars(closes, hours, high_pad=5.0, low_pad=0.5)
    config = trade.TradingConfig(False, "demo", 100.0, 250.0, 5)
    sim = _sim(tmp_path, bars, config)
    strategy.simulate(sim, 0)

    by_day: dict[str, list[float]] = {}
    for entry in sim.ledger:
        by_day.setdefault(entry["ts"][:10], []).append(entry["amount"])
    assert by_day and all(sum(v) <= 250.0 and len(v) <= 5 for v in by_day.values())
    assert any(
        v == [100.0, 100.0, 50.0] for v in by_day.values()
    )  # the third is capped
    assert sim.refusals["limit"] > 0  # then the day's cap refuses the rest
    assert strategy.busiest_day(sim.ledger)["usd"] == 250.0
    assert [t["reason"] for t in sim.trades] == ["target"] * len(sim.trades)


def test_without_settings_the_replay_uses_the_default_limits(tmp_path, monkeypatch):
    config, source, _notes = strategy.trading_limits()
    assert config == trade.DEFAULTS and source == "defaults"
    kc.clawk_home().mkdir(parents=True, exist_ok=True)
    (kc.clawk_home() / "config.yaml").write_text(
        "skills:\n  config:\n    kronos:\n      trading:\n        max_daily_usd: 150\n",
        encoding="utf-8",
    )
    config, source, _notes = strategy.trading_limits()
    assert (config.max_daily_usd, source) == (150.0, "config.yaml")


def test_the_lesson_gate_stops_buying_once_its_forecasts_keep_missing(
    tmp_path, monkeypatch
):
    _bullish(monkeypatch)
    days = [datetime(2026, 1, 5) + timedelta(days=i) for i in range(30)]
    closes = [200.0 - 1.5 * i for i in range(30)]  # forecasts say up, prices fall
    bars = _bars(closes, days, high_pad=0.2, low_pad=3.0)  # every buy is stopped out
    generous = trade.TradingConfig(False, "demo", 100.0, 10_000.0, 100)
    sim = _sim(tmp_path, bars, generous, horizon=3)
    strategy.simulate(sim, 0)
    assert sim.refusals["lesson"] > 0
    record = journal.gate_status(journal.read_forecasts(sim.journal), "TSLA")
    assert record["blocked"] and record["matured"] >= journal.MIN_MATURED
    # The forecast made at bar i is scored at bar i + 3, so the fifth miss is known at bar 7:
    # the last buy is the one decided at bar 6, filled at bar 7's open.
    last_entry = max(datetime.fromisoformat(t["entry"][:-1]) for t in sim.trades)
    assert last_entry == days[3 + journal.MIN_MATURED - 1]


def test_a_fill_that_gaps_through_the_stop_is_refused_like_a_real_order(
    tmp_path, monkeypatch
):
    _bullish(monkeypatch)
    days = [datetime(2026, 1, 5) + timedelta(days=i) for i in range(6)]
    bars = _bars([100.0] * 6, days, high_pad=1, low_pad=1)
    bars[1] = kc.Bar(days[1], 90.0, 91.0, 89.0, 90.0, 1000.0)  # opens below the 98 stop
    sim = _sim(tmp_path, bars, trade.DEFAULTS)
    sim.forecasts = {0: 110.0}
    strategy.simulate(sim, 0)
    assert sim.refusals["stop"] == 1 and sim.ledger == [] and sim.trades == []


# ── CLI, record and dashboard ──


def _wave_csv(path: Path, n: int = 400, start=datetime(2025, 1, 6)) -> Path:
    rows, day, i = ["timestamps,open,high,low,close,volume"], start, 0
    while i < n:
        if day.weekday() < 5:
            close = 100 + 12 * math.sin(i / 6) + 0.05 * i
            rows.append(
                f"{day.date()},{close - 0.4},{close + 1.5},{close - 1.5},{close},1000"
            )
            i += 1
        day += timedelta(days=1)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_the_cli_reports_records_and_feeds_the_dashboard(tmp_path, capsys):
    data = _wave_csv(tmp_path / "aapl.csv")
    bench = _wave_csv(tmp_path / "spy.csv", n=460, start=datetime(2024, 11, 1))
    argv = ["--input", str(data), "--symbol", "AAPL", "--benchmark-input", str(bench)]
    assert strategy.main([*argv, "--report", "auto", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["limits"]["source"] == "defaults"
    assert result["limits"]["max_daily_usd"] == trade.DEFAULTS.max_daily_usd
    assert (
        result["benchmark"]["symbol"] == "SPY" and "cagr_pct" in result["buy_and_hold"]
    )
    trades = result["strategy"]["trades"]
    assert len(result["recent_trades"]) == min(trades, 10)
    assert any("quantstats is not installed" in w for w in result["warnings"])

    (row,) = kc.read_jsonl(journal.strategy_path())
    assert (row["symbol"], row["method"]) == ("AAPL", "ets")
    snapshot = read_snapshot(kc.clawk_home() / "dashboards" / "kronos.json")
    panel = next(p for p in snapshot["panels"] if p["id"] == "strategy")
    (shown,) = panel["rows"]
    assert shown["symbol"] == "AAPL" and shown["forecaster"] == "ETS (built-in)"
    assert shown["benchmark"].startswith("SPY ")

    assert strategy.main([*argv, "--no-record", "--json"]) == 0
    assert len(kc.read_jsonl(journal.strategy_path())) == 1


def test_the_backtest_panel_shows_fresh_and_stale_verdicts_in_spanish(tmp_path):
    now = datetime(2026, 10, 26, 15, 0, tzinfo=kc.UTC)
    kdir = tmp_path / "kronos"
    rows = [
        {
            "symbol": "AAPL",
            "interval": "1 day",
            "verdict": "adds_value",
            "made_at": "2026-10-25T10:00:00Z",
            "origins": 20,
            "mae_skill_vs_naive": 0.05,
            "mae_skill_vs_ets": 0.03,
            "hit_rate": 0.6,
        },
        {
            "symbol": "BTC",
            "interval": "1 day",
            "verdict": "worse_than_naive",
            "made_at": "2026-10-01T10:00:00Z",
            "origins": 20,
            "mae_skill_vs_naive": -0.2,
            "mae_skill_vs_ets": -0.3,
            "hit_rate": 0.4,
        },
    ]
    for row in rows:
        kc.append_jsonl(journal.backtests_path(kdir), row)
    config = tmp_path / "config.yaml"
    config.write_text("display:\n  language: es\n", encoding="utf-8")
    out = dash.refresh(
        config_path=config, kronos_dir=kdir, out=tmp_path / "k.json", now=now
    )
    snapshot = read_snapshot(out)
    panel = next(p for p in snapshot["panels"] if p["id"] == "backtests")
    shown = {r["symbol"]: r for r in panel["rows"]}
    assert (
        shown["AAPL"]["verdict"] == "aporta valor"
        and shown["AAPL"]["_tone"] == "positive"
    )
    assert shown["AAPL"]["vs_ets"] == 3.0
    assert (
        "de más de 7 días" in shown["BTC"]["verdict"]
        and shown["BTC"]["_tone"] == "neutral"
    )
    assert panel["title"] == "Veredictos de backtest"
