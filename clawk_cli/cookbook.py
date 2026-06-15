"""Local-models Cookbook — "what can my machine run, and run it".

Inspired by Odysseus's Cookbook (AGPL — concept only, not its code/catalog):

  1. A curated catalog of open LLMs that run well locally (our own data).
  2. Hardware detection (RAM / CPU / GPU+VRAM).
  3. A fit recommender — for each model, does it fit on GPU / via CPU / not at all,
     and a tier (perfect / good / marginal / no_fit).
  4. Run it via **Ollama** (pull) and wire it as the agent's model — Clawksis
     already speaks to a local OpenAI-compatible server, so "use it" just points
     the model config at http://localhost:11434/v1 with the ollama tag.

Shared by the `clawk cookbook` CLI and the dashboard `/api/cookbook/*` endpoints.
All detection is best-effort and never raises into a caller.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import threading
import urllib.request
from typing import Any, Dict, List, Optional

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_OPENAI_URL = "http://localhost:11434/v1"

# Headroom multiplier: a model is only "perfect" with >=1.3x the memory it needs.
_PERFECT_HEADROOM = 1.3
_GOOD_RAM_HEADROOM = 1.5


def _m(
    name: str,
    family: str,
    params_b: float,
    tag: str,
    ctx: int,
    tool_use: bool,
    use_case: str,
    *,
    size_gb: Optional[float] = None,
    vram: Optional[float] = None,
    ram: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a catalog entry, deriving rough Q4 memory needs from param count."""
    sz = size_gb if size_gb is not None else round(params_b * 0.6, 1)
    return {
        "id": tag.replace(":", "-"),
        "name": name,
        "family": family,
        "params_b": params_b,
        "ollama": tag,
        "quant": "Q4_K_M",
        "size_gb": sz,
        # Memory to load + a little runtime overhead (very rough, Q4).
        "min_vram_gb": vram if vram is not None else round(sz + 1.5, 1),
        "min_ram_gb": ram if ram is not None else round(sz + 2.5, 1),
        "context": ctx,
        "tool_use": tool_use,
        "use_case": use_case,
    }


# Curated list of open models that run locally via Ollama. Hand-picked across
# sizes/families; memory figures are rough Q4 estimates for guidance, not a
# guarantee. `tool_use` flags models that reliably do function-calling (the
# agent needs that for most tools).
CATALOG: List[Dict[str, Any]] = [
    # ── tiny (CPU / low VRAM) ───────────────────────────────────────────────
    _m(
        "Qwen2.5 0.5B",
        "Qwen",
        0.5,
        "qwen2.5:0.5b",
        32768,
        True,
        "Tiny, tools, CPU-friendly",
    ),
    _m("Llama 3.2 1B", "Llama", 1.0, "llama3.2:1b", 131072, True, "Tiny chat + tools"),
    _m("Gemma 2 2B", "Gemma", 2.0, "gemma2:2b", 8192, False, "Small, fast chat"),
    _m("Qwen2.5 3B", "Qwen", 3.0, "qwen2.5:3b", 32768, True, "Small, tools"),
    _m("Llama 3.2 3B", "Llama", 3.0, "llama3.2:3b", 131072, True, "Small chat + tools"),
    _m("Phi-3 Mini 3.8B", "Phi", 3.8, "phi3:3.8b", 131072, False, "Small reasoning"),
    # ── small (8–9B, the sweet spot) ────────────────────────────────────────
    _m(
        "Qwen2.5 7B",
        "Qwen",
        7.6,
        "qwen2.5:7b",
        32768,
        True,
        "General + tools (great default)",
    ),
    _m("Llama 3.1 8B", "Llama", 8.0, "llama3.1:8b", 131072, True, "General + tools"),
    _m("Mistral 7B", "Mistral", 7.2, "mistral:7b", 32768, True, "General + tools"),
    _m(
        "Qwen2.5-Coder 7B",
        "Qwen",
        7.6,
        "qwen2.5-coder:7b",
        32768,
        True,
        "Coding + tools",
    ),
    _m(
        "DeepSeek-R1 8B",
        "DeepSeek",
        8.0,
        "deepseek-r1:8b",
        65536,
        False,
        "Reasoning (distilled)",
    ),
    _m("Gemma 2 9B", "Gemma", 9.0, "gemma2:9b", 8192, False, "Strong small chat"),
    # ── medium (12–34B, needs a real GPU or lots of RAM) ────────────────────
    _m(
        "Mistral Nemo 12B",
        "Mistral",
        12.2,
        "mistral-nemo:12b",
        131072,
        True,
        "Long-context + tools",
    ),
    _m("Phi-4 14B", "Phi", 14.7, "phi4:14b", 16384, False, "Strong reasoning"),
    _m(
        "Qwen2.5 14B",
        "Qwen",
        14.8,
        "qwen2.5:14b",
        32768,
        True,
        "Capable general + tools",
    ),
    _m(
        "DeepSeek-R1 14B",
        "DeepSeek",
        14.8,
        "deepseek-r1:14b",
        65536,
        False,
        "Reasoning",
    ),
    _m("Gemma 2 27B", "Gemma", 27.0, "gemma2:27b", 8192, False, "Large chat"),
    _m("Qwen2.5 32B", "Qwen", 32.5, "qwen2.5:32b", 32768, True, "High quality + tools"),
    _m(
        "Qwen2.5-Coder 32B",
        "Qwen",
        32.5,
        "qwen2.5-coder:32b",
        32768,
        True,
        "Top local coding",
    ),
    _m(
        "DeepSeek-R1 32B",
        "DeepSeek",
        32.8,
        "deepseek-r1:32b",
        65536,
        False,
        "Strong reasoning",
    ),
    _m("Command R 35B", "Cohere", 35.0, "command-r:35b", 131072, True, "RAG + tools"),
    # ── large (needs a workstation GPU / big unified memory) ─────────────────
    _m(
        "Mixtral 8x7B",
        "Mistral",
        46.7,
        "mixtral:8x7b",
        32768,
        True,
        "MoE, fast for size",
        size_gb=26.0,
    ),
    _m(
        "Llama 3.3 70B",
        "Llama",
        70.0,
        "llama3.3:70b",
        131072,
        True,
        "Frontier-ish + tools",
        size_gb=43.0,
    ),
    _m(
        "Qwen2.5 72B",
        "Qwen",
        72.7,
        "qwen2.5:72b",
        32768,
        True,
        "Top quality + tools",
        size_gb=47.0,
    ),
    _m(
        "DeepSeek-R1 70B",
        "DeepSeek",
        70.0,
        "deepseek-r1:70b",
        65536,
        False,
        "Top reasoning",
        size_gb=43.0,
    ),
]


# ── hardware detection ────────────────────────────────────────────────────────


def _detect_gpu() -> Dict[str, Any]:
    """Best-effort discrete-GPU + VRAM detection. Returns {name, vram_gb}."""
    # NVIDIA (Linux/Windows) — nvidia-smi.
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run(
                [smi, "--query-gpu=memory.total,name", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=6,
            )
            if out.returncode == 0 and out.stdout.strip():
                # Sum VRAM across identical GPUs; report the first name.
                best_name = ""
                total_mb = 0
                for line in out.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        try:
                            total_mb += float(parts[0])
                        except ValueError:
                            continue
                        if not best_name:
                            best_name = parts[1]
                if total_mb > 0:
                    return {
                        "name": best_name or "NVIDIA GPU",
                        "vram_gb": round(total_mb / 1024, 1),
                    }
        except Exception:
            pass

    # Apple Silicon — unified memory acts as the GPU budget (~70% usable).
    if platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}:
        try:
            mem = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            total = int(mem.stdout.strip()) if mem.returncode == 0 else 0
            if total > 0:
                return {
                    "name": "Apple Silicon (unified)",
                    "vram_gb": round((total / (1024**3)) * 0.7, 1),
                    "unified": True,
                }
        except Exception:
            pass

    return {"name": "", "vram_gb": 0.0}


def detect_hardware() -> Dict[str, Any]:
    """Detect RAM / CPU / GPU. Never raises; missing pieces default to 0/empty."""
    ram_gb = 0.0
    cpu_cores = os.cpu_count() or 0
    try:
        import psutil

        ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:
        try:
            # Linux fallback.
            with open("/proc/meminfo", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemTotal:"):
                        ram_gb = round(int(line.split()[1]) / (1024**2), 1)
                        break
        except Exception:
            ram_gb = 0.0

    gpu = _detect_gpu()
    return {
        "ram_gb": ram_gb,
        "cpu_cores": cpu_cores,
        "gpu_name": gpu.get("name", ""),
        "vram_gb": gpu.get("vram_gb", 0.0),
        "unified_memory": bool(gpu.get("unified")),
        "platform": platform.system(),
        "arch": platform.machine(),
    }


# ── fit / recommender ─────────────────────────────────────────────────────────


def fit_model(model: Dict[str, Any], hw: Dict[str, Any]) -> Dict[str, Any]:
    """Decide whether *model* fits *hw*: run mode + tier.

    mode: "gpu" | "cpu" | "none"; tier: "perfect" | "good" | "marginal" | "no_fit".
    """
    vram = float(hw.get("vram_gb") or 0)
    ram = float(hw.get("ram_gb") or 0)
    need_vram = float(model["min_vram_gb"])
    need_ram = float(model["min_ram_gb"])

    # GPU path (discrete VRAM, or Apple unified budget).
    if vram > 0 and vram >= need_vram:
        tier = "perfect" if vram >= need_vram * _PERFECT_HEADROOM else "good"
        return {"mode": "gpu", "tier": tier, "reason": f"fits {need_vram:g}GB VRAM"}

    # CPU / RAM path (slower, but works).
    if ram >= need_ram:
        tier = "good" if ram >= need_ram * _GOOD_RAM_HEADROOM else "marginal"
        # Big models on CPU are technically loadable but painfully slow → marginal.
        if model["params_b"] >= 30:
            tier = "marginal"
        return {
            "mode": "cpu",
            "tier": tier,
            "reason": f"runs on CPU/RAM ({need_ram:g}GB)",
        }

    return {"mode": "none", "tier": "no_fit", "reason": f"needs ~{need_ram:g}GB RAM"}


_TIER_RANK = {"perfect": 0, "good": 1, "marginal": 2, "no_fit": 3}


def catalog_with_fit(
    hw: Optional[Dict[str, Any]] = None, installed: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Return the catalog enriched with a per-model fit verdict + installed flag.

    Sorted by: best fit → tool-capable first → larger first. Tool-capable wins
    within a tier because the agent needs function-calling for most tasks; a
    no-tools model (e.g. phi3, gemma2) errors the moment a tool is invoked.
    """
    hw = hw or detect_hardware()
    installed_set = set(installed or [])
    rows: List[Dict[str, Any]] = []
    for model in CATALOG:
        fit = fit_model(model, hw)
        rows.append({
            **model,
            "fit": fit,
            "installed": model["ollama"] in installed_set,
        })
    rows.sort(
        key=lambda r: (
            _TIER_RANK.get(r["fit"]["tier"], 9),
            0 if r["tool_use"] else 1,
            -r["params_b"],
        )
    )
    return rows


# ── Ollama integration ────────────────────────────────────────────────────────


def ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def ollama_running() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=2) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def ollama_models() -> List[str]:
    """Tags currently pulled into the local Ollama (e.g. ['qwen2.5:7b'])."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode())
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def ollama_status() -> Dict[str, Any]:
    return {
        "installed": ollama_installed(),
        "running": ollama_running(),
        "models": ollama_models(),
        "base_url": OLLAMA_OPENAI_URL,
    }


# Background pull tracking: tag -> "pulling" | "done" | "error: ...".
_pull_status: Dict[str, str] = {}
_pull_lock = threading.Lock()


def pull_status(tag: str) -> str:
    with _pull_lock:
        return _pull_status.get(tag, "")


def _do_pull(tag: str) -> None:
    try:
        proc = subprocess.run(
            ["ollama", "pull", tag], capture_output=True, text=True, timeout=3600
        )
        with _pull_lock:
            _pull_status[tag] = (
                "done"
                if proc.returncode == 0
                else ("error: " + (proc.stderr or "pull failed").strip()[:200])
            )
    except Exception as exc:
        with _pull_lock:
            _pull_status[tag] = f"error: {exc}"


def start_pull(tag: str) -> Dict[str, Any]:
    """Kick off `ollama pull <tag>` in the background. Returns immediately."""
    if not ollama_installed():
        return {"ok": False, "error": "ollama is not installed (see ollama.com)."}
    with _pull_lock:
        if _pull_status.get(tag) == "pulling":
            return {"ok": True, "status": "pulling", "tag": tag}
        _pull_status[tag] = "pulling"
    threading.Thread(
        target=_do_pull, args=(tag,), name=f"ollama-pull-{tag}", daemon=True
    ).start()
    return {"ok": True, "status": "pulling", "tag": tag}


def pull_blocking(tag: str) -> Dict[str, Any]:
    """Pull synchronously (for the CLI). Returns {ok, error?}."""
    if not ollama_installed():
        return {"ok": False, "error": "ollama is not installed (see ollama.com)."}
    try:
        proc = subprocess.run(["ollama", "pull", tag], timeout=3600)
        return {"ok": proc.returncode == 0}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def use_model(tag: str) -> Dict[str, Any]:
    """Point the agent's model config at a local Ollama model (OpenAI-compatible).

    Reuses Clawksis's custom-provider support: provider=custom + base_url at the
    Ollama /v1 endpoint + the tag as the model name.
    """
    try:
        from clawk_cli.config import load_config, save_config

        config = load_config()
        model_cfg = config.get("model")
        if not isinstance(model_cfg, dict):
            model_cfg = {}
        model_cfg.update({
            "provider": "custom",
            "default": tag,
            "base_url": OLLAMA_OPENAI_URL,
            "api_key": "ollama",  # ollama ignores it; a non-empty value avoids prompts
        })
        config["model"] = model_cfg
        save_config(config)
        return {
            "ok": True,
            "provider": "custom",
            "model": tag,
            "base_url": OLLAMA_OPENAI_URL,
        }
    except Exception as exc:
        return {"ok": False, "error": f"failed to set model: {exc}"}
