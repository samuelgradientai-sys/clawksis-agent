---
name: kronos
description: Forecast stocks/crypto; eToro data and limited trading.
version: 0.6.0
author: samuelgradientai-sys, Clawksis
license: MIT
platforms: [linux, macos, windows]
metadata:
  clawk:
    tags: [Finance, Forecasting, Stocks, Crypto, eToro, Portfolio, Trading, Backtesting, Stop Loss, Time Series, Technical Analysis]
    category: finance
    related_skills: [stocks]
    dashboard:
      title: Kronos
      description: What Kronos bought, sold, refused and learned.
    config:
      - key: kronos.trading.enabled
        description: "Let the agent place eToro orders inside the limits (off until the user turns it on)"
        default: false
        label: {es: "Trading automático"}
        confirm: true
      - key: kronos.trading.account
        description: "eToro account for orders: demo (virtual money) or real"
        default: demo
        choices: [demo, real]
        choice_labels: {es: {demo: "Demo (dinero virtual)", real: "Real (dinero de verdad)"}}
        label: {es: "Cuenta de eToro"}
        confirm: [real]
      - key: kronos.trading.max_order_usd
        description: "Max USD per stock/ETF buy (crypto has its own limits)"
        default: 100
        min: 1
        label: {es: "Acciones/ETF: máximo por orden (USD)"}
        confirm: true
      - key: kronos.trading.max_daily_usd
        description: "Max USD of stock/ETF buys in one UTC day"
        default: 300
        min: 1
        label: {es: "Acciones/ETF: máximo por día (USD)"}
        confirm: true
      - key: kronos.trading.max_orders_per_day
        description: "Max stock/ETF buys per UTC day"
        default: 5
        min: 1
        label: {es: "Acciones/ETF: compras máximas por día"}
        confirm: true
      - key: kronos.trading.max_positions
        description: "Max stock/ETF positions Kronos holds open at once"
        default: 5
        min: 1
        label: {es: "Acciones/ETF: posiciones abiertas máximas"}
        confirm: true
      - key: kronos.trading.stop_pct
        description: "Stock/ETF stop-loss in % below the entry; 0 = 2×ATR (volatility)"
        type: number
        default: 0
        min: 0
        max: 50
        label: {es: "Acciones/ETF: stop-loss % (0 = según volatilidad)"}
        confirm: true
      - key: kronos.crypto.enabled
        description: "Let Kronos buy crypto (24/7) inside the crypto limits; needs trading on"
        default: false
        label: {es: "Comprar criptomonedas"}
        confirm: true
      - key: kronos.crypto.watchlist
        description: "Crypto Kronos follows, comma-separated eToro symbols (e.g. BTC, ETH, SOL)"
        label: {es: "Cripto: lista de seguimiento"}
      - key: kronos.crypto.max_order_usd
        description: "Max USD per crypto buy (meme coins included)"
        default: 50
        min: 1
        label: {es: "Cripto: máximo por orden (USD)"}
        confirm: true
      - key: kronos.crypto.max_daily_usd
        description: "Max USD of crypto buys (meme coins included) in one UTC day"
        default: 150
        min: 1
        label: {es: "Cripto: máximo por día (USD)"}
        confirm: true
      - key: kronos.crypto.max_orders_per_day
        description: "Max crypto buys (meme coins included) per UTC day"
        default: 3
        min: 1
        label: {es: "Cripto: compras máximas por día"}
        confirm: true
      - key: kronos.crypto.max_positions
        description: "Max crypto positions Kronos holds open at once (meme coins apart)"
        default: 2
        min: 1
        label: {es: "Cripto: posiciones abiertas máximas"}
        confirm: true
      - key: kronos.crypto.stop_pct
        description: "Crypto stop-loss in % below the entry; 0 = 2×ATR (volatility)"
        type: number
        default: 12
        min: 0
        max: 50
        label: {es: "Cripto: stop-loss % (0 = según volatilidad)"}
        confirm: true
      - key: kronos.crypto.meme.enabled
        description: "Also let Kronos buy meme coins (extremely volatile; needs crypto on)"
        default: false
        label: {es: "Comprar meme coins"}
        confirm: true
      - key: kronos.crypto.meme.symbols
        description: "Coins treated as meme coins, comma-separated eToro symbols"
        default: "DOGE, SHIB, PEPE, BONK, FLOKI, WIF"
        label: {es: "Meme coins: lista"}
      - key: kronos.crypto.meme.max_order_usd
        description: "Max USD per meme-coin buy"
        default: 20
        min: 1
        label: {es: "Meme coins: máximo por orden (USD)"}
        confirm: true
      - key: kronos.crypto.meme.max_daily_usd
        description: "Max USD of meme-coin buys in one UTC day"
        default: 50
        min: 1
        label: {es: "Meme coins: máximo por día (USD)"}
        confirm: true
      - key: kronos.crypto.meme.max_orders_per_day
        description: "Max meme-coin buys per UTC day (they count as crypto buys too)"
        default: 1
        min: 1
        label: {es: "Meme coins: compras máximas por día"}
        confirm: true
      - key: kronos.crypto.meme.max_positions
        description: "Max meme-coin positions Kronos holds open at once"
        default: 1
        min: 1
        label: {es: "Meme coins: posiciones abiertas máximas"}
        confirm: true
      - key: kronos.crypto.meme.stop_pct
        description: "Meme-coin stop-loss in % below the entry; 0 = 2×ATR (volatility)"
        type: number
        default: 20
        min: 0
        max: 50
        label: {es: "Meme coins: stop-loss % (0 = según volatilidad)"}
        confirm: true
      - key: kronos.goals.watchlist
        description: "Symbols Kronos follows, comma-separated (e.g. AAPL, BTC)"
        label: {es: "Lista de seguimiento"}
      - key: kronos.goals.objective
        description: "The user's goal (e.g. learn on demo, grow savings slowly)"
        label: {es: "Objetivo"}
      - key: kronos.goals.risk
        description: "Risk tolerance: low, medium or high"
        default: low
        choices: [low, medium, high]
        choice_labels: {es: {low: Bajo, medium: Medio, high: Alto}}
        label: {es: "Riesgo"}
      - key: kronos.goals.horizon
        description: "Holding horizon: days, weeks or months"
        choices: [days, weeks, months]
        choice_labels: {es: {days: Días, weeks: Semanas, months: Meses}}
        label: {es: "Horizonte"}
      - key: kronos.goals.schedule
        description: "How often to analyze (e.g. weekdays at 10:30, every 1h)"
        label: {es: "Frecuencia"}
required_environment_variables:
  - name: ETORO_API_KEY
    prompt: eToro public API key (sent as x-api-key)
    help: "eToro > Settings > Trading > API Key Management. Only needed for eToro data or trading; CSV files work without it."
    required_for: "eToro market data, portfolio and (when enabled) trading"
    optional: true
  - name: ETORO_USER_KEY
    prompt: eToro user key (sent as x-user-key; shown only once when created)
    help: "eToro > Settings > Trading > API Key Management. Only needed for eToro data or trading; CSV files work without it."
    required_for: "eToro market data, portfolio and (when enabled) trading"
    optional: true
---

# Kronos Skill

Forecasts the next candles of a stock, ETF, index or crypto with the open-source Kronos model
on CPU, adds technical indicators and position sizing, reads eToro candles and portfolios, and,
when the user turns trading on, buys (always with a stop-loss when it decides alone) and closes
eToro positions inside hard limits (demo account by default); crypto and meme coins are
separate buckets with their own switches and smaller limits. It scores every forecast against
"repeat the last close" and a classical ETS model, turns misses into lessons that block
automatic buys, replays its own rules on past prices, and publishes a dashboard of what it
bought, sold, refused and learned. Kronos is a research model that often loses to those simple
baselines; this is not a live-quote, fundamentals or leverage tool.

## When to Use

- "Forecast AAPL for the next 10 days", "what might BTC do in 24 hours", "RSI / MACD of Tesla",
  "how much should I buy and where is the stop", "is this model any good for this stock?".
- Spanish: "pronóstico de acciones", "¿qué hará Tesla la próxima semana?", "analiza el RSI",
  "conecta mi cuenta de eToro", "analiza mi portafolio", "instalé Kronos, ¿y ahora?",
  "analiza Apple cada día", "¿qué aprendió Kronos?", "muéstrame qué compró y vendió".
- Setting goals and a recurring routine (watchlist, objective, risk, horizon, schedule).
- Trading when enabled: "compra 50 dólares de Apple", "vende mi posición de Tesla", "opera
  automáticamente con Kronos", "¿cuánto me queda del límite de hoy?".
- Crypto and meme coins when enabled: "compra 20 dólares de Bitcoin", "compra DOGE",
  "opera criptos cada hora", "¿cuánto me queda de cripto hoy?", "¿qué meme coins sigue?".
- Checking the rules: "¿cómo le habría ido a la estrategia con Apple?", "backtest de la
  estrategia contra el SPY", "¿Kronos le gana a un modelo simple?".
- Not for: leverage, short selling, limit orders, moving a stop after the buy (the user does
  those in the app), live quotes or fundamentals (the optional `stocks` skill covers Yahoo).

## Prerequisites

- **Runtime, once** (`kronos_setup.py`): a dedicated venv under `$CLAWK_HOME/kronos/` with
  CPU PyTorch, upstream Kronos code pinned and verified file by file, and pinned weights;
  ~1.2 GB and a few minutes (pypi.org, download.pytorch.org, codeload.github.com,
  huggingface.co), plus ~300 MB of optional extras: statsforecast (AutoETS baseline),
  pandas_market_calendars (exchange holidays), quantstats (HTML tear sheet). A failed extra
  never fails the install and every script degrades without it (`--no-extras` skips them).
  Kronos-small needs ~1 GB RAM. Indicators, risk, review and the ETS replay need no runtime.
- **Data**: 64+ ordered bars (300–500 ideal) from eToro, a CSV (timestamps/date, open, high,
  low, close, optional volume) or the `stocks` skill's `history` JSON.
- **eToro (optional)**: `ETORO_API_KEY` and `ETORO_USER_KEY` in the profile's `.env`, created
  under Settings > Trading > API Key Management (one environment per key pair; the user key
  is shown once). eToro's creation screen labels them **Clave privada** (the user key →
  `ETORO_USER_KEY`) and **Clave pública** (the API key → `ETORO_API_KEY`); map them that way.
  Ask for read-only scopes (minimal set and full catalog: `references/etoro-permissions.md`).
  Keys pasted in chat: save them with `clawk config set ETORO_API_KEY ...` /
  `clawk config set ETORO_USER_KEY ...` through `terminal`, never echo them back, then verify
  with `etoro_data.py check`.
- **Trading (off by default)**: only the user runs `clawk config set
  skills.config.kronos.trading.enabled true`. Orders go to the demo account unless the user
  sets `trading.account real`; limits `max_order_usd` (100), `max_daily_usd` (300),
  `max_orders_per_day` (5), `max_positions` (5 open at once) and `stop_pct` (0 = stop 2 ATR
  below the entry, else a fixed % below it), which cover stocks, ETFs and everything but
  crypto. Never change these yourself. The script adds its own refusals on top: automatic
  buys need a stop, a fresh `adds_value` backtest and an open market.
- **Crypto (off by default, on top of trading)**: `kronos.crypto.enabled` lets Kronos buy
  crypto (eToro instrument type 10) inside its own caps `crypto.max_order_usd` (50),
  `max_daily_usd` (150), `max_orders_per_day` (3), `max_positions` (2), `stop_pct` (12);
  `crypto.watchlist` lists the coins it follows. Meme coins (`crypto.meme.symbols`, default
  DOGE, SHIB, PEPE, BONK, FLOKI, WIF) also need `crypto.meme.enabled` and count against
  `meme.max_order_usd` (20), `meme.max_daily_usd` (50), `meme.max_orders_per_day` (1) and the
  crypto caps, with their own `meme.max_positions` (1) and `meme.stop_pct` (20). The user
  flips these in the Kronos dashboard's Settings (it asks them to confirm) or with
  `clawk config set`; never you. Rules: playbook § 7.
- **Goals** (`skills.config.kronos.goals.*`): saved by you when the user states them. The
  loaded skill's `[Skill config]` block shows all current values.

## How to Run

Run every script through `terminal` with `python3` and the full path
(`${CLAWK_SKILL_DIR}` is expanded when the skill loads; shell variables do not persist between
calls). Forecast, backtest and the strategy replay relaunch themselves inside the skill venv
(the ETS replay also runs without it). Output is chat-ready
text; `--format json` (or `--json` on the newer scripts) for automation. Errors are JSON with
`error` and `hint`.

```bash
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_review.py --etoro
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_forecast.py --etoro AAPL --interval OneDay --horizon 10 --plot auto
```

## Quick Reference

```bash
# runtime (once per profile; idempotent)
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_setup.py --check
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_setup.py

# eToro, read-only
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_data.py check
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_data.py search TSLA
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_data.py candles BTC --interval OneHour --count 500 --output btc_1h.csv
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_data.py portfolio --account demo --format table

# analysis: indicators (no model), honesty check (verdict recorded), forecast, sizing, replay
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_indicators.py --etoro AAPL --interval OneDay
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_backtest.py --etoro AAPL --interval OneDay
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_forecast.py --etoro AAPL --interval OneDay --horizon 10 --format json
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_forecast.py --input aapl.csv --symbol AAPL --horizon 5
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_risk.py --account-size 10000 --etoro AAPL --interval OneDay
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_strategy_backtest.py --etoro AAPL --benchmark SPY --report auto

# learning loop and dashboard
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_review.py --etoro
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_review.py --bars AAPL=aapl.csv --json
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_dashboard.py

# trading (only when enabled; the script enforces account, limits, lessons, stop and hours)
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py status
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py positions
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py buy AAPL --amount 50 --stop 180.5 --target 199.3 --reason "adds_value, +2.1% in 5d, bullish" --dry-run
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py buy AAPL --amount 50 --reason "user asked" --user-requested
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_risk.py --account-size 10000 --etoro DOGE --interval OneHour --asset meme
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py buy BTC --amount 30 --stop 61000 --target 68000 --reason "adds_value, +1.8% in 24h" --dry-run
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py close 123456789 --units 0.5 --reason "thesis broken"
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py set-stop 123456789 --stop 359.98 --target 456.3 --reason "no broker stop"
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py reconcile
```

Intervals: `OneMinute`, `FiveMinutes`, `TenMinutes`, `FifteenMinutes`, `ThirtyMinutes`, `OneHour`,
`FourHours`, `OneDay`, `OneWeek` (aliases `1h`, `1d` ...). CPU knobs (`--model`,
`--lookback`, `--samples`, `--threads`): `references/model-notes.md`.

## Procedure

1. **First use: goals.** If `kronos.goals.watchlist` is `(not set)` and the user wants more
   than a one-off answer, ask the five onboarding questions in one message (symbols,
   objective, risk, horizon, how often; `references/trading-playbook.md` § 1), resolve
   symbols with `etoro_data.py search`, and save each answer with `clawk config set
   skills.config.kronos.goals.<key> "<value>"` through `terminal`. Saving goals never
   enables trading.
2. **Offer the routine.** Create one `cronjob_manage` job (`action="create"`,
   `skills=["kronos"]`, `schedule` from the goals, the prompt template in playbook § 2;
   leave `deliver` unset). Schedule times are the user's Clawksis timezone; keep US stocks
   inside 9:30–16:00 New York. Update that job when goals change; never duplicate it. With
   crypto on, offer a second job for `crypto.watchlist` every hour (crypto trades 24/7).
3. **Runtime.** `kronos_setup.py --check`; if `setup_needed`, say it is a one-time ~1.5 GB
   download (with the optional extras), then run `kronos_setup.py`.
4. **Learn first.** Run `kronos_review.py --etoro` (or `--bars SYMBOL=FILE` for file data)
   before analyzing or trading: it scores matured forecasts, updates lessons and the buy
   gate, and refreshes the dashboard. Tell the user about new lessons in plain words.
5. **Analyze each symbol.** `kronos_indicators.py` (signal + reasons), the backtest verdict
   (`kronos_backtest.py`; re-run when older than 7 days: it is recorded, and automatic buys
   need a fresh `adds_value`, i.e. Kronos beat both "repeat the last close" and ETS), then
   `kronos_forecast.py` with a horizon that fits the bars (daily 5–10, hourly 12–24).
   Forecasts are journaled automatically; pass `--symbol` for file input so reviews, verdicts
   and trades match it, and `--no-journal` only for throwaway experiments. Before trading a
   new symbol, replay the rules once with `kronos_strategy_backtest.py` (playbook § 6).
6. **Present compactly.** Last close, close at horizon with % and direction, the p10–p90 band
   (too narrow), the backtest verdict, the indicator signal, `track_record` and `lessons` from
   the forecast output, and the disclaimer. Lead with `worse_than_naive` or a blocked track
   record when present. On messaging apps use bullets and attach `MEDIA:/abs/path.png` from
   `chart_path`.
7. **Portfolio review** ("analiza mi portafolio"): `etoro_data.py portfolio`, summarize cash,
   weights, concentration, P&L and copy-trading, then analyze the 3–5 largest holdings.
8. **Trading** (only when `status` shows `enabled: true`; no confirmation per order):
   - First `etoro_trade.py reconcile`: it settles `unknown` buys and stops counting positions
     eToro closed on its own (stop or target hit); report what it found.
   - Buy only when every check in playbook § 3 passes (verdict `adds_value`, forecast up by
     at least half an ATR, indicators not bearish, no blocking lesson, limits and a free
     position slot left), sized with `kronos_risk.py`: pass its `buy_args` (`--amount --stop
     --target`; the stop follows the bucket's `stop_pct`); eToro then executes the stop and
     target. Never split one decision into several orders.
   - The script refuses automatic buys without a stop, a stop farther than the bucket's
     `stop_pct`, a buy beyond the bucket's `max_positions`, symbols whose recent forecasts
     mostly missed or without a fresh `adds_value` verdict, and any buy while the market is
     closed or the price is stale; accept it and tell the user. `--user-requested` is ONLY for
     a buy the user explicitly asked for in this conversation (it skips the lesson and
     backtest checks and may omit the stop); never in a scheduled run or to get past a refusal.
   - Crypto and meme coins follow the same checks with their own caps (playbook § 7):
     size them with `kronos_risk.py --asset crypto|meme` (auto when eToro says crypto or the
     symbol is on a list) and buy the exact eToro symbol (`etoro_data.py search`). A
     `CryptoRefused` (switch off, meme coin eToro does not list) is final; tell the user.
   - Manage open positions every run (broken thesis, time stop; playbook § 4) by closing
     with `close` (not capped). A position whose `stop_loss` in `positions --format json` is
     missing or ~0 has no stop at eToro: give it one with `set-stop` (eToro then closes it
     between runs too; a stop at or above the price is refused, it would close at once).
   - Always pass a one-line `--reason`; after every order report what, how much, the stop,
     status and why. `submitted`/`placed` means not filled yet: check `positions` later.
9. **Dashboard.** Forecasts, reviews and orders refresh `$CLAWK_HOME/dashboards/kronos.json`
   on their own; `kronos_dashboard.py` rebuilds it. Point the user to the Kronos dashboard in
   the Clawksis web dashboard for what was bought, sold, refused and learned.

## Pitfalls

- **Not advice, often no better than naive.** Independent tests found Kronos losing to
  "repeat the last close" and its bands covering ~58% instead of 90%. Never present a
  forecast without the backtest verdict and its track record.
- **Trading is the user's switch.** If `status` says `enabled: false`, explain how the user
  enables it; never enable it, raise limits, switch to real, or call eToro trading any way
  other than `etoro_trade.py`.
- **Refusals are final for today.** A `TradingRefused` (limits, stop, market) or
  `LessonRefused`/`BacktestRefused` (track record) stands. eToro orders have no reliable
  idempotency, so the script resends an order only after HTTP 429; a timeout or 5xx leaves it
  `unknown`, counted toward the limits: run `reconcile` a minute later, never buy it again
  blindly. `not_found` keeps counting too; tell the user, no automatic rebuy that day.
- **Unjournaled or mislabeled forecasts teach nothing.** File forecasts without `--symbol` are
  journaled under the file name and never match the eToro symbol a trade uses.
- **Reviews need matching bars**: same bar size as the forecast and reaching back before it;
  eToro returns at most 1000 bars, so very old forecasts can no longer be scored.
- **Minimums and market hours.** eToro rejects buys under the instrument minimum (HTTP 400).
  The script refuses buys when the newest eToro price is over 2 hours old and, for anything
  with no Saturday trading (24/5 stocks included), outside the NYSE regular session (holidays
  and 13:00 early closes included; non-US stocks are held to New York hours too).
- **Rate limits**: 60 reads and 20 order requests per minute per user key, shared with any
  other app using it.
- **401/403 from eToro**: wrong key, demo/real key mismatch with `--account` or
  `trading.account`, or a key without that permission; `etoro_data.py check` shows scopes.
- **Unverified API details**: the stop/target fields and the lookup by request id follow the
  v2 reference excerpts and third-party clients; see `references/etoro-api.md` and try new
  flows on demo first.
- **Calendar**: weekday series get NYSE trading days (holidays, early closes) as future
  timestamps; `--calendar weekdays` or `sessions` for markets open on US holidays.
  Unscheduled closures cannot be known in advance.
- **Meme coins are extremely volatile.** They can halve in hours and gap through a stop;
  say so whenever one is bought or suggested, keep to the meme caps, and never present a meme
  forecast as more than a coin flip. eToro lists some coins per million units (`SHIBxM`): the
  meme list matches both spellings, but buy the exact symbol eToro shows.
- **Crypto limits are separate.** Crypto buys never use the stock limits and stock buys never
  use the crypto ones; a meme coin uses both its own and the crypto daily caps, but only a meme
  position slot. `status` shows each, with open positions and the stop rule per bucket.
- **Open positions are counted from the ledger.** A position eToro closed at its stop or
  target keeps counting until `reconcile` sees it gone from the portfolio; run it before
  buying, and never delete or edit `trades.jsonl` to free a slot.
- **Replays are not forecasts.** With $100 orders on a large account the equity curve barely
  moves; read the win rate and average trade too, and never suggest raising limits because a
  replay looked good.
- **CPU cost** grows with lookback x horizon x samples; for long watchlists use
  `--model mini` or fewer `--samples` (`references/model-notes.md`). `mini`/`base` need
  `kronos_setup.py --model mini --pin-on-first-use`.
- **Keys saved mid-conversation are not in the environment yet.** The running gateway and
  terminal inherited their environment at startup, so scripts report "eToro API keys are not
  configured" while the keys sit in `.env`. Do not ask for the keys again: read `.env` in
  Python and pass the pair through `env={**os.environ, "ETORO_API_KEY": ..., "ETORO_USER_KEY": ...}`
  to the script. Only a `cronjob` needs the user to restart the gateway first.
- **Audit the scopes before trusting a key.** `etoro_data.py check` lists them; with
  `etoro-public:trade.real:write` present the key can place real orders, so say so plainly.
  Never change `kronos.trading.*` to compensate.
- **20 origins is too few to claim an edge.** On daily bars a 20-origin audit can flip (NVDA:
  +0.089 `adds_value` at 20, -0.042 `worse_than_naive` at 40). Use `--origins 40` before
  treating a symbol as having edge, and re-audit before each trading decision.
- `pip install kronos` is an unrelated package; never run the upstream web UI or fine-tune
  pipeline. Uninstall: delete `$CLAWK_HOME/kronos/`.

Details: `references/trading-playbook.md` (decisions, onboarding, routine prompt, reporting,
replaying the rules, crypto and meme coins), `references/learning-loop.md` (journal, scoring, lessons, gates,
dashboard panels), `references/etoro-api.md` (routes, at-most-once orders, reconcile),
`references/etoro-permissions.md` (scope catalog, read-only set),
`references/model-notes.md` (models, CPU knobs, baselines).

## Verification

```bash
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_setup.py --check
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_indicators.py --input prices.csv --json
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_review.py --json
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_strategy_backtest.py --input prices.csv --json --no-record
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py status
```

`--check` prints `"ok": true` and which `extras` are installed; indicators print a `signal`
with `reasons`; the review prints `"ok": true` with `accuracy`, `buy_gate` and `lessons` and
refreshes the dashboard file; the replay prints `strategy`, `buy_and_hold` and `limits`;
`status` prints the trading settings, today's remaining limits and the open positions against
their maximum with the stop rule, crypto and meme coins apart.
