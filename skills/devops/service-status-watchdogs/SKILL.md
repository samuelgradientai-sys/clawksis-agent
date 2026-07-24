---
name: service-status-watchdogs
description: "Monitor public service-status pages and wire silent cron watchdogs that alert on recovery or degradation changes."
version: 1.0.0
author: Clawksis
tags: [cron, watchdog, monitoring, status-pages, alerts, service-health, public-json]
metadata:
  clawk:
    tags: [cron, watchdog, monitoring, status-pages, alerts, service-health, public-json]
---

# Service Status Watchdogs

Use this skill when the user wants to monitor a third-party service, a public status feed, or a machine-readable application signal and receive an alert only when the state changes.

## When to trigger

- The user asks to watch a vendor status page (Meta, OpenAI, Discord, Cloudflare, etc.).
- The user wants an automatic alert when a service comes back up or degrades.
- You need a durable cron job that stays silent while the service is still unhealthy.
- You need to discover whether a status page exposes a machine-readable JSON endpoint.

## Core pattern

1. Find the official status page or the machine-readable signal that represents the condition you care about.
2. Inspect the source, API, or table schema for a reliable structured endpoint.
3. Prefer JSON, SQL, or another structured feed over DOM scraping when available.
4. Normalize the relevant states, statuses, or labels.
5. Create a **silent** cron watchdog:
   - recurring schedule
   - `no_agent: true` when the script itself can decide the output
   - emit nothing when there is nothing to report
   - print a short human message only when the interesting condition is true
6. Verify the cron with `cronjob action=list`.

## Application data watchdogs

This skill also covers Supabase-backed monitors that audit conversation rows or function outputs.

Typical flow:

1. Filter tightly first (`user_id`, `conversation_id`, tenant key).
2. Pair inbound and outbound rows.
3. Compare the outbound response against the function’s expected role and the inbound prompt.
4. Classify findings as `ok`, `suspicious`, `incorrect`, or `needs_review`.
5. Emit only actionable evidence in the report.

For session notes and a reusable checklist, see `references/supabase-audit-watchdog.md`.

## Design rules

- Favor official vendor status pages over rumors or third-party summaries.
- Prefer machine-readable feeds (`.json`, RSS, API responses) over brittle HTML selectors.
- When a status page offers both page UI and JSON, read the JSON directly.
- Keep watchdogs quiet by default; avoid spam.
- If the alert condition is recovery, only print on transition back to healthy/operational.
- If the user wants both recovery and outage alerts, split them into two jobs or two branches in one job.

## Silent cron script pattern

A good watchdog script should:

- exit `0` and print nothing when the condition is not met
- print a concise report when the state changes
- exit non-zero only for real script failures (bad URL, parse failure, broken dependency)

Example shape:

```bash
#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json, sys, urllib.request

URL = 'https://example.com/status.json'
GOOD = {'Operational', 'No known issues', 'Resolved'}

with urllib.request.urlopen(URL, timeout=20) as resp:
    data = json.load(resp)

# inspect data...
if not should_alert(data):
    sys.exit(0)

print('✅ Service is healthy again')
PY
```

## Verification checklist

- Confirm the official status page exists.
- Confirm the JSON endpoint is stable and public.
- Confirm the script is silent when the condition is false.
- Confirm the script prints a useful message when the condition is true.
- Confirm the cron is listed and scheduled.

## Pitfalls

- Don’t scrape random mirrors when the official status page is available.
- Don’t make the watchdog chatty; silent is the default.
- Don’t alert on every run if the service is still degraded.
- Don’t couple the watchdog to a brittle HTML layout if a JSON feed exists.

## Related Clawksis tools

- `cronjob` — schedule and manage the watchdog
- `browser` — inspect status pages when needed
- `terminal` — quick probing of HTML/JSON endpoints
- `skills` — manage and update this skill family

## Reddit archive scraping (pullpush.io)

When monitoring requires gathering community sentiment, reviews, or hardware discussions from Reddit and Reddit directly blocks access (403), use the **pullpush.io** public archive.

### When to use

- User asks "what does Reddit say about X?" and direct Reddit access fails
- You need public historical Reddit data for research/product validation
- You want to correlate service outages with user-reported issues on Reddit

### Pattern

```python
from scrapling.fetchers import Fetcher
import json, urllib.parse

url = f"https://api.pullpush.io/reddit/search/submission/" \
      f"?subreddit=SUBREDDIT" \
      f"&q={urllib.parse.quote('query')}" \
      f"&sort=score&size=20"

page = Fetcher.get(url, stealthy_headers=True, timeout=15)

# CRITICAL: page.body (bytes), NOT page.text (empty parsed Selector)
data = json.loads(page.body)
posts = data.get('data', [])
```

For the full reference including comment extraction, rate limits, and known issues, see `references/reddit-pullpush-scraping.md`.

## Reference files

- `references/meta-status.md` — discovered Meta status JSON endpoints and the WhatsApp Business Platform check.
- `references/supabase-audit-watchdog.md` — reusable checklist for auditing Supabase message tables and function outputs.
- `references/billing-monitor.md` — no-agent cron + `.env` script pattern for billing/usage reports (OpenAI, DeepSeek, OpenRouter, etc.).
- `references/reddit-pullpush-scraping.md` — complete pattern for scraping Reddit via pullpush.io when Reddit blocks direct access.
