---
name: linkedin-outreach
description: "Find B2B leads on LinkedIn and run personalized, rate-limited outreach (connect + follow-up) via an open-source LinkedIn MCP server."
version: 1.0.0
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

The LinkedIn MCP ships in the Clawksis catalog (same as the n8n MCP), so it's
one command to install:

```bash
clawk mcp install linkedin     # or: clawk mcp install official/linkedin
clawk mcp test linkedin        # verify the connection
clawk mcp list                 # confirm it's registered
```

This installs **stickerdaniel/linkedin-mcp-server** — open-source, self-hosted,
launched locally via `uvx` (stdio). Auth is a **browser session on the
operator's own machine** — no cookie or password is ever pasted into chat.
Sign in once:

```bash
uvx mcp-server-linkedin@latest --login
```

The two action tools — `connect_with_person` and `send_message` — are **off by
default** (read/discovery tools are on). Enable them only when ready to send:

```bash
clawk mcp configure linkedin
```

Then start a new Clawksis session so the tools load. Available tools:
`search_people`, `search_companies`, `get_person_profile`, `get_company_profile`,
`get_inbox` / `get_conversation` / `search_conversations`, `search_jobs`,
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

### 2. Find & qualify leads
Use the MCP's people/company search to build a candidate list matching the ICP.
For each candidate, pull enough profile context to (a) confirm fit and
(b) personalize. Drop poor-fit matches — quality over count. Present the list to
the operator for approval before any contact.

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

## When to stop and ask the operator

- Any CAPTCHA / "unusual activity" / checkpoint, or auth/cookie expiry.
- A message or connection request fails to send.
- The daily cap is reached.
- The ICP or message templates are ambiguous — confirm before sending.
