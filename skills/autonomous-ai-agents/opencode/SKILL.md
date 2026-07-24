---
name: opencode
description: "External coding agents: delegate to OpenCode CLI (primary), Claude Code (Anthropic), or Codex (OpenAI) for features, PR review, and autonomous coding tasks."
version: 1.6.0
author: Clawksis
license: MIT
platforms: [linux, macos, windows]
metadata:
  clawk:
    tags: [Coding-Agent, OpenCode, Autonomous, Refactoring, Code-Review]
    related_skills: [claude-code, codex, clawksis-agent]
---

# OpenCode CLI

Use [OpenCode](https://opencode.ai) as an autonomous coding worker. OpenCode is a provider-agnostic, open-source AI coding agent with a TUI and CLI.

Clawksis supports **two integration methods**:

| Method | Tool | Best for |
|--------|------|----------|
| **`opencode_run` tool** | Built-in Clawksis tool | Bounded one-shot tasks (implement feature, fix bug, create project, write tests, generate static pages) |
| **terminal-based** | `terminal(pty=true)` + `process()` | Interactive/long-running TUI sessions needing multiple exchanges |

**Prefer `opencode_run` for most tasks** — it's simpler, handles timeouts, returns structured results, and doesn't need PTY setup. Fall back to terminal-based only for iterative sessions where back-and-forth is expected.

## When to Use

- User explicitly asks to use OpenCode
- You want an external coding agent to implement/refactor/review code
- You need long-running coding sessions with progress checks
- You want parallel task execution in isolated workdirs/worktrees

## Prerequisites

- OpenCode installed: `npm i -g opencode-ai@latest` or `brew install anomalyco/tap/opencode`
- Auth configured: `opencode providers login` or set provider env vars (OPENROUTER_API_KEY, etc.)
- Verify: `opencode providers list` should show at least one provider
- Git repository for code tasks (recommended)
- `pty=true` for interactive TUI sessions

### Provider Setup: Local Models via Ollama (Free, No Credits)

OpenCode can run entirely offline using **Ollama** local models — no API credits needed. This is ideal for testing, air-gapped environments, or when cloud credits are exhausted.

**Prerequisites:**
- Ollama installed and running (`ollama --version`; verify with `curl http://localhost:11434/api/tags`)
- A model that supports **tool/function calling** (required for OpenCode's agent mode). Models like `qwen2.5-coder`, `llama3.2`, and instruct-variant Mistral support tools. `phi3:3.8b` does NOT.

**Configuration — `~/.config/opencode/opencode.json`:**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama",
      "options": {
        "baseURL": "http://localhost:11434/v1"
      },
      "models": {
        "qwen2.5-coder:1.5b": {
          "name": "qwen2.5-coder:1.5b"
        }
      }
    }
  }
}
```

**Usage:** `opencode run "Write a simple function" --model "ollama/qwen2.5-coder:1.5b"`

**Notes:**
- Model name in `--model` must match the key in the `models` object
- `@ai-sdk/openai-compatible` is bundled with OpenCode — no separate npm install needed
- OpenCode requires tools support AND 64K+ context. Verify with `ollama show <model>` before using
- Local models on CPU: expect 30s–2min for a 1.5B model on a simple prompt; larger models scale proportionally slower
- Config goes in `~/.config/opencode/opencode.json` (OpenCode checks multiple paths; this one takes precedence)
- See `references/ollama-setup.md` for compatible model list, troubleshooting, and GPU acceleration

### Provider Setup: OpenRouter (Common Pattern)

OpenCode is provider-agnostic. The most common setup is via **OpenRouter** (no separate API key needed if you already have one):

```bash
# OpenCode auto-detects OPENROUTER_API_KEY from the environment
export OPENROUTER_API_KEY="sk-or-..."
```

⚠️ **OpenCode v1.17+ uses the NEW config format** at `~/.config/opencode/opencode.json`. The old flat format at `~/.opencode/config.json` is deprecated:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": "openrouter",
  "model": "anthropic/claude-sonnet-4-5",
  "base_url": "https://openrouter.ai/api/v1"
}
```

**Config precedence:** `~/.config/opencode/opencode.json` wins over `~/.opencode/config.json`. If OpenCode ignores your OpenRouter config and uses Ollama instead, delete or rename the old `~/.opencode/config.json`.

The auth JSON lives at `~/.local/share/opencode/auth.json` (manageable via `opencode providers list`).

For other providers, use `opencode providers login -p <provider> -m <method>` (interactive).

### Provider Setup: Direct OpenAI-Compatible API (DeepSeek, Together, etc.)

For providers with an OpenAI-compatible endpoint and an API key set as an env var:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "deepseek": {
      "name": "DeepSeek",
      "apiKey": "DEEPSEEK_API_KEY",
      "options": {
        "baseURL": "https://api.deepseek.com/v1"
      },
      "models": {
        "deepseek-v4-flash": {
          "name": "deepseek-v4-flash",
          "tool_call": true,
          "structured_output": true
        }
      }
    }
  }
}
```

The `apiKey` field references an env var name (not the literal key). Model keys under `models` define what `--model` argument to pass (format: `provider/model-key`).

**⚠️ Config format strictness:** Unrecognized top-level keys cause OpenCode to reject the entire file with `"Configuration is invalid"`. Do NOT add `base_url`, `systemPrompt`, or other flat keys at the top level — they belong inside the provider's `options` object.

## Using `opencode_run` (Built-in Tool)

The `opencode_run` tool delegates work to OpenCode and returns results directly. No PTY or process management needed.

### Basic Usage

```
opencode_run(prompt="Implement OAuth refresh flow and add tests", workdir="~/project")
opencode_run(prompt="Refactor auth module", workdir="~/project", model="openrouter/anthropic/claude-sonnet-4")
```

### Creating Static Projects (Landing Pages, Docs, etc.)

For static site generation (landing pages, docs, portfolios), give OpenCode a **detailed, self-contained prompt** with:

- Exact file structure (single `index.html` or separate files)
- Design spec: color palette (hex codes), visual direction ("dark mode, fintech vibes")
- Every section listed in order with content descriptions
- Responsiveness requirements (mobile-first, breakpoints)
- Animation and interaction specs (scroll reveal, counter animations)

Example pattern:

```python
opencode_run(
    prompt="""Crea un sitio estático... [spec detallada: secciones, paleta, animaciones, responsive]""",
    workdir="/root/project-landing",
    timeout=300  # generous for full-page generation
)
```

After creation, verify output:

```
terminal(command="wc -l /root/project-landing/index.html")
terminal(command="head -5 /root/project-landing/index.html")
```

See `references/static-site-pattern.md` for a reusable prompt template with exact palette and section structure.
See `references/openrouter-setup.md` for configuring OpenCode with an existing OpenRouter key (no separate Anthropic/OpenAI API keys needed).

### Key Parameters

| Parameter | Purpose |
|-----------|---------|
| `prompt` | Full, self-contained task description |
| `workdir` | Project directory (required for file output) |
| `model` | Optional model override |
| `timeout` | Max seconds before kill (default 600, max 3600) |
| `yolo` | Full autonomy (bypass permissions) — only in isolated envs |

---

## Other External Coding Agents

This skill primarily covers **OpenCode** (the recommended/default coding agent). Two other external coding CLIs are also available: **Claude Code** (Anthropic) and **Codex** (OpenAI). Their detailed usage is preserved in the references below.

### Claude Code (`references/claude-code.md`)

Anthropic's autonomous coding agent. Supports two orchestration modes:
- **Print mode** (`-p`): one-shot, non-interactive, preferred for automation
- **Interactive PTY via tmux**: multi-turn sessions needing dialog handling

Key differences from OpenCode:
- Requires `ANTHROPIC_API_KEY` or OAuth login
- Uses `claude -p 'prompt'` for print mode (vs `opencode run 'prompt'`)
- PTY dialog handling needed for workspace trust and permissions dialogs
- Structured JSON output with `--output-format json` including cost tracking

See `references/claude-code.md` for the full CLI reference, PTY dialog handling, session continuation, and bare mode for CI.

### Codex (`references/codex.md`)

OpenAI's autonomous coding agent. Key characteristics:
- Uses `codex exec 'prompt'` for one-shot tasks
- Requires `pty=true` in terminal calls
- **Must run inside a git repository** — Codex refuses to run outside one
- Supports `--full-auto` (sandboxed auto-approvals) and `--yolo` (bypass sandbox)
- Gateway sandbox caveat: `--sandbox danger-full-access` when bubblewrap fails
- Parallel worktree pattern for batch issue fixing

See `references/codex.md` for full CLI flags, PR review patterns, parallel issue fixing, and gateway caveats.

---

## Binary Resolution (Important)

Shell environments may resolve different OpenCode binaries. If behavior differs between your terminal and Clawksis, check:

```
terminal(command="which -a opencode")
terminal(command="opencode --version")
```

If needed, pin an explicit binary path:

```
terminal(command="$HOME/.opencode/bin/opencode run '...'", workdir="~/project", pty=true)
```

## One-Shot Tasks (Terminal Method)

Use `opencode run` for bounded, non-interactive tasks via terminal:

```
terminal(command="opencode run 'Add retry logic to API calls and update tests'", workdir="~/project")
```

Attach context files with `-f`:

```
terminal(command="opencode run 'Review this config for security issues' -f config.yaml -f .env.example", workdir="~/project")
```

## Interactive Sessions (Background)

For iterative work requiring multiple exchanges, start the TUI in background:

```
terminal(command="opencode", workdir="~/project", background=true, pty=true)
# Returns session_id

# Send a prompt
process(action="submit", session_id="<id>", data="Implement OAuth refresh flow and add tests")

# Monitor progress
process(action="poll", session_id="<id>")
process(action="log", session_id="<id>")

# Send follow-up input
process(action="submit", session_id="<id>", data="Now add error handling for token expiry")

# Exit cleanly — Ctrl+C
process(action="write", session_id="<id>", data="\x03")
# Or just kill the process
process(action="kill", session_id="<id>")
```

**Important:** Do NOT use `/exit` — it is not a valid OpenCode command and will open an agent selector dialog instead. Use Ctrl+C (`\x03`) or `process(action="kill")` to exit.

## Procedure

1. Choose method: `opencode_run` for bounded tasks, terminal-based for iterative work.
2. Verify tool readiness: `terminal(command="opencode --version")`
3. For static site generation, craft a detailed prompt with exact design specs (colors, sections, animations).
4. For bounded tasks via tool: call `opencode_run(prompt=..., workdir=...)` directly.
5. For iterative tasks via terminal: start `opencode` with `background=true, pty=true`.
6. Monitor with `process(action="poll"|"log")`.
7. Verify output exists and report file sizes, structure, and key outcomes.

## PR Review Workflow

OpenCode has a built-in PR command:

```
terminal(command="opencode pr 42", workdir="~/project", pty=true)
```

Or review in a temporary clone for isolation:

```
terminal(command="REVIEW=$(mktemp -d) && git clone https://github.com/user/repo.git $REVIEW && cd $REVIEW && opencode run 'Review this PR vs main. Report bugs, security risks, test gaps, and style issues.' -f $(git diff origin/main --name-only | head -20 | tr '\n' ' ')", pty=true)
```

## Parallel Work Pattern

Use separate workdirs/worktrees to avoid collisions:

```
terminal(command="opencode run 'Fix issue #101 and commit'", workdir="/tmp/issue-101", background=true, pty=true)
terminal(command="opencode run 'Add parser regression tests and commit'", workdir="/tmp/issue-102", background=true, pty=true)
process(action="list")
```

## Session & Cost Management

### Ad Monetization Wrapper (ad-opencode)

Monetize OpenCode's "thinking" time by showing sponsored ads in the terminal while the agent processes. Each 5 seconds of processing = 1 paid impression at ~$0.0035/impression (70% of $5 CPM).

**Trigger:** User asks about "kickbacks for OpenCode", "monetize coding agent", "generate revenue from thinking time", or wants to build an ad-based wrapper around OpenCode.

**How it works:**

1. The wrapper (`scripts/ad-opencode.py`) runs `opencode run` as a subprocess
2. While OpenCode processes, it prints a rotating sponsored line every 5 seconds
3. Each 5-second window = 1 impression, logged to ~/.ad-opencode/sessions.jsonl
4. Optionally pushes impressions to Supabase (if SUPABASE_SERVICE_ROLE_KEY is set)
5. At session end, displays summary: impressions, earnings, RPM

**Usage:**

```bash
# Install
sudo cp scripts/ad-opencode.py /usr/local/bin/ad-opencode
chmod +x /usr/local/bin/ad-opencode

# Run
ad-opencode "fix this security vulnerability"

# Customize
AD_MODEL="ollama/qwen2.5-coder:1.5b" ad-opencode "refactor this function"

# Custom ads
AD_OPTS='[{"text":"My Product — get it here","url":"https://example.com","brand":"MyProduct","cpm":5.00}]' ad-opencode "write tests"
```

**Economics:** See `references/ad-monetization.md` for full business model, scaling projections, competitor analysis ($0.0035/impression, ~$2.50/hr per dev, $168K/mo at 1,000 devs), and Supabase schema.

**Implementation notes:**
- Uses Ollama local models (free inference) — no API credits needed
- The wrapper counts wall-clock processing time, not token usage
- Longer processing = more impressions. Smaller/local models are slower = more impressions per prompt
- For distribution: wrap as pip package or npm. Revenue split 70/30 (dev/platform)
- Fraud detection: each impression requires real LLM inference on the device

**Pitfalls:**
- Local models on CPU are slow (30s-2min per prompt for 1.5B) — this is actually good for impressions but bad for UX
- OpenCode must be configured with Ollama provider (see Provider Setup: Local Models via Ollama above)
- Supabase table `ad_impressions` must exist for cloud logging (can log locally without it)
- The `opencode_run` built-in tool cannot be used with the wrapper — use terminal method
- Ad inventory needs real advertisers. Start with house ads, build demand
- Supabase table schema for `ad_impressions`: session_id TEXT, device_id TEXT, prompt TEXT, model TEXT, impressions INT, seconds INT, earnings DECIMAL, created_at TIMESTAMPTZ

---

List past sessions:

```
terminal(command="opencode session list")
```

Check token usage and costs:

```
terminal(command="opencode stats")
terminal(command="opencode stats --days 7 --models anthropic/claude-sonnet-4")
```

## Post-Build: Deployment Options

After OpenCode generates a static site (landing page, docs, portfolio), choose a deployment method based on what auth is available.

### Priority Order (Avoid Auth-Churn)

1. **Deliver the file directly** — If the user hasn't explicitly set up a hosting service, send the HTML file via `MEDIA:/path/to/index.html` and offer to set up permanent hosting later. This is instant and avoids frustration.
2. **Zero-Auth Preview** — Use cloudflared tunnel (trycloudflare.com, no account needed) for quick sharing during development (see below).
3. **Permanent hosting** — Only ask for a Cloudflare/GitHub/Vercel token after the user agrees to set up permanent deployment.

**Rule: Do NOT iterate through 5+ different auth flows.** One attempt at zero-auth, then offer the file. Multiple failed auth attempts in sequence frustrates the user.

### Zero-Auth Preview (No Account Needed)

Use cloudflared tunnel with trycloudflare.com -- no Cloudflare account or API token needed:

```bash
# Start a local HTTP server
cd /path/to/landing-page && python3 -m http.server 8080 &

# Expose via Cloudflare Tunnel (no auth)
cloudflared tunnel --url http://localhost:8080
# Output: https://random-words.trycloudflare.com  <- public URL
```

No account, no token, no setup. The tunnel is ephemeral -- URL lasts as long as the process lives. Perfect for sharing previews during development.

Install cloudflared: `curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared`

### Permanent Deployment Options

| Service | Auth Required | Pros | Setup |
|---------|--------------|------|-------|
| Cloudflare Pages | CLOUDFLARE_API_TOKEN or OAuth | Free, fast, custom domains, SSL | `npx wrangler pages deploy . --project-name <name>` |
| GitHub Pages | GitHub token or gh CLI | Free, version-controlled | Push to repo, enable Pages in settings |
| Vercel | vercel login | Instant deploy, auto-SSL | `npx vercel --prod` |
| Netlify | Netlify token | Drag-drop or CLI | `npx netlify deploy` |
| Surge.sh | Email/password | Dead simple CLI | `npx surge --domain project.surge.sh` |

## Pitfalls

- **⚠️ `opencode_run` usa el modelo por defecto, no el de la sesión.** Si no configuras `--model`, OpenCode usa su modelo por defecto. En servidores sin GPU esto suele ser `qwen2.5-coder:1.5b` vía Ollama — demasiado pequeño para tareas complejas. Siempre explícita el modelo:
  ```python
  opencode_run(prompt="...", model="openrouter/anthropic/claude-sonnet-4")
  ```
  O configura un modelo decente en `~/.opencode/config.json` antes de usarlo.

- **Local models on CPU are slow** — a 1.5B model takes 30s–2min per simple prompt. Don't set short timeouts. For real work, prefer cloud models via OpenRouter or add a GPU.
- Interactive `opencode` (TUI) sessions require `pty=true`. The `opencode run` command does NOT need pty.
- `/exit` is NOT a valid command -- it opens an agent selector. Use Ctrl+C to exit the TUI.
- PATH mismatch can select the wrong OpenCode binary/model config.
- If OpenCode appears stuck, inspect logs before killing: `process(action="log", session_id="<id>")`
- Avoid sharing one working directory across parallel OpenCode sessions.
- Enter may need to be pressed twice to submit in the TUI (once to finalize text, once to send).
- **`opencode_run` doesn't support passing custom env vars** — use terminal method if you need to set env vars before the run. Alternatively, configure the provider via config file (e.g. `~/.opencode/config.json`) so env vars aren't needed.
- When using OpenRouter, auth must be set via `~/.opencode/config.json` + `OPENROUTER_API_KEY` env var — there is no interactive login flow for OpenRouter.
- **Static site prompts must be MAXIMALLY SPECIFIC** -- include exact hex colors, section order, animation requirements, and file naming. OpenCode follows the spec literally; vagueness produces generic output.
- **When deployment auth fails repeatedly, pivot fast.** Deliver the artifact directly (HTML file via `MEDIA:`) or use zero-auth options (`cloudflared tunnel --url`). Multiple failed auth attempts in sequence frustrates the user.

## Verification

Smoke test:

```bash
terminal(command="opencode run 'Respond with exactly: OPENCODE_SMOKE_OK'")
```

Success criteria:
- Output includes `OPENCODE_SMOKE_OK`
- Command exits without provider/model errors
- For code tasks: expected files changed and tests pass
- For static sites: file exists with expected size, basic structure check passes

## Rules

1. Prefer `opencode_run` for one-shot automation — it's simpler and doesn't need pty.
2. Use interactive background mode only when iteration is needed.
3. Always scope OpenCode sessions to a single repo/workdir.
4. For long tasks, provide progress updates from `process` logs.
5. Report concrete outcomes (files created/modified, test results, remaining risks).
6. Exit interactive sessions with Ctrl+C or kill, never `/exit`.
7. For static page generation, always verify output exists and report file stats.
