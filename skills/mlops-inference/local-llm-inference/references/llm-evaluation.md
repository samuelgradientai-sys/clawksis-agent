# LLM Evaluation (lm-eval-harness + W&B)

> Absorbed from `evaluating-llms-harness` and `weights-and-biases` skills.

## lm-eval-harness

Benchmark LLMs on standard tasks (MMLU, GSM8K, HumanEval, etc.).

```bash
pip install lm-eval

# Basic evaluation
lm_eval --model hf --model_args pretrained=meta-llama/Llama-3.1-8B \
  --tasks mmlu,gsm8k --num_fewshot 5 \
  --output_path ./results

# With local GGUF (using llama.cpp)
lm_eval --model local-completions --model_args model=mymodel.gguf \
  --tasks mmlu --batch_size 32

# With vLLM
lm_eval --model vllm \
  --model_args pretrained=model-name,tensor_parallel_size=1 \
  --tasks mmlu
```

## W&B Experiment Tracking

```bash
pip install wandb
wandb login  # set API key

# In Python
import wandb
wandb.init(project="llm-eval", name="run-1")
wandb.config.update({"model": "Llama-3.1-8B", "lr": 1e-5})
wandb.log({"mmlu": 0.68, "gsm8k": 0.72})
wandb.finish()
```

## Sweeps (W&B Hyperparameter Tuning)

```yaml
# sweep.yaml
program: train.py
method: bayes
metric: {name: mmlu, goal: maximize}
parameters:
  lr: {min: 1e-6, max: 1e-4}
  batch_size: {values: [8, 16, 32]}
```

```bash
wandb sweep sweep.yaml
wandb agent <sweep-id>
```
