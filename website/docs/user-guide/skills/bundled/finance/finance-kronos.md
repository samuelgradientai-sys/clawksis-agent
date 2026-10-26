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
| Version | `0.3.0` |
| Author | samuelgradientai-sys, Clawksis |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `Finance`, `Forecasting`, `Stocks`, `Crypto`, `eToro`, `Portfolio`, `Trading`, `Time Series`, `Technical Analysis` |
| Related skills | [`stocks`](../../optional/finance/finance-stocks.md) |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Clawksis loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Kronos Skill

Forecasts the next candles of a stock, ETF, index or crypto with the open-source Kronos model
on CPU, adds technical indicators and position sizing, reads eToro candles and portfolios, and,
when the user turns trading on, buys and closes eToro positions inside hard limits (demo account
by default). It journals every forecast, scores it once the real price is known, turns misses
into lessons that block automatic buys of symbols it keeps getting wrong, and publishes a
dashboard of what it bought, sold and learned. Kronos is a research model that often fails to
beat "repeat the last close"; this is not a live-quote, fundamentals or leverage tool.

## When to Use

- "Forecast AAPL for the next 10 days", "what might BTC do in 24 hours", "RSI / MACD of Tesla",
  "how much should I buy and where is the stop", "is this model any good for this stock?".
- Spanish: "pronóstico de acciones", "¿qué hará Tesla la próxima semana?", "analiza el RSI",
  "conecta mi cuenta de eToro", "analiza mi portafolio", "instalé Kronos, ¿y ahora?",
  "analiza Apple cada día", "¿qué aprendió Kronos?", "muéstrame qué compró y vendió".
- Setting goals and a recurring routine (watchlist, objective, risk, horizon, schedule).
- Trading when enabled: "compra 50 dólares de Apple", "vende mi posición de Tesla", "opera
  automáticamente con Kronos", "¿cuánto me queda del límite de hoy?".
- Not for: leverage, short selling, limit orders, stop-loss edits in eToro (the user does
  those in the app), live quotes or fundamentals (the optional `stocks` skill covers Yahoo).

## Prerequisites

- **Runtime, once** (`kronos_setup.py`): a dedicated venv under `$CLAWK_HOME/kronos/` with
  CPU PyTorch, upstream Kronos code pinned and verified file by file, and pinned weights;
  ~1.2 GB and a few minutes (pypi.org, download.pytorch.org, codeload.github.com,
  huggingface.co). Kronos-small needs ~1 GB RAM. Indicators, risk and review need no runtime.
- **Data**: 64+ ordered bars (300–500 ideal) from eToro, a CSV (timestamps/date, open, high,
  low, close, optional volume) or the `stocks` skill's `history` JSON.
- **eToro (optional)**: `ETORO_API_KEY` and `ETORO_USER_KEY` in the profile's `.env`, created
  under Settings > Trading > API Key Management (one environment per key pair; the user key
  is shown once). Keys pasted in chat: save them with `clawk config set ETORO_API_KEY ...` /
  `clawk config set ETORO_USER_KEY ...` through `terminal`, never echo them back.
- **Trading (off by default)**: only the user runs `clawk config set
  skills.config.kronos.trading.enabled true`. Orders go to the demo account unless the user
  sets `trading.account real`; limits `max_order_usd` (100), `max_daily_usd` (300),
  `max_orders_per_day` (5). Never change these yourself.
- **Goals** (`skills.config.kronos.goals.*`): saved by you when the user states them. The
  loaded skill's `[Skill config]` block shows all current values.

## How to Run

Run every script through `terminal` with `python3` and the full path
(`${CLAWK_SKILL_DIR}` is expanded when the skill loads; shell variables do not persist between
calls). Forecast and backtest relaunch themselves inside the skill venv. Output is chat-ready
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

# analysis: indicators (no model), honesty check, forecast (journaled), sizing
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_indicators.py --etoro AAPL --interval OneDay
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_backtest.py --etoro AAPL --interval OneDay
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_forecast.py --etoro AAPL --interval OneDay --horizon 10 --format json
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_forecast.py --input aapl.csv --symbol AAPL --horizon 5
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_risk.py --account-size 10000 --etoro AAPL --interval OneDay

# learning loop and dashboard
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_review.py --etoro
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_review.py --bars AAPL=aapl.csv --json
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_dashboard.py

# trading (only when enabled; the script enforces account, limits and lessons)
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py status
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py positions
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py buy AAPL --amount 50 --reason "adds_value, +2.1% in 5d, bullish" --dry-run
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py buy AAPL --amount 50 --reason "user asked" --user-requested
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py close 123456789 --units 0.5 --reason "target hit"
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
3. **Runtime.** `kronos_setup.py --check`; if `setup_needed`, say it is a one-time ~1.2 GB
   download, then run `kronos_setup.py`.
4. **Learn first.** Run `kronos_review.py --etoro` (or `--bars SYMBOL=FILE` for file data)
   before analyzing or trading: it scores matured forecasts, updates lessons and the buy
   gate, and refreshes the dashboard. Tell the user about new lessons in plain words.
5. **Analyze each symbol.** `kronos_indicators.py` (signal + reasons), the backtest verdict
   (`kronos_backtest.py`; re-run when older than 7 days), then `kronos_forecast.py` with a
   horizon that fits the bars (daily 5–10, hourly 12–24). Forecasts are journaled
   automatically; pass `--symbol` for file input so reviews and trades match it, and
   `--no-journal` only for throwaway experiments.
6. **Present compactly.** Last close, close at horizon with % and direction, the p10–p90 band
   (too narrow), the backtest verdict, the indicator signal, `track_record` and `lessons` from
   the forecast output, and the disclaimer. Lead with `worse_than_naive` or a blocked track
   record when present. On messaging apps use bullets and attach `MEDIA:/abs/path.png` from
   `chart_path`.
7. **Portfolio review** ("analiza mi portafolio"): `etoro_data.py portfolio`, summarize cash,
   weights, concentration, P&L and copy-trading, then analyze the 3–5 largest holdings.
8. **Trading** (only when `status` shows `enabled: true`; no confirmation per order):
   - Buy only when every check in playbook § 3 passes (verdict `adds_value`, forecast up by
     at least half an ATR, indicators not bearish, no blocking lesson, limits left), sized
     with `kronos_risk.py`. Never split one decision into several orders.
   - The script refuses automatic buys of a symbol whose recent forecasts mostly missed;
     accept it and tell the user. `--user-requested` is ONLY for a buy the user explicitly
     asked for in this conversation; never in a scheduled run or to get past a refusal.
   - Manage open positions every run (stop, target, broken thesis, time stop; playbook § 4)
     by closing with `close` (not capped).
   - Always pass a one-line `--reason`; after every order report what, how much, status and
     why. `submitted`/`placed` means not filled yet: check `positions` later.
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
- **Refusals are final for today.** A `TradingRefused` (limits) or `LessonRefused` (track
  record) stands; an `unknown` order keeps counting: check `positions`, never resend blindly.
- **Unjournaled or mislabeled forecasts teach nothing.** File forecasts without `--symbol` are
  journaled under the file name and never match the eToro symbol a trade uses.
- **Reviews need matching bars**: same bar size as the forecast and reaching back before it;
  eToro returns at most 1000 bars, so very old forecasts can no longer be scored.
- **Minimums and market hours.** eToro rejects buys under the instrument minimum (HTTP 400);
  stock orders outside market hours stay `placed` until the open.
- **401/403 from eToro**: wrong key, demo/real key mismatch with `--account` or
  `trading.account`, or a key without that permission; `etoro_data.py check` shows scopes.
- **Unverified API details**: endpoints follow two third-party clients; see
  `references/etoro-api.md` before debugging odd responses.
- **No holiday calendar** for future timestamps (reviews count real bars, so scoring is fine).
- **CPU cost** grows with lookback x horizon x samples; for long watchlists use
  `--model mini` or fewer `--samples` (`references/model-notes.md`). `mini`/`base` need
  `kronos_setup.py --model mini --pin-on-first-use`.
- **Keys added mid-conversation** may need a new session before `terminal` sees them.
- `pip install kronos` is an unrelated package; never run the upstream web UI or fine-tune
  pipeline. Uninstall: delete `$CLAWK_HOME/kronos/`.

Details: `references/trading-playbook.md` (decisions, onboarding, routine prompt, reporting),
`references/learning-loop.md` (journal, scoring, lessons, gate, dashboard panels),
`references/etoro-api.md`, `references/model-notes.md`.

## Verification

```bash
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_setup.py --check
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_indicators.py --input prices.csv --json
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_review.py --json
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py status
```

`--check` prints `"ok": true`; indicators print a `signal` with `reasons`; the review prints
`"ok": true` with `accuracy`, `buy_gate` and `lessons` and refreshes the dashboard file;
`status` prints the trading settings and today's remaining limits.
