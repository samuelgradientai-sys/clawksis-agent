# Billing Monitor (no-agent cron + .env script)

A reusable pattern for creating cron jobs that report billing/credit usage from LLM provider APIs. Uses a **no-agent** cron with a standalone bash script that reads API keys from `~/.clawksis/.env` and queries provider endpoints.

## When to use

- The user asks for recurring billing/usage summaries.
- You need to poll provider APIs that aren't accessible through a browser session.
- You want a lightweight cron that runs without consuming LLM tokens every tick.

## Pattern

```
cronjob(
  action='create',
  schedule='0 10 */3 * *',      # every 3 days at 10am
  script='billing-report.sh',     # resolves under ~/.clawksis/scripts/
  no_agent=True,                  # script IS the job, no LLM involved
  deliver='telegram',             # output goes to the user's channel
  schedule='0 10 */3 * *',
)
```

## Script structure

```bash
#!/bin/bash
ENV_FILE="$HOME/.clawksis/.env"

# Load keys from .env (never hardcode credentials)
if [ -f "$ENV_FILE" ]; then
  export $(grep -E '^(PROVIDER_API_KEY|ANOTHER_KEY)=' "$ENV_FILE" | xargs)
fi

echo "=== REPORT - $(date '+%Y-%m-%d') ==="

# Provider 1
if [ -n "$PROVIDER_API_KEY" ]; then
  curl -s "https://api.provider.com/v1/billing" \
    -H "Authorization: Bearer $PROVIDER_API_KEY"
fi
```

The script lives at `~/.clawksis/scripts/<name>.sh` and must be executable.

## Known provider billing endpoints

| Provider | Endpoint | Notes |
|----------|----------|-------|
| OpenAI | `/v1/usage?date=YYYY-MM-DD` | Usage API key: shows cost per day |
| | `/v1/dashboard/billing/subscription` | **Session key only** (browser) |
| OpenAI (DALL-E, TTS) | `/v1/usage` with `dalle_api_data` | Returns empty if no usage that day |
| DeepSeek | `/user/balance` | Returns `balance_infos` with `total_balance`, `topped_up_balance`, `granted_balance` |
| OpenRouter | `/api/v1/auth/key` | Returns `usage` (total), `limit`, `is_free_tier`, `expires_at` |

## Pitfalls

- **OpenAI billing dashboard** requires a session key (browser login) — API keys return 403. Use the `/v1/usage` endpoint instead for per-day costs.
- **Authenticator codes expire every 30 seconds** — when logging into LinkedIn or any service, ask the user for a code only when you're ready to type + submit immediately.
- **Keys in `.env` are NOT exported to the process environment by default** — the script must grep and export them explicitly.
- **`clawk config set openai_api_key <key>`** stores a key in `.env`; the tool `image_gen.provider` needs to be set separately.
