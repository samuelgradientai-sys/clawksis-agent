---
name: mcp-server-auth
description: "Authenticate MCP servers that use browser-based sessions (cookies, OAuth, interactive login) on headless/remote environments."
version: 1.0.0
author: Clawksis
metadata:
  clawk:
    tags: [mcp, auth, browser, cookies, vnc, cloudflare-tunnel]
    related_skills: [clawksis-provider-management, clawksis-dashboard]
---

# MCP Server Browser-Based Authentication

Many MCP servers (LinkedIn, Instagram, etc.) use browser-based session auth instead of API keys. These require special handling on headless/remote servers.

## Two Authentication Strategies

| Strategy | When to use | Effort |
|----------|------------|--------|
| **Cookie injection** | You have a valid `li_at`-style cookie from the user's real browser | Medium |
| **Interactive login bridge** | No cookie available; user needs to log in visually | High (needs VNC) |

---

## Strategy A: Cookie Injection (Direct)

### The 3-File Requirement

MCP servers using browser sessions typically check THREE files:

| File | Path (default) | Purpose |
|------|---------------|---------|
| **Browser profile** | `~/.linkedin-mcp/profile/` | Persistent Chromium profile (Cookies DB, Local Storage) |
| **Portable cookies** | `~/.linkedin-mcp/cookies.json` | JSON array of session cookies for cross-runtime bridge |
| **Source state** | `~/.linkedin-mcp/source-state.json` | Metadata linking cookies to a "source runtime" generation |

All three must exist and be valid. Missing source-state.json is the most common silent failure.

### The Bridge Trick (Force Cookie Import)

Some MCP servers (e.g. LinkedIn) check if `current_runtime_id == source_state.source_runtime_id`. When they match, the server skips importing cookies from `cookies.json` and just launches the browser directly — expecting the profile's Cookies DB to already have valid session cookies. This often fails because the MCP's modded browser (e.g. Patchright) may not read the same cookie format as regular Playwright.

**Fix:** Set `source_runtime_id` to a value that DIFFERS from the current runtime, forcing the "foreign runtime" bridge path that calls `import_cookies()`:

```json
{
  "version": 1,
  "source_runtime_id": "macos-arm64-host",     // anything ≠ current runtime
  "login_generation": "manual-injection",
  "created_at": "2026-06-16T17:55:00Z",
  "profile_path": "/root/.linkedin-mcp/profile",
  "cookies_path": "/root/.linkedin-mcp/cookies.json"
}
```

### Cookie Bootstrap with Regular Playwright

When the MCP's own browser (e.g. Patchright) fails to recognize the cookie but the cookie is definitely valid:

1. Create a clean profile dir
2. Use regular Playwright (`playwright` package, NOT `patchright`) to:
   - Launch a persistent context with the clean profile
   - Inject the cookie via `context.add_cookies()`
   - Navigate to the service's main page to establish the session
   - Save `storage_state` for later reuse
3. Then launch the MCP server with `--user-data-dir` pointing to this profile

```python
# skeleton — see references/linkedin-mcp-cookie-injection.md for full script
browser = await p.chromium.launch_persistent_context(profile_dir, headless=True)
await browser.add_cookies([{"name": "li_at", "value": "...", "domain": ".www.linkedin.com", ...}])
page = await browser.new_page()
await page.goto("https://www.linkedin.com/feed/")
# verify logged in
await browser.storage_state(path=state_path)
```

### Recovering from "Chromium didn't shut down correctly"

The "Restore pages" dialog blocks the login UI. Fix in `Preferences`:

```python
data["profile"]["exit_type"] = "Normal"
data["session"]["restore_on_startup"] = 1
```

Also delete `Default/Current Session`, `Default/Current Tabs`, `Default/Last Session`, `Default/Last Tabs`.

---

## Strategy B: Interactive Login Bridge (VNC)

When no valid cookie exists and the user must log in visually on a headless VPS.

### Stack

```
App (Chromium via Patchright/Playwright)
  → Xvfb (virtual display :99)
    → x11vnc (VNC server, port 5900)
      → websockify / noVNC (WebSocket → VNC bridge, port 6080)
        → cloudflared tunnel (public URL)
          → User's browser
```

### Setup Steps

```bash
# 1. Ensure Xvfb is running
Xvfb :99 -screen 0 1920x1080x24 &

# 2. Start x11vnc
x11vnc -display :99 -forever -nopw -bg

# 3. Start noVNC websockify
cd /usr/share/novnc
python3 -m websockify --web /usr/share/novnc 6080 localhost:5900

# 4. Create cloudflared tunnel
cloudflared tunnel --url http://localhost:6080
# → Prints: https://<random>.trycloudflare.com

# 5. Start the MCP with --login --no-headless
uvx mcp-server-linkedin@latest --no-headless --user-data-dir /path/to/profile --login

# 6. Give URL to user, they log in
```

### Cleanup

```bash
pkill -f cloudflared
pkill -f websockify
pkill x11vnc
```

### Pitfalls

- **"Chromium didn't shut down correctly" dialog**: Fix Preferences before starting the MCP.
- **x11vnc needs DISPLAY set**: Match the Xvfb display number.
- **noVNC websockify must start AFTER x11vnc** or it fails to connect.
- **Some MCPs detect Docker/container environments** and refuse interactive login. Not all MCPs support `--no-headless` in containers.
- **Cookies from injected sessions expire** — LinkedIn `li_at` cookies may only last hours when used from a different IP.
- **Cannot use terminal(background=true) with nohup** for servers/daemons. Use the tool's `background=true` parameter instead.

### LinkedIn MCP-Specific Notes

The `mcp-server-linkedin` CLI (v4.15.0) key flags:

| Flag | Purpose |
|------|---------|
| `--login` | Open browser for interactive login, saves profile on success |
| `--status` | Check if current session is valid, shows runtime info |
| `--logout` | Clear all stored auth state |
| `--user-data-dir PATH` | Custom profile path (default: `~/.linkedin-mcp/profile`) |
| `--no-headless` | Show browser window (needs DISPLAY/Xvfb) |
| `--log-level {DEBUG,INFO,WARNING,ERROR}` | Control verbosity |
| `--timeout MS` | Browser page timeout (default: 5000ms) |
| `--tool-timeout SECONDS` | Per-tool execution timeout (default: 180) |

#### Auth Minimal Cookie Preset

The MCP imports only a subset of cookies from `cookies.json`. The `auth_minimal` preset requires these exact cookie names:

```
li_at, JSESSIONID, bcookie, bscookie, lidc
```

If `cookies.json` is missing any of these names (especially `li_at`), the import silently skips. All five must be present for the session to be valid.

#### Diagnostic Flow

1. Run `--status` to check session validity
2. Check output for:
   - `Current runtime: <id>` — the detected runtime ID (e.g. `linux-amd64-container`)
   - `Source runtime: <id>` — the runtime ID in source-state.json
   - `Profile mode: source` → same runtime, skips cookie import (likely to fail with injected cookies)
   - `Profile mode: foreign runtime (fresh bridge each startup)` → different runtime, imports cookies.json
   - `Profile mode: derived` → cached runtime profile, skips fresh bridge
3. If session is invalid, check that all three files exist (profile, cookies.json, source-state.json)
4. Verify li_at in cookies.json with: `python3 -c "import json; c=json.load(open('cookies.json')); print(any(x['name']=='li_at' for x in c))"`
5. If cookie is expired, use VNC interactive login or get fresh cookie from user

#### "No valid LinkedIn session is available in Docker" Error

The MCP detects container runtimes (`linux-amd64-container`) and may refuse to start. This happens when the MCP's modded browser (Patchright) doesn't recognize cookies that regular Playwright accepts. Workaround: bootstrap with regular Playwright first, then use the bridge trick (different source_runtime_id) to force cookie import.

---

## Common Pitfalls

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| "No valid session" despite cookies | Missing source-state.json | Create it with bridge trick |
| "Session expired" error | Cookie expired | Get fresh cookie from user or re-login |
| "Chromium didn't shut down" | Previous crash in profile | Fix Preferences file or recreate profile |
| HTTP response code failure | LinkedIn detecting Patchright | Use regular Playwright for bootstrapping |
| No VNC output in browser | websockify not connected to x11vnc | Check x11vnc port, restart stack |
| OAuth/MCP hangs with no output | No TTY, stdin closed | Use foreground with PTY or redirect streams |

## References

- `references/linkedin-mcp-cookie-bootstrap.md` — Full Playwright bootstrap script for LinkedIn
- `clawksis-dashboard` skill — Cloudflare tunnel basics
