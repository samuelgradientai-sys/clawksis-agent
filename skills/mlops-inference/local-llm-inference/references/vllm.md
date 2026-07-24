# vLLM — High-Throughput LLM Serving

> Absorbed from `serving-llms-vllm` skill.

## Overview

vLLM provides high-throughput LLM serving with PagedAttention, continuous batching, and OpenAI-compatible API.

## Quick Start

```bash
pip install vllm

# One-shot generation
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --port 8000

# Query (OpenAI-compatible)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"meta-llama/Llama-3.1-8B-Instruct","messages":[{"role":"user","content":"Hello"}]}'
```

## Quantization

```bash
# AWQ quantized models
--quantization awq --model path/to/awq-model

# FP8 (H100+)
--quantization fp8

# GPTQ
--quantization gptq
```

## Multi-GPU

```bash
# Tensor parallelism
--tensor-parallel-size 2

# Pipeline parallelism
--pipeline-parallel-size 2
```

## Key Parameters
- `--max-model-len` — max sequence length (reduces memory)
- `--gpu-memory-utilization 0.9` — fraction of GPU memory to use
- `--enforce-eager` — disable CUDA graph (debug, lower perf)
- `--dtype auto` — half/float/bfloat
