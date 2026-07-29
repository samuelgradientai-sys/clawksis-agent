# Obliteratus — Abliterate LLM Refusals

> Absorbed from `obliteratus` skill.

## Overview

Remove safety refusals from LLMs without retraining. Uses the diff-in-means method: find refusal direction in the residual stream, ablate it during forward pass.

## Installation

```bash
pip install obliteratus torch transformers bitsandbytes accelerate safetensors
```

## Usage

```bash
# Abliterate a model
obliterate --model_path meta-llama/Llama-3.1-8B-Instruct \
  --save_path ./abliterated-model

# Test before/after comparison
obliterate --model_path ./abliterated-model --test
```

## Programmatic Use

```python
from obliteratus import ObliterationConfig, abliterate_model

config = ObliterationConfig(
    model_name="meta-llama/Llama-3.1-8B-Instruct",
    refusal_layer_range=(6, 10),  # layers to scan for refusal direction
)
abliterated = abliterate_model(config)
```

## Key Parameters
- `refusal_layer_range` — which layers to scan (default: last ~40%)
- `--quantize bitsandbytes-4bit` — 4-bit to save VRAM
- `--model_dtype bfloat16` — precision

## Pitfalls
- Does NOT work on all architectures (tested on Llama-family)
- Abliteration is a research technique, not production-grade
- Some models may lose useful refusals (e.g., NSFW content filters)
