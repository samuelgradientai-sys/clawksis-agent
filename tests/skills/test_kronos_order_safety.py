"""Behaviour contracts for order safety in ``finance/kronos`` trading (``etoro_trade.py``).

eToro order requests carry no idempotency guarantee, so an order POST is resent only after HTTP
429 (eToro did not process it), honouring Retry-After; a 5xx, timeout, dropped connection or
unreadable answer is never resent and the buy stays ``unknown``, counted toward the limits until
``reconcile`` settles it from eToro's own records without ever freeing the limits. Automatic buys
carry a stop-loss checked against the current price, need a fresh ``adds_value`` backtest, and
no buy goes out while the instrument's market is closed. Stdlib fakes only, no network.
"""

from __future__ import annotations

import http.client
import importlib.util
import io
import json
import sys
import types
import urllib.error
from datetime import datetime, timedelta
from email.message import Message
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

MONDAY = datetime(2026, 10, 26, 15, 0, tzinfo=kc.UTC)  # 11:00 in New York, market open
SEARCH = {"items": [{"instrumentId": 1001, "internalSymbolFull": "AAPL"}]}
PROTECTED = ("--stop", "95", "--target", "110")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RawResponse(FakeResponse):
    """A 200 whose body is not JSON."""


def _http_error(code: int, headers: dict | None = None):
    msg = Message()
    for key, value in (headers or {}).items():
        msg[key] = value
    return urllib.error.HTTPError("https://x", code, "err", msg, io.BytesIO(b"{}"))


class Recorder:
    """Fake opener: records requests and replays queued responses or exceptions."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, RawResponse):
            return item
        return FakeResponse(json.dumps(item).encode())


def _candles(now=MONDAY, price=100.0, weekends=True, hours=200, last_age_hours=0):
    """Hourly candles ending *last_age_hours* before *now* (the newest one still forming)."""
    newest = now.replace(minute=0, tzinfo=None) - timedelta(hours=last_age_hours)
    stamps = [newest - timedelta(hours=hours - 1 - i) for i in range(hours)]
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
        if weekends or ts.weekday() < 5
    ]
    return {"candles": [{"instrumentId": 1001, "candles": rows}]}


def _config(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "config.yaml"
    path.write_text(
        "skills:\n  config:\n    kronos:\n      trading:\n        enabled: true\n",
        encoding="utf-8",
    )
    return path


def _backtest(deps, verdict="adds_value", *, days_ago=1, interval="1 day", now=MONDAY):
    kc.append_jsonl(
        trade.backtests_path(deps.kronos_dir()),
        {
            "symbol": "AAPL",
            "interval": interval,
            "verdict": verdict,
            "made_at": (now - timedelta(days=days_ago)).isoformat(),
        },
    )


def _deps(tmp_path, reader=(), trader=(), now=MONDAY, verdict="adds_value"):
    reader_rec, trader_rec = Recorder(*reader), Recorder(*trader)
    sleeps: list[float] = []
    deps = trade.Deps(
        config_path=_config(tmp_path),
        ledger=tmp_path / "kronos" / "trades.jsonl",
        now=lambda: now,
        reader=etoro.EtoroClient("a", "u", opener=reader_rec, sleep=sleeps.append),
        trader=trade.TradeClient("a", "u", opener=trader_rec, sleep=sleeps.append),
        sleep=lambda _s: None,
        dashboard=tmp_path / "dashboards" / "kronos.json",
    )
    if verdict:
        _backtest(deps, verdict, now=now)
    return deps, reader_rec, trader_rec, sleeps


def _buy(deps, *extra, amount="50"):
    argv = ["buy", "AAPL", "--amount", amount, "--reason", "test", *extra]
    return trade.cmd_buy(trade.build_parser().parse_args(argv), deps)


def _posts(recorder):
    return [r for r in recorder.requests if r.get_method() == "POST"]


def _usage(deps, now=MONDAY):
    return trade.usage_today(trade.read_ledger(deps.ledger), "demo", now)


def _refusals(deps):
    return kc.read_jsonl(trade.refused_path(deps.kronos_dir()))


# ── At most once: only 429 is resent ──


@pytest.mark.parametrize(
    "failure",
    [
        _http_error(500),
        _http_error(503),
        urllib.error.URLError("timed out"),
        TimeoutError("read timed out"),
        ConnectionResetError("reset by peer"),
        http.client.RemoteDisconnected("closed without response"),
        http.client.IncompleteRead(b"{"),
        RawResponse(b"<html>gateway</html>"),
    ],
    ids=[
        "http500",
        "http503",
        "urlerror",
        "timeout",
        "reset",
        "disconnected",
        "incomplete",
        "not_json",
    ],
)
def test_an_ambiguous_order_failure_is_never_resent_and_keeps_counting(
    tmp_path, failure
):
    deps, _, trader_rec, sleeps = _deps(
        tmp_path, reader=[SEARCH, _candles()], trader=[failure]
    )
    with pytest.raises(etoro.EtoroError) as caught:
        _buy(deps, *PROTECTED, amount="60")
    assert len(_posts(trader_rec)) == 1 and sleeps == []
    (row,) = trade.read_ledger(deps.ledger)
    assert row["status"] == "unknown"
    assert _usage(deps) == (1, 60.0)  # counts toward today's limits until settled
    assert "reconcile" in caught.value.hint


def test_a_rate_limited_order_is_resent_with_the_same_id_after_retry_after(tmp_path):
    deps, _, trader_rec, sleeps = _deps(
        tmp_path,
        reader=[SEARCH, _candles()],
        trader=[
            _http_error(429, {"Retry-After": "7"}),
            _http_error(429),
            {"orderId": 77},
            {"status": {"id": 3}},
        ],
    )
    result = _buy(deps, *PROTECTED)
    posts = _posts(trader_rec)
    assert len(posts) == 3 and result["order"]["status"] == "filled"
    assert {p.get_header("X-request-id") for p in posts} == {result["order"]["id"]}
    # Retry-After when given, else the 15 s step of the backoff; nothing else slept.
    assert sleeps[:2] == [7.0, 30.0]


def test_a_persistent_rate_limit_gives_up_and_frees_the_limit(tmp_path):
    deps, _, trader_rec, sleeps = _deps(
        tmp_path,
        reader=[SEARCH, _candles()],
        trader=[_http_error(429, {"Retry-After": "600"})] * 4,
    )
    with pytest.raises(etoro.EtoroError) as caught:
        _buy(deps, *PROTECTED)
    assert caught.value.status == 429 and len(_posts(trader_rec)) == 4
    assert sleeps == [trade.MAX_WRITE_RETRY_AFTER] * 3  # Retry-After is capped
    (row,) = trade.read_ledger(deps.ledger)
    assert row["status"] == "rejected"  # every attempt was refused unprocessed
    assert _usage(deps) == (0, 0.0)


def test_reads_retry_a_429_once_and_backoff_defaults_without_a_header():
    rec = Recorder(_http_error(429), {"status": {"id": 2}})
    sleeps: list[float] = []
    client = trade.TradeClient("a", "u", opener=rec, sleep=sleeps.append)
    assert client.lookup("demo", 5) == ("placed", None)
    assert sleeps == [trade.READ_RETRY_WAITS[0]]

    rec = Recorder(_http_error(429), _http_error(429))
    client = trade.TradeClient("a", "u", opener=rec, sleep=lambda _s: None)
    assert client.lookup("demo", 5) == ("submitted", None)  # unknown, not an error
    assert len(rec.requests) == 2


def test_the_ledger_lock_outlives_the_longest_order_attempt():
    attempts = len(trade.WRITE_RETRY_WAITS) + 1
    timeout = trade.TradeClient("a", "u")._timeout
    per_route = attempts * timeout + len(trade.WRITE_RETRY_WAITS) * (
        trade.MAX_WRITE_RETRY_AFTER
    )
    assert trade.LedgerLock.stale_after > 2 * per_route  # v2, then the v1 fallback


def test_an_ambiguous_close_is_not_resent_and_says_to_check_first(tmp_path):
    portfolio = {
        "clientPortfolio": {
            "positions": [{"positionID": 555, "instrumentID": 1001, "units": 2.0}]
        }
    }
    deps, _, trader_rec, _ = _deps(
        tmp_path, reader=[portfolio], trader=[_http_error(502)]
    )
    args = trade.build_parser().parse_args(
        ["close", "555", "--units", "1", "--reason", "x"]
    )
    with pytest.raises(etoro.EtoroError) as caught:
        trade.cmd_close(args, deps)
    assert len(_posts(trader_rec)) == 1 and "twice" in caught.value.hint
    (row,) = trade.read_ledger(deps.ledger)
    assert row["status"] == "failed" and row["in_doubt"] is True


# ── Stop-loss and take-profit ──


def test_an_automatic_buy_without_a_stop_is_refused_before_any_request(tmp_path):
    deps, reader, trader_rec, _ = _deps(tmp_path)
    with pytest.raises(trade.ProtectionRefused, match="needs a stop-loss") as caught:
        _buy(deps, "--target", "110")
    assert "kronos_risk.py" in caught.value.hint
    assert reader.requests == [] and trader_rec.requests == []
    (row,) = _refusals(deps)
    assert row["kind"] == "stop" and trade.read_ledger(deps.ledger) == []


def test_a_user_requested_buy_may_omit_the_stop(tmp_path):
    deps, _, trader_rec, _ = _deps(
        tmp_path,
        reader=[SEARCH, _candles()],
        trader=[{"orderId": 7}, {"status": {"id": 3}}],
        verdict=None,  # the backtest gate is skipped for a user-requested buy too
    )
    result = _buy(deps, "--user-requested")
    body = json.loads(_posts(trader_rec)[0].data)
    assert result["ok"] and not {"stopLossRate", "takeProfitRate"} & set(body)


@pytest.mark.parametrize(
    ("levels", "match"),
    [
        (("--stop", "100"), "not below the current price"),
        (("--stop", "101", "--target", "120"), "not below the current price"),
        (("--stop", "40"), "more than 50% below"),
        (("--stop", "95", "--target", "99"), "not above the current price"),
    ],
)
def test_stops_and_targets_on_the_wrong_side_of_the_price_never_reach_eToro(
    tmp_path, levels, match
):
    deps, _, trader_rec, _ = _deps(tmp_path, reader=[SEARCH, _candles(price=100.0)])
    with pytest.raises(trade.ProtectionRefused, match=match):
        _buy(deps, *levels)
    assert trader_rec.requests == [] and trade.read_ledger(deps.ledger) == []


@pytest.mark.parametrize(
    "levels",
    [("--stop", "110", "--target", "105"), ("--stop", "-1"), ("--stop", "nan")],
)
def test_impossible_levels_are_refused_without_any_request(tmp_path, levels):
    deps, reader, trader_rec, _ = _deps(tmp_path)
    with pytest.raises(trade.ProtectionRefused):
        _buy(deps, *levels)
    assert reader.requests == [] and trader_rec.requests == []


def test_a_protected_buy_never_falls_back_to_the_route_that_may_drop_its_stop(
    tmp_path,
):
    deps, _, trader_rec, _ = _deps(
        tmp_path, reader=[SEARCH, _candles()], trader=[_http_error(404)]
    )
    with pytest.raises(etoro.EtoroError, match="nothing was bought"):
        _buy(deps, *PROTECTED)
    (post,) = _posts(trader_rec)
    assert "/api/v2/" in post.full_url
    assert trade.read_ledger(deps.ledger)[0]["status"] == "rejected"
    assert _usage(deps) == (0, 0.0)


# ── Market hours ──

THANKSGIVING = datetime(2026, 11, 26, 16, 0, tzinfo=kc.UTC)  # a weekday holiday
EARLY_CLOSE_DAY = datetime(
    2026, 11, 27, 18, 30, tzinfo=kc.UTC
)  # 13:30 NY, closed at 13:00
SATURDAY = datetime(2026, 10, 24, 15, 0, tzinfo=kc.UTC)


@pytest.mark.parametrize(
    "now", [THANKSGIVING, EARLY_CLOSE_DAY, datetime(2026, 10, 26, 21, 0, tzinfo=kc.UTC)]
)
def test_stocks_are_never_bought_while_the_new_york_market_is_closed(tmp_path, now):
    stock = _candles(now=now, weekends=False)  # fresh prices, but no weekend trading
    deps, _, trader_rec, _ = _deps(tmp_path, reader=[SEARCH, stock], now=now)
    with pytest.raises(trade.MarketRefused, match="closed") as caught:
        _buy(deps, *PROTECTED)
    assert "next regular session" in caught.value.hint
    assert trader_rec.requests == [] and _refusals(deps)[0]["kind"] == "market"

    # The user asking for it does not open the market either.
    deps, _, trader_rec, _ = _deps(
        tmp_path / "user", reader=[SEARCH, stock], now=now, verdict=None
    )
    with pytest.raises(trade.MarketRefused):
        _buy(deps, "--user-requested")
    assert trader_rec.requests == []


def test_a_stock_is_bought_inside_the_session_and_an_early_close_morning_counts(
    tmp_path,
):
    morning = datetime(2026, 11, 27, 17, 30, tzinfo=kc.UTC)  # 12:30 NY, before 13:00
    deps, _, trader_rec, _ = _deps(
        tmp_path,
        reader=[SEARCH, _candles(now=morning, weekends=False)],
        trader=[{"orderId": 1}, {"status": {"id": 3}}],
        now=morning,
    )
    result = _buy(deps, *PROTECTED)
    assert result["order"]["market"]["calendar"] == "nyse" and _posts(trader_rec)


def test_stale_prices_refuse_and_weekend_traders_buy_on_saturday(tmp_path):
    stale = _candles(now=SATURDAY, weekends=False)  # newest candle: Friday evening
    deps, _, trader_rec, _ = _deps(tmp_path, reader=[SEARCH, stale], now=SATURDAY)
    with pytest.raises(trade.MarketRefused, match="looks closed"):
        _buy(deps, *PROTECTED)
    assert trader_rec.requests == []

    deps, _, trader_rec, _ = _deps(
        tmp_path / "crypto",
        reader=[SEARCH, _candles(now=SATURDAY, weekends=True)],
        trader=[{"orderId": 2}, {"status": {"id": 3}}],
        now=SATURDAY,
    )
    assert _buy(deps, *PROTECTED)["order"]["market"]["calendar"] == "24x7"


def test_an_instrument_etoro_marks_untradable_is_refused(tmp_path):
    search = {"items": [{**SEARCH["items"][0], "isCurrentlyTradable": False}]}
    deps, _, trader_rec, _ = _deps(tmp_path, reader=[search, _candles()])
    with pytest.raises(trade.MarketRefused, match="not tradable"):
        _buy(deps, *PROTECTED)
    assert trader_rec.requests == []


# ── Backtest gate ──


@pytest.mark.parametrize(
    ("setup", "match"),
    [
        ([], "No backtest of AAPL"),
        ([("adds_value", 8, "1 day")], "No backtest of AAPL in the last 7 days"),
        ([("adds_value", 3, "1 day"), ("no_clear_edge", 1, "1 day")], "no_clear_edge"),
        ([("adds_value", 1, "1 day"), ("worse_than_naive", 2, "1 hour")], "worse"),
    ],
    ids=["none", "stale", "newest_says_no", "other_bar_size_says_no"],
)
def test_automatic_buys_need_a_fresh_adds_value_backtest(tmp_path, setup, match):
    deps, reader, trader_rec, _ = _deps(tmp_path, verdict=None)
    for verdict, days_ago, interval in setup:
        _backtest(deps, verdict, days_ago=days_ago, interval=interval)
    with pytest.raises(trade.BacktestRefused, match=match) as caught:
        _buy(deps, *PROTECTED)
    assert "--user-requested" in caught.value.hint
    assert reader.requests == [] and trader_rec.requests == []
    assert _refusals(deps)[0]["kind"] == "backtest"


def test_an_unreadable_backtest_log_refuses_automatic_buys(tmp_path):
    deps, reader, _, _ = _deps(tmp_path, verdict=None)
    trade.backtests_path(deps.kronos_dir()).mkdir(parents=True)
    with pytest.raises(trade.BacktestRefused, match="could not be read"):
        _buy(deps, *PROTECTED)
    assert reader.requests == []


# ── Reconcile ──


def _unknown_buy(deps, *, minutes_ago=5, now=MONDAY, amount=60.0):
    entry = {
        "id": "req-1",
        "legacy_request_id": "req-1-v1",
        "ts": (now - timedelta(minutes=minutes_ago)).isoformat(),
        "action": "open",
        "account": "demo",
        "symbol": "AAPL",
        "instrument_id": 1001,
        "amount": amount,
        "status": "unknown",
    }
    trade.append_ledger(entry, deps.ledger)
    return entry


def _reconcile(deps):
    return trade.cmd_reconcile(trade.build_parser().parse_args(["reconcile"]), deps)


def test_reconcile_finds_a_landed_buy_by_its_request_id(tmp_path):
    portfolio = {
        "clientPortfolio": {
            "positions": [{"positionID": 9, "instrumentID": 1001, "orderID": 4242}]
        }
    }
    deps, reader, trader_rec, _ = _deps(
        tmp_path,
        reader=[portfolio],
        trader=[{"orderId": 4242, "status": {"id": 3}}],
    )
    _unknown_buy(deps)
    result = _reconcile(deps)
    (lookup,) = trader_rec.requests
    assert lookup.get_method() == "GET" and "referenceId=req-1" in lookup.full_url
    (row,) = trade.read_ledger(deps.ledger)
    assert (row["status"], row["order_id"]) == ("filled", 4242)
    assert result["reconciled"][0]["status"] == "filled"
    assert all(r.get_method() == "GET" for r in reader.requests + trader_rec.requests)


def test_reconcile_matches_a_pending_order_by_instrument_time_and_amount(tmp_path):
    pending = {
        "instrumentID": 1001,
        "amount": 60.0,
        "openDateTime": (MONDAY - timedelta(minutes=4)).isoformat(),
    }
    portfolio = {"clientPortfolio": {"positions": [], "ordersForOpen": [pending]}}
    deps, _, _, _ = _deps(
        tmp_path, reader=[portfolio], trader=[_http_error(404), _http_error(404)]
    )
    _unknown_buy(deps)
    _reconcile(deps)
    assert trade.read_ledger(deps.ledger)[0]["status"] == "placed"


def test_a_buy_eToro_never_saw_becomes_not_found_and_still_counts(tmp_path):
    older_position = {
        "instrumentID": 1001,
        "amount": 60.0,
        "openDateTime": (MONDAY - timedelta(days=3)).isoformat(),  # not this buy
    }
    portfolio = {"clientPortfolio": {"positions": [older_position]}}
    deps, _, _, _ = _deps(
        tmp_path,
        reader=[portfolio],
        trader=[{"status": {"id": 4, "errorMessage": "rejected"}}],
    )
    _unknown_buy(deps)
    before = _usage(deps)
    result = _reconcile(deps)
    (row,) = trade.read_ledger(deps.ledger)
    assert row["status"] == "not_found" and "tell the user" in row["reconcile_note"]
    assert _usage(deps) == before == (1, 60.0)  # reconcile never frees a limit
    assert result["reconciled"][0]["symbol"] == "AAPL"


def test_reconcile_leaves_a_buy_younger_than_a_minute_alone(tmp_path):
    deps, _, trader_rec, _ = _deps(tmp_path, reader=[{"clientPortfolio": {}}])
    _unknown_buy(deps, minutes_ago=0)
    result = _reconcile(deps)
    assert result["too_recent"] == ["req-1"] and trader_rec.requests == []
    assert trade.read_ledger(deps.ledger)[0]["status"] == "unknown"


def test_reconcile_with_nothing_in_doubt_makes_no_request(tmp_path, capsys):
    deps, reader, trader_rec, _ = _deps(tmp_path)
    assert trade.main(["reconcile"], deps) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["reconciled"] == [] and reader.requests == trader_rec.requests == []
