# Langfuse Observability Plugin

This plugin ships bundled with Clawksis but is **opt-in** — it only loads when
you explicitly enable it.

## Enable

Pick one:

```bash
# Interactive: walks you through credentials + SDK install + enable
clawk tools  # → Langfuse Observability

# Manual
pip install langfuse
clawk plugins enable observability/langfuse
```

## Required credentials

Set these in `~/.clawksis/.env` (or via `clawk tools`):

```bash
CLAWK_LANGFUSE_PUBLIC_KEY=pk-lf-...
CLAWK_LANGFUSE_SECRET_KEY=sk-lf-...
CLAWK_LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or your self-hosted URL
```

Without the SDK or credentials the hooks no-op silently — the plugin fails
open.

## Verify

```bash
clawk plugins list                 # observability/langfuse should show "enabled"
clawk chat -q "hello"              # then check Langfuse for a "Clawksis turn" trace
```

## Optional tuning

```bash
CLAWK_LANGFUSE_ENV=production       # environment tag
CLAWK_LANGFUSE_RELEASE=v1.0.0       # release tag
CLAWK_LANGFUSE_SAMPLE_RATE=0.5      # sample 50% of traces
CLAWK_LANGFUSE_MAX_CHARS=12000      # max chars per field (default: 12000)
CLAWK_LANGFUSE_DEBUG=true           # verbose plugin logging
```

## Disable

```bash
clawk plugins disable observability/langfuse
```
