---
name: billing-monitoring
description: "Monitor API provider balances and usage across DeepSeek, OpenAI, and OpenRouter. Set up daily billing reports delivered to Telegram via Clawksis cron. Covers the script+agent pattern, provider-specific billing APIs, known limitations (e.g. OpenAI project keys can't access org billing), and report formatting."
version: 1.0.0
author: Clawksis
tags: [billing, monitoring, deepseek, openai, openrouter, cron, costs, devops, telegram]
related_skills: [news-briefing-cron, clawksis-agent, service-status-watchdogs]
---

# Billing Monitoring

## Overview

Track API provider spending across DeepSeek, OpenAI, and OpenRouter with a daily cron report delivered to Telegram.

## Architecture

```
Daily Cron (0 10 * * *)
    │
    ├── Script: billing-report.sh  ← fetches all provider balances
    │       │
    │       ├── DeepSeek:   GET /user/balance    (Bearer token)
    │       ├── OpenAI:     GET /v1/usage         (Bearer token)
    │       ├── OpenAI:     GET /v1/me             (account info)
    │       └── OpenRouter: GET /api/v1/auth/key    (Bearer token)
    │       │   Script cost: $0
    │       ▼
    └── Agent: no_agent=true (script stdout IS the report, delivered verbatim)
```

## Cron Configuration

```python
cronjob(
    action="create",       # or "update" for existing job
    name="Reporte de billing diario",
    schedule="0 10 * * *", # daily at 10:00 UTC
    script="billing-report.sh",
    no_agent=True,         # script output delivered verbatim
    deliver="origin",      # to connected Telegram channel
    profile="default"
)
```

## Script: billing-report.sh

Located at `~/.clawksis/scripts/billing-report.sh`.

### What it queries

| Provider | Endpoint | Auth | Data returned |
|---|---|---|---|
| **DeepSeek** | `https://api.deepseek.com/user/balance` | Bearer `$DEEPSEEK_API_KEY` | `total_balance`, `topped_up_balance`, `granted_balance` |
| **OpenAI** | `https://api.openai.com/v1/usage?date=YYYY-MM-DD` | Bearer `$OPENAI_API_KEY` | Daily cost records (limited for project keys) |
| **OpenAI** | `https://api.openai.com/v1/me` | Bearer `$OPENAI_API_KEY` | Account email (to confirm which account) |
| **OpenRouter** | `https://openrouter.ai/api/v1/auth/key` | Bearer `$OPENROUTER_API_KEY` | Usage total, limit, expiration, free tier status |

### Output format

```
📊 BILLING REPORT — 2026-07-12 16:33 UTC

🤖 DEEPSEEK
  Balance: $18.65
  Topped up: $18.65
  Granted: $0.00

🟢 OPENAI
  Key: Project API Key
  Account: samuelgomez2466@gmail.com
  Usage this month: $0.0000 USD
  Records: 0

🔮 OPENROUTER
  Usage: $5.00
  Limit: Unlimited
  Free tier: False
  Expires: Never

=== END REPORT ===
```

## Provider-Specific Details

### DeepSeek
- **Endpoint:** `GET https://api.deepseek.com/user/balance`
- **Auth:** `Authorization: Bearer $DEEPSEEK_API_KEY`
- **Response:** `{"balance_infos": [{"total_balance": "18.65", "topped_up_balance": "18.65", "granted_balance": "0.00"}]}`
- **Granularity:** Total balance across all top-ups
- **Reset:** Key from `.env` via `DEEPSEEK_API_KEY`

### OpenAI — Known Limitation ⚠️

**Project API Keys (sk-proj-...) CANNOT access org-level billing data.**

The `/v1/usage` endpoint works but returns 0 records for project keys. Key type detection:

| Key prefix | Type | `/v1/usage` | Org endpoints |
|---|---|---|---|
| `sk-proj-...` | Project API Key | ✅ Works (returns $0) | ❌ 403 Forbidden |
| `sk-org-...` | Organization Key | ✅ Full data | ✅ Full access |
| `sk-...` (legacy) | Legacy Key | ✅ May work | ⚠️ Depends |

**Tested endpoints that DON'T work with project keys:**
- `GET /v1/dashboard/billing/usage` → 403 (needs browser session)
- `GET /v1/dashboard/billing/subscription` → 403 (needs browser session)
- `GET /v1/dashboard/billing/credit_grants` → 403 (needs browser session)
- `GET /v1/organizations` → 403 (Forbidden)
- `GET /v1/organization/usage` → 404 (Not Found)
- `GET /v1/costs` → 404 (Not Found)
- `GET /v1/completions/usage` → 404 (Not Found)

**What DOES work with project keys:**
- `GET /v1/me` → Returns account email, MFA status, PAYG info ✅
- `GET /v1/models` → Lists accessible models ✅
- `GET /v1/usage?date=YYYY-MM-DD` → Returns data structure (may be empty) ✅

**To get real OpenAI billing data, you need:**
1. An **Organization API Key** (sk-org-...) instead of a Project key, OR
2. A **browser session key** (from dashboard.openai.com), OR
3. Check manually at https://platform.openai.com/usage

### OpenRouter
- **Endpoint:** `GET https://openrouter.ai/api/v1/auth/key`
- **Auth:** `Authorization: Bearer $OPENROUTER_API_KEY`
- **Response:** `{"data": {"usage": 4.999, "limit": null, "is_free_tier": false, "expires_at": null}}`
- `limit: null` = Unlimited
- No billing endpoint needed — the key info includes cumulative usage

## Recent Changes

| Date | Change |
|---|---|
| 2026-07-15 | Added combined monthly projection + cross-provider budgeting section |
| 2026-07-15 | Added `scripts/daily-spend-tracker.py` for automated snapshot tracking |
| 2026-07-12 | Changed from every 3 days to **daily** at 10 UTC |
| 2026-07-12 | Added OpenAI key type detection and account email |
| 2026-07-12 | Added emoji formatting to output |
| 2026-07-12 | Discovered OpenAI project key billing limitation |

## Combined Budgeting & Monthly Projections

When the user asks about total spend across providers, calculate:

1. **Daily spend** per provider from balance deltas
2. **Combined daily total** = DeepSeek daily + OpenAI daily
3. **Monthly projection** = combined daily total × 30
4. **Top-up recommendation**:
   - If monthly < $25 → recommend **$20 every 2 months** per provider
   - If monthly $25-50 → recommend **$20-30 every month** per provider
   - If monthly > $50 → recommend **$50 every month**

### Example output format

```
📊 BILLING PROJECTION — Jul 13-14

🤖 DEEPSEEK          🟢 OPENAI
   Daily: $0.48         Daily: $0.36
   Month: ~$14.40       Month: ~$10.80

💵 Combined monthly: ~$25.20
🪙 Rec: $20 c/2 meses (DeepSeek) + $20 c/2 meses (OpenAI)
```

### Daily spend tracker script

A companion script lives at `scripts/daily-spend-tracker.py`. It records balance snapshots into `~/.clawksis/data/billing-history.json` and computes daily averages and monthly projections.

```bash
python3 scripts/daily-spend-tracker.py              # Show current + projection
python3 scripts/daily-spend-tracker.py --record     # Record today's snapshot
python3 scripts/daily-spend-tracker.py --history    # Show all snapshots
python3 scripts/daily-spend-tracker.py --project    # Projection only
```

### Cross-provider budgeting notes

- **DeepSeek** = prepaid balance (recargar cuando baje de $3)
- **OpenAI** = PAYG (postpaid, llega en factura) — pero la usuaria la trata como prepago porque consume créditos para vision
- **OpenRouter** = PAYG, cumulative usage, only bill once it's significant
- Para la proyección, sumar gasto diario de DeepSeek + OpenAI ignorando OpenRouter si es < $10

## Pitfalls

1. **OpenAI always shows $0** — If using a Project API Key (sk-proj-...), `/v1/usage` returns 0 records. This is a key-scope limitation, not a bug. The account email still confirms the right account is connected.
2. **Billing cron frequency changes** — Use `cronjob update` with the new schedule. The no_agent script pattern means no prompt changes needed.
3. **Script env vars** — Cron scripts read `.env` directly (`export $(grep ...)`) — they do NOT inherit Clawksis's process environment. If you add a new provider, add its key to the export line.
4. **Emoji rendering** — Telegram supports emojis in verbatim script output. Test new emojis before committing.
5. **OpenRouter usage is cumulative, not monthly** — The `/api/v1/auth/key` endpoint returns total lifetime usage, not monthly. To track monthly spend, record the value on the 1st of each month and subtract.
