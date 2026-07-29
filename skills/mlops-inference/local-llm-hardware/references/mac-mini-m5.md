# Apple Mac Mini M5/M5 Pro for AI/LLM (as of July 2026)

All prices in USD. Mac Mini M5 NOT YET RELEASED — delayed to late 2026.

## Release Status
- **Not announced at WWDC** (June 8, 2026) as expected
- Bloomberg (Mark Gurman): shifted from H1 2026 to **later in 2026**
- Supply constraints: chip shortages, memory supply competing with AI data centers
- Base M4 model (16GB/256GB at $599) **discontinued** May 2026

## Pricing (rumored/leak consensus)

| SKU | Rumored Price | COP (≈3,300/USD) | Notes |
|-----|--------------|-------------------|-------|
| M5 16GB/512GB | ~$699–799 | ~$2.3–2.6M | New base config |
| M5 24GB/512GB | ~$899 | ~$2.9M | Sweet spot for light AI |
| M5 Pro 24GB/512GB | ~$999–1,099 | ~$3.3–3.6M | Thunderbolt 5 |
| M5 Pro 48GB/1TB | ~$1,399–1,499 | ~$4.6–4.9M 🔴 | Exceeds 4M COP |

## Specs: M5 vs M5 Pro

| Spec | Mac Mini M5 | Mac Mini M5 Pro |
|------|------------|-----------------|
| **Process** | TSMC N3P (3nm) | Same die, higher bin |
| **CPU cores** | 6P + 4E (rumored) | 8–10P + 4E (rumored) |
| **GPU cores** | 8–10 | 14–20 |
| **Neural Engine** | ~18 TOPS class uplift | Higher sustained clocks |
| **Unified memory** | 16GB entry → 24GB max | 24GB → 48GB max |
| **Memory bandwidth** | **153 GB/s** | **307 GB/s** |
| **RAM type** | LPDDR5X soldered ❌ | LPDDR5X soldered ❌ |
| **Storage** | 512GB base (up to 4TB) | 512GB base (up to 8TB) |
| **Thunderbolt** | Thunderbolt 4 | Thunderbolt 5 |
| **Networking** | Gigabit (10Gb optional) | 10Gb standard (rumored) |
| **Wireless** | Wi-Fi 6E, BT 5.3 | Wi-Fi 7, BT 6 |
| **Chassis** | Same M4 compact | Same shell |

## For AI/LLM workloads

### What fits in RAM

| RAM | Max model size (Q4_K_M) | Examples |
|-----|------------------------|----------|
| 16GB | ~9B | Gemma 4 9B, Llama 3.1 8B |
| 24GB | ~15B | Qwen 3 15B, Mistral 7B with context |
| 48GB | ~34B | Qwen 3 30B, CodeGemma 27B |

### vs Strix Halo (user's current MS-S1 Max)

| Metric | Mac Mini M5 Pro 48GB | MS-S1 Max 128GB |
|--------|---------------------|-----------------|
| **Max LLM size** | ~34B | **~70B** 🚀 |
| **Bandwidth** | 307 GB/s | 256 GB/s |
| **RAM** | 48GB max | **128GB** 🚀 |
| **NPU TOPS** | ~18 | ~50 (XDNA 2) |
| **OCuLink/eGPU** | ❌ | ✅ Sí |
| **10GbE** | Incluido (Pro) | ✅ Dual |
| **Price** | ~$1,399 | $2,599 (when available) |

### Key takeaway
- **Mac Mini M5:** good for small models (<15B), not released yet, RAM hard-capped at 24GB
- **Mac Mini M5 Pro:** decent for mid-size models (<34B), ~$1,399 for 48GB, but soldered RAM (no future upgrade)
- **Vs Strix Halo:** user's MS-S1 Max with 128GB can run 70B models — M5 Pro is a downgrade for LLM work
- **Only buy if:** you need a compact secondary machine for small models, macOS-specific tools, or Xcode. For pure LLM inference, the MS-02 Ultra ($1,159 + RAM) or MS-A2 ($799 + RAM) offers expandable RAM + PCIe GPU slot at a similar or lower price.
