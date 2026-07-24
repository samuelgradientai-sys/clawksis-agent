# Minisforum MS-S1 Max — Full Specifications

## CPU
- **Model**: AMD Ryzen™ AI Max+ 395 (Strix Halo)
- **Cores/Threads**: 16C / 32T
- **Max Clock**: 5.1 GHz
- **TDP**: 130W sustained / 160W peak
- **NPU**: 50 TOPS
- **Total AI**: 126 TOPS

## RAM
- **Capacity**: 128GB LPDDR5X-8000 MT/s
- **Architecture**: Quad-channel Unified Memory Architecture (UMA)
- **Expandable**: ❌ NO (soldered on board)

## GPU
- **Graphics**: AMD Radeon 8060S (RDNA 3.5)
- **Performance**: ~RTX 4070 Laptop-class

## Storage
- **Slots**: 2x M.2 NVMe (PCIe 4.0 x4 + x1)
- **Max capacity**: Up to 16TB (8TB + 8TB)
- **RAID**: 0/1

## Ports (Front)
- 2x USB4 (40 Gbps, Alt DP2.0, PD 15W)
- 1x USB 3.2 Gen2 (10 Gbps)
- 1x 3.5mm audio combo jack
- 2x DMIC (AI noise-cancelling mic)

## Ports (Rear)
- 2x USB4 V2 (80 Gbps, Alt DP2.0, PD 15W)
- 2x USB 2.0
- 1x USB 3.2 Gen2 (10 Gbps)
- 1x HDMI 2.1 FRL (8K@60Hz / 4K@120Hz)
- 2x 10GbE LAN (Realtek RTL8127)
- Power button, reset hole (clear CMOS), anti-theft lock

## Expansion
- **PCIe x16**: 1x full-length slot
- **OCuLink**: ✅ Supported via DEG2 eGPU Dock (optional)

## Networking
- **Ethernet**: Dual 10GbE RJ45
- **Wi-Fi**: Wi-Fi 7
- **Bluetooth**: 5.4

## Physical
- **Chassis**: Aerospace-grade aluminum
- **Design**: Slide-out tray (easy maintenance)
- **Orientation**: Vertical or horizontal
- **Rack support**: ✅ 2U, up to 4-unit cluster
- **PSU**: 320W internal (CCC, FCC, UL, CE, UKCA certified)
- **Cooling**: Copper base + 6 heat pipes + dual turbine fans + phase-change material

## Power Modes
| Mode | TDP | Use case |
|------|-----|----------|
| Performance | 130W sustained / 160W peak | Intensive AI inference |
| Balanced | 95W | Daily driving |
| Quiet | 60W | Low-noise / office |
| Rack | — | Cluster deployment |

## AI Workload Capacity
With 128GB shared (UMA, ~112GB usable after OS):
- **Qwen 72B Q4_K_M** (~45GB) ✅
- **DeepSeek Coder 33B Q8** (~33GB) ✅
- **Llama 4 70B Q4_K_M** (~42GB) ✅
- **Dual-model**: 72B + 33B simultaneously (~78GB total) ✅
- **Cluster (4 units)**: DeepSeek-R1 671B Q4 (380GB) — tested by Minisforum

## References
- Official product page: https://www.minisforum.com/products/ms-s1-max
- Minisforum store: https://store.minisforum.com/products/minisforum-ms-s1-max-mini-pc
- ServeTheHome review: https://www.servethehome.com/minisforum-ms-s1-max-review-the-best-ryzen-ai-max-mini-pc-yet/
