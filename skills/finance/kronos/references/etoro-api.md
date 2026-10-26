# eToro Public API — what `etoro_data.py` and `etoro_trade.py` call

The official reference lives at `https://api-portal.etoro.com` (developer portal) and
`https://builders.etoro.com` (guides). Neither could be fetched when this skill was written
(2026-10), so the client follows two independent third-party clients that agree with each
other, plus search-result excerpts of the official pages:

- `florinel-chis/etoro-go` v0.1.1 (MIT, July 2026) — its README states the candle behaviours
  below were verified against the live API.
- `etoropy` v0.1.7 on PyPI (unofficial SDK, March 2026).

Treat anything marked **UNVERIFIED** as the first suspect when a response looks wrong.

## Authentication

| Header | Value | Status |
|---|---|---|
| `x-api-key` | `ETORO_API_KEY` — the public API key (identifies the application) | agreed by both clients + portal excerpts |
| `x-user-key` | `ETORO_USER_KEY` — the user key (identifies the account; shown once at creation) | agreed |
| `x-request-id` | fresh UUID v4 per request | agreed |
| `User-Agent` | browser-compatible string; the CDN rejects generic tool agents | etoro-go only |

Keys are created in the eToro app under Settings > Trading > API Key Management, and each
key pair belongs to ONE environment: real or demo. `GET /api/v1/me` returns the username and
the scopes granted to the pair; a 403 elsewhere means the pair lacks that endpoint's scope.
Whether a key can be limited to read-only scopes at creation time is **UNVERIFIED** — if the
portal offers it and trading stays off, choose read-only; `etoro_trade.py` needs trading scope.

Base URL: `https://public-api.etoro.com`. The client refuses redirects so the key headers are
never replayed to another host, and refuses any path outside the read-only prefixes
`/api/v1/market-data/`, `/api/v1/trading/info/` and `/api/v1/me`.

## Endpoints used (all GET)

| Purpose | Path | Notes |
|---|---|---|
| Identity / scopes | `/api/v1/me` | `etoro_data.py check` prints only `username` and `scopes` |
| Symbol search | `/api/v1/market-data/search?internalSymbolFull=AAPL&fields=...` | matches by containment (`AAPL` also returns `AAPL.24-7`, `AAPL.EUR`); the client keeps the exact, case-insensitive match. Response `{page, pageSize, totalItems, items:[{instrumentId, internalSymbolFull, ...}]}`. Comma lists must stay literal (percent-encoded commas are ignored). |
| Candles | `/api/v1/market-data/instruments/{id}/history/candles/{asc\|desc}/{interval}/{count}` | `count` ≤ 1000; window always ends at the most recent bar (no from/to). Response `{interval, candles:[{instrumentId, candles:[{instrumentID, fromDate, open, high, low, close, volume}]}]}`. Unknown id → HTTP 200 with `"candles": null`. |
| Instrument names | `/api/v1/market-data/instruments?instrumentIds=ID` | `instrumentDisplayDatas[0].symbolFull` / `instrumentDisplayName`; one id per call (etoropy reports HTTP 500 for comma lists). |
| Portfolio with P&L | real `/api/v1/trading/info/real/pnl`, demo `/api/v1/trading/info/demo/pnl` | `{clientPortfolio:{positions, credit, mirrors, orders, ordersForOpen, unrealizedPnL, accountCurrencyId}}`; each position may carry `unrealizedPnL.pnL`. |
| Portfolio breakdown (fallback on 404) | real `/api/v1/trading/info/portfolio`, demo `/api/v1/trading/info/demo/portfolio` | **UNVERIFIED for real**: both SDKs use `/trading/info/portfolio`, an eToro builders guide shows `/trading/info/real/portfolio`; the client tries both after the P&L route. |

Intervals accepted by the candle route: `OneMinute`, `FiveMinutes`, `TenMinutes`,
`FifteenMinutes`, `ThirtyMinutes`, `OneHour`, `FourHours`, `OneDay`, `OneWeek`.

Position fields read (`group_positions`): `instrumentID`, `isBuy`, `units`, `amount` (USD
invested incl. collateral), `openRate`, `leverage`, `unrealizedPnL.pnL`, `mirrorID`. Mirrors
(copy-trading) carry `parentUsername`, `availableAmount` and their own `positions`.

## Rate limits and errors

- Market-data endpoints share roughly 120 requests per 60 s; account endpoints a default
  60/60 s pool (etoro-go). The server reports quotas in `ratelimit-*` headers.
- On HTTP 429 the client waits `Retry-After` (capped at 30 s, default 2 s) and retries once.
- Error bodies come in several envelopes (`errorMessage`, `message`, `detail`, `title`); the
  client surfaces the first one present, capped at 300 chars, never headers or keys.

## Trading (`etoro_trade.py`, only when enabled)

A separate client (`TradeClient`) that can reach exactly these routes; `etoro_data.py` stays
GET-only. `{demo/}` is present for the demo account and absent for real.

| Purpose | Route | Source / status |
|---|---|---|
| Market buy by amount | `POST /api/v2/trading/execution/{demo/}orders` with `{"action": "open", "transaction": "buy", "instrumentId", "settlementType": "real", "orderType": "mkt", "leverage": 1, "amount"}` → `{token, orderId, referenceId}` | Current route per the official guide; field names from etoro-go v0.1.1 and the portal's example (camelCase). Not yet exercised live by this skill: verify on demo first. |
| Fallback buy (only if the v2 route answers 404/405) | `POST /api/v1/trading/execution/{demo/}market-open-orders/by-amount` with `{"InstrumentID", "IsBuy": true, "Leverage": 1, "Amount"}` → `{orderForOpen: {orderID, ...}, token}` | Deprecated in the official Swagger, still documented; etoropy uses it. |
| Close a position | `POST /api/v1/trading/execution/{demo/}market-close-orders/positions/{positionId}` with `{"InstrumentId", "UnitsToDeduct"}` (`null` closes it all) → `{orderForClose, token}` | Official reference; etoro-go and etoropy agree. |
| Order status | `GET /api/v2/trading/info/{demo/}orders:lookup?orderId=` → `{status: {id, name, errorCode, errorMessage}, positionExecutions}`; ids 1 received, 2 placed, 3 filled, 4 rejected, 5 partially filled, 7 canceled, 8 expired | etoro-go only (**UNVERIFIED**); a failed lookup leaves the order as `submitted`. |

Behaviour notes:

- A 200 on an open means *submitted*, not filled: execution is asynchronous.
- `x-request-id` doubles as the idempotency key; the client retries a 429 once with the same id.
- Trading endpoints share roughly 20 requests per 60 s.
- Per-instrument minimum amounts are enforced by eToro (HTTP 400); the script does not guess them.
- Settlement `real` buys the underlying asset without leverage; instruments that only trade as
  CFDs are rejected rather than silently opened as CFDs.
- The close route returns no realized P&L, so a close's ledger entry records `open_rate`,
  `invested_usd` and `pnl_usd` from the position's last `unrealizedPnL` valuation (pro-rated
  for partial closes) — an estimate the learning loop and dashboard label as such.
- Buys refused before any request (limits, lessons) are logged to `kronos/refused.jsonl`, never
  to the ledger, so they cannot count toward the daily limits.

## Not implemented

Leverage, short selling (`sellShort`), limit / market-if-touched orders, stop-loss and
take-profit edits, order cancellation, cash transactions, watchlists, social feeds and
WebSocket streaming. The user does those in the eToro app.
