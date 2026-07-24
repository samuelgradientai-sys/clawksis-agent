# Minisforum MS-S1 Max — Complete Technical Specifications

## Overview
The MS-S1 Max is the flagship AI workstation from Minisforum, powered by AMD Strix Halo APU. Primary machine for self-hosted Clawksis and local LLM inference.

## CPU
| Spec | Value |
|------|-------|
| **Processor** | AMD Ryzen™ AI Max+ 395 (Strix Halo) |
| **Cores/Threads** | 16C / 32T |
| **Max Clock** | 5.1 GHz |
| **TDP** | 130W sustained / 160W peak |
| **NPU** | 50 TOPS |
| **Total AI Performance** | 126 TOPS |

## Memory
| Spec | Value |
|------|-------|
| **Capacity** | 128GB LPDDR5X-8000 MT/s |
| **Architecture** | Quad-channel UMA (Unified Memory Architecture) |
| **Expandable** | ❌ Soldered (not user-upgradeable) |

## GPU
| Spec | Value |
|------|-------|
| **Graphics** | AMD Radeon 8060S (RDNA 3.5) |
| **Performance** | Comparable to RTX 4070 Laptop GPU |

## Storage
| Spec | Value |
|------|-------|
| **Slots** | 2x M.2 (PCIe 4.0 x4 + PCIe 4.0 x1) |
| **Max Capacity** | Up to 16TB (8TB + 8TB) |
| **RAID Support** | RAID 0 / 1 |

## I/O Ports
| Port | Qty | Spec |
|------|-----|------|
| **USB4 V2** | 2 (rear) | 80 Gbps, Alt DP2.0, PD 15W |
| **USB4** | 2 (front) | 40 Gbps, Alt DP2.0, PD 15W |
| **USB 3.2 Gen2** | 2 (1 front + 1 rear) | 10 Gbps |
| **USB 2.0** | 2 (rear) | |
| **HDMI 2.1 FRL** | 1 (rear) | 8K@60Hz / 4K@120Hz |
| **Audio** | 1 combo jack | 3.5mm |
| **DMIC** | 2 | AI noise-cancelling microphones |

## Networking
| Spec | Value |
|------|-------|
| **Ethernet** | Dual 10GbE (Realtek RTL8127) |
| **Wi-Fi** | Wi-Fi 7 |
| **Bluetooth** | 5.4 |

## Expansion
| Spec | Value |
|------|-------|
| **PCIe x16** | 1 full-length slot (GPU, capture card, NIC, etc.) |
| **OCuLink** | ✅ Via DEG2 eGPU Dock (separate, ~$240) |

## Physical
| Spec | Value |
|------|-------|
| **Chassis** | Aerospace-grade aluminum |
| **Design** | Slide-out tray for easy maintenance |
| **Orientation** | Vertical (desktop) or horizontal (rack) |
| **Rack Support** | 2U, up to 4 units in cluster |
| **PSU** | 320W internal (CCC, FCC, UL, CE, UKCA certified) |
| **Cooling** | Copper base + 6 heat pipes + dual turbine fans + PCM |

## Power Modes
| Mode | TDP |
|------|-----|
| **Performance** | 130W sustained |
| **Balanced** | 95W |
| **Quiet** | 60W |
| **Rack** | Cluster-optimized |

## Usage for Self-Hosted Clawksis + Local LLMs

With 128GB UMA memory, this machine can run:

| Model | Quant | VRAM Est. | Notes |
|-------|-------|-----------|-------|
| Qwen 72B | Q4_K_M | ~45 GB | Primary security review model |
| DeepSeek Coder 33B | Q8 | ~33 GB | Code analysis |
| Llama 4 70B | Q4_K_M | ~40 GB | Second opinion |
| Mistral Small 22B | Q8 | ~22 GB | Fast lightweight option |
| System + Clawksis | — | ~10-15 GB | OS, tools, skills |

**Practical limit:** Run 2-3 models simultaneously. Total 128GB requires careful allocation.
**For larger models (235B+):** Cluster multiple MS-S1 Max units via 10GbE rack setup.
