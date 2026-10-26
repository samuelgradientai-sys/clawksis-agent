"""Behaviour contracts for the classical baseline in ``finance/kronos`` backtests.

``kronos_backtest.py`` now scores Kronos against two baselines, "repeat the last close" and an
exponential-smoothing (ETS) forecast: statsforecast's AutoETS when importable, a built-in Holt
fit otherwise. ``adds_value`` requires beating BOTH, so the verdict only ever gets stricter, and
each finished backtest is recorded so ``etoro_trade.py`` can refuse automatic buys without a
fresh ``adds_value``. Stdlib only: statsforecast, numpy and the model are fakes.
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
baselines = _load("_kronos_baselines")
backtest = _load("kronos_backtest")
trade = _load("etoro_trade")
kmodel = _load("_kronos_model")


@pytest.fixture(autouse=True)
def _no_statsforecast(monkeypatch):
    """The built-in fit answers unless a test installs the fake library."""
    monkeypatch.setitem(sys.modules, "statsforecast", None)
    monkeypatch.setitem(sys.modules, "statsforecast.models", None)


# ── The ETS baseline ──


def test_builtin_holt_follows_a_trend_and_stays_flat_on_flat_prices():
    trend = [100.0 + 0.5 * i for i in range(120)]
    forecast = baselines.holt_forecast(trend, 3)
    assert forecast == sorted(forecast) and forecast[0] > trend[-1]
    assert forecast[-1] == pytest.approx(trend[-1] + 1.5, rel=0.01)
    assert baselines.holt_forecast([50.0] * 80, 2) == pytest.approx([50.0, 50.0])
    assert baselines.holt_forecast([3.0, 4.0], 2) == [4.0, 4.0]


def test_without_statsforecast_the_builtin_fit_is_used_and_named():
    windows = [[100.0 + math.sin(i / 3) for i in range(90)]] * 2
    forecasts, engine = baselines.ets_forecasts(windows, 4)
    assert engine == baselines.ENGINE_BUILTIN and [len(f) for f in forecasts] == [4, 4]


def _fake_statsforecast(monkeypatch, fail_on_length: int | None = None):
    class AutoETS:
        def __init__(self, season_length):
            assert season_length == 1

        def forecast(self, y, h):
            if len(y) == fail_on_length:
                raise ValueError("no ETS model could be fitted")
            return {"mean": [y[-1] + 1.0] * h}

    models = types.ModuleType("statsforecast.models")
    models.AutoETS = AutoETS
    numpy = types.ModuleType("numpy")
    numpy.asarray = lambda values, dtype=None: list(values)
    monkeypatch.setitem(sys.modules, "statsforecast", types.ModuleType("statsforecast"))
    monkeypatch.setitem(sys.modules, "statsforecast.models", models)
    monkeypatch.setitem(sys.modules, "numpy", numpy)


def test_autoets_is_preferred_and_a_window_it_cannot_fit_falls_back(monkeypatch):
    _fake_statsforecast(monkeypatch, fail_on_length=70)
    good, short = [10.0] * 80, [10.0] * 70
    forecasts, engine = baselines.ets_forecasts([good], 2)
    assert engine == baselines.ENGINE_AUTOETS and forecasts == [[11.0, 11.0]]
    forecasts, engine = baselines.ets_forecasts([good, short], 2)
    # Plain comparisons: pytest.approx would consult the fake numpy module.
    assert forecasts[0] == [11.0, 11.0]
    assert [round(v, 9) for v in forecasts[1]] == [10.0, 10.0]
    assert "built-in Holt for 1 window" in engine


# ── Scores and the verdict ──

ORIGINS = [
    {"last_close": 100.0, "actual": [101.0, 102.0], "kronos": [101.0, 102.0]},
    {"last_close": 100.0, "actual": [99.0, 98.0], "kronos": [99.5, 98.5]},
]


def test_ets_scores_appear_only_when_every_origin_has_a_baseline():
    assert kc.score_origins(ORIGINS)["mae_skill_vs_ets"] is None
    with_ets = [{**o, "ets": [o["last_close"]] * 2} for o in ORIGINS]
    scores = kc.score_origins(with_ets)
    assert scores["ets"]["mae"] == scores["naive_last_close"]["mae"] == 1.5
    assert scores["mae_skill_vs_ets"] == pytest.approx(1 - 0.25 / 1.5)
    partial = [with_ets[0], ORIGINS[1]]
    assert kc.score_origins(partial)["ets"] is None


def _scores(skill, ets_skill, hit, origins=20):
    return {
        "origins": origins,
        "mae_skill_vs_naive": skill,
        "mae_skill_vs_ets": ets_skill,
        "kronos": {"direction_hit_rate": hit},
    }


@pytest.mark.parametrize(
    ("skill", "ets_skill", "hit", "code", "detail"),
    [
        (0.10, 0.10, 0.6, "adds_value", "adds_value"),
        (0.10, 0.01, 0.6, "no_clear_edge", "no_edge_over_ets"),
        (0.10, -0.30, 0.9, "no_clear_edge", "no_edge_over_ets"),
        (0.10, None, 0.6, "no_clear_edge", "no_ets_baseline"),
        (0.10, 0.10, 0.4, "no_clear_edge", "no_edge_over_ets"),
        (-0.10, 0.50, 0.9, "worse_than_naive", "worse_than_naive"),
    ],
)
def test_adds_value_needs_both_baselines_beaten(skill, ets_skill, hit, code, detail):
    scores = _scores(skill, ets_skill, hit)
    verdict_code, text = kc.verdict(scores)
    assert (verdict_code, kc.verdict_detail(scores)) == (code, detail)
    if detail.startswith("no_e"):
        assert "ETS" in text


def test_the_new_verdict_never_says_adds_value_where_the_old_one_would_not():
    def old_adds_value(scores):  # the rule before the ETS baseline existed
        return (
            scores["origins"] >= 10
            and scores["mae_skill_vs_naive"] > 0.02
            and scores["kronos"]["direction_hit_rate"] >= 0.5
        )

    grid = [-0.3, -0.02, 0.0, 0.02, 0.021, 0.1, 0.5]
    for skill in grid:
        for ets_skill in [None, *grid]:
            for hit in (0.3, 0.5, 0.8):
                for origins in (6, 10, 30):
                    scores = _scores(skill, ets_skill, hit, origins)
                    if kc.verdict(scores)[0] == "adds_value":
                        assert old_adds_value(scores), scores


# ── The backtest run records its verdict for the buy gate ──

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=kc.UTC)


def _wave_csv(path: Path, n: int = 400) -> dict[datetime, float]:
    closes, rows, day = (
        {},
        ["timestamps,open,high,low,close,volume"],
        datetime(2025, 1, 6),
    )
    i = 0
    while i < n:
        if day.weekday() < 5:
            close = 100 + 10 * math.sin(i / 7) + 0.05 * i
            closes[day] = close
            rows.append(
                f"{day.isoformat()},{close},{close + 1},{close - 1},{close},1000"
            )
            i += 1
        day += timedelta(days=1)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return closes


def _fake_model(monkeypatch, closes, *, oracle: bool):
    """A stand-in predictor: the true future (oracle) or a flat line at the last close."""

    def predict_paths(predictor, windows, future, horizon, **_kwargs):
        out = []
        for window, stamps in zip(windows, future):
            values = [closes[ts] if oracle else window[-1].close for ts in stamps]
            out.append(
                [
                    {"close": v, "open": v, "high": v, "low": v, "volume": 0.0}
                    for v in values
                ]
            )
        return out

    monkeypatch.setattr(backtest, "reexec_in_skill_venv", lambda *_a: None)
    monkeypatch.setattr(backtest, "require_state", dict)
    monkeypatch.setattr(kmodel, "load_predictor", lambda *a, **k: object())
    monkeypatch.setattr(kmodel, "predict_paths", predict_paths)


def _run(tmp_path, capsys, *extra):
    argv = [
        "--input",
        str(tmp_path / "aapl.csv"),
        "--symbol",
        "AAPL",
        "--format",
        "json",
    ]
    assert backtest.main([*argv, *extra]) == 0
    return json.loads(capsys.readouterr().out)


def test_a_backtest_records_its_verdict_and_a_good_one_unlocks_automatic_buys(
    tmp_path, capsys, monkeypatch
):
    closes = _wave_csv(tmp_path / "aapl.csv")
    _fake_model(monkeypatch, closes, oracle=True)
    result = _run(tmp_path, capsys)
    assert result["verdict"] == "adds_value" and result["recorded_as"] == "AAPL"
    assert result["ets_engine"] == baselines.ENGINE_BUILTIN
    assert result["metrics"]["mae_skill_vs_ets"] > 0.02
    assert any("statsforecast is not installed" in w for w in result["warnings"])
    log = trade.backtests_path()
    (row,) = kc.read_jsonl(log)
    assert (row["symbol"], row["verdict"], row["interval"]) == (
        "AAPL",
        "adds_value",
        "1 day",
    )
    gate = trade.check_backtest("aapl", log, datetime.now(kc.UTC), user_requested=False)
    assert gate["blocked"] is False


def test_a_forecast_no_better_than_no_change_keeps_automatic_buys_off(
    tmp_path, capsys, monkeypatch
):
    closes = _wave_csv(tmp_path / "aapl.csv")
    _fake_model(monkeypatch, closes, oracle=False)
    result = _run(tmp_path, capsys)
    assert result["verdict"] == "no_clear_edge"
    log = trade.backtests_path()
    with pytest.raises(trade.BacktestRefused, match="no_clear_edge"):
        trade.check_backtest("AAPL", log, datetime.now(kc.UTC), user_requested=False)


def test_no_record_leaves_the_gate_closed(tmp_path, capsys, monkeypatch):
    closes = _wave_csv(tmp_path / "aapl.csv")
    _fake_model(monkeypatch, closes, oracle=True)
    assert "recorded_as" not in _run(tmp_path, capsys, "--no-record")
    assert kc.read_jsonl(trade.backtests_path()) == []
