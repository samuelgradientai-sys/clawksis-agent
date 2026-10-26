# eToro Public API — what `etoro_data.py` and `etoro_trade.py` call

The official reference lives at `https://api-portal.etoro.com` (developer portal) and
`https://builders.etoro.com` (guides). Neither host could be fetched directly when this skill
was written (2026-10); the client follows what these sources agree on:

- excerpts of the official portal pages (rate limits, market orders, v2 create-order and
  order lookup) as returned by web search;
- eToro's own agent guidance in `github.com/etoro-builders/etoro-agent-skills` (read as a
  reference only: that repository has no license, nothing was copied from it);
- `florinel-chis/etoro-go` v0.1.1 (MIT, July 2026), whose author verified the candle and order
  behaviours against the live API, and the `etoropy` SDK v0.1.7.

Treat anything marked **UNVERIFIED** as the first suspect when a response looks wrong, and try
new trading flows on the demo account first.

## Authentication

| Header | Value | Status |
|---|---|---|
| `x-api-key` | `ETORO_API_KEY` — the public API key (identifies the application) | agreed by all sources |
| `x-user-key` | `ETORO_USER_KEY` — the user key (identifies the account; shown once at creation) | agreed |
| `x-request-id` | fresh UUID v4 per request (for an order: the ledger entry id) | agreed; see "At most once" |
| `User-Agent` | browser-compatible string; the CDN rejects generic tool agents | etoro-go only |

Keys are created in the eToro app under Settings > Trading > API Key Management, and each
key pair belongs to ONE environment: real or demo, with read or write access. `GET /api/v1/me`
returns the username and the scopes granted to the pair; a 403 elsewhere means the pair lacks
that endpoint's scope. If trading stays off, a read-only key is enough; `etoro_trade.py`
needs write access.

Base URL: `https://public-api.etoro.com`. The read client refuses redirects so the key headers
are never replayed to another host, and refuses any path outside the read-only prefixes
`/api/v1/market-data/`, `/api/v1/trading/info/` and `/api/v1/me`.

## Endpoints used (all GET)

| Purpose | Path | Notes |
|---|---|---|
| Identity / scopes | `/api/v1/me` | `etoro_data.py check` prints only `username` and `scopes` |
| Symbol search | `/api/v1/market-data/search?internalSymbolFull=AAPL&fields=...` | matches by containment (`AAPL` also returns `AAPL.24-7`, `AAPL.EUR`); the client keeps the exact, case-insensitive match. Response `{page, pageSize, totalItems, items:[{instrumentId, internalSymbolFull, isCurrentlyTradable, isDelisted, ...}]}`. Comma lists must stay literal (percent-encoded commas are ignored). |
| Candles | `/api/v1/market-data/instruments/{id}/history/candles/{asc\|desc}/{interval}/{count}` | `count` ≤ 1000; window always ends at the most recent bar, which is still forming (no from/to). Response `{interval, candles:[{instrumentId, candles:[{instrumentID, fromDate, open, high, low, close, volume}]}]}`. Unknown id → HTTP 200 with `"candles": null`. |
| Instrument names | `/api/v1/market-data/instruments?instrumentIds=ID` | `instrumentDisplayDatas[0].symbolFull` / `instrumentDisplayName`; one id per call (etoropy reports HTTP 500 for comma lists). |
| Portfolio with P&L | real `/api/v1/trading/info/real/pnl`, demo `/api/v1/trading/info/demo/pnl` | `{clientPortfolio:{positions, credit, mirrors, orders, ordersForOpen, unrealizedPnL, accountCurrencyId}}`; each position may carry `unrealizedPnL.pnL`, `stopLossRate`, `takeProfitRate`, `openDateTime`, `orderID`. The answer is cached ~10 s (rolling): a position opened seconds ago is not in it yet. |
| Portfolio breakdown (fallback on 404) | real `/api/v1/trading/info/portfolio`, demo `/api/v1/trading/info/demo/portfolio` | **UNVERIFIED for real**: both SDKs use `/trading/info/portfolio`, an eToro builders guide shows `/trading/info/real/portfolio`; the client tries both after the P&L route. |

Intervals accepted by the candle route: `OneMinute`, `FiveMinutes`, `TenMinutes`,
`FifteenMinutes`, `ThirtyMinutes`, `OneHour`, `FourHours`, `OneDay`, `OneWeek`.

Position fields read (`group_positions`): `instrumentID`, `isBuy`, `units`, `amount` (USD
invested incl. collateral), `openRate`, `leverage`, `unrealizedPnL.pnL`, `mirrorID`. Mirrors
(copy-trading) carry `parentUsername`, `availableAmount` and their own `positions`.

## Rate limits and errors

- Limits are per user key over a rolling minute: **60 requests for reads** (market data,
  portfolio, account) and **20 for writes** (opening and closing orders). Other apps using the
  same key share them.
- HTTP 429 means eToro did not process the request. Reads wait `Retry-After` (capped at 30 s,
  default 2 s) and retry once. Order requests: see below.
- Error bodies come in several envelopes (`errorMessage`, `message`, `detail`, `title`); the
  client surfaces the first one present, capped at 300 chars, never headers or keys.

## Trading (`etoro_trade.py`, only when enabled)

A separate client (`TradeClient`) that can reach exactly these routes; `etoro_data.py` stays
GET-only. `{demo/}` is present for the demo account and absent for real.

| Purpose | Route | Source / status |
|---|---|---|
| Market buy by amount | `POST /api/v2/trading/execution/{demo/}orders` with `{"action": "open", "transaction": "buy", "instrumentId", "settlementType": "real", "orderType": "mkt", "leverage": 1, "amount"}` plus, when set, `"stopLossRate"`, `"stopLossType": "fixed"`, `"takeProfitRate"` (absolute prices) → `{token, orderId, referenceId}` | v2 reference excerpts (a stop is mandatory there only for leverage, short and trailing stops; the skill requires it for automatic buys), field names per etoro-go. |
| Fallback buy (only if v2 answers 404/405 and the order has no stop or target) | `POST /api/v1/trading/execution/{demo/}market-open-orders/by-amount` with `{"InstrumentID", "IsBuy": true, "Leverage": 1, "Amount"}` → `{orderForOpen: {orderID, ...}, token}` | Deprecated but documented. Not known to keep a stop, so a protected order never falls back: it is refused and nothing is bought. |
| Close a position | `POST /api/v1/trading/execution/{demo/}market-close-orders/positions/{positionId}` with `{"InstrumentId", "UnitsToDeduct"}` (`null` closes it all) → `{orderForClose, token}` | Official reference; etoro-go and etoropy agree. |
| Order status | `GET /api/v2/trading/info/{demo/}orders:lookup?orderId=` or `?referenceId=<x-request-id>` → `{status: {id, name, errorCode, errorMessage}, positionExecutions}`; ids 1 received, 2 placed, 3 filled, 4 rejected, 5 partially filled, 7 canceled, 8 expired | etoro-go and the v2 reference excerpt; the `referenceId` form is **UNVERIFIED** on the live API (a failed lookup only leaves the order `submitted`/`unknown`). |

### At most once

eToro's own agent guidance says trade requests have no idempotency key, while the v2 reference
and etoro-go call `x-request-id` one. The skill assumes the stricter reading:

- An order POST is resent only after **HTTP 429**, with the same `x-request-id`, waiting
  `Retry-After` (capped at 60 s) or 15, 30 and 60 s, at most three times. After that the buy is
  logged `rejected` (eToro never processed it) and does not count.
- A **4xx** other than 429 is an explicit refusal: logged `rejected`, never resent.
- A **5xx, timeout, dropped connection or unreadable answer** is ambiguous: the order may exist.
  It is never resent, logged `unknown`, and keeps counting toward the day's limits.
- `etoro_trade.py reconcile` (read-only) settles `unknown` buys a minute or more later: the
  order lookup by `referenceId`, then the portfolio (`positions[]` = filled, `ordersForOpen[]`
  = placed, matched by order id, or by instrument, open time from 2 minutes before the buy and
  amount). Found → `filled`/`placed`; otherwise `not_found`, which still counts. Reconcile
  never frees a limit.
- Closes follow the same rule; an ambiguous close is logged `failed` with `in_doubt: true`
  and the hint to check positions before closing again (a repeated partial close sells twice).

### Guards before any order

Run in this order, before the order request: trading enabled, limits, lesson gate, backtest
gate (automatic buys need a verdict `adds_value` from the last 7 days in
`kronos/backtests.jsonl`), stop present (automatic buys), then the read-only checks: the
instrument is tradable (`isCurrentlyTradable`/`isDelisted` from the search), the newest hourly
candle is under 2 hours old, the NYSE regular session is open for an instrument with no Saturday
candles (`_kronos_calendar.py`), and the stop sits below the current price (by at most 50%) with
the target above it. Refused buys go to `kronos/refused.jsonl` with their kind (`limit`,
`lesson`, `backtest`, `stop`, `market`), never to the ledger.

Behaviour notes:

- A 200 on an open means *submitted*, not filled: execution is asynchronous.
- Per-instrument minimum amounts and minimum stop distances are enforced by eToro (HTTP 400);
  the script does not guess them.
- Settlement `real` buys the underlying asset without leverage; instruments that only trade as
  CFDs are rejected rather than silently opened as CFDs.
- The close route returns no realized P&L, so a close's ledger entry records `open_rate`,
  `invested_usd` and `pnl_usd` from the position's last `unrealizedPnL` valuation (pro-rated
  for partial closes) — an estimate the learning loop and dashboard label as such.

## Not implemented

Leverage, short selling (`sellShort`), limit / market-if-touched orders, editing a stop or
target after the buy, trailing stops, order cancellation, cash transactions, watchlists, social
feeds, agent portfolios (real money only) and WebSocket streaming. The user does those in the
eToro app.
