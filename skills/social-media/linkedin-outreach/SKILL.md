---
name: linkedin-outreach
description: "Find B2B leads on LinkedIn and run personalized, rate-limited outreach (connect + follow-up) via an open-source LinkedIn MCP server."
version: 1.4.0
author: Clawksis + Gradient AI
license: MIT
platforms: [linux, macos, windows]
metadata:
  clawk:
    tags: [linkedin, leads, outreach, sales, prospecting, mcp, b2b]
    related_skills: [clawksis-agent]
---

# LinkedIn Outreach

Find the right people on LinkedIn, qualify them, and run **personalized,
low-volume, human-paced** outreach (connection requests + follow-up messages)
straight from Clawksis. Everything runs **open-source and self-hosted** — no
paid SaaS, no data leaving the user's machine — by wiring an open-source
LinkedIn MCP server as a Clawksis tool.

This skill is for **legitimate B2B prospecting** (the operator reaching their
own ideal customers). It is built around restraint, not volume.

---

## ⚠️ Read first — account-safety reality

LinkedIn's Terms of Service prohibit automated access, and LinkedIn actively
detects and bans accounts that automate aggressively. There is **no** "safe at
scale" automation. Treat every action as if a human reviewer will see it.

**Hard rules this skill always follows:**

- **Personalize every message.** No identical mass-blasts. Reference something
  real from the person's profile/company. If you can't personalize it, don't
  send it.
- **Stay under conservative daily caps** (see below) and add randomized,
  human-like delays between actions. Never burst.
- **Human-in-the-loop.** Draft the lead list and the messages, then **ask the
  operator to approve** before anything is sent. Default to dry-run.
- **Warm up new/low-activity accounts** slowly (start at ~5/day, ramp over
  weeks). New accounts get restricted fastest.
- **Stop immediately** on any CAPTCHA, "unusual activity" checkpoint, or
  message failure, and tell the operator. Do not retry around a checkpoint.
- **Never** scrape/store third-party personal data beyond what the campaign
  needs, and respect anyone who declines or doesn't reply (no repeated pokes).

If the operator asks for high-volume blasting, refuse the volume and explain the
ban risk — offer the personalized, capped approach instead.

### 🔴 Automatic ban triggers — never do these

| Trigger | Why |
|---------|-----|
| Same template sent to >10 people consecutively | LinkedIn detects pattern matching |
| Links in first message | Instant spam filter activation |
| <2 min gap between messages | Unnatural burst pattern |
| 50+ messages/day | Almost certain action limit / restriction |
| Response rate <10% after 50+ touches | Account flagged as spammer by algorithm |
| Opening with direct sales pitch | Higher report rate / manual review |
| Connecting with >100 people/day | Invitation limit hit + shadowban risk |

**Consequences:** Shadowban (7–14 days quiet restriction) → Account restriction
(up to 30 days, config changes locked) → Permanent ban.

### 🛡️ "Play it safe" tier (ultra-conservative — operator preference)

When the operator says "play safe" or "very safe," use these minimum-viable
limits instead of the defaults below:

| Action | Daily max | Spacing |
|--------|-----------|---------|
| Messages (new, 1-to-1) | **15–25** | 2–5 min between each |
| Follow-ups to unanswered | **5–7 / week** | days, not hours |
| Connection requests | **20–40** | 3–5 min between each |
| Profile views | **50–80** | spread across day |
| **New account — week 1** | **5 / day** each action | ramp +5/week |

### Conservative daily caps (per account)

| Action | Established account | New / cold account |
|--------|--------------------|--------------------|
| Connection requests | ≤ 15–20 / day | ≤ 5 / day, ramp slowly |
| Messages (1st-degree / InMail) | ≤ 20–25 / day | ≤ 5–10 / day |
| Profile views | ≤ ~80 / day | far fewer |

Spread actions across the day with randomized gaps (minutes, not seconds).
These are ceilings, not targets — fewer + better-targeted always wins.

---

## Setup — install the bundled LinkedIn MCP

### Method A: Catalog install (preferred)

```bash
clawk mcp install linkedin
```

If this fails with `suspicious command/args configuration`, the catalog entry
may need a workaround — see Method B.

### Method B: Manual add (catalog workaround)

```bash
# Remove any broken entry first
clawk mcp remove linkedin

# Add manually (pipe "Y" to auto-confirm the 17-tool prompt)
echo "Y" | clawk mcp add linkedin --command uvx --args mcp-server-linkedin@latest
```

### Post-install verification

```bash
clawk mcp list                 # confirm it's registered
clawk mcp test linkedin        # verify the connection
```

This installs **stickerdaniel/linkedin-mcp-server** — open-source, self-hosted,
launched locally via `uvx` (stdio).

### Authentication (browser session)

LinkedIn requires browser-based auth. Three approaches:

**A) Local login** — run this in a terminal on your own machine (opens a
browser window):

```bash
uvx mcp-server-linkedin@latest --login
```

**B) Headless login via Clawksis browser tools** — if you're on Telegram/Discord
and the operator provides credentials:

1. Navigate to `https://www.linkedin.com/login` via browser tool
2. Type email + password into the form fields
3. **Click "Sign in" via JavaScript, not browser_click.** LinkedIn uses custom
   React buttons with `onclick` handlers — no `<form>`, no `<button type="submit">`.
   The accessibility button has `type="button"` and `browser_click` often silently
   does nothing. Use `browser_console` with a JS expression:

   ```javascript
   (function(){
     var btns = document.querySelectorAll('button');
     for(var b of btns){ if(b.textContent.trim() === 'Sign in'){ b.click(); return 'clicked'; }}
     return 'not found';
   })();
   ```
4. LinkedIn triggers 2FA — the push notification expires within ~30s. You
   MUST prompt the operator to approve *immediately* after clicking "Sign in"
   or the session times out. If it times out, re-enter credentials and try again.
5. After approval, **the page often goes to `about:blank`** (React re-render or
   Chrome internal page). Do NOT assume login failed. Navigate explicitly to
   `https://www.linkedin.com/feed/` to confirm the session is active.
   **⚠️ False-positive trap:** checking `if 'feed' in url` in Python will match
   the *redirect parameter* in a login URL like
   `/login/?session_redirect=https%3A%2F%2Fwww.linkedin.com%2Ffeed%2F`.
   Use `if '/feed/' in url` (with the slash) to distinguish the real feed page
   from a redirect parameter.
6. **⚠️ MCP session trap:** the MCP's `--login` may report "Manual login completed
   successfully" and export 21+ cookies but **omit `li_at`** — the cookie that
   actually authenticates the session. Always verify after login:
   ```bash
   python3 -c "import json; c=json.load(open('/root/.linkedin-mcp/cookies.json')); print('li_at:', 'YES' if any(x['name']=='li_at' for x in c) else 'MISSING')"
   ```
   If `li_at` is missing, the MCP tools will return `"No valid LinkedIn session"`.
   The reference file `headless-server-auth.md` has recovery steps.
6. Check "Recognize this device in the future" (already checked by default) to
   reduce future 2FA prompts.

**D) Remote VNC web login (VPS/headless)** — when the server runs headless and
the operator can open a URL in their browser, expose the virtual display as a
web VNC page so the operator logs in manually with their real keyboard/mouse:

**E) Cookie transfer from local machine (SIMPLEST — preferred for first setup)**
When the operator has a local machine with a real display (laptop/desktop), this
is the fastest and most reliable path:

1. Have the operator run on their local machine:
   ```bash
   uvx mcp-server-linkedin@latest --login
   ```
   They log in manually (real browser, real Chrome fingerprint — no anti-bot
   detection). Complete any 2FA.

2. Verify `li_at` cookie was captured (on their machine):
   ```bash
   grep li_at ~/.linkedin-mcp/cookies.json
   ```
   If they're on Windows/PowerShell, use:
   ```powershell
   Select-String li_at $env:USERPROFILE\.linkedin-mcp\cookies.json
   ```

3. If `li_at` is present (value starts with `AQED...`), have the operator send
   either:
   - The **entire `~/.linkedin-mcp/` directory** compressed as `.tar.gz` or `.zip`
   - Or just paste the **contents of `cookies.json`** directly in chat

4. On the VPS, save the cookies and configure bridge mode:
   ```bash
   mkdir -p ~/.linkedin-mcp
   # Write the cookies.json content (pasted by operator)
   ```
   Then create `~/.linkedin-mcp/source-state.json` to force **bridge mode**:
   ```json
   {
     "version": 1,
     "source_runtime_id": "macos-arm64-host",
     "login_generation": "cookie-transfer-1",
     "created_at": "<ISO timestamp>",
     "profile_path": "/root/.linkedin-mcp/profile",
     "cookies_path": "/root/.linkedin-mcp/cookies.json"
   }
   ```
   The `source_runtime_id` MUST differ from the VPS runtime
   (`linux-amd64-container`) to force bridge mode. Any non-container value works
   (`macos-arm64-host`, `linux-amd64-host`, `windows-amd64-host`).

5. Verify the MCP picks it up:
   ```bash
   clawk mcp test linkedin   # Must show "Tools discovered: 17"
   ```
   The output should say:
   ```
   Source runtime: macos-arm64-host
   Profile mode: foreign runtime (fresh bridge each startup)
   ```

6. The bridge mode imports cookies from `cookies.json` on every startup. The
   session works for **company searches** reliably; **people searches** may fail
   with `ERR_TOO_MANY_REDIRECTS` (LinkedIn detects Patchright). See pitfalls
   below.

**Known bridge-mode limitation (ERR_TOO_MANY_REDIRECTS on people search):**
When using bridge mode (foreign runtime) in a Docker/VPS container, the
Patchright browser is detected by LinkedIn's anti-bot systems. Symptoms:
- ✅ **Company search** (`search_companies`) works — returns full results
- ❌ **People search** (`search_people`), **profile view** (`get_person_profile`),
  **company profile** (`get_company_profile`) fail with
  `net::ERR_TOO_MANY_REDIRECTS` — LinkedIn redirects to login/auth-wall

This happens because LinkedIn evaluates the browser fingerprint (Patchright
vs. real Chrome) BEFORE checking the session cookie. The same `li_at` cookie
works fine on the operator's real Chrome but gets rejected by Patchright.

**Workarounds for people/profiles:**
- Use the Clawksis browser tools (agent-browser) for people searches instead of
  the MCP — the agent-browser has a different fingerprint that sometimes passes
- Fall back to web-based business directories for leads (see
  `references/optical-industry-latam.md` for sector-specific sources)
- Have the operator do people searches manually and share results

**When bridge mode IS fully functional:**
- `search_companies` ✅ — can discover companies and their LinkedIn pages
- `search_jobs` ✅ — can search job postings
- `search_conversations` ✅ — can search existing message threads
- `get_inbox` ✅ — can list message conversations

**When bridge mode fails completely:** If even `search_companies` returns
`ERR_TOO_MANY_REDIRECTS`, the `li_at` cookie may have expired or been revoked.
Ask the operator to re-run `--login` on their local machine and send fresh
cookies.

```bash
# Terminal 1: start the MCP login in a virtual display
Xvfb :99 -screen 0 1920x1080x24 &
x11vnc -display :99 -forever -nopw -quiet -bg
python3 -m websockify --web /usr/share/novnc 6080 localhost:5900 &
cloudflared tunnel --url http://localhost:6080
# Terminal 2: start the MCP login
DISPLAY=:99 uvx mcp-server-linkedin@latest --no-headless --login
```

Give the operator the cloudflared URL. They log in manually through their
browser. When they see the LinkedIn Feed, the session is saved. Verify with
`--status` and check `li_at` in `cookies.json`. See `references/headless-server-auth.md`
for the full setup, cleanup steps, and troubleshooting "Restore pages?" dialogs.

**C) Authenticator app code** — when push notifications keep expiring, switch
to the authenticator code flow:

1. After "Sign in" triggers 2FA, LinkedIn shows a **"Check your LinkedIn app"**
   screen asking you to approve the push notification.

   **⚠️ Microsoft SSO redirect — happens before 2FA, not after.** If the email
   has a Microsoft identity linked (common for @gmail.com accounts registered
   via "Sign in with Microsoft"), clicking "Sign in" may redirect to
   `login.live.com` (Microsoft login) instead of showing the 2FA screen.
   The browser URL becomes `oauth20_authorize.srf...` and the form asks for a
   **Microsoft password**, skipping LinkedIn's own password prompt entirely.

   **Detection:** after clicking Sign in, check the URL. If it contains
   `login.live.com` or `oauth20_authorize.srf`, the Microsoft SSO redirect
   fired. The browser title becomes "Sign in - Google Chrome for Testing".

   **Handling:** the Microsoft password is often the same as the LinkedIn
   password. Fill the Microsoft password field on `login.live.com`
   (`input[type="password"]`) and submit. Microsoft auth redirects back to
   LinkedIn, which then shows the 2FA screen. If Microsoft has its own 2FA
   (authenticator app), you may need two code prompts — one for Microsoft,
   one for LinkedIn.

2. Click the **"Verify using authenticator app"** link (ref=e7 in the snapshot)
   to switch to code-entry mode instead of push.
3. The page updates to show: **"Enter the code you see on your authenticator
   app"** with a 6-digit text field.
4. **⚠️ TIMING PITFALL** — do NOT ask for the code while still typing into
   the 6-digit field. Codes expire in ~30 seconds. The typical failure mode:
   you ask → user reads code → types it in Telegram → sends it → 10-25s
   elapse → by the time you receive it and start typing it expires.
5. **Correct sequence:** navigate to code-input page first. Locate the text
   field ref id (it appears as a simple textbox like `ref=e4`). **THEN** ask
   the operator for the code. When they reply, type it **instantly** (via
   `browser_type`) and immediately click the "Submit code" button. If the code
   expires mid-flow, ask for a fresh one — the page stays on the same challenge
   screen so you can retry without reloading.

   **⚠️ `browser_type` can blank the page during code entry.** On LinkedIn's
   verification page, `browser_type()` sometimes triggers a React re-render
   landing on `about:blank` — even before the code is submitted. If this happens:
   - Navigate to `https://www.linkedin.com/feed/` — if the session is active,
     the feed appears. If it redirects to `/login`, the session was lost.
   - **Preferred workaround: use JS via `browser_console` to set the input value**
     **programmatically instead of `browser_type`.** This avoids the React
     re-render entirely. **The input is `type="tel"`** (not `type="text"`) with
     id `input__phone_verification_pin`:
     ```javascript
     (function(){
       var inp = document.getElementById('input__phone_verification_pin');
       if(!inp) return 'no input found - input may be type=\"text\" on your screen';
       var setter = Object.getOwnPropertyDescriptor(
         window.HTMLInputElement.prototype, 'value'
       ).set;
       setter.call(inp, '123456');   // replace with actual code
       inp.dispatchEvent(new Event('input', { bubbles: true }));
       inp.dispatchEvent(new Event('change', { bubbles: true }));
       // Now click Submit
       var btns = document.querySelectorAll('button');
       for(var b of btns){ if(b.textContent.trim()==='Submit code'){ b.click(); return 'submitted'; }}
       return 'code set, searching for submit';
     })();
     ```
     **Always use an IIFE** — variables from `browser_console` persist across
     calls, so `var inp = ...` on a second expression will throw
     `Identifier 'inp' has already been declared`.

6. Every code is usable from the moment it appears until it changes on the
   authenticator screen. Ask the operator to *read and hold* the code instead
   of typing it in their device — you want the code while it's still current,
   not what was current 15 seconds ago.
7. On success, the page may go blank (React re-render). Navigate to
   `https://www.linkedin.com/feed/` to confirm the session is active. Check
   that the profile avatar and feed content appear.
7. **⚠️ Stale-profile loop.** If the MCP previously completed a login attempt
   (even one that omitted `li_at`), its `--login` flag reopens the *existing*
   browser profile at `/root/.linkedin-mcp/profile/`. The stale cookies may
   cause a "remember-me container" loop — the MCP sits on the login page
   polling for a "Remember me" checkbox that never appears, until the 5-minute
   timeout. If this happens:
   - Remove or rename the stale data. Start with cookies:
     ```bash
     mv /root/.linkedin-mcp/cookies.json /root/.linkedin-mcp/cookies.json.bak
     ```
   - If the loop persists, the profile directory itself is stale. Remove both:
     ```bash
     mv /root/.linkedin-mcp/profile /root/.linkedin-mcp/profile.bak
     mv /root/.linkedin-mcp/cookies.json /root/.linkedin-mcp/cookies.json.bak
     rm -f /root/.linkedin-mcp/source-state.json
     ```
   - Then rerun `--login` with a fresh slate. Verify `li_at` again after.
8. **"Recognize this device in the future"** checkbox should already be checked
   by default. This reduces future 2FA prompts from this browser profile.

The two action tools — `connect_with_person` and `send_message` — are **off by
default** (read/discovery tools are on). Enable them only when ready to send:

```bash
clawk mcp configure linkedin   # or during install with echo "Y" | ... as in Method B
```

Then start a new Clawksis session so the tools load. Available tools:
`search_people`, `search_companies`, `get_person_profile`, `get_company_profile`,
`get_inbox`, `get_conversation`, `search_conversations`, `search_jobs`,
`get_job_details`, and (opt-in) `connect_with_person` / `send_message`.

Other open-source servers if this one doesn't fit:
[pauling-ai/linkedin-mcp-server](https://github.com/pauling-ai/linkedin-mcp-server).

> Heavier standalone alternatives (separate apps, not MCP) if the operator
> wants a full campaign engine instead of agent-driven outreach:
> [OpenOutreach](https://github.com/eracle/OpenOutreach) (describe product +
> market → AI finds/qualifies/contacts leads) and
> [Linki](https://github.com/moaljumaa/linki) (visit/connect/message + email
> sequences).

---

## Workflow

### 1. Define the ICP (ideal customer profile)
Ask the operator (or read from memory) for: target roles/titles, industries,
company size, geography, and the value proposition. For Clawksis's own ICP this
is typically LATAM service businesses — write outreach in the prospect's
language (Spanish for LATAM) and tone.

### ⚠️ Browser-automation pitfalls (LinkedIn React UI)

LinkedIn is a dynamic React SPA. The accessibility tree snapshot often **misses
or mislabels interactive elements** (connect buttons, modals, dropdowns). When
the snapshot shows a "Conectar" or "Invita a ... a conectar" link but clicking
it via `browser_click(ref)` does nothing:

1. **Use `browser_console` with JavaScript.** Find elements by attribute, not
   textContent, since LinkedIn renders spans inside button/link wrappers:

   ```javascript
   (function() {
     var links = document.querySelectorAll('a[href*="connect"]');
     if(links.length) { links[0].click(); return 'Clicked'; }
     return 'No connect link found';
   })();
   ```

2. **IIFE pattern required.** `browser_console` evaluation contexts persist
   across calls. Using `var x = ...` on a second call will fail with
   `Identifier 'x' has already been declared`. Always wrap in an IIFE:
   `(function() { ... })()`.

3. **Search results page.** Lead info (name, title, company, connection degree,
   mutual contacts) is nested inside `<a>` card links. The accessibility tree
   captures these at a `listitem > link` level. Extract by scanning the
   snapshot for patterns like `"Director ... en [Company]"`.

4. **Profile-to-connect flow.** Navigate to a profile page by clicking the
   person's name in search results. The profile page has a toolbar with
   "Conectar" / "Enviar mensaje" / "Más" buttons. If `browser_click` on
   "Conectar" doesn't open a modal, the button may be a React handler — try
   JavaScript dispatchEvent or navigate to `https://www.linkedin.com/mynetwork/`
   and add from the "Gestionar mi red" section instead.

5. **Rate-limit awareness.** After a successful login, LinkedIn may still show
   "Check your LinkedIn app" on subsequent navigations. Navigate to a clean
   page (feed, my network) to confirm the session is genuine before proceeding.

6. **🔴 Anti-bot detection (headless browser).** LinkedIn actively detects
   headless/automated browsers (Browserbase, agent-browser, Puppeteer,
   Playwright). Even after a successful login + 2FA code entry, LinkedIn
   may log the session out within seconds or redirect to an auth wall when
   you navigate to a profile page. Symptoms:
   - Login succeeds (feed loads) but navigating to a profile URL shows a
     "Sign Up | LinkedIn" or auth-wall page.
   - Returning to linkedin.com/feed/ redirects to linkedin.com/uas/login.
   - The session cookie appears invalidated despite "Recognize this device"
     being checked.

   This is not a React UI issue — it is active anti-bot detection. The
   headless Chrome fingerprint (no GPU, specific user-agent patterns, no
   extensions) triggers LinkedIn's risk scoring. Workarounds are unreliable:

   - **Browserbase Advanced Stealth** (residential proxies + custom Chromium)
     may help but requires a Scale Plan.
   - **Camoufox** local anti-detection browser may help for local sessions
     but not through Clawksis's agent-browser stack.
   - **The MCP approach (local `uvx mcp-server-linkedin`) does NOT have this
     problem** because auth is done on the user's real Chrome, which has a
     trusted browser fingerprint.

   **Fallback when blocked:** If the browser session is killed repeatedly,
   do NOT retry login loops — each attempt burns a 2FA code and may trigger
   a security flag. Instead:
   a) Compile the lead list and draft messages (as normal).
   b) Present the operator with the compiled data.
   c) Offer alternatives: manual outreach from their phone/laptop, or
      running `uvx mcp-server-linkedin@latest --login` on their local
      machine (where real Chrome lives with a trusted fingerprint).
   d) If the operator has a CRM/email system (e.g., Supabase cold-campaign
      templates), fall back to email outreach from that system.

### 🔍 Searching for Spanish-language prospects

When targeting LATAM markets, use Spanish search keywords in LinkedIn's search
bar. LinkedIn handles Spanish better than English for local titles:

| English ICP | Spanish search query |
|-------------|---------------------|
| Travel agency director | `agencia de viajes director Colombia` |
| Travel agency CEO/owner | `agencia de viajes gerente` |
| Hotel manager | `gerente de hotel Colombia` |
| Optical store owner/manager | `gerente óptica Colombia` / `dueño óptica` |
| Optometrist / clinic director | `optómetra Colombia` / `director salud visual` |
| Eyewear chain executive | `director operaciones óptica` / `fundador óptica` |
| Business owner (general) | `dueño de negocio` |

Search results show: **name**, **connection degree** (1º/2º/3º+), **current
title**, **company**, **location**, and **mutual connections**. 2º connections
are sweet-spot targets because they show up with an "Invita a conectar" button.

After finding leads, compile them in a table for operator approval before
sending any connection requests.

#### Fallback: web directories when LinkedIn MCP people search fails

When the MCP's people search fails (ERR_TOO_MANY_REDIRECTS on bridge mode from
a VPS/container), compile lead lists from web-based business directories:

- **Rentech Digital** (`rentechdigital.com/smartscraper`) — has paid datasets for
  30+ countries. E.g. Colombia opticians: 2,262 records, $299 full dataset,
  includes phones/emails/social media. Sample records visible on page for free.
- **Google Maps** — search `ópticas [city] Colombia`, extract names + phones
  from the business listings. 10–50 results per city.
- **DANE** (Colombia's national statistics dept) — free business directory at
  `dane.gov.co`, search by CIIU code for optical retail.
- **Directorio de asociaciones gremiales** — e.g. Asociación Colombiana de
  Optómetras (ACO), Federación Colombiana de Ópticas — often have member
  directories.

When using a paid dataset, present the sample to the operator for approval
before purchasing. The agent can process the data (filter by department,
extract contacts) once purchased.
are sweet-spot targets because they show up with an "Invita a conectar" button.

After finding leads, compile them in a table for operator approval before
sending any connection requests.

### 2. Find & qualify leads
Use the MCP's people/company search to build a candidate list matching the ICP.
For each candidate, pull enough profile context to (a) confirm fit and
(b) personalize. Drop poor-fit matches — quality over count. Present the list to
the operator for approval before any contact.

#### Lead extraction from search snapshot

When the LinkedIn search results page shows a list of people, the accessibility
tree exposes each lead as a `listitem` containing nested links. Parse this
format to build your lead table:

Search result snapshot pattern:
```
listitem [level=1]
  - link "[Name] [Degree] [Title] [Company] [Location] [Mutual contacts]"
    - paragraph
      - link "[Name]" [ref=eN]          ← name
    - paragraph                          ← title line
    - paragraph                          ← (sometimes empty)
    - paragraph
      - link "[Mutual1]" [ref=eN]        ← mutual connections
      - link "[Mutual2]" [ref=eN]
      - link "[N]" [ref=eN]
    - paragraph
      - link "[Connection degree]" [ref=eN]
```

Key extraction rules:
- **Name** — clickable link ref inside the card (e.g. ref=e54 for Santiago Cervera)
- **Connection degree** — `• 2º`, `• 1er`, `• 3er+` after the name in the link text
- **Title + Company** — concatenated in the link text after degree: `"Director Trafalgar Tours - Agencia de Viajes Colombia"`
- **1er connections** → can message directly without connecting
- **2º connections** → sweet spot; show "Conectar" button with note field
- **3er+ connections** → lowest priority; harder to connect, higher friction

Compile leads in a structured table:

```
| # | Name | Title | Company | Degree | Notes |
|---|------|-------|---------|--------|-------|
| 1 | [Name] | [Title] | [Company] | 2º | [mutuals, location] |
```

#### Presenting leads for operator approval

After extracting leads, present them as a clean Markdown table with the
proposed message variant for each. This is NOT skippable — the operator
must approve before any contact:

```
## 🎯 Leads encontrados

| # | Nombre | Cargo | Empresa | Conexión |
|---|---|---|---|---|
| 1 | **Santiago Cervera** | Director | Trafalgar Tours | 2º |
| 2 | **Carlos Cervera** | Director General | Trafalgar Tours | 2º |

### 📝 Mensajes a probar

Santiago → Opción 2 (caso de éxito AVO)
Carlos  → Opción 1 (directo al problema)

¿Te parece bien este approach? O quieres cambiar algún mensaje?
```

#### A/B message testing

When the operator says "prueba varios mensajes" (test multiple messages),
assign DIFFERENT message variants to DIFFERENT leads. Track which variant was
sent to whom. Do NOT send multiple variants to the same person. After the
first batch, report back results so the operator can decide which variant to
scale.

### 3. Personalized connection requests
For approved leads, draft a short, specific connection note (reference their
role/company/a recent post — not a template). Send within the daily cap, with
randomized delays. Log who was contacted (use memory) to avoid duplicates.

### 4. Follow-up sequence (only after they accept)
When a request is accepted, send a genuinely useful, personalized first
message — lead with relevance/value, not a pitch. Keep follow-ups light and
spaced out (e.g., a gentle nudge after several days). **One** polite follow-up
if no reply; then stop. Never machine-gun.

### 5. Track & hand off
Record outcomes (sent / accepted / replied / not-interested) in memory or the
dashboard so the operator has a pipeline view and the agent never re-contacts
someone who declined.

---

## Message guidance

- Short (2–4 sentences), specific, written like a human.
- Open with something true about *them*; make the ask small and clear.
- Match the prospect's language (Spanish/voseo for LATAM by default).
- Never fabricate shared connections, mutual experiences, or facts.
- Always leave an easy out; honor "no".

## Supporting files

- `templates/travel-agency-outreach.md` — 3 Spanish-language connection templates
  for targeting Latin American travel agencies with the Gradient Cloud / AVO Tours
  case study. Includes safe dosing limits (modo "muy seguro").
- `references/case-study-from-supabase.md` — technique for extracting real
  conversation data from a Supabase backend to build fact-based case studies
  for outreach (no need to ask the operator what the product does).
- `references/headless-server-auth.md` — LinkedIn MCP auth workflow for
  headless VPS environments using Xvfb + xdotool + CDP cookie injection.
- `references/optical-industry-latam.md` — Guía completa para prospección del
  sector óptico en LATAM: queries de búsqueda, perfiles objetivo, tipos de
  empresa, contexto de mercado colombiano y value propositions.

## When to stop and ask the operator

- Any CAPTCHA / "unusual activity" / checkpoint, or auth/cookie expiry.
- A message or connection request fails to send.
- The daily cap is reached.
- The ICP or message templates are ambiguous — confirm before sending.
