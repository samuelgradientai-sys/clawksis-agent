# Kronos learning loop

Kronos learns from its mistakes by keeping score. Every forecast is journaled, scored once the
real price is known, summarized per symbol, and turned into short lessons; the worst lesson
("this symbol's forecasts keep missing") is enforced by `etoro_trade.py` itself. All files live
in the profile's `$CLAWK_HOME` and are append-only JSONL (later lines update earlier ones).

## Files

| File | Written by | Holds |
|---|---|---|
| `kronos/forecasts.jsonl` | `kronos_forecast.py` (one line per run), `kronos_review.py` (`{"id", "outcome"}` lines) | the forecast journal |
| `kronos/lessons.jsonl` | `kronos_review.py` | lessons, folded by `key` |
| `kronos/trades.jsonl` | `etoro_trade.py buy/close` | the trade ledger (limits are counted from it) |
| `kronos/refused.jsonl` | `etoro_trade.py buy` | buys refused by the limits or the lessons |
| `dashboards/kronos.json` | `kronos_dashboard.py` (called by all of the above) | the dashboard snapshot |

Journal record: `id`, `made_at`, `symbol` (eToro symbol, `--symbol`, or the file name
upper-cased), `source`, `interval` ("1 day"), `step_seconds`, `horizon`, `model`,
`last_timestamp`, `last_close`, `target_timestamp`, `predicted_close`, `pct_change`,
`direction` (up/down/flat, ±0.1% counts as flat), `band` (p10, p90 at the horizon).
`--no-journal` skips it (throwaway experiments only: unjournaled forecasts teach nothing).

## Scoring (`kronos_review.py`)

A forecast is due once its target bar has closed. The actual price is the close of the
horizon-th bar after `last_timestamp` in the bars the review gets (`--bars SYMBOL=FILE` with
the same bar size, or `--etoro`), so exchange holidays shift nothing. Bars that start after the
forecast, or have a different bar size, are refused with a note. The outcome stores
`actual_close`, `actual_direction`, `direction_hit` (predicted == actual direction),
`error_pct`, `naive_error_pct` (error of "no change"), `beat_naive`, `in_band`.

## Accuracy and the buy gate

- Recent accuracy = the last 10 scored forecasts (`--window`) per symbol and bar size; no
  claim is made below 5.
- **Buy gate** (in `etoro_trade.py buy`, before any network call): the symbol's last 10 scored
  forecasts across all bar sizes; with at least 5 and a direction hit rate under 50%, an
  automatic buy is refused (`LessonRefused`, logged to `refused.jsonl`). An unreadable journal
  refuses too (fail closed). `--user-requested` skips only this check, for a buy the user
  explicitly asked for; the limits still apply. The order's ledger entry records
  `user_requested` and the `track_record` it was checked against.

## Lessons

Rebuilt from the journal and the ledger on every review. Only differences are written: a new
lesson or new numbers append a line; a lesson whose condition no longer holds is retired
(`"active": false`, shown as resolved on the dashboard). The text is rendered from `kind` +
`evidence` (English in `text`, Spanish on the dashboard when `display.language` is `es`).

| Kind | Condition (recent window, ≥5 scored) | What the agent does |
|---|---|---|
| `buy_blocked` | symbol hit rate < 50% (the gate above) | no automatic buys; tell the user |
| `low_accuracy` | hit rate < 50% for one bar size | don't trade on that forecast alone |
| `good_accuracy` | hit rate ≥ 60% and beat "no change" ≥ 50% | usable as one input, still confirm |
| `worse_than_naive` | "no change" closer in ≥ 60% | treat price targets as noise; skip |
| `narrow_band` | price outside p10–p90 in ≥ 40% | halve the size |
| `bullish_bias` | predicted up ≥ 80% but rose ≤ 50% | discount "up" calls |
| `losing_trades` | ≥2 closed trades, net loss, more losers | require `adds_value` + bullish indicators |
| `winning_trades` | ≥2 closed trades, net gain | keep the playbook; don't raise size |
| `unknown_orders` | a buy with status `unknown` | check positions before buying again |

Closed-trade P&L is estimated from the position's last valuation (`unrealizedPnL`) when
`etoro_trade.py close` ran, pro-rated for partial closes; eToro's realized figure may differ
slightly (spread, fill price).

## How the agent uses it

- Run `kronos_review.py` at the start of every analysis or scheduled run, before deciding.
- Read `track_record` and `lessons` in each forecast's output and apply them (playbook § 3).
- Tell the user what changed ("lesson_changes", new lessons) in plain words.
- Never edit or delete these files yourself; starting over is the user's call (delete
  `forecasts.jsonl` and `lessons.jsonl` under `$CLAWK_HOME/kronos/`).

## Dashboard panels (`dashboards/kronos.json`, contract version 1)

`summary` (account, trading on/off, buys and USD today vs caps, orders in flight, forecast hit
rate, closed P&L, active lessons), `goals`, `lessons` ("What it learned"), `bought`, `sold`,
`refused`, `accuracy_chart` (rolling hit rate, overall + busiest symbols), `accuracy_by_symbol`,
`forecasts` (recent, with hit/miss), `disclaimer`. Written atomically, at most 512 KiB, local
files only. The skill declares it in `metadata.clawk.dashboard`, so the web dashboard lists it
before the first snapshot exists.
