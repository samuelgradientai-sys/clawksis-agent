"""Behaviour contracts for ``finance/kronos`` trading (``etoro_trade.py``).

The script places real orders when the user enables it, so every guard is pinned here:
off by default and fail-closed config, per-order and daily limits counted from the ledger,
long-only unleveraged buys with their stop-loss on the configured account, the exact routes the
client may reach, honest outcome logging (rejected vs unknown), and the file lock. Stdlib fakes
only, no network. Order-retry, protection, market-hours, backtest-gate and reconcile contracts
live in ``test_kronos_order_safety.py``.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
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

NOW = datetime(2026, 10, 24, 15, 0, tzinfo=kc.UTC)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code: int, body: dict | None = None):
    payload = json.dumps(body or {}).encode()
    return urllib.error.HTTPError(
        "https://x", code, "err", Message(), io.BytesIO(payload)
    )


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
        return FakeResponse(json.dumps(item).encode())


SEARCH_AAPL = {
    "items": [
        {"instrumentId": 1001, "internalSymbolFull": "AAPL", "instrumentTypeID": 5}
    ]
}
PROTECTED = ("--stop", "95", "--target", "110")  # around the fake price of 100


def _candles(now=NOW, price=100.0, hours=200):
    """Hourly candles up to the still-forming one at *now*, weekends included (24/7)."""
    start = now.replace(minute=0, tzinfo=None) - timedelta(hours=hours - 1)
    rows = [
        {
            "fromDate": (start + timedelta(hours=i)).isoformat() + "Z",
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price,
            "volume": 10,
        }
        for i in range(hours)
    ]
    return {"candles": [{"instrumentId": 1001, "candles": rows}]}


MARKET = [SEARCH_AAPL, _candles()]


def _adds_value(deps, symbol="AAPL"):
    """A fresh backtest verdict that lets automatic buys of *symbol* through."""
    kc.append_jsonl(
        trade.backtests_path(deps.kronos_dir()),
        {
            "symbol": symbol,
            "interval": "1 day",
            "verdict": "adds_value",
            "made_at": (NOW - timedelta(days=1)).isoformat(),
        },
    )


def _config(tmp_path: Path, **trading) -> Path:
    lines = ["skills:", "  config:", "    kronos:", "      trading:"]
    lines += [f"        {k}: {v}" for k, v in trading.items()]
    path = tmp_path / "config.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _deps(tmp_path, config_path, reader_responses=(), trader_responses=()):
    reader_rec, trader_rec = Recorder(*reader_responses), Recorder(*trader_responses)
    deps = trade.Deps(
        config_path=config_path,
        ledger=tmp_path / "kronos" / "trades.jsonl",
        now=lambda: NOW,
        reader=etoro.EtoroClient("api-secret", "user-secret", opener=reader_rec),
        trader=trade.TradeClient(
            "api-secret", "user-secret", opener=trader_rec, sleep=lambda _s: None
        ),
        sleep=lambda _s: None,
    )
    return deps, reader_rec, trader_rec


def _args(*argv):
    return trade.build_parser().parse_args(list(argv))


def _buy(deps, symbol="AAPL", amount="50", extra=PROTECTED):
    return trade.cmd_buy(
        _args("buy", symbol, "--amount", amount, "--reason", "test", *extra), deps
    )


def _ledger_rows(deps):
    return trade.read_ledger(deps.ledger)


# ── Off by default, fail closed ──


def test_trading_is_off_without_config_and_nothing_is_sent(tmp_path):
    deps, reader, trader_rec = _deps(tmp_path, tmp_path / "missing.yaml")
    with pytest.raises(trade.TradingRefused, match="turned off"):
        _buy(deps)
    assert reader.requests == [] and trader_rec.requests == []
    assert trade.load_trading_config(tmp_path / "missing.yaml") == trade.DEFAULTS


def test_unparsable_config_keeps_trading_off(tmp_path):
    bad = tmp_path / "config.yaml"
    bad.write_text("skills: [unclosed\n", encoding="utf-8")
    with pytest.raises(trade.TradingRefused, match="could not be read"):
        trade.load_trading_config(bad)


def test_values_written_as_strings_by_config_set_are_understood(tmp_path):
    path = _config(
        tmp_path,
        enabled="'true'",
        account="DEMO",
        max_order_usd="'150'",
        max_daily_usd=400,
        max_orders_per_day="'2'",
    )
    assert trade.load_trading_config(path) == trade.TradingConfig(
        True, "demo", 150.0, 400.0, 2
    )


@pytest.mark.parametrize(
    "setting", [{"account": "margin"}, {"max_order_usd": -5}, {"enabled": "maybe"}]
)
def test_invalid_settings_refuse_instead_of_guessing(tmp_path, setting):
    with pytest.raises(trade.TradingRefused):
        trade.load_trading_config(_config(tmp_path, **{"enabled": "true", **setting}))


# ── Limits ──


def test_buy_over_the_per_order_limit_never_reaches_eToro(tmp_path):
    deps, reader, trader_rec = _deps(tmp_path, _config(tmp_path, enabled="true"))
    with pytest.raises(trade.TradingRefused, match="per-order limit of 100.00"):
        _buy(deps, amount="100.01")
    assert reader.requests == [] and trader_rec.requests == []


def test_daily_limits_count_only_todays_money_moving_buys_on_this_account(tmp_path):
    deps, _, _ = _deps(
        tmp_path,
        _config(
            tmp_path,
            enabled="true",
            max_order_usd=200,
            max_daily_usd=300,
            max_orders_per_day=3,
        ),
    )
    today, yesterday = NOW.isoformat(), (NOW - timedelta(days=1)).isoformat()
    rows = [
        {
            "id": "a",
            "ts": today,
            "action": "open",
            "account": "demo",
            "amount": 100,
            "status": "filled",
        },
        {
            "id": "b",
            "ts": today,
            "action": "open",
            "account": "demo",
            "amount": 90,
            "status": "unknown",
        },
        {
            "id": "c",
            "ts": today,
            "action": "open",
            "account": "demo",
            "amount": 99,
            "status": "rejected",
        },
        {
            "id": "d",
            "ts": today,
            "action": "open",
            "account": "real",
            "amount": 99,
            "status": "filled",
        },
        {
            "id": "e",
            "ts": yesterday,
            "action": "open",
            "account": "demo",
            "amount": 99,
            "status": "filled",
        },
        {
            "id": "f",
            "ts": today,
            "action": "close",
            "account": "demo",
            "status": "submitted",
        },
    ]
    for row in rows:
        trade.append_ledger(row, deps.ledger)
    assert trade.usage_today(_ledger_rows(deps), "demo", NOW) == (2, 190.0)
    with pytest.raises(trade.TradingRefused, match="daily limit is 300.00 USD"):
        _buy(deps, amount="110.01")
    trade.append_ledger(
        {
            "id": "g",
            "ts": today,
            "action": "open",
            "account": "demo",
            "amount": 1,
            "status": "placed",
        },
        deps.ledger,
    )
    with pytest.raises(trade.TradingRefused, match="limit of 3 buys"):
        _buy(deps, amount="1")


# ── Orders ──


def test_buy_sends_one_unleveraged_long_market_order_to_the_demo_account(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, enabled="true"),
        reader_responses=MARKET,
        trader_responses=[
            {"token": "t", "orderId": 77, "referenceId": "r"},
            {"status": {"id": 3, "name": "Filled"}},
        ],
    )
    _adds_value(deps)
    result = _buy(deps, amount="50")
    order_request, lookup_request = trader_rec.requests
    assert order_request.get_method() == "POST"
    assert order_request.full_url == (
        "https://public-api.etoro.com/api/v2/trading/execution/demo/orders"
    )
    assert json.loads(order_request.data) == {
        "action": "open",
        "transaction": "buy",
        "instrumentId": 1001,
        "settlementType": "real",
        "orderType": "mkt",
        "leverage": 1,
        "amount": 50.0,
        "stopLossRate": 95.0,
        "stopLossType": "fixed",
        "takeProfitRate": 110.0,
    }
    assert lookup_request.full_url.endswith(
        "/api/v2/trading/info/demo/orders:lookup?orderId=77"
    )
    (row,) = _ledger_rows(deps)
    headers = {k.lower(): v for k, v in order_request.header_items()}
    assert headers["x-request-id"] == row["id"]  # the lookup handle is the logged id
    assert (row["status"], row["order_id"], row["reason"]) == ("filled", 77, "test")
    assert (row["stop_loss"], row["take_profit"]) == (95.0, 110.0)
    assert result["ok"] and result["order"]["status"] == "filled"
    assert result["limits"]["usd_left_after"] == 250.0


def test_real_account_orders_use_the_real_routes(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, enabled="true", account="real"),
        reader_responses=MARKET,
        trader_responses=[
            {"orderId": 5},
            {"status": {"id": 2}},
            {"status": {"id": 2}},
            {"status": {"id": 2}},
        ],
    )
    _adds_value(deps)
    result = _buy(deps)
    assert trader_rec.requests[0].full_url.endswith("/api/v2/trading/execution/orders")
    assert "/demo/" not in trader_rec.requests[1].full_url
    assert result["order"]["status"] == "placed" and result["ok"]


def test_rejected_order_is_logged_and_frees_the_daily_limit(tmp_path):
    deps, _, _ = _deps(
        tmp_path,
        _config(tmp_path, enabled="true"),
        reader_responses=MARKET,
        trader_responses=[_http_error(400, {"errorMessage": "amount below minimum"})],
    )
    _adds_value(deps)
    with pytest.raises(etoro.EtoroError, match="amount below minimum"):
        _buy(deps, amount="5")
    (row,) = _ledger_rows(deps)
    assert row["status"] == "rejected"
    assert trade.usage_today(_ledger_rows(deps), "demo", NOW) == (0, 0.0)


def test_an_unanswered_order_keeps_counting_until_confirmed(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, enabled="true"),
        reader_responses=MARKET,
        trader_responses=[urllib.error.URLError("timed out")],
    )
    _adds_value(deps)
    with pytest.raises(etoro.EtoroError) as caught:
        _buy(deps, amount="60")
    assert "reconcile" in caught.value.hint
    assert len(trader_rec.requests) == 1  # never resent blindly
    assert trade.usage_today(_ledger_rows(deps), "demo", NOW) == (1, 60.0)


def test_legacy_route_is_used_only_when_the_v2_route_is_missing(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, enabled="true"),
        reader_responses=MARKET,
        trader_responses=[
            _http_error(404),
            {"orderForOpen": {"orderID": 9}, "token": "t"},
            {"status": {"id": 3}},
        ],
    )
    # Only an unprotected (user-requested) buy may fall back: v1 may drop a stop.
    result = _buy(deps, amount="20", extra=("--user-requested",))
    v2, v1, _lookup = trader_rec.requests
    assert v1.full_url.endswith(
        "/api/v1/trading/execution/demo/market-open-orders/by-amount"
    )
    assert json.loads(v1.data) == {
        "InstrumentID": 1001,
        "IsBuy": True,
        "Leverage": 1,
        "Amount": 20.0,
    }
    assert v1.get_header("X-request-id") != v2.get_header("X-request-id")
    assert result["order"]["order_id"] == 9 and result["order"]["api"] == "v1"

    deps, _, trader_rec = _deps(
        tmp_path / "second",
        _config(tmp_path, enabled="true"),
        reader_responses=MARKET,
        trader_responses=[_http_error(500)],
    )
    _adds_value(deps)
    with pytest.raises(etoro.EtoroError):
        _buy(deps)
    assert (
        len(trader_rec.requests) == 1
    )  # an ambiguous failure never triggers a second order


def test_dry_run_checks_everything_and_sends_nothing(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path, _config(tmp_path, enabled="true"), reader_responses=MARKET
    )
    _adds_value(deps)
    result = trade.cmd_buy(
        _args(
            "buy", "AAPL", "--amount", "40", "--reason", "x", "--dry-run", *PROTECTED
        ),
        deps,
    )
    assert result["dry_run"] and result["would_buy"]["leverage"] == 1
    assert result["would_buy"]["market"]["price"] == 100.0
    assert trader_rec.requests == [] and _ledger_rows(deps) == []


# ── Closes ──

PORTFOLIO = {
    "clientPortfolio": {
        "positions": [
            {
                "positionID": 555,
                "instrumentID": 1001,
                "isBuy": True,
                "units": 2.0,
                "amount": 400,
            }
        ]
    }
}


def test_close_sells_an_existing_position_on_the_configured_account(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, enabled="true"),
        reader_responses=[PORTFOLIO],
        trader_responses=[{"orderForClose": {"orderID": 12}, "token": "t"}],
    )
    result = trade.cmd_close(_args("close", "555", "--reason", "turned down"), deps)
    (request,) = trader_rec.requests
    assert request.full_url.endswith(
        "/api/v1/trading/execution/demo/market-close-orders/positions/555"
    )
    assert json.loads(request.data) == {"InstrumentId": 1001, "UnitsToDeduct": None}
    assert result["close"]["order_id"] == 12
    (row,) = _ledger_rows(deps)
    assert row["action"] == "close" and row["status"] == "submitted"


@pytest.mark.parametrize(
    "argv", [["999"], ["555", "--units", "3"], ["555", "--units", "0"]]
)
def test_close_refuses_unknown_positions_and_impossible_units(tmp_path, argv):
    deps, _, trader_rec = _deps(
        tmp_path, _config(tmp_path, enabled="true"), reader_responses=[PORTFOLIO]
    )
    with pytest.raises(trade.TradingRefused):
        trade.cmd_close(_args("close", *argv, "--reason", "x"), deps)
    assert trader_rec.requests == []


PROTECTABLE = {
    "clientPortfolio": {
        "positions": [
            {
                "positionID": 555,
                "instrumentID": 1001,
                "isBuy": True,
                "units": 2.0,
                "amount": 400,
                "openRate": 200,
                "stopLossRate": 0.0001,
                "unrealizedPnL": {"pnL": -20},  # price ~190
            }
        ]
    }
}


def test_set_stop_puts_a_broker_stop_on_an_open_position(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, enabled="true"),
        reader_responses=[PROTECTABLE],
        trader_responses=[{"operationId": "op", "positionId": 555}],
    )
    result = trade.cmd_set_stop(
        _args(
            "set-stop", "555", "--stop", "180", "--target", "230", "--reason", "no stop"
        ),
        deps,
    )
    (request,) = trader_rec.requests
    assert request.get_method() == "PATCH"
    assert request.full_url.endswith("/api/v2/trading/demo/positions/555")
    assert json.loads(request.data) == {
        "stopLossRate": 180.0,
        "stopLossType": "fixed",
        "takeProfitRate": 230.0,
    }
    (row,) = _ledger_rows(deps)
    assert row["action"] == "protect" and row["status"] == "submitted"
    assert row["stop_loss"] == 180.0 and result["ok"]


def test_set_stop_trailing_asks_etoro_for_a_trailing_stop(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, enabled="true"),
        reader_responses=[PROTECTABLE],
        trader_responses=[{"operationId": "op", "positionId": 555}],
    )
    trade.cmd_set_stop(
        _args("set-stop", "555", "--stop", "180", "--trailing", "--reason", "meme"),
        deps,
    )
    (request,) = trader_rec.requests
    assert json.loads(request.data) == {
        "stopLossRate": 180.0,
        "stopLossType": "trailing",
    }
    (row,) = _ledger_rows(deps)
    assert row["trailing_stop"] is True


def test_buy_order_fields_carry_a_trailing_stop_only_when_asked():
    order = {"stop_loss": 95.0, "take_profit": None}
    assert trade._protection_fields(order) == {
        "stopLossRate": 95.0,
        "stopLossType": "fixed",
    }
    assert trade._protection_fields({**order, "trailing_stop": True}) == {
        "stopLossRate": 95.0,
        "stopLossType": "trailing",
    }


def test_buy_refuses_trailing_without_a_stop(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path, _config(tmp_path, enabled="true"), reader_responses=MARKET
    )
    with pytest.raises(trade.TradingRefused, match="--trailing needs --stop"):
        _buy(deps, extra=["--trailing", "--dry-run"])
    assert trader_rec.requests == []


@pytest.mark.parametrize(
    "argv",
    [
        ["555", "--stop", "195"],  # above the ~190 price: eToro would close it at once
        ["555", "--stop", "0"],
        ["555", "--stop", "180", "--target", "185"],
        ["999", "--stop", "180"],
    ],
)
def test_set_stop_refuses_a_stop_that_would_close_or_an_unknown_position(
    tmp_path, argv
):
    deps, _, trader_rec = _deps(
        tmp_path, _config(tmp_path, enabled="true"), reader_responses=[PROTECTABLE]
    )
    with pytest.raises(trade.TradingRefused):
        trade.cmd_set_stop(_args("set-stop", *argv, "--reason", "x"), deps)
    assert trader_rec.requests == []


def test_set_stop_dry_run_sends_nothing(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path, _config(tmp_path, enabled="true"), reader_responses=[PROTECTABLE]
    )
    result = trade.cmd_set_stop(
        _args("set-stop", "555", "--stop", "180", "--reason", "x", "--dry-run"), deps
    )
    assert result["would_protect"]["stop_loss"] == 180.0
    assert trader_rec.requests == [] and _ledger_rows(deps) == []


# ── Client surface and lock ──


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PATCH", "/api/v2/trading/positions/1/close"),
        ("DELETE", "/api/v2/trading/demo/positions/1"),
        ("DELETE", "/api/v2/trading/execution/demo/orders/1"),
        ("POST", "/api/v2/trading/execution/demo/orders/1"),
        ("GET", "/api/v1/trading/info/demo/pnl"),
        ("POST", "/api/v1/watchlists"),
    ],
)
def test_trade_client_reaches_only_its_trading_routes(method, path):
    rec = Recorder()
    client = trade.TradeClient("a", "u", opener=rec)
    with pytest.raises(trade.TradingRefused, match="Refusing"):
        client.send(method, path)
    assert rec.requests == []


def test_a_held_lock_blocks_a_second_order_and_a_stale_one_is_reclaimed(tmp_path):
    lock_path = tmp_path / "trades.lock"
    clock = iter(range(0, 1000, 5))
    with trade.LedgerLock(lock_path):
        waiting = trade.LedgerLock(
            lock_path, timeout=10, sleep=lambda _s: None, clock=lambda: next(clock)
        )
        with pytest.raises(trade.TradingRefused, match="still being placed"):
            waiting.__enter__()
    assert not lock_path.exists()

    lock_path.write_text("123", encoding="utf-8")
    old = lock_path.stat().st_mtime - trade.LedgerLock.stale_after - 5
    os.utime(lock_path, (old, old))
    with trade.LedgerLock(lock_path):
        assert lock_path.read_text(encoding="utf-8") != "123"


def test_status_cli_reports_settings_and_what_is_left_today(tmp_path, capsys):
    deps, _, _ = _deps(tmp_path, _config(tmp_path, enabled="true", max_daily_usd=300))
    trade.append_ledger(
        {
            "id": "a",
            "ts": NOW.isoformat(),
            "action": "open",
            "account": "demo",
            "amount": 120,
            "status": "filled",
        },
        deps.ledger,
    )
    assert trade.main(["status"], deps) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["config"]["enabled"] is True and out["config"]["account"] == "demo"
    assert out["today_utc"] == {
        "buys": 1,
        "usd": 120.0,
        "buys_left": 4,
        "usd_left": 180.0,
    }


def test_position_and_stop_settings_default_parse_and_fail_closed(tmp_path):
    defaults = trade.load_trading_config(tmp_path / "missing.yaml")
    assert (defaults.max_positions, defaults.stop_pct) == (5, 0.0)  # 0 = ATR stop
    path = _config(tmp_path, max_positions="'3'", stop_pct="'8.5'")
    config = trade.load_trading_config(path)
    assert (config.max_positions, config.stop_pct) == (3, 8.5)
    for setting in ({"stop_pct": 60}, {"stop_pct": -1}, {"stop_pct": "wide"}):
        with pytest.raises(trade.TradingRefused, match="stop_pct must be a number"):
            trade.load_trading_config(_config(tmp_path, **setting))
    with pytest.raises(trade.TradingRefused, match="max_positions"):
        trade.load_trading_config(_config(tmp_path, max_positions=0))


def _held(deps, instrument_id, *, days_ago=1):
    trade.append_ledger(
        {
            "id": f"held-{instrument_id}",
            "ts": (NOW - timedelta(days=days_ago)).isoformat(),
            "action": "open",
            "account": "demo",
            "symbol": f"S{instrument_id}",
            "instrument_id": instrument_id,
            "amount": 50.0,
            "status": "filled",
        },
        deps.ledger,
    )


def test_stock_buys_stop_at_five_open_positions_by_default(tmp_path):
    deps, reader, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, enabled="true"),
        reader_responses=MARKET,
        trader_responses=[{"orderId": 3}, {"status": {"id": 3}}],
    )
    _adds_value(deps)
    for instrument_id in range(1, 6):
        _held(deps, instrument_id)
    with pytest.raises(trade.TradingRefused, match="already holds 5 stock position"):
        _buy(deps)
    assert reader.requests == [] and trader_rec.requests == []
    (refusal,) = kc.read_jsonl(trade.refused_path(deps.kronos_dir()))
    assert (refusal["kind"], refusal["bucket"]) == ("limit", "stock")

    # A full close frees the slot; the buy then goes through exactly as before.
    trade.append_ledger(
        {
            "id": "close-1",
            "ts": NOW.isoformat(),
            "action": "close",
            "account": "demo",
            "instrument_id": 1,
            "units": "all",
            "status": "submitted",
        },
        deps.ledger,
    )
    result = _buy(deps)
    assert result["order"]["status"] == "filled"
    assert result["limits"]["usd_left_after"] == 250.0
    assert (result["limits"]["positions_open"], result["limits"]["max_positions"]) == (
        4,
        5,
    )


def test_an_unreadable_ledger_refuses_the_buy(tmp_path):
    deps, reader, trader_rec = _deps(tmp_path, _config(tmp_path, enabled="true"))
    deps.ledger.mkdir(parents=True)  # a directory where the ledger should be
    with pytest.raises(trade.TradingRefused, match="ledger could not be read"):
        _buy(deps)
    assert reader.requests == [] and trader_rec.requests == []
    (refusal,) = kc.read_jsonl(trade.refused_path(deps.kronos_dir()))
    assert refusal["kind"] == "limit"


@pytest.mark.parametrize(
    ("stop_pct", "stop", "refused"),
    [
        (None, "60", False),  # default: ATR stops, only the 50% typo bound applies
        ("10", "60", True),
        ("10", "89.5", False),  # 10.5%: inside the one-point slack
    ],
)
def test_a_stock_stop_pct_bounds_the_stop_and_the_default_keeps_atr_stops(
    tmp_path, stop_pct, stop, refused
):
    settings = {"enabled": "true", **({"stop_pct": stop_pct} if stop_pct else {})}
    deps, _, trader_rec = _deps(
        tmp_path, _config(tmp_path, **settings), reader_responses=MARKET
    )
    _adds_value(deps)
    extra = ("--stop", stop, "--dry-run")
    if refused:
        with pytest.raises(trade.ProtectionRefused, match="stop-loss is 10%"):
            _buy(deps, extra=extra)
    else:
        assert _buy(deps, extra=extra)["would_buy"]["stop_loss"] == float(stop)
    assert trader_rec.requests == []


def test_positions_lists_ids_the_agent_needs_to_sell(tmp_path):
    deps, reader, _ = _deps(
        tmp_path,
        _config(tmp_path),  # reading positions works even with trading off
        reader_responses=[
            PORTFOLIO,
            {"instrumentDisplayDatas": [{"symbolFull": "AAPL"}]},
        ],
    )
    result = trade.cmd_positions(_args("positions"), deps)
    (row,) = result["positions"]
    assert (row["position_id"], row["symbol"], row["units"]) == (555, "AAPL", 2.0)
    assert all(r.get_method() == "GET" for r in reader.requests)
