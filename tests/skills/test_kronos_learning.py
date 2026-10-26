"""Behaviour contracts for the Kronos learning loop (``finance/kronos``).

The forecast journal, scoring matured forecasts against real bars, recent accuracy per
symbol, lessons (rules, dedupe, retirement, English/Spanish text) and the ``kronos_review.py``
CLI with bar files or a fake eToro fetcher. Stdlib fakes only: no network, no torch.
"""

from __future__ import annotations

import importlib.util
import json
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
journal = _load("_kronos_journal")
lessons = _load("_kronos_lessons")
forecast = _load("kronos_forecast")
review = _load("kronos_review")

NOW = datetime(2026, 10, 26, 14, 0, tzinfo=kc.UTC)
DAY = 86400


def _bars(closes, start=datetime(2026, 6, 1), step=timedelta(days=1), weekdays=True):
    out, ts = [], start
    for close in closes:
        while weekdays and ts.weekday() >= 5:
            ts += step
        out.append(kc.Bar(ts, close, close + 1, close - 1, close, 1000.0))
        ts += step
    return out


def _csv(path: Path, bars) -> Path:
    lines = ["timestamps,open,high,low,close,volume"]
    lines += [
        f"{b.ts.isoformat()},{b.open},{b.high},{b.low},{b.close},{b.volume}"
        for b in bars
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _result(bars, origin: int, predicted: float, horizon: int = 5, band=None):
    last = bars[origin]
    change = (predicted - last.close) / last.close * 100.0
    return {
        "interval": "1 day",
        "horizon": horizon,
        "model": "Kronos-small",
        "last_timestamp": last.ts.isoformat(),
        "last_close": last.close,
        "forecast": [{"timestamp": bars[origin + horizon].ts.isoformat()}],
        "summary": {
            "close_at_horizon": predicted,
            "pct_change": change,
            "direction": kc.direction_of(change),
            "band_at_horizon": band or [predicted - 0.5, predicted + 0.5],
        },
        "warnings": [],
    }


def _journal_calls(home: Path, bars, calls, symbol="AAPL", step=DAY):
    """Journal one forecast per (origin, predicted) pair; returns the forecast results."""
    results = []
    for origin, predicted in calls:
        result = _result(bars, origin, predicted)
        forecast.journal_forecast(
            result,
            label=symbol,
            source="file",
            step_seconds=step,
            kronos_dir=home,
            now=NOW,
        )
        results.append(result)
    return results


def _run_review(home: Path, *argv: str, fetch=None, capsys=None) -> dict:
    deps = review.ReviewDeps(
        kronos_dir=home,
        config_path=home / "missing.yaml",
        dashboard=home / "dash.json",
        now=lambda: NOW,
        fetch=fetch,
    )
    assert review.main([*argv, "--json"], deps) == 0
    return json.loads(capsys.readouterr().out)


# A steadily rising series: "up" calls hit, "down" calls miss.
RISING = [100.0 + i for i in range(80)]


# ── Journal ──


def test_every_forecast_is_journaled_with_what_the_review_needs(tmp_path):
    bars = _bars(RISING)
    (result,) = _journal_calls(tmp_path, bars, [(40, 147.0)])
    (record,) = journal.read_forecasts(journal.forecasts_path(tmp_path))
    assert record["symbol"] == "AAPL" and record["made_at"] == "2026-10-26T14:00:00Z"
    assert (record["horizon"], record["step_seconds"], record["direction"]) == (
        5,
        DAY,
        "up",
    )
    assert record["last_close"] == 140.0 and record["predicted_close"] == 147.0
    assert record["target_timestamp"] == bars[45].ts.isoformat()
    assert result["journal"]["id"] == record["id"]
    assert result["track_record"]["matured"] == 0 and result["lessons"] == []


def test_a_journal_that_cannot_be_written_only_adds_a_warning(tmp_path):
    blocker = tmp_path / "kronos"
    blocker.write_text("not a directory", encoding="utf-8")
    result = _result(_bars(RISING), 40, 147.0)
    forecast.journal_forecast(
        result,
        label="AAPL",
        source="file",
        step_seconds=DAY,
        kronos_dir=blocker,
        now=NOW,
    )
    assert any("not journaled" in w for w in result["warnings"])
    assert "journal" not in result


def test_forecast_flags_and_labels_match_trades(tmp_path):
    args = forecast.build_parser().parse_args(["--input", "x.csv", "--no-journal"])
    assert args.no_journal is True and args.symbol is None
    assert forecast.journal_label(args, {"input": "/data/aapl_1d.csv"}) == "AAPL_1D"
    args = forecast.build_parser().parse_args(["--etoro", "aapl", "--symbol", "aapl"])
    assert forecast.journal_label(args, {"symbol": "AAPL"}) == "AAPL"


# ── Scoring ──


def test_the_actual_price_is_the_horizon_th_bar_after_the_forecast():
    bars = _bars(RISING)
    record = journal.forecast_record(
        _result(bars, 40, 147.0, band=[144.0, 150.0]),
        label="AAPL",
        source="file",
        step_seconds=DAY,
        now=NOW,
    )
    # An exchange holiday the forecast calendar did not know about: drop one bar.
    holiday = bars[:43] + bars[44:]
    outcome = journal.evaluate(record, holiday, NOW)
    assert outcome["actual_close"] == bars[46].close == 146.0
    assert outcome["direction_hit"] is True and outcome["actual_direction"] == "up"
    assert outcome["error_pct"] == pytest.approx(1 / 146 * 100)
    assert outcome["naive_error_pct"] == pytest.approx(6 / 146 * 100)
    assert outcome["beat_naive"] is True and outcome["in_band"] is True


def test_scoring_waits_for_the_horizon_and_refuses_misaligned_bars():
    bars = _bars(RISING)
    record = journal.forecast_record(
        _result(bars, 40, 147.0), label="AAPL", source="file", step_seconds=DAY, now=NOW
    )
    assert journal.evaluate(record, bars[:44], NOW) is None  # only 3 bars after
    assert journal.evaluate(record, bars[41:], NOW) is None  # starts after the forecast
    target = kc.parse_timestamp(record["target_timestamp"])
    assert not journal.is_due(record, target + timedelta(hours=23))
    assert journal.is_due(record, target.replace(tzinfo=kc.UTC) + timedelta(days=1))


def test_recent_accuracy_looks_only_at_the_latest_window(tmp_path):
    bars = _bars(RISING)
    misses = [(o, bars[o].close - 3) for o in range(10, 30, 2)]
    hits = [(o, bars[o].close + 3) for o in range(30, 70, 4)]
    _journal_calls(tmp_path, bars, misses + hits)
    path = journal.forecasts_path(tmp_path)
    journal.append_locked(
        path,
        [
            {"id": r["id"], "outcome": journal.evaluate(r, bars, NOW)}
            for r in journal.read_forecasts(path)
        ],
    )
    records = journal.read_forecasts(path)
    gate = journal.gate_status(records, "aapl")
    assert (gate["matured"], gate["hits"], gate["blocked"]) == (10, 10, False)
    assert journal.gate_status(records, "aapl", window=20)["hits"] == 10


# ── Review CLI and lessons ──


def test_review_scores_due_forecasts_and_writes_lessons_once(tmp_path, capsys):
    bars = _bars([100.0 + i for i in range(90)])
    calls = [(o, bars[o].close - 2) for o in (10, 15, 20, 25, 30)]  # 5 misses
    calls += [(o, bars[o].close + 2) for o in (35, 40)]  # 2 hits
    calls += [(76, 200.0)]  # its horizon bar is not in the file yet
    _journal_calls(tmp_path, bars, calls)
    csv = _csv(tmp_path / "aapl.csv", bars[:80])

    out = _run_review(tmp_path, "--bars", f"AAPL={csv}", capsys=capsys)
    assert (out["reviewed_now"], out["hits_now"], out["misses_now"]) == (7, 2, 5)
    assert out["waiting"] == 1
    (gate,) = out["buy_gate"]
    assert (gate["symbol"], gate["matured"], gate["hits"], gate["blocked"]) == (
        "AAPL",
        7,
        2,
        True,
    )
    texts = [lesson["text"] for lesson in out["lessons"]]
    assert any("automatic buys are blocked" in t and "2/7" in t for t in texts)
    assert any("direction right only 2/7" in t for t in texts)
    assert (tmp_path / "dash.json").exists() and out["dashboard"]

    lines = lessons.lessons_path(tmp_path).read_text(encoding="utf-8").splitlines()
    again = _run_review(tmp_path, "--bars", f"AAPL={csv}", capsys=capsys)
    assert again["reviewed_now"] == 0 and again["lesson_changes"] == 0
    assert (
        lessons.lessons_path(tmp_path).read_text(encoding="utf-8").splitlines() == lines
    )


def test_lessons_retire_when_their_condition_stops_holding(tmp_path):
    path = lessons.lessons_path(tmp_path)
    lesson = lessons._lesson(
        "low_accuracy", "negative", "AAPL", "1 day", {"hits": 1, "n": 6}
    )
    lessons.update_lessons({lesson["key"]: lesson}, NOW, path)
    assert [x["key"] for x in lessons.active_lessons(path)] == [lesson["key"]]
    retired = lessons.update_lessons({}, NOW + timedelta(days=1), path)
    assert retired == [
        {"key": lesson["key"], "active": False, "updated_at": "2026-10-27T14:00:00Z"}
    ]
    assert lessons.active_lessons(path) == []
    (kept,) = lessons.all_lessons(path)
    assert kept["text"] == lesson["text"] and kept["active"] is False


def test_lessons_read_naturally_in_spanish():
    lesson = lessons._lesson(
        "low_accuracy", "negative", "AAPL", "1 day", {"hits": 2, "n": 7}
    )
    assert lesson["text"].startswith("AAPL 1 day: direction right only 2/7")
    spanish = lessons.render(lesson, "es")
    assert spanish.startswith("AAPL 1 día: acertó la dirección solo 2/7")
    assert lessons.interval_label("4 hours", "es") == "4 horas"


def test_closed_trades_and_unconfirmed_orders_become_lessons():
    ledger = [
        {
            "id": "o",
            "action": "open",
            "symbol": "AAPL",
            "instrument_id": 1001,
            "status": "filled",
        },
        {
            "id": "u",
            "action": "open",
            "symbol": "TSLA",
            "instrument_id": 7,
            "status": "unknown",
        },
        {"id": "a", "action": "close", "instrument_id": 1001, "pnl_usd": -5.0},
        {"id": "b", "action": "close", "instrument_id": 1001, "pnl_usd": -3.0},
        {"id": "c", "action": "close", "instrument_id": 1001, "pnl_usd": 1.0},
        {
            "id": "f",
            "action": "close",
            "instrument_id": 1001,
            "pnl_usd": 99.0,
            "status": "failed",
        },
    ]
    assert lessons.trade_stats(ledger) == {
        "AAPL": {"n": 3, "wins": 1, "losses": 2, "net": -7.0}
    }
    current = lessons.build_lessons([], ledger)
    losing = current["losing_trades|AAPL|"]
    assert "2 of 3 closed trades lost money (-$7.00)" in losing["text"]
    assert current["unknown_orders||"]["evidence"] == {"count": 1}


def test_review_fetches_etoro_candles_matching_each_forecast(tmp_path, capsys):
    hourly = _bars(
        RISING, start=datetime(2026, 10, 20), step=timedelta(hours=1), weekdays=False
    )
    _journal_calls(
        tmp_path, hourly, [(30, hourly[30].close + 2)], symbol="BTC", step=3600
    )
    calls = []

    def fake_fetch(symbol, interval, count):
        calls.append((symbol, interval, count))
        return hourly, {"symbol": symbol}, []

    out = _run_review(tmp_path, "--etoro", fetch=fake_fetch, capsys=capsys)
    ((symbol, interval, count),) = calls
    assert (symbol, interval) == ("BTC", "OneHour") and 0 < count <= 1000
    assert out["reviewed_now"] == 1 and out["scored"][0]["hit"] is True


def test_review_explains_missing_or_mismatched_prices(tmp_path, capsys):
    bars = _bars(RISING)
    _journal_calls(tmp_path, bars, [(40, 147.0)])
    out = _run_review(tmp_path, capsys=capsys)
    assert out["reviewed_now"] == 0
    assert any(
        "no prices" in note and "--bars AAPL=FILE" in note for note in out["notes"]
    )

    hourly = _bars(RISING, step=timedelta(hours=1), weekdays=False)
    csv = _csv(tmp_path / "aapl_1h.csv", hourly)
    out = _run_review(tmp_path, "--bars", f"AAPL={csv}", capsys=capsys)
    assert out["reviewed_now"] == 0
    assert any("1 hour bars" in note and "1 day bars" in note for note in out["notes"])


def test_review_rejects_a_bars_argument_without_a_symbol():
    with pytest.raises(SystemExit):
        review.build_parser().parse_args(["--bars", "aapl.csv"])
