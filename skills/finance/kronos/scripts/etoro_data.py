#!/usr/bin/env python3
"""Read-only eToro Public API client: instrument search, OHLCV candles, portfolio.

READ-ONLY BY CONSTRUCTION: the client only issues GET requests, and only to the
market-data, trading-info (portfolio/P&L) and identity paths in READ_ONLY_PREFIXES.
There is no code path for orders, position changes or any other trading endpoint.

Auth: every request sends ``x-api-key`` (ETORO_API_KEY, the public API key),
``x-user-key`` (ETORO_USER_KEY) and a fresh ``x-request-id`` UUID. Keys are read from
the environment (Clawksis loads them from the profile's .env) and are never printed.

API shape notes. The official reference at api-portal.etoro.com could not be fetched
when this was written; the endpoints below are the ones two independent third-party
clients implement and agree on (florinel-chis/etoro-go v0.1.1, whose author verified
them against the live API, and the etoropy SDK v0.1.7). Items marked UNVERIFIED are
where sources disagree or only one source exists; see references/etoro-api.md.

Usage:
  etoro_data.py check
  etoro_data.py search SYMBOL
  etoro_data.py candles SYMBOL [--interval OneDay] [--count 500] [--format csv|json] [--output PATH]
  etoro_data.py portfolio [--account real|demo] [--format json|table]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_common import (
    UTC,
    Bar,
    SkillError,
    display_home,
    drop_unclosed_bar,
    dump_json,
    iso_z,
    render_table,
    rows_to_bars,
    run_cli,
)

BASE_URL = "https://public-api.etoro.com"
READ_ONLY_PREFIXES = ("/api/v1/market-data/", "/api/v1/trading/info/", "/api/v1/me")
ENV_API_KEY = "ETORO_API_KEY"
ENV_USER_KEY = "ETORO_USER_KEY"
# The API sits behind a CDN that rejects generic tool user agents (etoro-go notes).
USER_AGENT = "Mozilla/5.0 (compatible; clawksis-kronos-skill)"
MAX_CANDLES = 1000  # server-side cap; the window always ends at the latest bar
MAX_RETRY_AFTER = 30.0
SEARCH_FIELDS = (
    "instrumentId,internalSymbolFull,displayname,instrumentTypeID,exchangeID,"
    "isCurrentlyTradable,isDelisted"
)
INTERVALS = (
    "OneMinute",
    "FiveMinutes",
    "TenMinutes",
    "FifteenMinutes",
    "ThirtyMinutes",
    "OneHour",
    "FourHours",
    "OneDay",
    "OneWeek",
)
_INTERVAL_ALIASES = {
    "1m": "OneMinute",
    "5m": "FiveMinutes",
    "10m": "TenMinutes",
    "15m": "FifteenMinutes",
    "30m": "ThirtyMinutes",
    "1h": "OneHour",
    "60m": "OneHour",
    "hourly": "OneHour",
    "4h": "FourHours",
    "1d": "OneDay",
    "d": "OneDay",
    "day": "OneDay",
    "daily": "OneDay",
    "1w": "OneWeek",
    "w": "OneWeek",
    "week": "OneWeek",
    "weekly": "OneWeek",
    **{name.lower(): name for name in INTERVALS},
}
# Portfolio paths per account, tried in order until one is not a 404. The P&L route
# (live valuations) is listed by both SDKs. The real-account breakdown route differs:
# both SDKs use /trading/info/portfolio, one eToro builders guide shows
# /trading/info/real/portfolio (UNVERIFIED which is current), so both are tried.
PORTFOLIO_PATHS = {
    "real": (
        "/api/v1/trading/info/real/pnl",
        "/api/v1/trading/info/portfolio",
        "/api/v1/trading/info/real/portfolio",
    ),
    "demo": ("/api/v1/trading/info/demo/pnl", "/api/v1/trading/info/demo/portfolio"),
}
_HTTP_HINTS = {
    400: "eToro rejected the request parameters.",
    401: "eToro rejected the API keys.",
    403: "eToro refused access: the key pair lacks permission for this data, or the key "
    "environment (real vs demo) does not match --account.",
    404: "eToro has no such resource (unknown instrument or path).",
    429: "eToro rate limit hit (60 reads per minute per user key, shared by every app "
    "using it); wait a minute and retry.",
}


class EtoroError(SkillError):
    """Any eToro failure, rendered without request headers or key material."""

    def __init__(
        self, message: str, *, hint: str | None = None, status: int | None = None
    ) -> None:
        super().__init__(message, hint=hint)
        self.status = status


def missing_keys_message(missing: list[str]) -> str:
    env_path = f"{display_home()}/.env"
    return (
        f"eToro API keys are not configured ({', '.join(missing)} missing). Add them to "
        f"{env_path}, e.g. `clawk config set ETORO_API_KEY <public api key>` and "
        "`clawk config set ETORO_USER_KEY <user key>`, then start a new session. Create the "
        "keys in eToro under Settings > Trading > API Key Management (keys are per "
        "environment: real or demo). Without keys, use a CSV file instead."
    )


def load_keys(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    env = os.environ if env is None else env
    values = {
        name: (env.get(name) or "").strip() for name in (ENV_API_KEY, ENV_USER_KEY)
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise EtoroError(missing_keys_message(missing))
    return values[ENV_API_KEY], values[ENV_USER_KEY]


def normalize_interval(value: str) -> str:
    key = str(value).strip().lower()
    if key not in _INTERVAL_ALIASES:
        raise EtoroError(
            f"Unknown interval {value!r}; use one of {', '.join(INTERVALS)}."
        )
    return _INTERVAL_ALIASES[key]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so the key headers are never replayed to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_opener() -> Callable[..., Any]:
    return urllib.request.build_opener(_NoRedirect).open


def _error_detail(body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8", "replace") or "null")
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        for key in ("errorMessage", "message", "detail", "title"):
            if payload.get(key):
                return str(payload[key])[:300]
    return body.decode("utf-8", "replace").strip()[:300]


def _retry_after(value: str | None) -> float:
    try:
        return min(max(float(value or ""), 0.0), MAX_RETRY_AFTER)
    except ValueError:
        return 2.0


class EtoroClient:
    """GET-only client; *opener* and *sleep* are injectable for tests."""

    def __init__(
        self,
        api_key: str,
        user_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._user_key = user_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._open = opener or _default_opener()
        self._sleep = sleep

    def build_request(
        self, path: str, query: Mapping[str, Any] | None = None
    ) -> urllib.request.Request:
        if not path.startswith(READ_ONLY_PREFIXES):
            raise EtoroError(
                f"Refusing {path}: this client only reads market data and portfolio info."
            )
        url = self._base_url + path
        if query:
            # Literal commas: the API ignores percent-encoded comma lists (etoro-go notes).
            url += "?" + urllib.parse.urlencode(query, safe=",")
        headers = {
            "x-api-key": self._api_key,
            "x-user-key": self._user_key,
            "x-request-id": str(uuid.uuid4()),
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        return urllib.request.Request(url, headers=headers, method="GET")

    def get(self, path: str, query: Mapping[str, Any] | None = None) -> Any:
        request = self.build_request(path, query)
        for attempt in range(2):
            try:
                with self._open(request, timeout=self._timeout) as response:
                    body = response.read()
                return json.loads(body.decode("utf-8") or "null") if body else None
            except urllib.error.HTTPError as exc:
                body = exc.read() if exc.fp else b""
                if exc.code == 429 and attempt == 0:
                    self._sleep(
                        _retry_after(
                            exc.headers.get("Retry-After") if exc.headers else None
                        )
                    )
                    continue
                raise EtoroError(
                    f"HTTP {exc.code} from eToro: {_error_detail(body) or 'no detail'}",
                    hint=_HTTP_HINTS.get(exc.code),
                    status=exc.code,
                ) from None
            except urllib.error.URLError as exc:
                raise EtoroError(f"Could not reach eToro: {exc.reason}") from None
            except ValueError as exc:
                raise EtoroError(f"eToro returned a non-JSON response: {exc}") from None
        raise EtoroError(
            "eToro rate limit persisted after one retry.", hint=_HTTP_HINTS[429]
        )

    # ── Market data ──

    def search(self, symbol: str) -> list[dict[str, Any]]:
        payload = self.get(
            "/api/v1/market-data/search",
            {"internalSymbolFull": symbol, "fields": SEARCH_FIELDS},
        )
        items = payload.get("items") if isinstance(payload, dict) else None
        return [i for i in (items or []) if isinstance(i, dict)]

    def resolve(self, symbol: str) -> dict[str, Any]:
        """Exact, case-insensitive match: search matches by containment (AAPL -> AAPL.24-7)."""
        return pick_exact(self.search(symbol), symbol)

    def candles(
        self, instrument_id: int, interval: str, count: int
    ) -> list[dict[str, Any]]:
        count = max(1, min(int(count), MAX_CANDLES))
        path = (
            f"/api/v1/market-data/instruments/{int(instrument_id)}/history/candles/"
            f"asc/{normalize_interval(interval)}/{count}"
        )
        return parse_candles(self.get(path), instrument_id)

    def instrument_info(self, instrument_id: int) -> dict[str, Any]:
        payload = self.get(
            "/api/v1/market-data/instruments", {"instrumentIds": int(instrument_id)}
        )
        rows = (
            payload.get("instrumentDisplayDatas") if isinstance(payload, dict) else None
        )
        return rows[0] if rows and isinstance(rows[0], dict) else {}

    # ── Account (read-only) ──

    def identity(self) -> dict[str, Any]:
        payload = self.get("/api/v1/me")
        return payload if isinstance(payload, dict) else {}

    def portfolio(self, account: str) -> tuple[dict[str, Any], str]:
        if account not in PORTFOLIO_PATHS:
            raise EtoroError(f"Unknown account {account!r}; use real or demo.")
        last_error: EtoroError | None = None
        for path in PORTFOLIO_PATHS[account]:
            try:
                payload = self.get(path)
            except EtoroError as exc:
                if exc.status != 404:
                    raise
                last_error = exc
                continue
            portfolio = (
                payload.get("clientPortfolio") if isinstance(payload, dict) else None
            )
            return (portfolio if isinstance(portfolio, dict) else {}), path
        raise last_error or EtoroError("No portfolio endpoint answered.")


def search_candidates(items: list[dict[str, Any]]) -> str:
    """The symbols a search returned, for an error message."""
    return ", ".join(str(i.get("internalSymbolFull")) for i in items[:15]) or "none"


def pick_exact(items: list[dict[str, Any]], symbol: str) -> dict[str, Any]:
    """The one search result whose symbol is exactly *symbol* (any case), else EtoroError."""
    exact = [
        i
        for i in items
        if str(i.get("internalSymbolFull", "")).lower() == symbol.lower()
    ]
    if len(exact) == 1:
        return exact[0]
    raise EtoroError(
        f"No single exact eToro instrument for {symbol!r} (search returned: "
        f"{search_candidates(items)}).",
        hint="Pass the exact eToro symbol shown by `etoro_data.py search`.",
    )


def parse_candles(payload: Any, instrument_id: int) -> list[dict[str, Any]]:
    """Rows from ``{"candles": [{"instrumentId", "candles": [...]}]}``.

    An unknown instrument id answers HTTP 200 with ``"candles": null``, not an error.
    """
    groups = payload.get("candles") if isinstance(payload, dict) else None
    first = groups[0] if groups and isinstance(groups[0], dict) else {}
    rows = first.get("candles") or []
    if not rows:
        raise EtoroError(f"eToro returned no candles for instrument {instrument_id}.")
    return [
        {
            "timestamps": row.get("fromDate"),
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "volume": row.get("volume"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def client_from_env() -> EtoroClient:
    api_key, user_key = load_keys()
    return EtoroClient(api_key, user_key)


def fetch_bars(
    symbol: str,
    interval: str,
    count: int,
    *,
    client: EtoroClient | None = None,
    now: datetime | None = None,
) -> tuple[list[Bar], dict[str, Any], list[str]]:
    """Closed OHLCV bars for *symbol* (the still-forming newest candle is dropped)."""
    client = client or client_from_env()
    instrument = client.resolve(symbol)
    rows = client.candles(int(instrument["instrumentId"]), interval, count)
    bars, warnings = rows_to_bars(rows)
    bars, dropped = drop_unclosed_bar(bars, now or datetime.now(UTC))
    if dropped:
        warnings.append(
            "dropped the newest candle because its period has not closed yet"
        )
    meta = {
        "symbol": instrument.get("internalSymbolFull", symbol),
        "name": instrument.get("displayname"),
        "instrument_id": instrument.get("instrumentId"),
        "instrument_type_id": instrument.get("instrumentTypeID"),
        "interval": normalize_interval(interval),
        "source": "eToro Public API (read-only)",
    }
    return bars, meta, warnings


# ── Portfolio summary ──


def _position_pnl(position: dict[str, Any]) -> float | None:
    pnl = position.get("unrealizedPnL")
    if isinstance(pnl, dict) and pnl.get("pnL") is not None:
        return float(pnl["pnL"])
    return None


def group_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (instrument, direction): units, invested USD, avg open rate, P&L."""
    groups: dict[tuple[int, bool], dict[str, Any]] = {}
    for pos in positions:
        key = (int(pos.get("instrumentID") or 0), bool(pos.get("isBuy", True)))
        group = groups.setdefault(
            key,
            {
                "instrument_id": key[0],
                "direction": "long" if key[1] else "short",
                "positions": 0,
                "units": 0.0,
                "invested_usd": 0.0,
                "_rate_units": 0.0,
                "unrealized_pnl": None,
                "max_leverage": 0,
            },
        )
        units = float(pos.get("units") or 0.0)
        group["positions"] += 1
        group["units"] += units
        group["invested_usd"] += float(pos.get("amount") or 0.0)
        group["_rate_units"] += float(pos.get("openRate") or 0.0) * units
        group["max_leverage"] = max(
            group["max_leverage"], int(float(pos.get("leverage") or 1))
        )
        pnl = _position_pnl(pos)
        if pnl is not None:
            group["unrealized_pnl"] = (group["unrealized_pnl"] or 0.0) + pnl
    rows = []
    for group in groups.values():
        rate_units = group.pop("_rate_units")
        group["avg_open_rate"] = rate_units / group["units"] if group["units"] else None
        rows.append(group)
    return sorted(rows, key=lambda r: r["invested_usd"], reverse=True)


def summarize_portfolio(
    portfolio: dict[str, Any], names: Mapping[int, dict[str, Any]] | None = None
) -> dict[str, Any]:
    names = names or {}

    def label(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for row in rows:
            info = names.get(row["instrument_id"], {})
            row["symbol"] = info.get("symbolFull")
            row["name"] = info.get("instrumentDisplayName")
        return rows

    direct = label(group_positions(list(portfolio.get("positions") or [])))
    mirrors = [
        {
            "copying": m.get("parentUsername"),
            "available_usd": m.get("availableAmount"),
            "positions": label(group_positions(list(m.get("positions") or []))),
        }
        for m in portfolio.get("mirrors") or []
        if isinstance(m, dict)
    ]
    invested = sum(r["invested_usd"] for r in direct)
    for row in direct:
        row["weight_pct"] = row["invested_usd"] / invested * 100.0 if invested else None
    return {
        "cash_credit_usd": portfolio.get("credit"),
        "unrealized_pnl": portfolio.get("unrealizedPnL"),
        "invested_usd_direct": invested,
        "positions": direct,
        "copy_trading": mirrors,
        "pending_orders": len(portfolio.get("orders") or [])
        + len(portfolio.get("ordersForOpen") or []),
    }


def _instrument_ids(portfolio: dict[str, Any]) -> list[int]:
    ids = {int(p.get("instrumentID") or 0) for p in portfolio.get("positions") or []}
    for mirror in portfolio.get("mirrors") or []:
        ids.update(
            int(p.get("instrumentID") or 0) for p in mirror.get("positions") or []
        )
    return sorted(i for i in ids if i)


def _lookup_names(
    client: EtoroClient, ids: list[int]
) -> tuple[dict[int, dict[str, Any]], list[int]]:
    """Best-effort symbol/name lookup; a failed lookup leaves that row unnamed."""
    names: dict[int, dict[str, Any]] = {}
    failed: list[int] = []
    for instrument_id in ids:
        try:
            names[instrument_id] = client.instrument_info(instrument_id)
        except EtoroError:
            failed.append(instrument_id)
    return names, failed


def fetch_portfolio(
    account: str, *, client: EtoroClient | None = None, max_lookups: int = 60
) -> dict[str, Any]:
    client = client or client_from_env()
    portfolio, path = client.portfolio(account)
    ids = _instrument_ids(portfolio)
    names, failed = _lookup_names(client, ids[:max_lookups])
    summary = summarize_portfolio(portfolio, names)
    warnings = (
        [f"could not resolve names for instrument ids {failed[:10]}"] if failed else []
    )
    if len(ids) > max_lookups:
        warnings.append(f"only the first {max_lookups} instruments were named")
    summary.update(
        {
            "account": account,
            "endpoint": path,
            "warnings": warnings,
            "source": "eToro Public API (read-only)",
        }
    )
    return summary


# ── CLI ──


def _bars_csv(bars: list[Bar]) -> str:
    lines = ["timestamps,open,high,low,close,volume"]
    lines.extend(
        f"{b.ts.isoformat()},{b.open!r},{b.high!r},{b.low!r},{b.close!r},"
        f"{'' if b.volume is None else repr(b.volume)}"
        for b in bars
    )
    return "\n".join(lines) + "\n"


def _bars_json(bars: list[Bar], meta: dict[str, Any], warnings: list[str]) -> str:
    rows = [
        {
            "timestamps": b.ts.isoformat(),
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in bars
    ]
    return dump_json({**meta, "warnings": warnings, "bars": rows})


def cmd_candles(args: argparse.Namespace) -> int:
    bars, meta, warnings = fetch_bars(args.symbol, args.interval, args.count)
    text = _bars_csv(bars) if args.format == "csv" else _bars_json(bars, meta, warnings)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(
            dump_json(
                {
                    "ok": True,
                    "path": str(out),
                    "rows": len(bars),
                    **meta,
                    "warnings": warnings,
                }
            )
        )
    else:
        print(text, end="")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    items = client_from_env().search(args.symbol)
    print(dump_json({"ok": True, "query": args.symbol, "results": items}))
    return 0


def _remember_scopes(scopes: Any) -> None:
    """Leave the granted scopes for the dashboard's read-only permissions panel (best effort)."""
    try:
        from kronos_dashboard import key_check_path, refresh_safely

        path = key_check_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "checked_at": iso_z(datetime.now(UTC)),
            "scopes": [str(s) for s in scopes] if isinstance(scopes, list) else [],
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        refresh_safely()
    except Exception:  # health: allow BLE001 -- the check already answered; a dashboard write must not turn it into an error
        print("The eToro key check was not saved for the dashboard.", file=sys.stderr)


def cmd_check(_args: argparse.Namespace) -> int:
    me = client_from_env().identity()
    _remember_scopes(me.get("scopes"))
    print(
        dump_json(
            {
                "ok": True,
                "username": me.get("username"),
                "scopes": me.get("scopes"),
                "note": "This client is read-only: it never calls trading endpoints.",
            }
        )
    )
    return 0


def _portfolio_table(summary: dict[str, Any]) -> str:
    rows = [
        (
            r["symbol"] or r["instrument_id"],
            r["direction"],
            r["units"],
            r["invested_usd"],
            r["weight_pct"],
            r["unrealized_pnl"],
        )
        for r in summary["positions"]
    ]
    table = render_table(
        ("symbol", "side", "units", "invested_usd", "weight_%", "unrealized_pnl"), rows
    )
    head = (
        f"eToro {summary['account']} account — cash {summary['cash_credit_usd']}, "
        f"unrealized P&L {summary['unrealized_pnl']}"
    )
    copies = (
        f"\ncopy-trading relationships: {len(summary['copy_trading'])}"
        if summary["copy_trading"]
        else ""
    )
    return f"{head}\n{table}{copies}\n(read-only snapshot; no trades can be placed from here)"


def cmd_portfolio(args: argparse.Namespace) -> int:
    summary = fetch_portfolio(args.account)
    print(
        _portfolio_table(summary)
        if args.format == "table"
        else dump_json({"ok": True, **summary})
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only eToro market data and portfolio."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "check", help="Verify the keys (identity + granted scopes)"
    ).set_defaults(func=cmd_check)
    search = sub.add_parser("search", help="Find instruments by eToro symbol")
    search.add_argument("symbol")
    search.set_defaults(func=cmd_search)
    candles = sub.add_parser("candles", help="OHLCV candles for one symbol")
    candles.add_argument("symbol")
    candles.add_argument(
        "--interval",
        default="OneDay",
        help=f"{', '.join(INTERVALS)} (or 1d, 1h, 15m...)",
    )
    candles.add_argument(
        "--count", type=int, default=500, help=f"bars, max {MAX_CANDLES}"
    )
    candles.add_argument("--format", choices=("csv", "json"), default="csv")
    candles.add_argument("--output", help="write to this file instead of stdout")
    candles.set_defaults(func=cmd_candles)
    portfolio = sub.add_parser("portfolio", help="Open positions, P&L and copy-trading")
    portfolio.add_argument("--account", choices=tuple(PORTFOLIO_PATHS), default="real")
    portfolio.add_argument("--format", choices=("json", "table"), default="json")
    portfolio.set_defaults(func=cmd_portfolio)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_cli(lambda: args.func(args))


if __name__ == "__main__":
    sys.exit(main())
