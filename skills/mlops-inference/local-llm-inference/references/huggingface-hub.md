# HuggingFace Hub CLI (`hf`)

> Absorbed from `huggingface-hub` skill.

## Quick Start

```bash
# Install
curl -LsSf https://hf.co/cli/install.sh | bash -s

# Auth
export HF_TOKEN=hf_...
# Or use `huggingface-cli login`

# Search models
hf model list --query "llama 3" --limit 5

# Download
hf model download meta-llama/Llama-3.2-1B --local-dir ./models

# Upload
hf model upload my-org/my-model ./path/to/model
```

## Key Commands

```bash
# Search datasets
hf dataset list --query "squad"

# Create a Space
hf space create my-space --type gradio

# List files in a repo
hf ls meta-llama/Llama-3.2-1B

# File info
hf file-info meta-llama/Llama-3.2-1B config.json
```

All the `hf` commands replace the deprecated `huggingface-cli` commands.
