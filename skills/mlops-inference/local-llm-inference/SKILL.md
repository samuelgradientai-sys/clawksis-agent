---
name: local-llm-inference
description: "Run, serve, customize, and discover LLMs locally: llama.cpp GGUF inference, vLLM high-throughput serving, HuggingFace model management, abliteration, and model discovery/evaluation."
version: 1.0.0
author: Clawksis (consolidated)
license: MIT
platforms: [linux, macos]
metadata:
  clawk:
    tags: [llm, inference, serving, quantization, llama-cpp, vllm, huggingface, models, abliteration, evaluation]
    related_skills: [local-llm-hardware, model-fallback]
---

# Local LLM Inference & Model Management

> **Umbrella skill** — covers running models locally (llama.cpp), high-throughput serving (vLLM), model management (HuggingFace Hub), abliteration (obliteratus), and model discovery/evaluation. Each subtopic has a detailed reference file.

## Quick Start

```bash
# Which tool to use?
# llama.cpp:     single-user local inference, GGUF format, CPU/GPU
# vLLM:          multi-user serving, OpenAI-compatible API, production
# obliteratus:   remove refusals from a model (diff-in-means)
# hf (Hub CLI):  download/upload models, datasets, Spaces
# model-discovery: research models by name, compare specs
```

## Subtopic References

| Topic | Reference | What It Covers |
|-------|-----------|----------------|
| **llama.cpp** | `references/llama-cpp.md` | GGUF inference, quantization, Python bindings, CLI, server mode |
| **vLLM** | `references/vllm.md` | High-throughput serving, OpenAI API, quantization, multi-GPU |
| **Obliteratus** | `references/obliteratus.md` | Abliterate refusals via diff-in-means, before/after comparison |
| **HuggingFace Hub** | `references/huggingface-hub.md` | `hf` CLI: search, download, upload models/datasets/Spaces |
| **Model Discovery** | `references/model-discovery.md` | Find models by name/capability, read config.json for architecture |
| **Model Evaluation** | `references/llm-evaluation.md` | lm-eval-harness benchmarks (MMLU, GSM8K), W&B experiment tracking |
