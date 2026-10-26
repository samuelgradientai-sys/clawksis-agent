# Security & Privacy Toggles

Common "why is Clawksis doing X to my output / tool calls / commands?" toggles — and the exact commands to change them. Most of these need a fresh session (`/reset` in chat, or start a new `clawk` invocation) because they're read once at startup.

### Secret redaction in tool output

Secret redaction is **on by default** — tool output (terminal stdout, `read_file`, web content, subagent summaries, etc.) is scanned for strings that look like API keys, tokens, and secrets before it enters the conversation context and logs. Leave it enabled for normal use:

```bash
clawk config set security.redact_secrets true       # keep enabled globally
```

**Restart required.** `security.redact_secrets` is snapshotted at import time — toggling it mid-session (e.g. via `export CLAWK_REDACT_SECRETS=false` from a tool call) will NOT take effect for the running process. Tell the user to change it in config from a terminal, then start a new session. This is deliberate — it prevents an LLM from flipping the toggle on itself mid-task.

Disable only when you deliberately need raw credential-like strings for debugging or redactor development:
```bash
clawk config set security.redact_secrets false
```

### PII redaction in gateway messages

Separate from secret redaction. When enabled, the gateway hashes user IDs and strips phone numbers from the session context before it reaches the model:

```bash
clawk config set privacy.redact_pii true    # enable
clawk config set privacy.redact_pii false   # disable (default)
```

### Command approval prompts

By default (`approvals.mode: smart`), Clawksis asks an auxiliary LLM to assess shell commands flagged as destructive (`rm -rf`, `git reset --hard`, etc.). The modes are:

- `smart` — auto-approve a low-risk command once, deny high-risk commands, and prompt when uncertain (default)
- `manual` — always prompt
- `off` — skip all approval prompts (equivalent to `--yolo`)

```bash
clawk config set approvals.mode smart       # recommended middle ground
clawk config set approvals.mode off         # bypass everything (not recommended)
```

Per-invocation bypass without changing config:
- `clawk --yolo …`
- `export CLAWK_YOLO_MODE=1`

Note: YOLO / `approvals.mode: off` does NOT turn off secret redaction. They are independent.

### "Full access" / "no restrictions" / "let it change its own settings"

One switch covers it:

```bash
clawk config permissions          # show the current state
clawk config permissions full     # no approval prompts (cron/unattended too), may edit SOUL.md/AGENTS.md,
                                  # schedule from cron, terminal on this machine
clawk config permissions default  # back to the safe defaults
```

`full` asks for confirmation on a terminal (`--yes` skips it). Run it only when the user explicitly
asks for full access, and tell them the trade-off: anyone who can message the agent then controls the
machine, so platform allowlists and the dashboard login matter. With or without it, the agent changes
its own settings with `clawk config set <key> <value>` (never by editing config.yaml directly — that
write is refused). The hardline floor (wiping / or /home, formatting disks, shutting down) always stays.

### "Reset permissions" / "make Clawksis ask again"

The user usually means: wipe the accumulated "Always allow" state — NOT yolo
mode, and NOT a per-edit diff prompt (which doesn't exist; file writes never
go through the approval prompt, only shell commands do). Two stores hold it:

1. Shell-command allowlist: `clawk config set command_allowlist '[]'`
2. Shell-hook consent (only if present): `rm -f ~/.clawksis/shell-hooks-allowlist.json`

Then sanity-check `clawk config get approvals.mode` (should not be `off`)
and confirm `--yolo` isn't baked into their launch alias or systemd unit.

### Shell hooks allowlist

Some shell-hook integrations require explicit allowlisting before they fire. Managed via `~/.clawksis/shell-hooks-allowlist.json` — prompted interactively the first time a hook wants to run.

### Disabling the web/browser/image-gen tools

To keep the model away from network or media tools entirely, open `clawk tools` and toggle per-platform. Takes effect on next session (`/reset`). See `references/configuration.md` for the toolset list.

