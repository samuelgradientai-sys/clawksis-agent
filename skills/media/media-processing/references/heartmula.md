# HeartMuLa — Open-Source Music Generation

> Absorbed from `heartmula` skill.

## Overview

Open-source music generation (Apache-2.0) from lyrics + tags. Comparable to Suno.

## Setup

```bash
git clone https://github.com/HeartMuLa/heartlib.git
cd heartlib
uv venv --python 3.10 .venv
. .venv/bin/activate
uv pip install -e .
uv pip install --upgrade datasets transformers
```

## Download Models

```bash
hf download --local-dir './ckpt' 'HeartMuLa/HeartMuLaGen'
hf download --local-dir './ckpt/HeartMuLa-oss-3B' 'HeartMuLa/HeartMuLa-oss-3B-happy-new-year'
hf download --local-dir './ckpt/HeartCodec-oss' 'HeartMuLa/HeartCodec-oss-20260123'
```

## Generate

```bash
python ./examples/run_music_generation.py \
  --model_path=./ckpt --version="3B" \
  --lyrics="./assets/lyrics.txt" \
  --tags="./assets/tags.txt" \
  --save_path="./assets/output.mp3" \
  --lazy_load true
```

## Hardware
- 3B model peaks at ~6.2GB VRAM with `--lazy_load true`
- Multi-GPU: `--mula_device cuda:0 --codec_device cuda:1`
- CPU is possible but extremely slow (30-60+ minutes)
