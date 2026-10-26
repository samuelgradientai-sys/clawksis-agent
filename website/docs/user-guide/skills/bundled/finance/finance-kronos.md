---
title: "Kronos — Forecast stocks/crypto; eToro data and limited trading"
sidebar_label: "Kronos"
description: "Forecast stocks/crypto; eToro data and limited trading"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Kronos

Forecast stocks/crypto; eToro data and limited trading.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/finance/kronos` |
| Version | `0.4.0` |
| Author | samuelgradientai-sys, Clawksis |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `Finance`, `Forecasting`, `Stocks`, `Crypto`, `eToro`, `Portfolio`, `Trading`, `Backtesting`, `Stop Loss`, `Time Series`, `Technical Analysis` |
| Related skills | [`stocks`](../../optional/finance/finance-stocks.md) |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Clawksis loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Kronos Skill

Forecasts the next candles of a stock, ETF, index or crypto with the open-source Kronos model
on CPU, adds technical indicators and position sizing, reads eToro candles and portfolios, and,
when the user turns trading on, buys (always with a stop-loss when it decides alone) and closes
eToro positions inside hard limits (demo account by default). It scores every forecast against
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
  is shown once). Keys pasted in chat: save them with `clawk config set ETORO_API_KEY ...` /
  `clawk config set ETORO_USER_KEY ...` through `terminal`, never echo them back.
- **Trading (off by default)**: only the user runs `clawk config set
  skills.config.kronos.trading.enabled true`. Orders go to the demo account unless the user
  sets `trading.account real`; limits `max_order_usd` (100), `max_daily_usd` (300),
  `max_orders_per_day` (5). Never change these yourself. The script adds its own refusals on
  top: automatic buys need a stop, a fresh `adds_value` backtest and an open market.
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
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py close 123456789 --units 0.5 --reason "thesis broken"
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
   inside 9:30–16:00 New York. Update that job when goals change; never duplicate it.
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
   - First `etoro_trade.py reconcile` when any buy is `unknown`; report what it found.
   - Buy only when every check in playbook § 3 passes (verdict `adds_value`, forecast up by
     at least half an ATR, indicators not bearish, no blocking lesson, limits left), sized
     with `kronos_risk.py`: pass its `buy_args` (`--amount --stop --target`); eToro then
     executes the stop and target. Never split one decision into several orders.
   - The script refuses automatic buys without a stop, of symbols whose recent forecasts
     mostly missed or without a fresh `adds_value` verdict, and any buy while the market is
     closed or the price is stale; accept it and tell the user. `--user-requested` is ONLY for
     a buy the user explicitly asked for in this conversation (it skips the lesson and
     backtest checks and may omit the stop); never in a scheduled run or to get past a refusal.
   - Manage open positions every run (broken thesis, time stop; playbook § 4) by closing
     with `close` (not capped).
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
- **Replays are not forecasts.** With $100 orders on a large account the equity curve barely
  moves; read the win rate and average trade too, and never suggest raising limits because a
  replay looked good.
- **CPU cost** grows with lookback x horizon x samples; for long watchlists use
  `--model mini` or fewer `--samples` (`references/model-notes.md`). `mini`/`base` need
  `kronos_setup.py --model mini --pin-on-first-use`.
- **Keys added mid-conversation** may need a new session before `terminal` sees them.
- `pip install kronos` is an unrelated package; never run the upstream web UI or fine-tune
  pipeline. Uninstall: delete `$CLAWK_HOME/kronos/`.

Details: `references/trading-playbook.md` (decisions, onboarding, routine prompt, reporting,
replaying the rules), `references/learning-loop.md` (journal, scoring, lessons, gates,
dashboard panels), `references/etoro-api.md` (routes, at-most-once orders, reconcile),
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
`status` prints the trading settings and today's remaining limits.
