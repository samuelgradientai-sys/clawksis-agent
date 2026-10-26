---
sidebar_position: 4
title: "Skill Dashboards"
description: "Give a skill its own mini dashboard in the web UI with a JSON snapshot"
---

# Skill Dashboards

A skill can have its own page in the web dashboard: the Kronos skill, for example, shows what it
bought, what it sold and what it learned. The page appears under **Plugins → Skills** in the
sidebar and as a **Dashboard** button on the skill's row.

The web server never runs skill code to build the page. The skill writes a JSON **snapshot** under
its profile's home whenever its state changes, and the dashboard renders it. That keeps a hub skill
as trusted as it was before: the snapshot is data, clipped to the shape below before it reaches the
browser.

## 1. Declare it

Add `metadata.clawk.dashboard` to the SKILL.md frontmatter. The page is listed as soon as the skill
is installed, with an empty state until the first snapshot exists.

```yaml
metadata:
  clawk:
    dashboard:
      title: Kronos
      description: Trades, forecasts and what it learned.
```

`dashboard: true` also works (the skill name is used as the title).

## 2. Write the snapshot

Path: `$CLAWK_HOME/dashboards/<skill-name>.json` (`CLAWK_HOME` is set for every terminal command the
agent runs, so a script under `scripts/` can read it). Write atomically — a temporary file in the
same directory, then `os.replace` — and keep it under 512 KiB.

```json
{
  "version": 1,
  "title": "Kronos",
  "subtitle": "eToro demo · max $100/order",
  "updated_at": "2026-10-26T14:03:00Z",
  "panels": [
    {"type": "stats", "title": "Today", "items": [
      {"label": "Orders", "value": 2, "hint": "of 5 allowed"},
      {"label": "Hit rate", "value": "62%", "tone": "positive"}
    ]},
    {"type": "table", "title": "Bought", "width": "half",
     "columns": [{"key": "symbol", "label": "Symbol"},
                 {"key": "usd", "label": "Amount", "format": "money", "align": "right"}],
     "rows": [{"symbol": "NVDA", "usd": 100, "_tone": "positive"}]},
    {"type": "chart", "title": "Forecast accuracy", "kind": "line",
     "series": [{"name": "Hit rate", "points": [["2026-10-25", 58], ["2026-10-26", 62]]}]},
    {"type": "list", "title": "What it learned", "items": [
      {"title": "TSLA: direction right 2/7", "body": "Don't trade it on the forecast alone.", "tone": "warning"}
    ]}
  ]
}
```

| Panel | Fields | Limits |
|---|---|---|
| every panel | `type`, `title`, optional `id`, `description`, `width` (`full` or `half`) | 24 panels |
| `stats` | `items: [{label, value, hint?, tone?}]` | 12 items |
| `table` | `columns: [{key, label, align?, format?}]`, `rows: [{…, _tone?}]`, `empty?` | 12 columns, 200 rows |
| `list` | `items: [{title, body?, meta?, tone?}]`, `empty?` | 100 items |
| `chart` | `kind` (`line` or `bar`), `x_label?`, `y_label?`, `series: [{name, points: [[x, y]]}]` | 4 series × 500 points |
| `text` | `body` (plain text) | 4,000 characters |

- `tone`: `positive`, `negative`, `warning` or `neutral`; the UI pairs it with an icon, never color alone.
- `format`: `text`, `number`, `money` (USD), `percent` (already in percent units: `12.5` → `12.5%`) or `datetime` (ISO string).
- Chart `x` is an ISO date string or a number; `y` is a number.
- Unknown fields are dropped, strings are truncated, and an unknown panel type renders as
  "needs a newer dashboard". A snapshot with another `version`, invalid JSON or no `panels` list
  shows its error on the page instead of the panels.

## 3. Refresh it

Rewrite the snapshot at the end of every command that changes what the page shows (Kronos does it
after each order, forecast and review). The page refreshes every 30 seconds while it is open.

The API behind the page is `GET /api/skills/dashboards` (the list) and
`GET /api/skills/dashboards/{name}` (one snapshot), both under the dashboard session token and the
usual `?profile=` scope: each profile reads its own snapshot.
