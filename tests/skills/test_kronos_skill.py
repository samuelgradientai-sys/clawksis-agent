"""Behaviour contracts for the bundled ``finance/kronos`` skill scripts.

Stdlib + pytest + unittest.mock only: no network, no torch, no pandas. Covers input
parsing and validation, trading-calendar timestamps, the naive baseline and backtest
scoring, the read-only eToro client (request construction, error handling, no trading
surface), the missing-keys message, the setup's fail-closed upstream pin, and the
inference wiring guards (``.eval()``, offline load, K paths) against fake modules.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import itertools
import json
import os
import subprocess
import sys
import tarfile
import types
import urllib.error
from datetime import datetime, timedelta
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock

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
forecast = _load("kronos_forecast")
backtest = _load("kronos_backtest")
setup = _load("kronos_setup")
kmodel = _load("_kronos_model")


def _daily_csv(
    path: Path, n: int = 120, start: datetime = datetime(2026, 1, 5)
) -> Path:
    rows = ["Date,Open,High,Low,Close,Volume"]
    day, i = start, 0
    while i < n:
        if day.weekday() < 5:
            p = 100 + i
            rows.append(
                f"{day.date().isoformat()},{p},{p + 1},{p - 1},{p + 0.5},{1000 + i}"
            )
            i += 1
        day += timedelta(days=1)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


# ── Argument parsing ──


def test_forecast_parser_defaults_fit_a_cpu_vps():
    args = forecast.build_parser().parse_args(["--input", "x.csv"])
    assert (args.model, args.device, args.samples, args.horizon, args.calendar) == (
        "small",
        "cpu",
        8,
        10,
        "auto",
    )
    assert args.lookback is None and args.format == "table" and not args.dry_run


@pytest.mark.parametrize(
    "argv",
    [
        [],  # a data source is required
        ["--input", "x.csv", "--etoro", "AAPL"],  # exactly one source
        ["--input", "x.csv", "--horizon", "0"],
        ["--input", "x.csv", "--samples", "65"],
        ["--input", "x.csv", "--lookback", "10"],
        ["--input", "x.csv", "--model", "large"],  # not released
    ],
)
def test_forecast_parser_rejects_bad_arguments(argv):
    with pytest.raises(SystemExit):
        forecast.build_parser().parse_args(argv)


def test_backtest_and_setup_parser_defaults():
    args = backtest.build_parser().parse_args(["--etoro", "AAPL"])
    assert (args.lookback, args.samples, args.horizon, args.origins, args.stride) == (
        256,
        4,
        5,
        20,
        None,
    )
    setup_args = setup.build_parser().parse_args([])
    assert (setup_args.model, setup_args.device, setup_args.check) == (
        "small",
        "cpu",
        False,
    )


# ── Input loading and validation ──


def test_csv_with_bom_aliases_unsorted_and_duplicates(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text(
        "﻿DATE,Open,HIGH,low,Close,Vol.\n"
        "2026-01-07,3,4,2,3.5,1.2K\n"
        "2026-01-05,1,2,0.5,1.5,100\n"
        "2026-01-06,2,3,1,2.5,\n"
        "2026-01-06,2,3,1,2.6,200\n",
        encoding="utf-8",
    )
    bars, warnings = kc.load_bars(path)
    assert [b.ts.day for b in bars] == [5, 6, 7]
    assert bars[1].close == 2.6  # duplicate timestamp: the last row wins
    assert bars[2].volume == 1200.0
    assert any("duplicate" in w for w in warnings)


def test_missing_close_column_is_a_clear_error(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("date,open,high,low\n2026-01-05,1,2,0.5\n", encoding="utf-8")
    with pytest.raises(kc.SkillError, match="close"):
        kc.load_bars(path)


def test_blank_prices_are_dropped_but_garbage_fails(tmp_path):
    blank = tmp_path / "blank.csv"
    blank.write_text(
        "date,open,high,low,close\n2026-01-05,1,2,0.5,1.5\n2026-01-06,,,,\n",
        encoding="utf-8",
    )
    bars, warnings = kc.load_bars(blank)
    assert len(bars) == 1 and any("missing prices" in w for w in warnings)
    garbage = tmp_path / "garbage.csv"
    garbage.write_text(
        "date,open,high,low,close\n2026-01-05,1,2,0.5,abc\n", encoding="utf-8"
    )
    with pytest.raises(kc.SkillError, match="Non-numeric"):
        kc.load_bars(garbage)


def test_semicolon_decimal_comma_export(tmp_path):
    path = tmp_path / "eu.csv"
    path.write_text(
        "timestamp;open;high;low;close;volume\n2026-01-05;1.234,50;1.240,00;1.230,00;1.236,25;10\n",
        encoding="utf-8",
    )
    (bar,), _ = kc.load_bars(path)
    assert bar.open == 1234.5 and bar.close == 1236.25


def test_us_slash_dates_and_price_column(tmp_path):
    path = tmp_path / "investing.csv"
    path.write_text(
        'Date,Price,Open,High,Low\n"01/13/2026","10.5","10","11","9.5"\n',
        encoding="utf-8",
    )
    (bar,), _ = kc.load_bars(path)
    assert bar.ts == datetime(2026, 1, 13) and bar.close == 10.5 and bar.volume is None


def test_stocks_skill_json_matches_equivalent_csv(tmp_path):
    rows = [
        {
            "date": "2026-01-05",
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "volume": 10,
        },
        {
            "date": "2026-01-06",
            "open": 2,
            "high": 3,
            "low": 1,
            "close": 2.5,
            "volume": 20,
        },
        {
            "date": "2026-01-07",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": None,
        },
    ]
    json_path = tmp_path / "h.json"
    json_path.write_text(json.dumps({"symbol": "X", "history": rows}), encoding="utf-8")
    csv_path = tmp_path / "h.csv"
    csv_path.write_text(
        "date,open,high,low,close,volume\n2026-01-05,1,2,0.5,1.5,10\n2026-01-06,2,3,1,2.5,20\n",
        encoding="utf-8",
    )
    assert kc.load_bars(json_path)[0] == kc.load_bars(csv_path)[0]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-10-22T14:30:00.1234567Z", datetime(2026, 10, 22, 14, 30, 0, 123456)),
        ("2026-10-22T16:30:00+02:00", datetime(2026, 10, 22, 14, 30)),
        ("20261022", datetime(2026, 10, 22)),
        (1761143400, datetime(2025, 10, 22, 14, 30)),
        (1761143400000, datetime(2025, 10, 22, 14, 30)),
    ],
)
def test_timestamp_formats_normalize_to_naive_utc(raw, expected):
    assert kc.parse_timestamp(raw) == expected


# ── Future timestamps ──


def test_daily_weekday_series_rolls_friday_to_monday():
    history = [datetime(2026, 10, 19) + timedelta(days=i) for i in range(5)]  # Mon..Fri
    future, calendar, step = kc.future_timestamps(history, 3)
    assert calendar == "nyse" and step == timedelta(days=1)
    assert [d.weekday() for d in future] == [0, 1, 2]
    assert future[0] == datetime(2026, 10, 26)


def test_crypto_hourly_series_runs_through_the_weekend():
    history = [
        datetime(2026, 10, 23, 20) + timedelta(hours=i) for i in range(30)
    ]  # spans Sat
    future, calendar, _ = kc.future_timestamps(history, 4)
    assert calendar == "24x7"
    assert future == [history[-1] + timedelta(hours=i + 1) for i in range(4)]


def test_intraday_sessions_continue_at_the_next_weekday_open():
    days = [datetime(2026, 10, 19) + timedelta(days=d) for d in range(5)]  # Mon..Fri
    history = [d.replace(hour=h, minute=30) for d in days for h in range(9, 16)]
    future, calendar, _ = kc.future_timestamps(history, 3)
    assert calendar == "nyse"
    assert future == [datetime(2026, 10, 26, h, 30) for h in (9, 10, 11)]


def test_weekly_bars_keep_their_weekday():
    history = [datetime(2026, 9, 7) + timedelta(weeks=i) for i in range(6)]
    future, _, _ = kc.future_timestamps(history, 2)
    assert future == [
        history[-1] + timedelta(weeks=1),
        history[-1] + timedelta(weeks=2),
    ]


def test_still_forming_candle_is_dropped():
    bars = [
        kc.Bar(datetime(2026, 10, 20) + timedelta(days=i), 1, 1, 1, 1) for i in range(4)
    ]
    kept, dropped = kc.drop_unclosed_bar(bars, datetime(2026, 10, 23, 15))
    assert dropped and kept == bars[:-1]
    kept, dropped = kc.drop_unclosed_bar(bars, datetime(2026, 10, 24, 1))
    assert not dropped and kept == bars


# ── Lookback planning and dry run ──


def test_lookback_clamps_to_context_and_history():
    assert forecast.resolve_lookback(2000, "small", 3000)[0] == 512
    assert forecast.resolve_lookback(2000, "mini", 3000)[0] == 2000
    lookback, warnings = forecast.resolve_lookback(None, "small", 100)
    assert lookback == 100 and warnings
    with pytest.raises(kc.SkillError, match="at least"):
        forecast.resolve_lookback(None, "small", kc.MIN_BARS - 1)


def test_dry_run_needs_no_runtime_and_reports_the_plan(tmp_path, capsys):
    path = _daily_csv(tmp_path / "d.csv")
    assert forecast.main(["--input", str(path), "--horizon", "3", "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] and out["bars"] == 120 and len(out["future_timestamps"]) == 3
    assert out["calendar"] == "nyse" and "financial advice" in out["disclaimer"]


def test_real_run_without_setup_points_at_the_setup_script(tmp_path, capsys):
    path = _daily_csv(tmp_path / "d.csv")
    assert forecast.main(["--input", str(path)]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "kronos_setup.py" in out["hint"]


def test_reexec_uses_the_venv_python_with_same_argv(tmp_path, monkeypatch):
    venv = tmp_path / "venv"
    state = {"venv_dir": str(venv), "venv_python": str(kc.venv_python_path(venv))}
    Path(state["venv_python"]).parent.mkdir(parents=True)
    Path(state["venv_python"]).write_text("", encoding="utf-8")
    monkeypatch.setattr(kc, "load_state", lambda: state)
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(kc.subprocess, "run", run)
    assert kc.reexec_in_skill_venv(Path("/s/f.py"), ["--input", "x"], 99) == 0
    cmd = run.call_args.args[0]
    assert cmd == [state["venv_python"], str(Path("/s/f.py")), "--input", "x"]
    assert run.call_args.kwargs["timeout"] == 99
    monkeypatch.setattr(kc, "running_in_skill_venv", lambda _s: True)
    assert kc.reexec_in_skill_venv(Path("/s/f.py"), [], 99) is None


# ── Bands, baseline, metrics ──


def test_quantile_matches_linear_interpolation():
    assert kc.quantile([1, 2, 3, 4, 5], 0.5) == 3
    assert kc.quantile([1, 2, 3, 4], 0.1) == pytest.approx(1.3)


def test_summarize_paths_mean_band_and_direction():
    future = [datetime(2026, 1, 5), datetime(2026, 1, 6)]
    paths = [
        [{"open": 1, "high": 2, "low": 0, "close": c, "volume": 1} for c in (100, v)]
        for v in (108, 110, 112)
    ]
    out = kc.summarize_paths(paths, future, last_close=100)
    assert out["forecast"][-1]["close"] == pytest.approx(110)
    assert out["summary"]["pct_change"] == pytest.approx(10)
    assert out["summary"]["direction"] == "up"
    assert out["forecast"][-1]["close_p10"] < 110 < out["forecast"][-1]["close_p90"]


def test_naive_baseline_and_scores():
    origins = [
        {"last_close": 100.0, "actual": [101.0, 102.0], "kronos": [101.0, 102.0]},
        {"last_close": 100.0, "actual": [99.0, 98.0], "kronos": [99.0, 98.0]},
    ]
    assert kc.naive_forecast(100.0, 3) == [100.0, 100.0, 100.0]
    scores = kc.score_origins(origins)
    assert scores["kronos"]["mae"] == 0 and scores["kronos"]["direction_hit_rate"] == 1
    assert scores["naive_last_close"]["mae"] == pytest.approx(1.5)
    assert scores["always_up_hit_rate"] == 0.5 and scores["mae_skill_vs_naive"] == 1


@pytest.mark.parametrize(
    "origins,skill,hit,expected",
    [
        (20, 0.10, 0.6, "adds_value"),
        (20, 0.10, 0.4, "no_clear_edge"),
        (20, 0.00, 0.6, "no_clear_edge"),
        (20, -0.20, 0.6, "worse_than_naive"),
        (6, 0.50, 0.9, "inconclusive"),
    ],
)
def test_verdict_is_honest(origins, skill, hit, expected):
    code, text = kc.verdict(
        {
            "origins": origins,
            "mae_skill_vs_naive": skill,
            "mae_skill_vs_ets": 0.10,  # also beat the ETS baseline (see test_kronos_baselines)
            "kronos": {"direction_hit_rate": hit},
        }
    )
    assert code == expected and text


def test_backtest_origins_are_walk_forward():
    picks = backtest.plan_origins(
        n_bars=400, lookback=256, horizon=5, origins=20, stride=5
    )
    assert picks == sorted(picks) and picks[-1] == 400 - 1 - 5
    assert picks[0] >= 255 and all(b - a == 5 for a, b in itertools.pairwise(picks))
    with pytest.raises(kc.SkillError, match="too short"):
        backtest.plan_origins(n_bars=270, lookback=256, horizon=5, origins=20, stride=5)


# ── eToro client ──


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code: int, body: dict | None = None, headers: dict | None = None):
    msg = Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    payload = json.dumps(body or {}).encode()
    return urllib.error.HTTPError("https://x", code, "err", msg, io.BytesIO(payload))


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


def _client(*responses, **kwargs):
    rec = Recorder(*responses)
    return etoro.EtoroClient("api-secret", "user-secret", opener=rec, **kwargs), rec


def test_request_carries_auth_headers_and_literal_commas():
    client, _ = _client()
    req = client.build_request(
        "/api/v1/market-data/search", {"internalSymbolFull": "AAPL", "fields": "a,b"}
    )
    assert req.get_method() == "GET"
    assert (
        req.full_url
        == "https://public-api.etoro.com/api/v1/market-data/search?internalSymbolFull=AAPL&fields=a,b"
    )
    headers = {k.lower(): v for k, v in req.header_items()}
    assert (
        headers["x-api-key"] == "api-secret" and headers["x-user-key"] == "user-secret"
    )
    assert len(headers["x-request-id"]) == 36 and "Mozilla" in headers["user-agent"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v2/trading/execution/orders",
        "/api/v1/trading/execution/demo/market-close-orders/positions/1",
        "/api/v2/trading/positions/1",
        "/api/v1/watchlists",
    ],
)
def test_trading_and_other_endpoints_are_refused_before_any_io(path):
    client, rec = _client()
    with pytest.raises(etoro.EtoroError, match="Refusing"):
        client.get(path)
    assert rec.requests == []


def test_client_has_no_trading_surface_and_only_ever_sends_get():
    words = ("order", "trade", "post", "put", "delete", "close", "execut")
    assert [
        n for n in dir(etoro.EtoroClient) if any(w in n.lower() for w in words)
    ] == []
    candles = {
        "candles": [
            {
                "instrumentId": 1,
                "candles": [
                    {
                        "fromDate": "2026-01-05T00:00:00Z",
                        "open": 1,
                        "high": 1,
                        "low": 1,
                        "close": 1,
                        "volume": 1,
                    }
                ],
            }
        ]
    }
    client, rec = _client(
        {"items": [{"instrumentId": 1, "internalSymbolFull": "AAPL"}]},
        candles,
        {"instrumentDisplayDatas": [{"symbolFull": "AAPL"}]},
        {"username": "u", "scopes": []},
        {"clientPortfolio": {}},
    )
    client.resolve("AAPL")
    client.candles(1, "OneDay", 5)
    client.instrument_info(1)
    client.identity()
    client.portfolio("demo")
    assert all(r.get_method() == "GET" for r in rec.requests)
    assert all(
        "execution" not in r.full_url and "orders" not in r.full_url
        for r in rec.requests
    )


def test_resolve_needs_one_exact_symbol():
    items = {
        "items": [
            {"instrumentId": 1, "internalSymbolFull": "AAPL.24-7"},
            {"instrumentId": 2, "internalSymbolFull": "aapl"},
        ]
    }
    client, _ = _client(items)
    assert client.resolve("AAPL")["instrumentId"] == 2
    client, _ = _client(
        {"items": [{"instrumentId": 1, "internalSymbolFull": "AAPL.EUR"}]}
    )
    with pytest.raises(etoro.EtoroError, match="AAPL.EUR"):
        client.resolve("AAPL")


def test_candles_clamp_count_map_aliases_and_reject_null():
    payload = {
        "candles": [
            {
                "instrumentId": 7,
                "candles": [
                    {
                        "fromDate": "2026-01-05T00:00:00Z",
                        "open": 1,
                        "high": 2,
                        "low": 0.5,
                        "close": 1.5,
                        "volume": 3,
                    }
                ],
            }
        ]
    }
    client, rec = _client(payload, {"candles": None})
    rows = client.candles(7, "1h", 5000)
    assert rec.requests[0].full_url.endswith(
        "/instruments/7/history/candles/asc/OneHour/1000"
    )
    assert rows[0]["close"] == 1.5 and rows[0]["timestamps"] == "2026-01-05T00:00:00Z"
    with pytest.raises(etoro.EtoroError, match="no candles"):
        client.candles(7, "OneDay", 10)
    with pytest.raises(etoro.EtoroError, match="Unknown interval"):
        etoro.normalize_interval("2d")


def test_http_errors_are_explained_without_leaking_keys():
    client, _ = _client(_http_error(401, {"errorMessage": "bad key"}))
    with pytest.raises(etoro.EtoroError) as info:
        client.identity()
    assert info.value.status == 401 and "bad key" in str(info.value)
    assert "secret" not in str(info.value) and "secret" not in (info.value.hint or "")


def test_rate_limit_retries_once_honouring_retry_after():
    sleeps = []
    client, rec = _client(
        _http_error(429, headers={"Retry-After": "3"}),
        {"username": "u"},
        sleep=sleeps.append,
    )
    assert client.identity() == {"username": "u"}
    assert sleeps == [3.0] and len(rec.requests) == 2


def test_network_failure_is_a_clear_error():
    client, _ = _client(urllib.error.URLError("dns down"))
    with pytest.raises(etoro.EtoroError, match="Could not reach eToro"):
        client.identity()


def test_redirects_are_refused():
    handler = etoro._NoRedirect()
    assert (
        handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example/")
        is None
    )


def test_real_portfolio_falls_back_when_pnl_route_is_missing():
    client, rec = _client(_http_error(404), {"clientPortfolio": {"credit": 5.0}})
    portfolio, path = client.portfolio("real")
    assert portfolio == {"credit": 5.0} and path == "/api/v1/trading/info/portfolio"
    assert rec.requests[0].full_url.endswith("/api/v1/trading/info/real/pnl")
    client, rec = _client({"clientPortfolio": {}})
    client.portfolio("demo")
    assert rec.requests[0].full_url.endswith("/api/v1/trading/info/demo/pnl")


def test_a_portfolio_snapshot_adds_cash_invested_and_open_pnl():
    summary = {
        "cash_credit_usd": 97721.0,
        "invested_usd_direct": 2000.0,
        "unrealized_pnl": -35.4,
        "positions": [
            {
                "symbol": "PANW",
                "instrument_id": 4124,
                "invested_usd": 1000.0,
                "unrealized_pnl": -33.12,
            },
            {
                "symbol": None,
                "instrument_id": 4286,
                "invested_usd": 1000.0,
                "unrealized_pnl": None,
            },
        ],
    }
    row = etoro.snapshot_row("demo", summary, "2026-10-29T14:00:00+00:00")
    assert row["equity_usd"] == 99685.6
    assert row["positions"] == [
        {"symbol": "PANW", "invested_usd": 1000.0, "unrealized_pnl": -33.12},
        {"symbol": "#4286", "invested_usd": 1000.0, "unrealized_pnl": None},
    ]
    assert (
        etoro.snapshot_row("demo", {**summary, "unrealized_pnl": None}, "t")[
            "equity_usd"
        ]
        is None
    )  # no made-up value when eToro leaves out the P&L


def test_portfolio_summary_groups_positions_and_weights():
    portfolio = {
        "credit": 50.0,
        "unrealizedPnL": 12.0,
        "positions": [
            {
                "instrumentID": 1,
                "isBuy": True,
                "units": 2,
                "amount": 200,
                "openRate": 100,
                "leverage": 1,
                "unrealizedPnL": {"pnL": 10},
            },
            {
                "instrumentID": 1,
                "isBuy": True,
                "units": 2,
                "amount": 240,
                "openRate": 120,
                "leverage": 2,
                "unrealizedPnL": {"pnL": -4},
            },
            {
                "instrumentID": 2,
                "isBuy": False,
                "units": 1,
                "amount": 60,
                "openRate": 60,
                "leverage": 1,
            },
        ],
        "mirrors": [
            {
                "parentUsername": "trader",
                "availableAmount": 5,
                "positions": [
                    {"instrumentID": 3, "units": 1, "amount": 10, "openRate": 10}
                ],
            }
        ],
    }
    summary = etoro.summarize_portfolio(
        portfolio, {1: {"symbolFull": "AAPL", "instrumentDisplayName": "Apple"}}
    )
    top = summary["positions"][0]
    assert (top["symbol"], top["positions"], top["units"], top["invested_usd"]) == (
        "AAPL",
        2,
        4.0,
        440.0,
    )
    assert top["avg_open_rate"] == pytest.approx(110) and top[
        "unrealized_pnl"
    ] == pytest.approx(6)
    assert top["max_leverage"] == 2 and top["weight_pct"] == pytest.approx(88)
    assert summary["positions"][1]["direction"] == "short"
    assert summary["copy_trading"][0]["copying"] == "trader"


def test_fetch_bars_resolves_symbol_and_drops_the_forming_candle():
    candles = [
        {
            "fromDate": f"2026-10-{d:02d}T00:00:00Z",
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": float(d),
            "volume": 1,
        }
        for d in (19, 20, 21, 22, 23)
    ]
    client, _ = _client(
        {
            "items": [
                {
                    "instrumentId": 9,
                    "internalSymbolFull": "MSFT",
                    "displayname": "Microsoft",
                }
            ]
        },
        {"candles": [{"instrumentId": 9, "candles": candles}]},
    )
    bars, meta, warnings = etoro.fetch_bars(
        "MSFT", "1d", 5, client=client, now=datetime(2026, 10, 23, 18)
    )
    assert [b.close for b in bars] == [19, 20, 21, 22] and meta["instrument_id"] == 9
    assert any("not closed" in w for w in warnings)


def test_etoro_keys_are_secret_and_reach_terminal_children():
    """The scripts run in `terminal`: a "tool"-category key would be scrubbed there."""
    from clawk_cli.config import OPTIONAL_ENV_VARS
    from tools.environments.local_env_policy import _is_provider_env_blocklisted
    from tools.env_passthrough import _is_clawk_provider_credential

    for name in (etoro.ENV_API_KEY, etoro.ENV_USER_KEY):
        assert OPTIONAL_ENV_VARS[name]["password"] is True
        assert not _is_provider_env_blocklisted(name)
        assert not _is_clawk_provider_credential(
            name
        )  # skill passthrough may register it


# ── Missing keys ──


def test_missing_keys_message_is_actionable_and_profile_aware(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAWK_HOME", str(tmp_path / "profiles" / "work"))
    with pytest.raises(etoro.EtoroError) as info:
        etoro.load_keys({"ETORO_API_KEY": "x"})
    message = str(info.value)
    assert "ETORO_USER_KEY" in message and "ETORO_API_KEY missing" not in message
    assert "clawk config set ETORO_USER_KEY" in message
    assert str(tmp_path / "profiles" / "work" / ".env") in message
    assert etoro.load_keys({"ETORO_API_KEY": " a ", "ETORO_USER_KEY": "b"}) == (
        "a",
        "b",
    )


def test_cli_without_keys_exits_2_with_json_error(monkeypatch, capsys):
    monkeypatch.delenv("ETORO_API_KEY", raising=False)
    monkeypatch.delenv("ETORO_USER_KEY", raising=False)
    assert etoro.main(["portfolio"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "ETORO_API_KEY" in out["error"]


# ── Setup: fail-closed upstream pin ──


def _tarball(
    files: dict[str, bytes], prefix: str = f"Kronos-{kc.UPSTREAM_SHA}"
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(f"{prefix}/{name}" if prefix else name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


FAKE_FILES = {"LICENSE": b"MIT", "model/__init__.py": b"x = 1\n"}
FAKE_PINS = {
    name: hashlib.sha256(content).hexdigest() for name, content in FAKE_FILES.items()
}


def test_shipped_pins_are_complete():
    assert len(kc.UPSTREAM_SHA) == 40 and set(kc.UPSTREAM_FILES) >= {
        "LICENSE",
        "model/kronos.py",
        "model/module.py",
    }
    assert all(setup._is_sha256(d) for d in kc.UPSTREAM_FILES.values())
    _repo, revision, tokenizer = setup.MODELS["small"]
    assert setup._SHA_RE.match(revision) and setup._SHA_RE.match(
        setup.TOKENIZERS[tokenizer][1]
    )


def test_extraction_keeps_only_allow_listed_files():
    archive = _tarball(
        {**FAKE_FILES, "webui/app.py": b"evil", "finetune/x.pkl": b"pickle"}
    )
    assert setup.extract_pinned_members(archive, FAKE_PINS) == FAKE_FILES


def test_extraction_rejects_path_traversal():
    archive = _tarball({"../escape.py": b"x"}, prefix="")
    with pytest.raises(setup.PinError, match="Unsafe"):
        setup.extract_pinned_members(archive, FAKE_PINS)


@pytest.mark.parametrize(
    "files,pins,match",
    [
        ({**FAKE_FILES, "LICENSE": b"tampered"}, FAKE_PINS, "mismatch"),
        ({"LICENSE": b"MIT"}, FAKE_PINS, "lacks"),
        (FAKE_FILES, {**FAKE_PINS, "LICENSE": ""}, "incomplete"),
        (FAKE_FILES, {**FAKE_PINS, "LICENSE": "FILL-ME-IN"}, "incomplete"),
    ],
)
def test_pin_verification_fails_closed(files, pins, match):
    with pytest.raises(setup.PinError, match=match):
        setup.verify_upstream_files(files, pins)


def test_tampered_download_installs_nothing(tmp_path):
    tampered = _tarball({**FAKE_FILES, "model/__init__.py": b"import os\n"})
    with pytest.raises(setup.PinError):
        setup.install_upstream_code(
            tmp_path, fetch=lambda _url: tampered, expected=FAKE_PINS
        )
    assert not (tmp_path / "src").exists()  # verified before anything is written


def test_verified_download_installs_and_is_idempotent(tmp_path):
    fetch = MagicMock(return_value=_tarball(FAKE_FILES))
    target = setup.install_upstream_code(tmp_path, fetch=fetch, expected=FAKE_PINS)
    assert (target / "model" / "__init__.py").read_bytes() == FAKE_FILES[
        "model/__init__.py"
    ]
    setup.install_upstream_code(tmp_path, fetch=fetch, expected=FAKE_PINS)
    assert fetch.call_count == 1


def test_check_on_an_empty_home_reports_setup_needed_without_network(tmp_path):
    runner = MagicMock(return_value=subprocess.CompletedProcess([], 1))
    status = setup.check_status(tmp_path / "kronos", runner)
    assert status["ok"] is False and status["setup_needed"] is True
    assert (
        status["upstream_code"] == "missing"
        and "kronos_setup.py" in status["next_step"]
    )
    runner.assert_not_called()  # no venv yet, so not even an import probe


def test_cpu_install_takes_torch_from_the_cpu_index_only():
    torch_step, rest = setup.install_commands(Path("/v/bin/python"), "cpu", uv=None)
    assert torch_step[-3:] == [
        "--index-url",
        setup.TORCH_CPU_INDEX,
        setup.TORCH_REQUIREMENT,
    ]
    assert "--index-url" not in rest
    cuda_torch, _ = setup.install_commands(
        Path("/v/bin/python"), "cuda", uv="/usr/bin/uv"
    )
    assert "--index-url" not in cuda_torch and cuda_torch[:3] == [
        "/usr/bin/uv",
        "pip",
        "install",
    ]
    assert all(
        "<" in req for req in (setup.TORCH_REQUIREMENT, *setup.RUNTIME_REQUIREMENTS)
    )


def test_unpinned_models_need_explicit_first_use_pinning(tmp_path):
    runner = MagicMock(
        return_value=subprocess.CompletedProcess(
            [], 0, stdout="a" * 40 + "\n", stderr=""
        )
    )
    with pytest.raises(kc.SkillError, match="No pinned"):
        setup.resolve_revision(
            "NeoQuasar/Kronos-mini", None, None, tmp_path, runner, False
        )
    runner.assert_not_called()
    assert setup.resolve_revision("r", None, "b" * 40, tmp_path, runner, False) == (
        "b" * 40,
        "first-use",
    )
    assert setup.resolve_revision("r", None, None, tmp_path, runner, True) == (
        "a" * 40,
        "first-use",
    )
    runner.return_value = subprocess.CompletedProcess([], 0, stdout="main\n", stderr="")
    with pytest.raises(kc.SkillError, match="unexpected revision"):
        setup.resolve_revision("r", None, None, tmp_path, runner, True)


# ── Inference wiring (fake torch/pandas/upstream) ──

FAKE_UPSTREAM = """
CALLS = []


class _Loadable:
    def __init__(self, path):
        self.path = path
        self.evaluated = False

    @classmethod
    def from_pretrained(cls, path):
        CALLS.append((cls.__name__, path))
        print("Loading weights from local directory")  # what huggingface_hub really prints
        return cls(path)

    def eval(self):
        self.evaluated = True
        return self


class KronosTokenizer(_Loadable):
    pass


class Kronos(_Loadable):
    pass


class _Col(list):
    def tolist(self):
        return list(self)


class KronosPredictor:
    def __init__(self, model, tokenizer, device=None, max_context=512):
        self.model, self.tokenizer, self.device, self.max_context = model, tokenizer, device, max_context
        self.batches = []

    def predict_batch(self, df_list, x_timestamp_list, y_timestamp_list, pred_len, **kw):
        self.batches.append((len(df_list), pred_len, kw))
        cols = ("open", "high", "low", "close", "volume")
        return [{c: _Col(float(i) for i in range(pred_len)) for c in cols} for _ in df_list]
"""


@pytest.fixture
def fake_runtime(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "model").mkdir(parents=True)
    (src / "model" / "__init__.py").write_text(FAKE_UPSTREAM, encoding="utf-8")
    monkeypatch.setattr(
        kmodel,
        "UPSTREAM_FILES",
        {"model/__init__.py": hashlib.sha256(FAKE_UPSTREAM.encode()).hexdigest()},
    )
    torch = types.SimpleNamespace(
        manual_seed=MagicMock(),
        set_num_threads=MagicMock(),
        cuda=types.SimpleNamespace(is_available=lambda: False),
    )
    pandas = types.SimpleNamespace(DataFrame=dict, Series=list, to_datetime=list)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "pandas", pandas)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    state = {
        "src_dir": str(src),
        "models": {
            "small": {
                "model_dir": "/w/model",
                "tokenizer_dir": "/w/tok",
                "max_context": 512,
            }
        },
    }
    yield state, torch
    for name in [m for m in sys.modules if m == "model" or m.startswith("model.")]:
        del sys.modules[name]


def test_predictor_loads_offline_in_eval_mode_from_local_dirs(fake_runtime, capsys):
    state, torch = fake_runtime
    predictor = kmodel.load_predictor(state, "small", device="cpu", threads=2, seed=7)
    assert (
        capsys.readouterr().out == ""
    )  # library chatter must not corrupt --format json
    upstream = sys.modules["model"]
    assert upstream.CALLS == [("KronosTokenizer", "/w/tok"), ("Kronos", "/w/model")]
    assert predictor.model.evaluated and predictor.tokenizer.evaluated
    assert (predictor.device, predictor.max_context) == ("cpu", 512)
    torch.manual_seed.assert_called_once_with(7)
    torch.set_num_threads.assert_called_once_with(2)
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_k_copies_give_k_paths_with_single_samples(fake_runtime):
    state, _ = fake_runtime
    predictor = kmodel.load_predictor(
        state, "small", device="cpu", threads=None, seed=1
    )
    window = [
        kc.Bar(datetime(2026, 1, 5) + timedelta(days=i), 1, 2, 0.5, 1.5, 10)
        for i in range(70)
    ]
    future = [datetime(2026, 4, 1) + timedelta(days=i) for i in range(3)]
    paths = kmodel.predict_paths(
        predictor,
        [window] * 5,
        [future] * 5,
        3,
        sample_count=1,
        temperature=1.0,
        top_p=0.9,
    )
    assert len(paths) == 5 and all(len(p) == 3 for p in paths)
    ((batch, pred_len, kwargs),) = predictor.batches
    assert (batch, pred_len, kwargs["sample_count"], kwargs["top_k"]) == (5, 3, 1, 0)


def test_tampered_or_missing_model_refuses_to_load(fake_runtime):
    state, _ = fake_runtime
    with pytest.raises(kc.SkillError, match="not installed"):
        kmodel.load_predictor(state, "mini", device="cpu", threads=None, seed=1)
    (Path(state["src_dir"]) / "model" / "__init__.py").write_text(
        "import os\n", encoding="utf-8"
    )
    with pytest.raises(kc.SkillError, match="verification"):
        kmodel.load_predictor(state, "small", device="cpu", threads=None, seed=1)
