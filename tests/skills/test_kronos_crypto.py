"""Behaviour contracts for crypto and meme-coin buys in ``finance/kronos`` (``etoro_trade.py``).

Crypto is its own bucket: off until the user turns ``kronos.crypto.enabled`` on, with its own
caps that stock buys never touch (and the other way round). Meme coins are a riskier sub-bucket
with their own switch and caps that also count against the crypto caps, and a meme coin eToro
does not list is refused. Classification follows eToro's instrument type, else Saturday trading.
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
crypto = _load("_kronos_crypto")
etoro = _load("etoro_data")
trade = _load("etoro_trade")
risk = _load("kronos_risk")

NOW = datetime(
    2026, 10, 24, 15, 0, tzinfo=kc.UTC
)  # a Saturday: only 24/7 markets trade
PROTECTED = ("--stop", "95", "--target", "110")  # around the fake price of 100
STOCK_TYPE, CRYPTO_TYPE = 5, 10


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


def _search(symbol, type_id=CRYPTO_TYPE, instrument_id=100000):
    item = {"instrumentId": instrument_id, "internalSymbolFull": symbol}
    if type_id is not None:
        item["instrumentTypeID"] = type_id
    return {"items": [item]}


def _candles(price=100.0, hours=200):
    """Hourly candles up to the still-forming one at NOW, weekends included (24/7)."""
    start = NOW.replace(minute=0, tzinfo=None) - timedelta(hours=hours - 1)
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
    return {"candles": [{"instrumentId": 100000, "candles": rows}]}


FILLED = [{"orderId": 7}, {"status": {"id": 3}}]


def _config(tmp_path: Path, crypto_lines: str = "", trading: str = "true") -> Path:
    text = (
        f"skills:\n  config:\n    kronos:\n      trading:\n        enabled: {trading}\n"
    )
    if crypto_lines:
        text += "      crypto:\n" + "".join(
            f"        {line}\n" for line in crypto_lines.strip("\n").split("\n")
        )
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


CRYPTO_ON = "enabled: true"
MEME_ON = "enabled: true\nmeme:\n  enabled: true"


def _deps(tmp_path, config_path, reader=(), trader=()):
    reader_rec, trader_rec = Recorder(*reader), Recorder(*trader)
    deps = trade.Deps(
        config_path=config_path,
        ledger=tmp_path / "kronos" / "trades.jsonl",
        now=lambda: NOW,
        reader=etoro.EtoroClient("a", "u", opener=reader_rec),
        trader=trade.TradeClient("a", "u", opener=trader_rec, sleep=lambda _s: None),
        sleep=lambda _s: None,
    )
    return deps, reader_rec, trader_rec


def _adds_value(deps, symbol):
    kc.append_jsonl(
        trade.backtests_path(deps.kronos_dir()),
        {
            "symbol": symbol,
            "interval": "1 hour",
            "verdict": "adds_value",
            "made_at": (NOW - timedelta(days=1)).isoformat(),
        },
    )


def _buy(deps, symbol, amount="20", extra=PROTECTED):
    args = trade.build_parser().parse_args(
        ["buy", symbol, "--amount", amount, "--reason", "test", *extra]
    )
    return trade.cmd_buy(args, deps)


def _bought(deps, bucket, amount, n=1, symbol="X"):
    for i in range(n):
        trade.append_ledger(
            {
                "id": f"{bucket}-{amount}-{i}",
                "ts": NOW.isoformat(),
                "action": "open",
                "account": "demo",
                "symbol": symbol,
                "amount": amount,
                "status": "filled",
                **({"bucket": bucket} if bucket else {}),
            },
            deps.ledger,
        )


def _refusals(deps):
    return kc.read_jsonl(trade.refused_path(deps.kronos_dir()))


# ── Switches ──


def test_crypto_is_refused_while_crypto_trading_is_off(tmp_path):
    deps, reader, trader_rec = _deps(
        tmp_path, _config(tmp_path), reader=[_search("BTC"), _candles()]
    )
    _adds_value(deps, "BTC")
    with pytest.raises(trade.CryptoRefused, match="Crypto trading is turned off"):
        _buy(deps, "BTC")
    assert (
        len(reader.requests) == 2 and trader_rec.requests == []
    )  # search + price only
    (row,) = _refusals(deps)
    assert (row["kind"], row["bucket"], row["symbol"]) == ("crypto", "crypto", "BTC")


def test_a_crypto_on_the_users_watchlist_is_refused_before_any_request(tmp_path):
    deps, reader, trader_rec = _deps(
        tmp_path, _config(tmp_path, "enabled: false\nwatchlist: BTC, ETH")
    )
    with pytest.raises(trade.CryptoRefused):
        _buy(deps, "eth")
    assert reader.requests == [] and trader_rec.requests == []


def test_a_meme_coin_needs_its_own_switch_on_top_of_crypto(tmp_path):
    deps, reader, trader_rec = _deps(tmp_path, _config(tmp_path, CRYPTO_ON))
    with pytest.raises(trade.CryptoRefused, match="Meme-coin trading is turned off"):
        _buy(deps, "DOGE")
    assert reader.requests == [] and trader_rec.requests == []
    assert _refusals(deps)[0]["bucket"] == "meme"


def test_the_main_trading_switch_still_gates_crypto(tmp_path):
    deps, reader, _ = _deps(tmp_path, _config(tmp_path, MEME_ON, trading="false"))
    with pytest.raises(trade.TradingRefused, match="Trading is turned off"):
        _buy(deps, "DOGE")
    assert reader.requests == []


# ── Orders and buckets ──


def test_a_crypto_buy_is_logged_in_its_bucket_and_leaves_the_stock_caps_alone(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, CRYPTO_ON),
        reader=[_search("BTC"), _candles()],
        trader=FILLED,
    )
    _adds_value(deps, "BTC")
    _bought(deps, None, 100.0, n=3)  # 300 USD of stocks: the stock daily cap is used up
    result = _buy(deps, "BTC", amount="40")
    order = json.loads(trader_rec.requests[0].data)
    assert (order["leverage"], order["transaction"], order["amount"]) == (
        1,
        "buy",
        40.0,
    )
    assert order["stopLossRate"] == 95.0  # the stop travels with a crypto order too
    assert (
        result["order"]["bucket"] == "crypto" and result["order"]["status"] == "filled"
    )
    assert result["limits"]["bucket"] == "crypto"
    assert result["limits"]["usd_left_after"] == 110.0  # 150 crypto cap - 40
    rows = trade.read_ledger(deps.ledger)
    assert trade.usage_today(rows, "demo", NOW) == (3, 300.0)  # stock usage unchanged
    assert trade.usage_today(rows, "demo", NOW, frozenset({"crypto"})) == (1, 40.0)


def test_stock_buys_never_count_against_the_crypto_caps(tmp_path):
    deps, _, _ = _deps(
        tmp_path,
        _config(tmp_path, CRYPTO_ON),
        reader=[_search("BTC"), _candles()],
        trader=FILLED,
    )
    _adds_value(deps, "BTC")
    _bought(deps, "stock", 100.0, n=2)
    assert _buy(deps, "BTC", amount="50")["limits"]["orders_today"] == 0


@pytest.mark.parametrize(
    ("ledger", "amount", "match"),
    [
        ([], "50.01", "crypto per-order limit of 50.00"),
        (
            [("crypto", 100.0, 1), ("meme", 40.0, 1)],
            "20",
            "crypto daily limit is 150.00",
        ),
        ([("crypto", 10.0, 3)], "5", "limit of 3 crypto buys"),
    ],
)
def test_crypto_caps_are_enforced_per_bucket(tmp_path, ledger, amount, match):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, CRYPTO_ON + "\nwatchlist: BTC"),
    )
    for bucket, usd, n in ledger:
        _bought(deps, bucket, usd, n=n)
    with pytest.raises(trade.TradingRefused, match=match):
        _buy(deps, "BTC", amount=amount)
    assert trader_rec.requests == []
    assert _refusals(deps)[0]["bucket"] == "crypto"


@pytest.mark.parametrize(
    ("ledger", "amount", "match"),
    [
        ([], "20.01", "meme-coin per-order limit of 20.00"),
        ([("meme", 20.0, 2)], "15", "meme-coin daily limit is 50.00"),
        ([("crypto", 140.0, 1)], "15", "crypto daily limit"),
    ],
)
def test_meme_coins_count_against_their_own_caps_and_the_crypto_caps(
    tmp_path, ledger, amount, match
):
    roomy = MEME_ON + "\n  max_orders_per_day: 5\n  max_positions: 5"
    deps, reader, _ = _deps(tmp_path, _config(tmp_path, roomy))
    for bucket, usd, n in ledger:
        _bought(deps, bucket, usd, n=n)
    with pytest.raises(trade.TradingRefused, match=match):
        _buy(deps, "PEPE", amount=amount)
    assert reader.requests == []


def test_a_meme_coin_buy_goes_through_inside_both_caps(tmp_path):
    deps, _, _ = _deps(
        tmp_path,
        _config(tmp_path, MEME_ON),
        reader=[_search("DOGE"), _candles()],
        trader=FILLED,
    )
    _adds_value(deps, "DOGE")
    _bought(deps, "crypto", 100.0)
    result = _buy(deps, "DOGE", amount="20")
    assert result["order"]["bucket"] == "meme"
    assert result["limits"]["usd_left_after"] == 30.0  # meme: 50 - 20
    assert result["limits"]["crypto_usd_left_after"] == 30.0  # crypto: 150 - 100 - 20


def test_a_meme_coin_etoro_does_not_list_is_refused(tmp_path):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, MEME_ON),
        reader=[_search("SHIBxM", instrument_id=5)],
    )
    _adds_value(deps, "SHIB")
    with pytest.raises(trade.CryptoRefused, match="does not list the meme coin SHIB"):
        _buy(deps, "SHIB")
    assert trader_rec.requests == []
    (row,) = _refusals(deps)
    assert (row["kind"], row["bucket"]) == ("crypto", "meme")


def test_a_coin_listed_per_million_units_stays_a_meme_coin(tmp_path):
    deps, _, _ = _deps(
        tmp_path,
        _config(tmp_path, CRYPTO_ON),  # meme coins off
        reader=[_search("SHIBxM"), _candles()],
    )
    _adds_value(deps, "SHIBxM")
    with pytest.raises(trade.CryptoRefused, match="Meme-coin trading is turned off"):
        _buy(deps, "SHIBxM")


def test_a_stock_over_its_caps_is_still_refused_while_crypto_is_on(tmp_path):
    # An unlisted symbol could be a crypto, so with crypto on the stock refusal waits for
    # eToro to name the instrument; a stock then gets exactly the stock refusal.
    deps, reader, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, CRYPTO_ON),
        reader=[_search("AAPL", type_id=STOCK_TYPE, instrument_id=1001), _candles()],
    )
    _adds_value(deps, "AAPL")
    _bought(deps, None, 100.0, n=3)
    with pytest.raises(trade.TradingRefused, match="the daily limit is 300.00 USD"):
        _buy(deps, "AAPL", amount="10")
    assert len(reader.requests) == 2 and trader_rec.requests == []
    assert _refusals(deps)[0]["bucket"] == "stock"


def test_a_stock_with_no_crypto_settings_buys_as_before(tmp_path):
    deps, _, _ = _deps(
        tmp_path,
        _config(tmp_path),
        reader=[_search("AAPL", type_id=STOCK_TYPE, instrument_id=1001), _candles()],
        trader=FILLED,
    )
    _adds_value(deps, "AAPL")
    _bought(deps, "crypto", 150.0)  # crypto spending never eats the stock cap
    result = _buy(deps, "AAPL", amount="100")
    assert result["order"]["bucket"] == "stock"
    assert result["limits"]["usd_left_after"] == 200.0


# ── Classification and settings ──


@pytest.mark.parametrize(
    ("type_id", "weekends", "expected"),
    [
        (10, False, "crypto"),
        ("10", True, "crypto"),
        (5, True, "stock"),  # eToro's type wins over the price history
        (None, True, "crypto"),  # no type: Saturday trading means crypto (fail closed)
        (None, False, "stock"),
    ],
)
def test_classification_follows_the_etoro_type_else_saturday_trading(
    type_id, weekends, expected
):
    instrument = {} if type_id is None else {"instrumentTypeID": type_id}
    settings = crypto.CRYPTO_DEFAULTS
    assert crypto.classify(("X",), instrument, weekends, settings) == expected
    # A symbol on the meme list is a meme coin whatever eToro calls it.
    assert crypto.classify(("x", "WIF"), instrument, weekends, settings) == "meme"


def test_settings_written_by_the_dashboard_or_config_set_are_understood(tmp_path):
    path = _config(
        tmp_path,
        "enabled: 'true'\nmax_order_usd: '75'\nwatchlist: [btc, ETH]\n"
        "meme:\n  enabled: on\n  symbols: doge; bonk\n  max_daily_usd: 30",
    )
    settings = trade.load_crypto_config(path)
    assert settings.enabled and settings.meme_enabled
    assert settings.max_order_usd == 75.0 and settings.meme_max_daily_usd == 30.0
    assert settings.watchlist == ("BTC", "ETH")
    assert settings.meme_symbols == ("DOGE", "BONK")
    assert trade.load_crypto_config(tmp_path / "missing.yaml") == crypto.CRYPTO_DEFAULTS


@pytest.mark.parametrize(
    "lines", ["enabled: maybe", "max_daily_usd: -1", "meme:\n  max_order_usd: zero"]
)
def test_invalid_crypto_settings_refuse_instead_of_guessing(tmp_path, lines):
    with pytest.raises(trade.TradingRefused, match="skills.config.kronos.crypto"):
        trade.load_crypto_config(_config(tmp_path, lines))


def test_status_reports_the_crypto_and_meme_caps_separately(tmp_path, capsys):
    deps, _, _ = _deps(tmp_path, _config(tmp_path, MEME_ON))
    _bought(deps, None, 120.0)
    _bought(deps, "crypto", 30.0)
    _bought(deps, "meme", 10.0)
    assert trade.main(["status"], deps) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["today_utc"] == {
        "buys": 1,
        "usd": 120.0,
        "buys_left": 4,
        "usd_left": 180.0,
    }
    assert out["crypto"]["config"]["enabled"] is True
    assert out["crypto"]["today_utc"] == {
        "buys": 2,
        "usd": 40.0,
        "buys_left": 1,
        "usd_left": 110.0,
    }
    assert out["crypto"]["meme_today_utc"] == {
        "buys": 1,
        "usd": 10.0,
        "buys_left": 0,  # one meme-coin buy a day by default
        "usd_left": 40.0,
    }
    assert out["positions"] == {
        "open": 1,
        "max": 5,
        "left": 4,
        "stop": {"kind": "atr", "atr_mult": 2.0},
    }
    assert out["crypto"]["positions"]["open"] == 1  # the meme coin takes no crypto slot
    assert out["crypto"]["positions"]["stop"] == {"kind": "fixed_pct", "stop_pct": 12.0}
    assert out["crypto"]["meme_positions"] == {
        "open": 1,
        "max": 1,
        "left": 0,
        "stop": {"kind": "fixed_pct", "stop_pct": 20.0},
    }


def test_sizing_a_meme_coin_uses_the_tighter_meme_and_crypto_caps(tmp_path, capsys):
    config = _config(tmp_path, MEME_ON)
    ledger = tmp_path / "kronos" / "trades.jsonl"
    deps = risk.RiskDeps(config_path=config, ledger=ledger, now=lambda: NOW)
    argv = ["--account-size", "100000", "--entry", "1", "--stop", "0.8", "--json"]
    assert risk.main([*argv, "--asset", "meme"], deps) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["limits"]["bucket"] == "meme" and out["limits"]["max_order_usd"] == 20.0
    assert out["suggested_amount_usd"] == 20.0
    assert any("extremely volatile" in w for w in out["warnings"])

    assert risk.main([*argv, "--asset", "crypto"], deps) == 0
    assert json.loads(capsys.readouterr().out)["suggested_amount_usd"] == 50.0


# ── Open positions, meme order cap and stop rule per bucket ──

positions = _load("_kronos_positions")
YESTERDAY = (NOW - timedelta(days=1)).isoformat()


def _held(deps, bucket, symbol, instrument_id, *, ts=YESTERDAY):
    """A position Kronos opened earlier (yesterday: today's caps stay untouched)."""
    trade.append_ledger(
        {
            "id": f"{symbol}-{instrument_id}-{ts}",
            "ts": ts,
            "action": "open",
            "account": "demo",
            "symbol": symbol,
            "instrument_id": instrument_id,
            "amount": 10.0,
            "status": "filled",
            "bucket": bucket,
        },
        deps.ledger,
    )


@pytest.mark.parametrize(
    ("held", "symbol", "match", "bucket"),
    [
        (
            [("crypto", "BTC", 100000), ("crypto", "ETH", 100001)],
            "SOL",
            "already holds 2 crypto position",
            "crypto",
        ),
        (
            [("meme", "DOGE", 100043)],
            "PEPE",
            "already holds 1 meme-coin position",
            "meme",
        ),
    ],
)
def test_a_bucket_at_its_maximum_of_open_positions_refuses_before_any_request(
    tmp_path, held, symbol, match, bucket
):
    deps, reader, trader_rec = _deps(
        tmp_path, _config(tmp_path, MEME_ON + "\nwatchlist: BTC, ETH, SOL")
    )
    for args in held:
        _held(deps, *args)
    with pytest.raises(trade.TradingRefused, match=match) as caught:
        _buy(deps, symbol)
    assert "reconcile" in caught.value.hint
    assert reader.requests == [] and trader_rec.requests == []
    (row,) = _refusals(deps)
    assert (row["kind"], row["bucket"]) == ("limit", bucket)


def test_a_meme_coin_takes_a_meme_slot_not_a_crypto_one(tmp_path):
    deps, _, _ = _deps(
        tmp_path,
        _config(tmp_path, MEME_ON),
        reader=[_search("BTC"), _candles()],
        trader=FILLED,
    )
    _adds_value(deps, "BTC")
    _held(deps, "meme", "DOGE", 100043)
    _held(deps, "crypto", "ETH", 100001)
    result = _buy(deps, "BTC")
    assert result["order"]["status"] == "filled"
    limits = result["limits"]
    assert (limits["positions_open"], limits["max_positions"]) == (1, 2)


def test_the_position_cap_is_checked_again_inside_the_lock(tmp_path):
    # Another run takes the last crypto slot while this one waits for the ledger lock.
    deps, reader, trader_rec = _deps(
        tmp_path, _config(tmp_path, CRYPTO_ON), reader=[_search("BTC"), _candles()]
    )
    _adds_value(deps, "BTC")
    _held(deps, "crypto", "ETH", 100001)
    unlocked = deps.lock

    def racing_lock():
        _held(deps, "crypto", "SOL", 100002, ts=NOW.isoformat())
        return unlocked()

    deps.lock = racing_lock
    with pytest.raises(trade.TradingRefused, match="already holds 2 crypto position"):
        _buy(deps, "BTC")
    assert len(reader.requests) == 2 and trader_rec.requests == []
    assert {r["status"] for r in trade.read_ledger(deps.ledger)} == {"filled"}


def test_meme_coins_have_their_own_daily_order_cap_and_count_as_crypto_buys(tmp_path):
    deps, reader, _ = _deps(tmp_path, _config(tmp_path, MEME_ON + "\nwatchlist: BTC"))
    _bought(deps, "meme", 5.0)
    with pytest.raises(trade.TradingRefused, match="limit of 1 meme-coin buys"):
        _buy(deps, "PEPE", amount="5")
    _bought(deps, "crypto", 10.0, n=2)
    with pytest.raises(trade.TradingRefused, match="limit of 3 crypto buys"):
        _buy(deps, "BTC", amount="5")
    assert reader.requests == []


@pytest.mark.parametrize(
    ("bucket_lines", "symbol", "stop", "refused"),
    [
        (CRYPTO_ON, "BTC", "80", True),  # 20% below 100; crypto's stop_pct is 12
        (CRYPTO_ON, "BTC", "87.5", False),  # 12.5%: inside the one-point slack
        (MEME_ON, "DOGE", "78", True),  # meme coins: 20% (+1 point of slack)
        (MEME_ON, "DOGE", "81", False),
        (
            CRYPTO_ON + "\nstop_pct: 0",
            "BTC",
            "60",
            False,
        ),  # 0 = ATR: only the 50% bound
    ],
)
def test_a_fixed_stop_pct_refuses_wider_stops(
    tmp_path, bucket_lines, symbol, stop, refused
):
    deps, _, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, bucket_lines),
        reader=[_search(symbol), _candles()],
    )
    _adds_value(deps, symbol)
    extra = ("--stop", stop, "--dry-run")
    if refused:
        with pytest.raises(trade.ProtectionRefused, match="stop-loss is"):
            _buy(deps, symbol, extra=extra)
    else:
        assert _buy(deps, symbol, extra=extra)["would_buy"]["stop_loss"] == float(stop)
    assert trader_rec.requests == []


def test_new_crypto_settings_are_understood_and_invalid_ones_refused(tmp_path):
    path = _config(
        tmp_path,
        "max_positions: '4'\nstop_pct: '9.5'\n"
        "meme:\n  max_orders_per_day: 2\n  max_positions: '3'\n  stop_pct: 0",
    )
    settings = trade.load_crypto_config(path)
    assert (settings.max_positions, settings.stop_pct) == (4, 9.5)
    assert settings.meme_max_orders_per_day == 2
    assert (settings.meme_max_positions, settings.meme_stop_pct) == (3, 0.0)
    for lines in ("stop_pct: 51", "stop_pct: -1", "meme:\n  stop_pct: lots"):
        with pytest.raises(trade.TradingRefused, match="stop_pct must be a number"):
            trade.load_crypto_config(_config(tmp_path, lines))
    with pytest.raises(trade.TradingRefused, match="max_positions"):
        trade.load_crypto_config(_config(tmp_path, "max_positions: 0"))


# ── Counting positions from the ledger ──


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([("open", {}), ("open", {})], 2),
        ([("open", {"status": "unknown"}), ("open", {"status": "not_found"})], 2),
        ([("open", {"status": "rejected"}), ("open", {"status": "canceled"})], 0),
        ([("open", {}), ("close", {"status": "submitted"})], 0),
        ([("open", {}), ("close", {"units": 0.5, "status": "submitted"})], 1),
        ([("open", {}), ("close", {"status": "failed"})], 1),  # may not have closed
        ([("open", {}), ("close", {"status": "submitting"})], 1),
        ([("open", {}), ("open", {}), ("flat", {})], 0),
        ([("open", {}), ("flat", {}), ("open", {})], 1),
        (
            [("close", {}), ("open", {})],
            1,
        ),  # closing someone else's position frees nothing
        ([("open", {}), ("open", {"instrument_id": 8, "bucket": "meme"})], 1),
        ([("open", {"instrument_id": None}), ("flat", {"instrument_id": None})], 1),
    ],
)
def test_open_positions_follow_buys_full_closes_and_flat_rows(rows, expected):
    ledger = [
        {
            "id": str(i),
            "ts": YESTERDAY,
            "action": action,
            "account": "demo",
            "instrument_id": 7,
            "status": "filled",
            "units": "all",
            "bucket": "crypto",
            **fields,
        }
        for i, (action, fields) in enumerate(rows)
    ]
    assert positions.open_positions(ledger, "demo", "crypto") == expected
    assert positions.open_positions(ledger, "real", "crypto") == 0


def test_reconcile_stops_counting_positions_etoro_closed_on_its_own(tmp_path):
    still_held = {"instrumentID": 100001, "positionID": 3}
    deps, reader, trader_rec = _deps(
        tmp_path,
        _config(tmp_path, CRYPTO_ON),
        reader=[{"clientPortfolio": {"positions": [still_held]}}],
    )
    _held(deps, "crypto", "BTC", 100000)  # its stop was hit on eToro
    _held(deps, "crypto", "ETH", 100001)
    _held(deps, "crypto", "SOL", 100002, ts=NOW.isoformat())  # too fresh to judge
    before = trade.read_ledger(deps.ledger)
    assert positions.open_positions(before, "demo", "crypto") == 3
    result = trade.cmd_reconcile(trade.build_parser().parse_args(["reconcile"]), deps)
    assert [r["symbol"] for r in result["closed_on_etoro"]] == ["BTC"]
    rows = trade.read_ledger(deps.ledger)
    assert positions.open_positions(rows, "demo", "crypto") == 2
    # The daily caps never loosen: the closed buy still counts for its day.
    assert trade.usage_today(rows, "demo", NOW, frozenset({"crypto"})) == (1, 10.0)
    assert len(reader.requests) == 1 and trader_rec.requests == []  # read-only


def test_sizing_applies_each_buckets_stop_pct_and_open_positions(tmp_path, capsys):
    config = _config(tmp_path, MEME_ON)
    ledger = tmp_path / "kronos" / "trades.jsonl"
    deps = risk.RiskDeps(config_path=config, ledger=ledger, now=lambda: NOW)
    argv = ["--account-size", "100000", "--entry", "100", "--json"]
    assert risk.main([*argv, "--asset", "crypto"], deps) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["stop_loss"], out["stop_rule"]) == (88.0, "fixed_pct")
    assert "--stop 88.0" in out["buy_args"]
    assert out["limits"]["positions_left"] == 2

    trade.append_ledger(
        {
            "id": "m",
            "ts": YESTERDAY,
            "action": "open",
            "account": "demo",
            "instrument_id": 100043,
            "amount": 10.0,
            "status": "filled",
            "bucket": "meme",
        },
        ledger,
    )
    assert risk.main([*argv, "--asset", "meme"], deps) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["stop_loss"] == 80.0
    assert (out["suggested_amount_usd"], out["binding_cap"]) == (0.0, "positions_left")
    assert any("already holds 1 meme" in w for w in out["warnings"])

    assert risk.main([*argv, "--asset", "crypto", "--stop", "70"], deps) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["stop_rule"] == "given"
    assert any("etoro_trade.py will refuse it" in w for w in out["warnings"])
