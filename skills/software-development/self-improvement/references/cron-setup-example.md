# Cron setup example — Samuel Gómez

## Context

Samuel runs Clawksis v0.16.0 on a headless Linux VPS. He wanted a cron that:
1. Runs daily at midnight (00:00 UTC / 7pm Colombia)
2. Scans skills, tools, MCPs for improvement opportunities
3. Implements fixes using coding agents (opencode_run / claude_code / codex_exec)
4. Deploys to main (`git push origin main`)
5. Runs `clawk update`
6. Reports back to Telegram chat

## The cron job definition

```json
{
  "job_id": "6ab0e6cb83d5",
  "name": "Auto-mejora: skills & tools",
  "schedule": "0 0 * * *",
  "repeat": "forever",
  "deliver": "origin",
  "enabled_toolsets": ["terminal", "file", "search", "web", "delegation", "coding"],
  "use_soul": true,
  "use_user_md": true,
  "use_memory": false,
  "skills": ["scrapegraphai", "scrapling-official"]
}
```

## Key decisions

### Toolsets enabled
Only what's needed: `terminal`, `file`, `search` (for reading code), `web` (for research), `delegation` (for coding agents), `coding` (opencode_run/claude_code). No browser, no cronjob (can't recursively schedule), no messaging tools.

### Skills loaded
`scrapegraphai` and `scrapling-official` — the user's most-used tools. The cron starts by checking if these need improvement before exploring others.

### Git credentials
The server has a GitHub classic token stored in `~/.git-credentials` via `credential.helper store` so pushes work without interaction.

## Self-improvement cron job creation via the cronjob tool

The agent created this cron with:

```python
cronjob(
    action="create",
    name="Auto-mejora: skills & tools",
    schedule="0 0 * * *",
    prompt="[full 5-phase mission prompt]",
    enabled_toolsets=["terminal", "file", "search", "web", "delegation", "coding"],
    use_soul=True,
    use_user_md=True,
    use_memory=False,
    skills=["scrapegraphai", "scrapling-official"],
)
```

## What the cron should NOT do in this setup

- ❌ Touch credentials or config files
- ❌ Delete anything
- ❌ Make architectural changes
- ❌ Add new features
- ❌ Touch other users' profiles or skills
- ❌ Recursively schedule more cron jobs
