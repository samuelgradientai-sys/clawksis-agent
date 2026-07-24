---
name: opportunity-research
description: >-
  Research and evaluate digital business opportunities for AI agent platforms.
  Covers underserved market discovery, competitive analysis, revenue data (MRR/ARR),
  market sizing, and matching platform capabilities to profitable niches.
emoji: 🔍
category: research
triggers:
  - ES: "investigar oportunidades de negocio"
  - ES: "qué nicho"
  - ES: "dónde meternos"
  - ES: "mercados desatendidos"
  - ES: "oportunidades digitales"
  - ES: "buscar ideas de negocio"
  - ES: "analizar competencia"
  - ES: "qué sector"
  - EN: "research business opportunities"
  - EN: "find a niche"
  - EN: "underserved market"
  - EN: "digital opportunities"
  - EN: "competitive analysis"
  - EN: "market research"
  - EN: "what sector"
---

# Market Opportunity Research for AI Agent Platforms

## Trigger

The user asks you to research business/digital opportunities, find a profitable niche, analyze the competitive landscape, or figure out what sector to target with an AI agent platform.

## Methodology

Always follow this sequence:

### 1. Understand the user's constraints

Before searching, identify:
- **Geography**: LatAm? Global? Specific country?
- **Platform**: What platform/capability is the user building on? (Clawksis, custom, etc.)
- **Scale ambition**: Agency/service vs platform/product? $1M vs $100M?
- **Competition awareness**: What competitors does the user already know about?
- **Personal interest**: Any sector the user mentioned (healthcare, fintech, devtools)?

### 2. Multi-source market research

Use at least **three parallel searches** on different angles:
- Market size data (Grand View, Mordor Intelligence, Gartner)
- Competitive landscape (who's winning, pricing, MRR data)
- Underserved/niche opportunities (empty spaces, what's growing)
- LatAm-specific data when user is in Latin America

Always scrape at least **2-3 full articles** for depth. Search snippets alone miss nuance.

### 2b. Anti-block extraction for JS-heavy / commercial sites

Many 3PL, logistics, and B2B company sites use aggressive anti-bot protection (Cloudflare, Turnstile, JS-required). When web_extract and scrape both fail:

1. Use `browser_navigate` to load the page (the browser tool has stealth features)
2. Use `browser_snapshot` to get the interactive element tree (tables may appear as accessible rows)
3. For long tables truncated by the snapshot cap, use `browser_console` with:
   ```
   expression: "document.body.innerText.substring(start, end)"
   ```
   — adjust start/end by scrolling in chunks to read the full dataset
4. For structured table data, extract row by row from the snapshot's cell elements (ref=eN) or use `browser_console` with a JavaScript expression that parses the table:
   ```
   expression: "JSON.stringify([...document.querySelectorAll('table tr')].map(r => [...r.querySelectorAll('td,th')].map(c => c.innerText.trim())))"
   ```
5. If you hit rate limits or empty page, the site may need residential proxies — note this to the user rather than retrying the same blocked URL

Commercial research sites (3PL rankings, logistics reports, business directories, market research portals) are the most common blockers.

### 3. Analyze through three lenses

| Lens | Question |
|------|----------|
| **Market signal** | What's the TAM, growth rate, and revenue data? |
| **Competition** | Who's already there? What are their weaknesses? |
| **Platform fit** | Does Clawksis (or the user's platform) have a unique advantage? |

### 4. Match against platform capabilities

Map the opportunity against what the platform can uniquely do:
- Multi-agent orchestration -> Underserved by single-model competitors
- WhatsApp MCP -> Differentiator for LatAm B2B
- Cron jobs + autonomy -> Beats human-in-the-loop tools
- Multi-model (OpenRouter) -> Independent review beats single-vendor lock-in
- Memory persistence -> Data moat over generic tools

### 5. Present findings

Structure the response as:
1. **Market overview table** — TAM, growth rate, revenue data
2. **Competitive landscape** — who competes, their pricing, their weakness
3. **Platform advantage** — why Clawksis wins in this niche
4. **Concrete opportunity** — specific product, pricing model, target customer
5. **Why NOT to do it** — risks, competition, barriers (builds trust)

Include **specific revenue data** (MRR ranges, ARR, pricing tiers from real companies).
Avoid vague statements. Lead with numbers.

## User preferences for this user (Samuel)

- Prefers **Spanish** responses
- Likes **data-heavy answers** with tables, MRR figures, growth rates
- Values **competitive analysis** (who wins today, what's their weakness)
- Wants **platform differentiation** — "why Clawksis beats X"
- Gets frustrated with obvious/saturated ideas (WhatsApp, generic chatbots)
- Responds to **counter-intuitive patterns** ("boring = profitable")
- Has **long-term ambition** — wants $100M+ scalable business, not agency
- Keep recommendations **actionable**: concrete product, pricing, first 5 customers

## Reference data (2026)

### Key market sizes
| Market | 2026 Value | Growth | Source |
|--------|-----------|--------|--------|
| AI agents total | $12-15B | 45% CAGR | Grand View / Presenc |
| Agentic AI dev platforms | $14.6B | 35.3% CAGR | Mordor Intelligence |
| AI code review tools | $420M ARR | 133% YoY | IdeaPlan |
| AI in healthcare (LatAm) | $2.05B | 34.9% CAGR | Towards Healthcare |
| AI code assistants (US) | $1.66B | 26.8% (security niche) | SNS Insider |

### What's SATURATED (avoid)
- AI writing assistants (commoditized, race to free)
- Generic chatbot builders (flat growth, competing on integrations)
- AI meeting summarizers (winner-take-most by Otter/Fireflies)
- AI image generation (race to free)
- WhatsApp chat agents for general business (crowded)

### What's UNDERSERVED (target)
- AI compliance and regulatory ($15-60K MRR, low competition)
- AI data analysis for non-technical teams ($10-40K MRR, vertical wins)
- Vertical AI workflow automation ($10-50K MRR, very low churn)
- AI code review / security scanning ($8-35K MRR, fast growth)
- AI for boring industries: funeral homes, pet grooming, marinas, breweries

### AI Code Security competitive landscape (2026)
| Tool | Price | Weakness |
|------|-------|----------|
| CodeRabbit | $15-30/dev | Generic, no security depth |
| GitHub Copilot Reviews | $19-39/dev bundled | Superficial, GitHub-only |
| Greptile | $30/dev | Heavy, not security-first |
| Claude Code Security | Enterprise only | Non-deterministic, single vendor |
| Snyk / Pixee | Custom | SAST/SCA only, no review logic |

### Key insight from LatAm
34% of business processes in Colombia are automatable today. SMEs spend 16 hrs/week on manual AP/AR. $18-30K USD annual savings per company. (diezX Colombia benchmark, 2026)

## Cybersecurity vertical deep-dive

### Core positioning: The independence moat
Claude Code Security's fundamental weakness: the SAME model that writes the code should NOT review it for security (`source: StackHawk, SonarSource`). This is your primary competitive differentiator. A multi-model approach (Claude + GPT + local Qwen/DeepSeek) provides INDEPENDENT security review that beats single-vendor lock-in.

### Claude Code Security vs multi-model approach
| Factor | Claude Code Security | Multi-model approach |
|--------|---------------------|---------------------|
| Determinism | Non-deterministic (same scan != same results) | Hybrid: deterministic SAST + AI consensus |
| Vendor lock-in | Anthropic only | Any provider (OpenRouter) + local models |
| Coverage | Source code only | Code + deps + infra + runtime |
| False positives | Not published | Reduced by cross-model consensus |
| Availability | Enterprise only ($100+/seat) | All tiers ($20-49/seat) |
| Buyer | Security team (AppSec) | Dev + security teams |

### Cybersecurity sub-opportunities (2026)
Beyond code review, the cybersecurity vertical has multiple scalable SaaS sub-niches:
1. **Compliance automation for LatAm** ($7-30K ARR/customer, very low competition) — SOC 2, ISO 27001, NIST in Spanish
2. **Automated pentesting as a service** ($15-50K annual, Cobalt-style) — weekly autonomous scanning
3. **Security skills library** — massive library of autonomous security skills for Clawksis (SAST scan, secret detection, dep audit, cloud misconfig, API security, compliance watch, vuln scan). Each skill = individual product at $49-199/mo, or bundle at $299-999/mo.

### The "skills-as-product" business model
This is a key insight: instead of building ONE security product, build a **platform with 50+ autonomous security skills**. Each skill is a self-contained Clawksis skill that performs one security task autonomously (via cron + tools + multi-model AI). Customers subscribe to individual skills or a bundle. This gives:
- Multiple price points ($49-999/mo range)
- Add-on upsell path (start with 1 skill, add more)
- Market network effects (more skills = more valuable platform)
- Low marginal cost per skill (all share same agent infrastructure)

### Local models strategy
User has Minisforum MS-S1 Max (128GB) for self-hosted inference. This enables:
- Qwen 72B in Q4 (~45GB) for security review
- DeepSeek Coder 33B (~20GB) for code analysis
- Zero external API dependency for core workflow
- Privacy for clients who can't send code to third-party APIs
- Vendor independence (not locked into Anthropic/OpenAI pricing)

### Kickbacks.ai pattern (novel AI agent monetization)
Kickbacks.ai (`https://kickbacks.ai`, launched Jun 2026) is an ad marketplace for AI agent "thinking" states. Developers display sponsored content in Claude Code/Codex spinners and earn 50% of ad revenue. Key relevance: demonstrates AI agent ecosystem can be monetized beyond seat pricing. Model: advertisers bid per 1K impressions (from $5), 50% goes to developer. Source code at `github.com/andrewmccalip/kickbacks.ai.git`.

## See also
- `hardware-research` — for hardware-specific market research (mini PCs, GPUs)
- `last30days` — for real-time trending/current events research
- `local-llm-hardware` — hardware specs and recommendations for local inference servers
- `references/market-data-2026.md` — market sizes, revenue data, saturated vs underserved niches
- `references/cybersecurity-competitive-analysis-2026.md` — deep analysis of Claude Code Security, SAST tools comparison, skills library pricing model
- `references/3pl-market-overview-2026.md` — top 20 global 3PLs, market size, Colombian operators, specialized segments — complete technical specifications for the Minisforum MS-S1 Max AI workstation
- `references/vscode-server-headless-setup.md` — headless VS Code Server setup with Cloudflare tunnel for installing and testing AI agent extensions (Kickbacks.dev, etc.)
