---
name: hardware-research
description: "Research and compare hardware (mini PCs, workstations, servers) for self-hosted AI workloads. Covers Reddit scraping via pullpush.io, Ollama model compatibility analysis, competitor comparison tables, and price/spec aggregation."
version: 1.0.0
author: Clawksis
tags: [hardware, research, mini-pc, server, workstation, comparison, ai-inference, reddit, scraping]
metadata:
  clawk:
    tags: [hardware, research, mini-pc, server, workstation, comparison, ai-inference, reddit, scraping]
---

# Hardware Research

Use this skill when the user asks to find, compare, or validate hardware for running AI workloads (LLMs, self-hosted services).

## When to trigger

- User asks for recommendations on mini PCs, workstations, or servers
- User wants to compare specs/prices across multiple machines
- User needs to know what models can fit in a given RAM budget
- User asks "what does Reddit think about X hardware?"
- User wants a cost-benefit analysis of different machines

## Research pipeline

### 1. Determine constraints

Ask or infer:
- RAM requirement (e.g., 128GB unified/expandable for 70B models at Q4)
- CPU preference (AMD vs Intel, core count)
- Connectivity (OCuLink, USB4, PCIe slots, 10GbE)
- Form factor (mini PC, tower, rack)
- Budget range
- Power/noise constraints

### 2. Scrape Reddit for community sentiment

Use pullpush.io (Reddit archive) when direct Reddit access is blocked:

```python
from scrapling.fetchers import Fetcher
import json, urllib.parse

url = f"https://api.pullpush.io/reddit/search/submission/"
f"?subreddit={sub}"
f"&q={urllib.parse.quote(query)}"
f"&sort=score&size=20"

page = Fetcher.get(url, stealthy_headers=True, timeout=15)
data = json.loads(page.body)  # ⚠️ .body not .text
posts = data.get('data', [])
```

**Best subreddits for hardware research:**

| Subreddit | Focus |
|-----------|-------|
| r/MiniPCs | Mini PC reviews, comparisons, specs |
| r/homelab | Server builds, Proxmox, power efficiency |
| r/LocalLLaMA | LLM inference hardware, GPU builds |
| r/sffpc | Small form factor, compact workstations |
| r/hardware | General hardware discussions |
| r/MINISFORUM | Minisforum-specific models |

**Key data to extract from posts:**
- Score (community validation)
- Title and selftext (specs, build details)
- Comments (real-world experience, issues, tips)
- Permalink (for user reference)

**Limits:** ~15 req/min, data up to ~May 2025

### 3. Calculate model compatibility

For Ollama/llama.cpp on a given RAM budget:

| Quantization | GB per 1B params |
|-------------|-----------------|
| Q4_K_M | ~0.56 GB/1B |
| Q5_K_M | ~0.69 GB/1B |
| Q8_0 | ~1.06 GB/1B |
| FP16 | ~2.0 GB/1B |

Available RAM = Total RAM - ~16GB for OS

Formula: `max_params = available_RAM / GB_per_param`

### 4. Build comparison table

Compare across:
- CPU (cores, architecture, single/multi-thread)
- RAM max capacity + expandability (soldered vs SODIMM)
- OCuLink presence (for future eGPU)
- Price (barebone vs configured)
- Community reputation (Reddit score, known issues)
- Power consumption and noise level

### 5. Present results

Format for readability:
1. Quick winner statement
2. Table with key specs
3. Reddit quotes with links
4. Known issues/caveats

## Known competitor categories

### Strix Halo (all use LPDDR5X soldered — NOT expandable)
- Minisforum MS-S1 Max (Ryzen AI Max+ 395, 128GB, OCuLink ✅, Dual 10GbE, ~$2,919 direct, $3,299 on Amazon)
- GMKtec EVO-X2 (Ryzen AI Max+ 395, 128GB LPDDR5X, 2TB, WiFi 7, lector SD, ~$3,299 Amazon)
- ACEMAGIC M1A PRO+ (Ryzen AI Max+ 395, 128GB LPDDR5X, 2TB, Radeon 8060S, dual 2.5GbE, WiFi 7, OCuLink, ~$3,099 direct / $3,299 Amazon)
- NIMO AI Mini PC (Ryzen AI Max+ 395, 128GB LPDDR5, 1TB, Radeon 8060S, USB4, ~$3,439 Amazon)
- Beelink GTR9 Pro (Ryzen AI Max+ 395, 128GB soldered, dual 10GbE, ~$1,809 → discontinued)
- Framework Desktop (Ryzen AI Max+ 395, 128GB soldered, modular, ~$1,999)
- Bosgame M5 (Ryzen AI Max+ 395, 128GB soldered, was $1,699 now $2,799)

### Mini PCs with expandable DDR5 + PCIe slot (Strix Halo alternatives)
- Minisforum MS-01 (i9-13900H, 2x DDR5 SO-DIMM up to 128GB, PCIe x4 slot, Dual 10GbE SFP+, ~$367 barebone)
- Minisforum MS-A2 (Ryzen 9 9955HX, DDR5 SO-DIMM up to 128GB, PCIe x16 real slot, Dual 2.5GbE + 10G SFP+, ~$795 barebone)
- Minisforum MS-02 Ultra (Ultra 9 285HX, 4x DDR5 up to 256GB, PCIe 5.0 x16, Dual 25GbE SFP+, ~$1,159 barebone)

### Used enterprise workstations
- HP Z2 Mini G9 (i9-14900K, 128GB DDR5, RTX 2000 Ada 16GB, ~$1,500 used on eBay)
- HP Proliant DL380 G9 (2x Xeon, 768GB, ~€650)
- Dell PowerEdge T340/T440 (Xeon, 512GB, ~$800)

## Key verification step: check RAM type on product page

Before recommending any machine, verify the RAM type by scraping the product page for these phrases:

| Phrase in specs | Meaning | Expandable? |
|----------------|---------|-------------|
| "Onboard LPDDR5X (non-upgradeable)" | Soldered | ❌ NO |
| "memory chips are soldered to the motherboard" | Soldered | ❌ NO |
| "LPDDR5x" | Soldered low-power | ❌ NO |
| "DDR5 SO-DIMM slots" | Socketed | ✅ YES |
| "DDR5 SODIMM" | Socketed, user-replaceable | ✅ YES |

**Do NOT assume any mini PC with 128GB has expandable RAM until you see "SO-DIMM" or "slot" in the specs.**

## Pitfalls

- Do NOT confuse the Minisforum AI X1 Pro (Ryzen AI 9 HX 370, max 96GB) with the GMKtec AI X1 Pro (7945HX, 128GB) — they share a name but are different machines
- Strix Halo machines (FEVM, Framework) have soldered RAM — no future expansion
- Pullpush.io data stops at ~May 2025 — newer models may have no Reddit data there
- Always verify actual max RAM from manufacturer specs, not just listings
- "128GB support" often requires 2x64GB SODIMM sticks or specific BIOS version
- **MercadoLibre** blocks scrapers with cookie/login walls — use `browser_navigate` in stealth mode (may still fail without residential proxies) or fall back to Amazon/Google Shopping for pricing. Amazon ships to most Latin American countries.
- For Latin American buyers (Colombia, Mexico, etc.): Amazon.com and official Minisforum/ACEMAGIC stores ship directly. Account for ~19% IVA (Colombia) + potential aranceles on import. Casilleros virtuales (Aeropost, FlashBox) are an alternative when stores don't ship directly.

## Reference files

- `references/ollama-model-sizes.md` — model RAM calculator with quantization factors, available RAM by machine, and what fits per model
- `references/reddit-subreddits.md` — tested subreddits for hardware research, signal quality, and pullpush data cutoff warning
- `references/ms-s1-max-specs.md` — full technical specifications for the Minisforum MS-S1 Max (Ryzen AI Max+ 395, 128GB, the user's primary machine)
