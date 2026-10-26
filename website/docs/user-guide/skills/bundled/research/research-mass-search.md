---
title: "Mass Search — Research many sources in parallel and merge them"
sidebar_label: "Mass Search"
description: "Research many sources in parallel and merge them"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Mass Search

Research many sources in parallel and merge them.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/research/mass-search` |
| Version | `1.0.0` |
| Author | Clawksis |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `búsqueda masiva`, `investigar`, `paralelo`, `pestañas`, `comparar`, `fuentes`, `deep research`, `many tabs` |
| Related skills | [`grounded-citations`](../../bundled/research/research-grounded-citations.md), [`last30days`](../../bundled/research/research-last30days.md), [`opportunity-research`](../../bundled/research/research-opportunity-research.md) |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Clawksis loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Mass Search Skill

Answers a broad question by splitting it into sub-questions, researching them **in parallel** —
many searches, many pages, several browser tabs or several subagents each with its own browser —
and merging everything into one report where every claim has numbered sources. It does not replace
a single quick lookup: for one fact, one `web_search` is enough.

## When to Use

- "Búsqueda masiva", "investigá a fondo", "compará 10 opciones", "buscá en muchas páginas".
- Market/product comparisons, due diligence on a company or stock, gathering prices or specs from
  many sites, "what do different sources say about X".
- The user wants to **watch** the agent work several pages at once (dashboard → Navegador →
  Mosaico shows every subagent's browser live).

## Prerequisites

- Native tools: `web_search`, `web_extract` (up to 5 URLs per call), `delegate_task`; for pages that
  need a real browser, `browser_navigate` / `browser_exec`.
- Parallel subagents: `delegation.max_concurrent_children` in `config.yaml` (default 10). Each
  browsing subagent starts its own Chromium (~300 MB RAM): on a 16 GB VPS keep it to ≤ 6 at once.

## How to Run

```
# after collecting findings as JSON Lines (one per line):
python skills/research/mass-search/scripts/merge_findings.py findings.jsonl > report.md
python skills/research/mass-search/scripts/merge_findings.py --json findings.jsonl
```

A finding: `{"question": "...", "claim": "...", "url": "https://...", "title": "...", "key": "optional"}`.
Give agreeing findings the same `key` so they merge into one claim.

## Quick Reference

| Need | Use |
|---|---|
| Many queries | several `web_search` calls in ONE turn (they run in parallel) |
| Read many static pages | `web_extract` with up to 5 `urls` per call, several calls per turn |
| JS-heavy / interactive sites | `delegate_task` — one task per sub-question, each browses on its own |
| Several tabs, one browser | `browser_exec`: `new_tab(url)` per page, then read each |
| Merge + cite | `scripts/merge_findings.py` → numbered sources, "confirmado" when 2+ sites agree |

## Procedure

1. **Plan.** Restate the goal; split it into 3–10 sub-questions. For each, write 1–3 concrete search
   queries (include the year, the market — e.g. "NVDA guidance Q3 2026", "precio iPhone 17 Colombia").
   Tell the user the plan in one short list.
2. **Fan out — pick the lightest tool that works.**
   - Text pages: issue all `web_search` calls together, then `web_extract` the best 3–5 results per
     sub-question in batches of 5.
   - Sites that need a browser, logins, or the user wants to watch: one `delegate_task` per
     sub-question (up to the concurrency limit). In each task's goal, ask the subagent to return
     findings as JSON Lines with `question`, `claim`, `url`, `title`, `key`.
   - A handful of pages in one browser: `browser_exec` with `new_tab(url)` for each — they show up
     as tabs in the dashboard's Navegador panel.
3. **Collect.** Append every finding (claim + exact URL it came from) to
   `~/clawksis_exports/<slug>/findings.jsonl` with `write_file`/`patch`. No URL, no finding.
4. **Merge.** Run `scripts/merge_findings.py` with `terminal`; read the report with `read_file`.
   Claims backed by one site only are flagged "una sola fuente" — verify the important ones with one
   more source or say they are unconfirmed.
5. **Deliver.** A short answer first (3–6 bullets), then the merged report and the sources list.
   Save it as `~/clawksis_exports/<slug>/report.md`; in the dashboard chat, link it. For a comparison,
   add a table.

## Pitfalls

- Opening a browser for a page `web_extract` can read wastes minutes and RAM — browse only when needed.
- Search results repeat the same press release across sites: count it once (`key`), don't call it
  "confirmed" by mirrors of one source.
- Paywalls and bot walls: note them and move on; don't retry the same blocked page in a loop.
- Prices and figures change: record the date you read them.
- More than ~10 parallel subagents rarely improves quality and multiplies cost.

## Verification

- Every claim in the final answer has at least one `[n]` that resolves to a URL in "Fuentes".
- The summary line from the merge script (claims / confirmed / sources) is reported to the user.
- Contradictions between sources are stated explicitly, not averaged away.
