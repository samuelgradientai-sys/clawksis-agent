"""Behaviour contracts for the lesson gate in ``finance/kronos`` trading (``etoro_trade.py``).

An automatic buy is refused while the symbol's recent reviewed forecasts mostly missed (at least
5, under 50% right), before any request leaves the machine; an unreadable journal refuses too.
``--user-requested`` skips only that check, never the limits. Refused buys are logged for the
dashboard without counting toward the limits, closes record an estimated P&L, and every
buy/close refreshes the dashboard without a dashboard failure ever breaking the order.
Stdlib fakes only, no network.
"""

from __future__ import annotations

import importlib.util
import io
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
etoro = _load("etoro_data")
trade = _load("etoro_trade")
journal = _load("_kronos_journal")
dashboard = _load("kronos_dashboard")

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=kc.UTC)  # a Monday, 11:00 in New York
SEARCH_AAPL = {
    "items": [
        {"instrumentId": 1001, "internalSymbolFull": "AAPL", "instrumentTypeID": 5}
    ]
}
FILLED = [{"orderId": 77}, {"status": {"id": 3}}]
PROTECTED = ("--stop", "95", "--target", "110")


def _candles(price=100.0, hours=200):
    """Hourly stock candles (no weekend bars) up to the still-forming one at NOW."""
    start = NOW.replace(tzinfo=None) - timedelta(hours=hours - 1)
    stamps = [start + timedelta(hours=i) for i in range(hours)]
    rows = [
        {
            "fromDate": ts.isoformat() + "Z",
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price,
            "volume": 10,
        }
        for ts in stamps
        if ts.weekday() < 5
    ]
    return {"candles": [{"instrumentId": 1001, "candles": rows}]}


MARKET = [SEARCH_AAPL, _candles()]


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Recorder:
    """Fake opener: records requests and replays queued responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        return FakeResponse(json.dumps(self.responses.pop(0)).encode())


def _config(tmp_path: Path, **trading) -> Path:
    lines = ["skills:", "  config:", "    kronos:", "      trading:"]
    lines += [f"        {k}: {v}" for k, v in {"enabled": "true", **trading}.items()]
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "config.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _deps(tmp_path, reader=(), trader=(), backtest="adds_value", **trading):
    reader_rec, trader_rec = Recorder(*reader), Recorder(*trader)
    deps = trade.Deps(
        config_path=_config(tmp_path, **trading),
        ledger=tmp_path / "kronos" / "trades.jsonl",
        now=lambda: NOW,
        reader=etoro.EtoroClient("a", "u", opener=reader_rec),
        trader=trade.TradeClient("a", "u", opener=trader_rec, sleep=lambda _s: None),
        sleep=lambda _s: None,
        dashboard=tmp_path / "dashboards" / "kronos.json",
    )
    if backtest:
        kc.append_jsonl(
            trade.backtests_path(deps.kronos_dir()),
            {
                "symbol": "AAPL",
                "interval": "1 day",
                "verdict": backtest,
                "made_at": (NOW - timedelta(days=2)).isoformat(),
            },
        )
    return deps, reader_rec, trader_rec


def _scored_journal(deps, symbol: str, hits: int, misses: int) -> None:
    """Journal reviewed forecasts for *symbol*: *hits* right calls, then *misses* wrong."""
    rows = []
    for index in range(hits + misses):
        hit = index < hits
        ts = (NOW - timedelta(days=30 - index)).replace(tzinfo=None).isoformat()
        rows.append(
            {
                "id": f"{symbol}-{index}",
                "symbol": symbol,
                "interval": "1 day",
                "direction": "up",
                "outcome": {
                    "actual_timestamp": ts,
                    "actual_direction": "up" if hit else "down",
                    "direction_hit": hit,
                    "error_pct": 1.0,
                    "beat_naive": hit,
                    "in_band": True,
                },
            }
        )
    journal.append_locked(journal.forecasts_path(deps.kronos_dir()), rows)


def _buy_args(*extra, amount="50"):
    protection = () if "--user-requested" in extra else PROTECTED
    return trade.build_parser().parse_args(
        [
            "buy",
            "AAPL",
            "--amount",
            amount,
            "--reason",
            "forecast up",
            *protection,
            *extra,
        ]
    )


def _refusals(deps):
    return kc.read_jsonl(trade.refused_path(deps.kronos_dir()))


def test_automatic_buy_is_refused_while_recent_forecasts_mostly_missed(tmp_path):
    deps, reader, trader_rec = _deps(tmp_path)
    _scored_journal(deps, "AAPL", hits=2, misses=4)
    with pytest.raises(trade.LessonRefused, match="only 2 of its last 6") as caught:
        trade.cmd_buy(_buy_args(), deps)
    assert "--user-requested" in caught.value.hint
    assert reader.requests == [] and trader_rec.requests == []
    assert (
        trade.read_ledger(deps.ledger) == []
    )  # a refusal never counts toward the limits
    (row,) = _refusals(deps)
    assert (row["symbol"], row["kind"], row["amount"]) == ("AAPL", "lesson", 50.0)


def test_too_few_reviewed_forecasts_never_block_and_good_ones_are_logged(tmp_path):
    deps, _, trader_rec = _deps(tmp_path, reader=MARKET, trader=FILLED)
    _scored_journal(deps, "AAPL", hits=0, misses=4)
    result = trade.cmd_buy(_buy_args(), deps)
    assert result["ok"] and len(trader_rec.requests) == 2
    assert result["order"]["track_record"] == {
        "user_requested": False,
        "checked": True,
        "matured": 4,
        "hits": 0,
        "blocked": False,
    }

    deps, _, _ = _deps(tmp_path / "good", reader=MARKET, trader=FILLED)
    _scored_journal(deps, "AAPL", hits=3, misses=3)
    assert trade.cmd_buy(_buy_args(), deps)["order"]["status"] == "filled"
    _scored_journal(
        deps, "TSLA", hits=0, misses=9
    )  # another symbol's misses don't count
    deps.reader = etoro.EtoroClient("a", "u", opener=Recorder(*MARKET))
    deps.trader = trade.TradeClient(
        "a", "u", opener=Recorder(*FILLED), sleep=lambda _s: None
    )
    assert trade.cmd_buy(_buy_args(), deps)["ok"]


def test_user_requested_buy_skips_only_the_lesson_check(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path, reader=MARKET, trader=FILLED, backtest="worse_than_naive"
    )
    _scored_journal(deps, "AAPL", hits=1, misses=5)
    result = trade.cmd_buy(_buy_args("--user-requested"), deps)
    assert result["ok"] and trader_rec.requests
    (entry,) = trade.read_ledger(deps.ledger)
    assert entry["user_requested"] is True and entry["track_record"]["blocked"] is True
    assert entry["backtest"]["blocked"] is True and entry["stop_loss"] is None

    with pytest.raises(trade.TradingRefused, match="per-order limit"):
        trade.cmd_buy(_buy_args("--user-requested", amount="100.01"), deps)
    assert [r["kind"] for r in _refusals(deps)] == ["limit"]


def test_an_unreadable_journal_refuses_automatic_buys(tmp_path):
    deps, reader, _ = _deps(tmp_path, reader=MARKET, trader=FILLED)
    journal.forecasts_path(deps.kronos_dir()).mkdir(
        parents=True
    )  # a directory, not a file
    with pytest.raises(trade.LessonRefused, match="could not be read"):
        trade.cmd_buy(_buy_args(), deps)
    assert reader.requests == []
    result = trade.cmd_buy(_buy_args("--user-requested"), deps)
    assert result["ok"] and result["order"]["track_record"]["checked"] is False


def test_a_refused_dry_run_is_not_logged(tmp_path):
    deps, _, _ = _deps(tmp_path)
    _scored_journal(deps, "AAPL", hits=0, misses=5)
    with pytest.raises(trade.LessonRefused):
        trade.cmd_buy(_buy_args("--dry-run"), deps)
    assert _refusals(deps) == []


def test_close_records_the_symbol_and_an_estimated_pnl(tmp_path):
    portfolio = {
        "clientPortfolio": {
            "positions": [
                {
                    "positionID": 555,
                    "instrumentID": 1001,
                    "units": 2.0,
                    "amount": 400,
                    "openRate": 200.0,
                    "unrealizedPnL": {"pnL": 12.5},
                }
            ]
        }
    }
    deps, _, _ = _deps(
        tmp_path, reader=[portfolio], trader=[{"orderForClose": {"orderID": 12}}]
    )
    trade.append_ledger(
        {"id": "o", "action": "open", "symbol": "AAPL", "instrument_id": 1001},
        deps.ledger,
    )
    args = trade.build_parser().parse_args(
        ["close", "555", "--units", "1", "--reason", "target hit"]
    )
    result = trade.cmd_close(args, deps)
    close = result["close"]
    assert (close["symbol"], close["invested_usd"], close["pnl_usd"]) == (
        "AAPL",
        200.0,
        6.25,
    )
    assert close["open_rate"] == 200.0 and "estimated" in result["note"]


def test_orders_refresh_the_dashboard_even_when_refused(tmp_path, capsys):
    deps, _, _ = _deps(tmp_path, reader=MARKET, trader=FILLED)
    argv = ["buy", "AAPL", "--amount", "40", "--reason", "x", *PROTECTED]
    assert trade.main(argv, deps) == 0
    snap = json.loads(deps.dashboard.read_text(encoding="utf-8"))
    bought = next(p for p in snap["panels"] if p["id"] == "bought")
    assert [row["symbol"] for row in bought["rows"]] == ["AAPL"]

    _scored_journal(deps, "AAPL", hits=0, misses=5)
    with pytest.raises(trade.LessonRefused):
        trade.main(argv, deps)
    snap = json.loads(deps.dashboard.read_text(encoding="utf-8"))
    refused = next(p for p in snap["panels"] if p["id"] == "refused")
    assert len(refused["rows"]) == 1 and refused["rows"][0]["symbol"] == "AAPL"


def test_a_dashboard_failure_never_breaks_an_order(tmp_path, capsys, monkeypatch):
    def broken(**_kwargs):
        raise RuntimeError("renderer bug")

    monkeypatch.setattr(dashboard, "refresh", broken)
    deps, _, _ = _deps(tmp_path, reader=MARKET, trader=FILLED)
    argv = ["buy", "AAPL", "--amount", "40", "--reason", "x", *PROTECTED]
    assert trade.main(argv, deps) == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["order"]["status"] == "filled"
    assert "not refreshed" in out.err and "renderer bug" in out.err
