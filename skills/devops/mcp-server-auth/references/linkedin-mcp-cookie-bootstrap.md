# LinkedIn MCP Cookie Bootstrap

Full Playwright script to set up a LinkedIn session from a `li_at` cookie.

## Prerequisites

- `playwright` Python package: `uv pip install playwright && playwright install chromium`
- A valid `li_at` cookie from the user's browser
- `uvx` for the MCP server

## Bootstrap Script

Save as `bootstrap_linkedin.py`:

```python
#!/usr/bin/env python3
"""Inject li_at cookie into a fresh profile and verify session."""
import asyncio
import json
import os
from playwright.async_api import async_playwright

LI_AT = "AQED..."  # Replace with fresh cookie
PROFILE_DIR = "/root/.linkedin-mcp/profile"
COOKIES_JSON = "/root/.linkedin-mcp/cookies.json"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=True,
            args=["--no-sandbox", "--disable-gpu"],
        )

        # Inject for both www and bare domains
        for domain in [".www.linkedin.com", ".linkedin.com"]:
            await browser.add_cookies([{
                "name": "li_at", "value": LI_AT,
                "domain": domain, "path": "/",
                "httpOnly": True, "secure": True,
            }])

        page = await browser.new_page()
        await page.goto("https://www.linkedin.com", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        url = page.url
        title = await page.title()
        if "login" in url.lower() or "Sign in" in title:
            print("❌ Cookie expired or invalid")
            return False

        print(f"✅ Logged in! URL: {url}")

        # Save cookies.json
        all_cookies = await browser.cookies()
        cookie_list = [{
            "name": c["name"], "value": c["value"],
            "domain": c["domain"], "path": c["path"],
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", True),
        } for c in all_cookies]

        with open(COOKIES_JSON, "w") as f:
            json.dump(cookie_list, f, indent=2)

        await browser.close()
        return True

asyncio.run(main())
```

## Create source-state.json

After the bootstrap script runs successfully:

```json
{
  "version": 1,
  "source_runtime_id": "macos-arm64-host",
  "login_generation": "manual-injection",
  "created_at": "2026-06-16T17:55:00Z",
  "profile_path": "/root/.linkedin-mcp/profile",
  "cookies_path": "/root/.linkedin-mcp/cookies.json"
}
```

> **Key:** Set `source_runtime_id` to anything DIFFERENT from the actual runtime (e.g. `macos-arm64-host` on a Linux VPS) so the MCP takes the "foreign runtime" bridge path and imports `cookies.json`.

## Verify

```bash
# --status should show "foreign runtime" mode
uvx mcp-server-linkedin@latest --user-data-dir /root/.linkedin-mcp/profile --status

# Then test with a tool call
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "No valid LinkedIn session is available" | source-state.json missing or wrong runtime_id |
| "Chromium didn't shut down correctly" | Delete Session files, fix Preferences |
| "net::ERR_HTTP_RESPONSE_CODE_FAILURE" | LinkedIn blocked the request — try VNC interactive login |
| Cookie works in Playwright but not in MCP | Use the bridge trick above |
| "No li_at cookie found" in logs | cookies.json missing the auth_minimal preset names (li_at, JSESSIONID, bcookie, bscookie, lidc) |

## Full Bootstrap + Cookie Injection Script

This script does everything in one shot: clean profile, inject cookie, save state, export cookies.json:

```python
#!/usr/bin/env python3
"""One-shot: clean profile, inject li_at, navigate to LinkedIn feed, save state."""
import asyncio
import json
import os
from playwright.async_api import async_playwright

LI_AT = "AQED..."  # Replace with cookie
PROFILE_DIR = "/root/.linkedin-mcp/profile"
COOKIES_JSON = "/root/.linkedin-mcp/cookies.json"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=True,
            args=["--no-sandbox", "--disable-gpu"],
        )
        for domain in [".www.linkedin.com", ".linkedin.com"]:
            await browser.add_cookies([{
                "name": "li_at", "value": LI_AT,
                "domain": domain, "path": "/",
                "httpOnly": True, "secure": True,
            }])
        page = await browser.new_page()
        await page.goto("https://www.linkedin.com", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        url = page.url
        title = await page.title()
        print(f"URL: {url}")
        print(f"Title: {title}")

        if "login" in url.lower():
            print("❌ Still on login page")
        else:
            print("✅ On feed!")

        # Save full state
        state_path = os.path.join(PROFILE_DIR, "linkedin_state.json")
        await browser.storage_state(path=state_path)

        # Export cookies.json
        all_cookies = await browser.cookies()
        cookie_list = []
        for c in all_cookies:
            cookie_list.append({
                "name": c["name"], "value": c["value"],
                "domain": c["domain"], "path": c["path"],
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", True),
            })
        with open(COOKIES_JSON, "w") as f:
            json.dump(cookie_list, f, indent=2)

        li_at_cookies = [c for c in all_cookies if c["name"] == "li_at"]
        jsid = [c for c in all_cookies if c["name"] == "JSESSIONID"]
        print(f"Cookies: {len(cookie_list)} total, {len(li_at_cookies)} li_at, {len(jsid)} JSESSIONID")

        await browser.close()

asyncio.run(main())
```

## VNC Interactive Login Setup (Headless VPS)

When no valid cookie exists:

```bash
# 1. Xvfb
Xvfb :99 -screen 0 1920x1080x24 &

# 2. x11vnc
x11vnc -display :99 -forever -nopw -bg

# 3. noVNC (install first: uv pip install websockify)
cd /usr/share/novnc
python3 -m websockify --web /usr/share/novnc 6080 localhost:5900 &

# 4. Cloudflare tunnel
cloudflared tunnel --url http://localhost:6080
# → URL: https://<random>.trycloudflare.com

# 5. Start MCP login
DISPLAY=:99 uvx mcp-server-linkedin@latest --no-headless --login
```

User opens the cloudflared URL in their browser, sees the LinkedIn login page, logs in manually.
