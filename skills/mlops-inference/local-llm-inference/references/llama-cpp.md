# llama.cpp — Local GGUF Inference

> Absorbed from `llama-cpp` skill.

## Installation

```bash
pip install llama-cpp-python  # or with specific backend:
CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python  # CUDA
CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python  # Apple Metal
```

Or use the CLI directly: download from https://github.com/ggusggml/llama.cpp/releases.

## Usage

```python
from llama_cpp import Llama
llm = Llama(model_path="model.gguf", n_ctx=4096)
output = llm("Q: What is 2+2? A:", max_tokens=32)
print(output["choices"][0]["text"])
```

## CLI

```bash
# Basic chat
./llama-cli -m model.gguf -p "Hello, how are you?" -n 128

# Interactive chat
./llama-cli -m model.gguf --interactive

# Server mode (OpenAI-compatible API)
./llama-server -m model.gguf --host 0.0.0.0 --port 8080
```

## Key Parameters
- `--temp 0.7` — temperature
- `--top-k 40`, `--top-p 0.9` — sampling
- `--ctx-size 4096` — context window
- `--ngl 48` — GPU layers (offload to GPU)
- `-ngl 0` — CPU only
