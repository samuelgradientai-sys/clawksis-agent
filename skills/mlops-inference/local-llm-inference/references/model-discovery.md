# Model Discovery

> Absorbed from `model-discovery` skill.

## Workflow

When someone asks about a specific model — can it run locally, how much RAM, what architecture, how it compares:

### Step 1: Find on HuggingFace

```bash
# Search by name
hf model list --query "Qwen 3 30B" --limit 5

# Get config.json to see architecture
hf file-info Qwen/Qwen3-30B config.json
# Then download and read it
hf download Qwen/Qwen3-30B config.json
```

### Step 2: Read config.json for architecture details

```python
import json
with open("config.json") as f:
    cfg = json.load(f)
# Key fields:
print("Architecture:", cfg.get("architectures"))
print("Total params:", cfg.get("num_parameters", "??"))
print("Hidden size:", cfg.get("hidden_size"))
print("Layers:", cfg.get("num_hidden_layers"))
print("Attention heads:", cfg.get("num_attention_heads"))
# MoE models have additional fields:
print("MoE experts:", cfg.get("num_local_experts"))
print("Activated experts:", cfg.get("num_experts_per_tok"))
print("Activated params:", cfg.get("num_activated_parameters", "?"))
```

### Step 3: Estimate RAM for local inference

**Rule of thumb:** ~2GB per 1B parameters at 16-bit, ~0.75GB per 1B at Q4_K_M.

| Precision | GB per 1B params | 7B model | 70B model |
|-----------|-----------------|----------|-----------|
| FP16 | ~2.0 GB | ~14 GB | ~140 GB |
| Q8_0 | ~1.1 GB | ~8 GB | ~80 GB |
| Q4_K_M | ~0.75 GB | ~5.5 GB | ~52 GB |
| Q2_K | ~0.4 GB | ~3 GB | ~28 GB |

For MoE models, use **activated params** (not total): a 141B MoE with 12B activated needs ~9 GB at Q4_K_M.
