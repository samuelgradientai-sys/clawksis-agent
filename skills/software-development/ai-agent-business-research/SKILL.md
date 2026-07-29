---
name: ai-agent-business-research
description: Research and validate AI agent business opportunities—market sizing, competitive landscape, underserved niches, pricing models, and go-to-market for Clawksis-based products.
tags:
  - business-research
  - market-analysis
  - opportunity-validation
  - product-strategy
  - competitive-intelligence
  - youtube-automation
  - content-creation
---

# AI Agent Business Research

Sistematic process for finding and validating AI agent business opportunities for Clawksis. Goes beyond generic "AI for X" to vertical, underserved, scalable niches.

## Trigger
User asks: "find me a business opportunity", "what niche should we target", "investigate market X", "find underserved markets", "YouTube automation", "faceless channel", "AI video content", or "content automation business". Also when asked to research competitors or validate an idea.

## Process

### 1. Define the Constraint Space
Before searching, clarify with user:
- **Scalability**: Platform/SaaS vs agency/service?
- **Geography**: Global, LatAm, Colombia-specific?
- **Model dependency**: Cloud-only, local-only, hybrid?
- **Budget/effort**: Time to first customer?
- **Existing assets**: What's already built (WhatsApp MCP, Supabase, etc.)

### 2. Market Discovery (Web Search)
Search broadly first, then narrow:
- "underserved AI SaaS niches [year]"
- "biggest pain points [industry] [region] [year]"
- "AI agent startup revenue MRR [niche]"
- "most profitable AI business ideas [year] solo founder"
- "[industry] automation [region] market size [year]"

### 3. Deep Dive (Scrape/Extract)
For promising candidates, scrape:
- **Market reports** (Mordor Intelligence, Grand View Research etc.)
- **Startup directories** (StartupIdeasDB, Impectly, IdeaProof)
- **Competitor analysis** articles
- **Real revenue data** (MRR, ARR, pricing)

### 4. Analyze Competition
Build a comparison table:
- Who are the incumbents?
- What are their weaknesses (price, lack of feature, vendor lock-in)?
- How does Clawksis's architecture (multi-agent, memory, cron, multi-channel) give an edge?

### 5. Price & Size the Opportunity
- Reference pricing from similar tools ($15-$50/dev/mo for developer tools, $99-$999/mo for business SaaS)
- Estimate market size from reports
- Calculate unit economics (inference costs vs price)

### 6. Synthesize & Recommend
Present the TOP opportunities ranked by:
- Scalability
- User's existing assets (Clawksis features that map directly)
- Competition level (prefer underserved/"boring")
- Time to revenue

Format: tables with clear columns, avoid walls of text. User prefers concise data-driven recommendations.

## Key Data Sources (2026)
- AgentMarketCap.ai — startup playbooks with real revenue
- StartupIdeasDB.com — validated problems database
- Impectly.ai — revenue-backed niche analysis
- IdeaProof.io — startup idea lists with pricing data
- Mordor Intelligence — agentic AI development platform market ($14.6B in 2026)
- Presenc.ai — AI agent marketplace landscape
- SaaS Hints — underserved market analysis
- OutlierKit — automation agency niche rankings

## Pitfalls
- DO NOT suggest saturated niches (AI writing, generic chatbots, meeting summarizers, WhatsApp service agencies). These are commoditized and user explicitly rejected them.
- DO NOT suggest WhatsApp/service agencies when user wants platform scalability — user said "eso es chiquito" and wants billion-dollar scale.
- Always include at least one "local models" angle for security-conscious users.
- For LatAm: 34% of Colombian processes are automatable per diezX data — use this for local opportunities.
- For code/security: Claude Code Security exists but is enterprise-only, single-model, non-deterministic — Clawksis's multi-model approach is the differentiation.
- **Boring markets = money**: The most profitable niches are the ones nobody talks about (compliance, cybersecurity, accounting automation, regulatory). Avoid hype.
- **Prefer B2B over B2C**: Businesses pay $200-$3K/mo for tools; consumers pay $10-20/mo. Scalability comes from platform play, not from selling to individuals.
- **YouTube Kids content = bad RPM**: Kids content pays $0.30-$0.50 RPM vs $9-$21 for finance/true crime. Also YouTube tightened rules against "inauthentic" AI content (July 2025) and 200+ advocacy groups petitioned to ban AI slop from YouTube Kids (Apr 2026). High risk of demonetization.
- **YouTube faceless channel automation**: Realistic timeline is 3-6 months to monetization, need 10M Shorts views or 4K watch hours. Tool costs $47-$180/mo per channel. Revenue stacking (ads + affiliates + sponsors) required — ad revenue alone is fragile.

## References
See `references/market-data-2026.md` for compiled research data from this session.
See `references/youtube-faceless-automation-2026.md` for YouTube faceless channel market data, tool stacks, RPM, and monetization strategies.
