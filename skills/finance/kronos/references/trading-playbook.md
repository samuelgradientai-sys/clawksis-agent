# Kronos trading playbook

How the agent turns a forecast, indicators and lessons into a decision, when it stays out,
how it manages open positions, how it reports, how it onboards a new user, and how it replays
these rules on past prices. Every script
named here lives in `scripts/` and runs through the `terminal` tool. Nothing in this playbook
overrides the hard limits in `etoro_trade.py` or the user's own instructions.

## 1. Goals (onboarding)

On first use (the loaded skill's `[Skill config]` block shows `kronos.goals.watchlist =
(not set)`), ask the user in ONE message, in their language:

1. Which stocks, ETFs or crypto should Kronos follow? (resolve each to the exact eToro symbol
   with `etoro_data.py search`, e.g. `AAPL`, `BTC`, `NSDQ100`)
2. What do you want from it? e.g. "learn with the demo account", "grow savings slowly",
   "active short-term trading", "just watch and tell me".
3. How much risk can you stomach? low / medium / high (loss per trade if the stop is hit:
   0.5% / 1% / 2% of the account).
4. How long do you hold? days / weeks / months.
5. How often should Kronos analyze? e.g. every hour, every weekday at 10:30, every Monday.

Save the answers (values are plain text; quote them):

```bash
clawk config set skills.config.kronos.goals.watchlist "AAPL, BTC"
clawk config set skills.config.kronos.goals.objective "learn with the demo account"
clawk config set skills.config.kronos.goals.risk low
clawk config set skills.config.kronos.goals.horizon weeks
clawk config set skills.config.kronos.goals.schedule "weekdays at 10:30"
```

Goals are the user's to change at any time; the trading limits (`kronos.trading.*`) are not
goals and only the user changes them. Saving goals never turns trading on. When the objective
is "just watch" (or similar), never buy: analyze, learn and report only.

Map the horizon to bar size and forecast length:

| Horizon | `--interval` | Forecast `--horizon` | Typical schedule |
|---|---|---|---|
| days | `OneHour` | 12–24 | `every 1h` (crypto) or `weekdays at 10:30` + `weekdays at 14:00` (stocks) |
| weeks | `OneDay` | 5–10 | `weekdays at 10:30` (New York time for US stocks) |
| months | `OneDay` (or `OneWeek`) | 10–20 | `every monday 10:30` |

## 2. Scheduled routine

Offer it right after saving the goals. Create it with `cronjob_manage` (`action="create"`,
`skills=["kronos"]`, `name="Kronos <watchlist>"`, `schedule` from the goals, `prompt` below;
leave `deliver` unset so the report comes back to this chat). Schedule times are in the
user's configured Clawksis timezone: for US stocks pick a time inside the New York session
(9:30–16:00 ET; 10:30 ET leaves the open's spike behind), crypto trades around the clock.
One job covers the whole watchlist; update it (`action="update"`) instead of creating
duplicates when the goals change.

Prompt template (fill in the braces; the run has no memory of this chat, so keep it whole):

```text
Kronos routine for {WATCHLIST} ({INTERVAL} bars, forecast horizon {H}). Use the kronos skill's
scripts through the terminal tool and follow its references/trading-playbook.md.
1. Learn first: kronos_review.py --etoro. If any buy is unknown: etoro_trade.py reconcile.
2. For each symbol: kronos_indicators.py --etoro SYMBOL --interval {INTERVAL}, then
   kronos_forecast.py --etoro SYMBOL --interval {INTERVAL} --horizon {H} --format json.
   Re-run kronos_backtest.py --etoro SYMBOL --interval {INTERVAL} when its last verdict is
   older than 7 days or unknown (automatic buys need a fresh adds_value).
3. If etoro_trade.py status shows trading enabled: manage open positions (playbook § 4), then
   buy only when every check in playbook § 3 passes, sized with kronos_risk.py and bought with
   its buy_args (--amount --stop --target). Never pass --user-requested in this routine. The
   script refuses buys while the market is closed; accept it.
4. Run kronos_dashboard.py.
5. Reply in the user's language with a short report (playbook § 5). If nothing was traded
   and nothing new was learned, three lines are enough.
```

## 3. Decision checklist (buy)

Gather, per symbol: the review (`kronos_review.py`), the indicator signal
(`kronos_indicators.py`), the backtest verdict (`kronos_backtest.py`, at most 7 days old), the
forecast JSON (`summary`, `track_record`, `lessons`) and `etoro_trade.py status` / `positions`.

Buy only when ALL of these hold:

- `status` shows `enabled: true`, `buys_left > 0` and enough `usd_left`.
- The user's objective allows trading (not "just watch").
- Backtest verdict is `adds_value` for this symbol and interval, from the last 7 days: Kronos
  beat both "repeat the last close" and the ETS baseline (the script enforces this).
- The forecast points up (`summary.direction == "up"`) by at least half the ATR in percent
  (`indicators.atr_pct` from `kronos_indicators.py`); smaller moves are noise.
- The indicator signal is `bullish` or `neutral`, never `bearish`, and RSI is not above 70.
- `track_record.blocked` is false and no active lesson for the symbol says
  `low_accuracy`, `worse_than_naive`, `losing_trades` or `buy_blocked`. A `narrow_band` or
  `bullish_bias` lesson means: halve the size.
- No buy of this symbol is still `submitted`/`placed`/`unknown`, and there is no open position
  in it already (no doubling down) unless the objective says to accumulate.

Size it with `kronos_risk.py --account-size <cash + invested from etoro_data.py portfolio>
--etoro SYMBOL --interval <same>` and buy with its `buy_args`: `suggested_amount_usd` (already
capped by the limits; less is fine) plus `--stop` and `--target`, which travel with the order so
eToro closes the position at either level even between runs. An automatic buy without `--stop`
is refused. Never split one decision into several orders. Pass a one-line `--reason` with the
evidence, e.g. `"adds_value; forecast +2.1% in 5d; indicators bullish (+3); 6/9 right"`.

Stay out (and say why in the report) when: the market is closed for that stock, the newest
bar is older than two bar lengths (stale data), any order is `unknown` (run `reconcile`), the
verdict is not `adds_value`, the script refuses the buy (limits, lessons, backtest, stop,
market), or the evidence disagrees (forecast up, indicators bearish). The script itself refuses
buys while the New York session is closed for anything that does not trade on weekends, and
when the newest eToro price is over 2 hours old.

`--user-requested` exists only for a buy the user explicitly asked for in the conversation
("compra 50 dólares de Apple"). It skips the lesson check, not the limits. Never use it in a
scheduled run or to get around a refusal; when a lesson refuses a buy, tell the user why.

## 4. Position management (sell)

For every open position (`etoro_trade.py positions`), on every run:

- **Stop and target:** eToro executes the `stop_loss` and `take_profit` the buy carried and
  closes the whole position at either one; `positions` shows them. A position without a stop
  (bought by the user, or before this version) is checked by hand: run `kronos_risk.py
  --account-size <account> --entry <open_rate> --etoro SYMBOL` and close it when the last close
  is at or below `stop_loss`.
- **Thesis broken:** forecast down and indicators `bearish` → close.
- **Time stop:** held longer than the goal horizon with no progress → close.
- Always `--reason` (`"thesis broken: forecast -1.8%, bearish"`). Closes are not capped. A
  close that failed `in_doubt` may have gone through: check `positions` before closing again.

## 5. Reporting

Short, in the user's language; bullets on Telegram/WhatsApp, no tables:

- Per symbol: indicator signal, forecast % and direction, track record (`6/9 right`), and the
  decision: bought $X / closed / held / skipped, with the reason in a few words.
- Orders: amount, stop and target, status (`submitted`/`placed` = not filled yet; `unknown` =
  reconcile pending; `not_found` = never went through), refusals and why.
- What Kronos learned this run (new lessons) and today's limits left.
- Where to see everything: the Kronos dashboard in the Clawksis web dashboard.
- One disclaimer line: not financial advice; Kronos often fails to beat "no change".

## 6. Replaying the rules (`kronos_strategy_backtest.py`)

Before trading a new symbol, when the user asks "how would the strategy have done?", or after
changing goals, replay this playbook on past bars:

```bash
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_strategy_backtest.py --etoro AAPL --interval OneDay --benchmark SPY --report auto
```

At each bar it applies § 3 and § 4 with what was known then: the ETS forecast (or
`--forecaster kronos`, slow: one model call per decision, batched) up by half an ATR,
indicators not bearish, the lesson gate over its own simulated forecasts, sizing from
`kronos_risk.py`, the user's limits (`check_limits`; defaults when unset), fills at the next open,
stop and target inside later bars, thesis and time exits, `--fee-pct` per side. It reports CAGR,
max drawdown, Sharpe, win rate, exposure and how many buys the limits, lessons or a gap through
the stop refused, against buying and holding the symbol and the benchmark; `--report` adds a
quantstats HTML tear sheet when installed. Present it as history under today's rules, never as
a promise: with small orders on a large account the curve barely moves, so read the per-trade
numbers too, and never propose raising limits because a replay looked good.
