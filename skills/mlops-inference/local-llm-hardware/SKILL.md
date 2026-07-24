---
name: local-llm-hardware
description: Research, compare, and recommend mini PCs / workstations for running local LLMs. Covers Strix Halo, DGX Spark, Apple Silicon, and DIY builds with unified memory trade-offs.
category: mlops-inference
---

# Local LLM Hardware Research

Use this skill when the user asks about **buying hardware to run local LLMs, mini PCs for AI, Strix Halo recommendations, or hardware budget comparisons.**

## Workflow

### 1. Clarify budget and currency
- If the user mentions a local currency (COP, MXN, EUR), look up the current USD exchange rate and convert their budget to USD.
- All Strix Halo and enterprise mini PCs are priced in USD; international buyers pay import duties/VAT on top.

### 2. Determine what models they want to run
Use this rough guide (Q4_K_M quantisation):

| RAM | Max Model Size | Example Models |
|-----|---------------|----------------|
| 32GB | ~15B | Gemma 4 9B, Mistral 7B, Llama 3.1 8B |
| 64GB | ~34B | Qwen 3 30B, Gemma 4 27B, Mistral Small 3.1 |
| 96GB | ~50B | Qwen 3.1 72B (IQ4), DeepSeek R1 Distill |
| 128GB | ~70B | Llama 4 70B, Qwen 3 70B, Gemma 4 70B |
| 192GB+ | ~120B | DeepSeek R1, Qwen 3 120B (IQ4) |

### 3. Decide architecture
- **Unified memory (preferred):** Strix Halo, Apple Silicon, DGX Spark — CPU + GPU share full pool at high bandwidth (256–819 GB/s). Best for LLM inference.
- **Regular DDR5:** Intel/AMD mini PCs with SODIMM slots — much lower bandwidth (~80 GB/s). CPU-only inference yields 3–10 tok/s. Only viable if user has no budget for unified memory.

### 4. Search sources (in order)
1. **Google Shopping** — quick price scan for specific models
2. **Brand stores** — Minisforum, GMKtec, Beelink, Framework, GEEKOM, Bosgame
3. **eBay** — used/open-box Strix Halo machines (prices 20–30% below new)
4. **AliExpress** — often has different pricing tiers; check "Choice" listings
5. **Reddit** via pullpush.io — r/MiniPCs, r/LocalLLaMA, r/LocalLLM for user experiences

### 5. Build comparison table
Include columns: model, price, CPU, RAM (type + capacity), bandwidth, OCuLink, 10GbE, key trade-off

### 6. Key trade-offs to flag
| Trade-off | Unified Memory | Regular DDR5 | Notes |
|-----------|---------------|--------------|-------|
| **Bandwidth** | 256–819 GB/s 🚀 | 50–80 GB/s 🐢 | 3–10× slower inference |
| **RAM expandible** | ❌ Soldered (mostly) | ✅ SODIMM slots | Only MS-S1 Max has expandible unified RAM |
| **OCuLink/eGPU** | Rare (MS-S1 Max has it) | Common (PCIe slot) | For future GPU upgrades |
| **LLM tok/s (70B)** | 30–38 tok/s | 3–10 tok/s | Strix Halo / DGX Spark win |

## International & Colombian user considerations
- **Check if brand ships to Colombia:** GMKtec (`gmktec.com`), Minisforum (`store.minisforum.com`), and GEEKOM (`geekompc.com`) have Colombia in their country/region selectors. Beelink and Framework may not.
- **Colombian import costs:** add ~19% IVA (VAT) on top of USD price, plus possible DHL/4-72 shipping fees.
- **COP exchange rate:** use a Google search scrape: `https://www.google.com/search?q=USD+to+COP+exchange+rate+2026`. As of mid-2026: 1 USD ≈ 3,450 COP.

## Pitfalls
- New Strix Halo 128GB machines now START at **$3,299** (GMKtec EVO-X2 on Amazon) and go up to $3,999+. The $1,809–$1,999 era is OVER — Beelink GTR9 Pro is discontinued on the official store, and most 128GB variants are sold out at original prices.
- **ALL Strix Halo use LPDDR5X soldered RAM — NONE are user-expandable.** Always check the product page for "Onboard LPDDR5X (non-upgradeable)" or "memory chips are soldered to the motherboard" text.
- **MS-S1 Max RAM is NOT expandable.** The product page states: "The 64GB memory chips on this model are soldered to the motherboard. User upgrade to 128GB is not possible."
- **DDR5 SO-DIMM vs LPDDR5X:** Mini PCs with regular DDR5 SO-DIMM slots (MS-01, MS-A2, MS-02 Ultra) ARE expandable by the user. Mini PCs with LPDDR5X (all Strix Halo, Apple Silicon) are NOT.
- **Bosgame M5** was $1,699 at launch but is now $2,799 — verify current pricing.
- **AliExpress** prices for Strix Halo are often HIGHER than brand stores.
- **Minisforum MS-01 + DIY 128GB DDR5** is cheap (~$700) but gives only 3-10 tok/s — do NOT recommend as a primary LLM machine without a GPU add-on plan.
- **Exchange rate lookup:** use scrape with `https://www.google.com/search?q=USD+to+COP+exchange+rate` for current rates.
- **Always include direct store links** in every recommendation — the user wants to click through to buy/quote immediately.

## Non-Strix Halo alternatives for tight budgets

When 128GB unified memory is out of budget (under $1,800), offer these alternatives:

| Machine | CPU | RAM type | Exp? | PCIe slot | Price | LLM tok/s |
|---------|-----|---------|------|-----------|-------|-----------|
| **MS-01** | i9-13900H | DDR5 SO-DIMM | ✅ 128GB | ✅ x4 | ~$700 | 3-10 CPU |
| **MS-A2** | Ryzen 9 9955HX | DDR5 SO-DIMM | ✅ 128GB | ✅ x16 | ~$1,125 | 3-10 CPU |
| **MS-02 Ultra** | Ultra 9 285HX | DDR5 4 slots | ✅ 256GB | ✅ x16 5.0 | ~$1,159 | 5-12 CPU |
| **HP Z2 G9 used** | i9-14900K | DDR5 | ❌ (comes with) | ✅ RTX incl. | ~$1,500 | **30-40 GPU** |

All four have **expandable RAM** and a **PCIe slot** for adding a dedicated GPU later — the GPU route gives Strix Halo-level inference speeds.

## Apple Silicon alternatives (Mac Mini M5)

| Machine | Chip | RAM type | Max RAM | Bandwidth | Price | LLM max |
|---------|------|---------|---------|-----------|-------|---------|
| **Mac Mini M5** | Apple M5 | LPDDR5X soldada ❌ | 24GB | 153 GB/s | ~$799 | ~15B |
| **Mac Mini M5 Pro** | Apple M5 Pro | LPDDR5X soldada ❌ | 48GB | 307 GB/s | ~$1,399 | ~34B |

⚠️ **Not yet released** as of July 2026 (delayed to late 2026). Good for macOS-specific tools and compact secondary machines, but RAM is soldered and maxes at 48GB — a downgrade for LLM work vs Strix Halo 128GB. See `references/mac-mini-m5.md` for full specs and pricing.

## User preference: include direct store links

When presenting recommendations, always include clickable store links:
- Amazon: `https://www.amazon.com/s?k={model-name}+128GB`
- Brand store: direct product page URL
- eBay (for used): `https://www.ebay.com/sch/i.html?_nkw={model-name}+128GB`
- Minisforum: `https://store.minisforum.com/`
- Framework: `https://frame.work/desktop`

## Reference files
- `references/strix-halo-128gb-models.md` — complete catalogue of all Strix Halo 128GB machines with prices, specs, and links.
- `references/mac-mini-m5.md` — Mac Mini M5/M5 Pro specs, pricing in COP, and LLM workload comparison.
