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
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
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
    # ── more tool-capable general models ─────────────────────────────────────
    _m("Qwen2.5 1.5B", "Qwen", 1.5, "qwen2.5:1.5b", 32768, True, "Tiny + tools"),
    _m("Qwen3 0.6B", "Qwen", 0.6, "qwen3:0.6b", 40960, True, "Tiny, newer gen + tools"),
    _m("Qwen3 1.7B", "Qwen", 1.7, "qwen3:1.7b", 40960, True, "Tiny + tools"),
    _m("Qwen3 4B", "Qwen", 4.0, "qwen3:4b", 40960, True, "Small + tools"),
    _m("Qwen3 8B", "Qwen", 8.2, "qwen3:8b", 40960, True, "General + tools"),
    _m("Qwen3 14B", "Qwen", 14.8, "qwen3:14b", 40960, True, "Capable + tools"),
    _m("Qwen3 30B-A3B", "Qwen", 30.0, "qwen3:30b-a3b", 40960, True, "MoE, fast + tools", size_gb=18.0),
    _m("Qwen3 32B", "Qwen", 32.8, "qwen3:32b", 40960, True, "High quality + tools"),
    _m("Llama 3.1 70B", "Llama", 70.0, "llama3.1:70b", 131072, True, "Frontier + tools", size_gb=43.0),
    _m("Mistral Small 24B", "Mistral", 24.0, "mistral-small:24b", 32768, True, "Strong + tools"),
    _m("Mixtral 8x22B", "Mistral", 141.0, "mixtral:8x22b", 65536, True, "Big MoE + tools", size_gb=80.0),
    _m("Command R+ 104B", "Cohere", 104.0, "command-r-plus:104b", 131072, True, "RAG + tools (large)", size_gb=62.0),
    _m("Granite 3.1 2B", "IBM", 2.5, "granite3.1-dense:2b", 131072, True, "Small enterprise + tools"),
    _m("Granite 3.1 8B", "IBM", 8.0, "granite3.1-dense:8b", 131072, True, "Enterprise + tools"),
    _m("Hermes 3 8B", "Hermes", 8.0, "hermes3:8b", 131072, True, "Tool-use tuned"),
    _m("Hermes 3 70B", "Hermes", 70.0, "hermes3:70b", 131072, True, "Tool-use tuned (large)", size_gb=43.0),
    _m("Aya Expanse 8B", "Cohere", 8.0, "aya-expanse:8b", 8192, True, "Multilingual + tools"),
    _m("Aya Expanse 32B", "Cohere", 32.0, "aya-expanse:32b", 8192, True, "Multilingual + tools"),
    _m("Nemotron Mini 4B", "NVIDIA", 4.0, "nemotron-mini:4b", 4096, True, "Small + tools"),
    _m("Nemotron 70B", "NVIDIA", 70.0, "nemotron:70b", 131072, True, "Tuned + tools (large)", size_gb=43.0),
    _m("SmolLM2 1.7B", "SmolLM", 1.7, "smollm2:1.7b", 8192, True, "Tiny + tools"),
    # ── more coding models ───────────────────────────────────────────────────
    _m("Qwen2.5-Coder 1.5B", "Qwen", 1.5, "qwen2.5-coder:1.5b", 32768, True, "Tiny coding + tools"),
    _m("Qwen2.5-Coder 3B", "Qwen", 3.0, "qwen2.5-coder:3b", 32768, True, "Small coding + tools"),
    _m("Qwen2.5-Coder 14B", "Qwen", 14.8, "qwen2.5-coder:14b", 32768, True, "Coding + tools"),
    _m("DeepSeek-Coder-V2 16B", "DeepSeek", 16.0, "deepseek-coder-v2:16b", 131072, False, "Coding MoE", size_gb=9.0),
    _m("CodeLlama 7B", "Llama", 7.0, "codellama:7b", 16384, False, "Code completion"),
    _m("CodeLlama 13B", "Llama", 13.0, "codellama:13b", 16384, False, "Code completion", size_gb=7.4),
    _m("CodeLlama 34B", "Llama", 34.0, "codellama:34b", 16384, False, "Code completion", size_gb=19.0),
    _m("StarCoder2 3B", "StarCoder", 3.0, "starcoder2:3b", 16384, False, "Code"),
    _m("StarCoder2 15B", "StarCoder", 15.0, "starcoder2:15b", 16384, False, "Code"),
    # ── more reasoning (DeepSeek-R1 sizes) ──────────────────────────────────
    _m("DeepSeek-R1 1.5B", "DeepSeek", 1.5, "deepseek-r1:1.5b", 65536, False, "Tiny reasoning"),
    _m("DeepSeek-R1 7B", "DeepSeek", 7.0, "deepseek-r1:7b", 65536, False, "Reasoning"),
    _m("DeepSeek-R1 32B", "DeepSeek", 32.8, "deepseek-r1:32b", 65536, False, "Strong reasoning"),
    # ── Gemma 3 + Phi (no tools) ─────────────────────────────────────────────
    _m("Gemma 3 1B", "Gemma", 1.0, "gemma3:1b", 32768, False, "Tiny chat"),
    _m("Gemma 3 4B", "Gemma", 4.0, "gemma3:4b", 131072, False, "Small chat (vision)"),
    _m("Gemma 3 12B", "Gemma", 12.0, "gemma3:12b", 131072, False, "Capable chat"),
    _m("Gemma 3 27B", "Gemma", 27.0, "gemma3:27b", 131072, False, "Large chat", size_gb=16.0),
    _m("Phi-3.5 Mini 3.8B", "Phi", 3.8, "phi3.5:3.8b", 131072, False, "Small reasoning"),
    _m("Phi-4 Mini 3.8B", "Phi", 3.8, "phi4-mini:3.8b", 131072, False, "Small reasoning"),
    # ── vision (multimodal; no tools) ────────────────────────────────────────
    _m("Llama 3.2 Vision 11B", "Llama", 11.0, "llama3.2-vision:11b", 131072, False, "Vision + chat"),
    _m("LLaVA 7B", "LLaVA", 7.0, "llava:7b", 4096, False, "Vision + chat"),
    _m("LLaVA 13B", "LLaVA", 13.0, "llava:13b", 4096, False, "Vision + chat", size_gb=8.0),
    _m("Moondream 1.8B", "Moondream", 1.8, "moondream:1.8b", 2048, False, "Tiny vision"),
    # ── small/older general (no tools) ───────────────────────────────────────
    _m("TinyLlama 1.1B", "TinyLlama", 1.1, "tinyllama:1.1b", 2048, False, "Tiny CPU chat"),
    _m("SmolLM2 360M", "SmolLM", 0.36, "smollm2:360m", 8192, False, "Ultra-tiny"),
    _m("Dolphin 3 8B", "Dolphin", 8.0, "dolphin3:8b", 131072, False, "Uncensored chat"),
    _m("OLMo 2 7B", "OLMo", 7.0, "olmo2:7b", 4096, False, "Open research model"),
    _m("Yi 9B", "Yi", 9.0, "yi:9b", 4096, False, "Bilingual chat"),
    _m("Yi 34B", "Yi", 34.0, "yi:34b", 4096, False, "Bilingual chat", size_gb=19.0),
    _m("Zephyr 7B", "Zephyr", 7.0, "zephyr:7b", 32768, False, "Chat"),
    _m("OpenChat 7B", "OpenChat", 7.0, "openchat:7b", 8192, False, "Chat"),
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

# Family fragments known to support function-calling, used to guess tool_use for
# installed models that aren't in the curated catalog (e.g. anything you pull by
# free-text tag). Conservative: unknown families default to no-tools.
_TOOL_FAMILIES = (
    "qwen2.5",
    "qwen3",
    "llama3.1",
    "llama3.2",
    "llama3.3",
    "mistral",
    "mixtral",
    "command-r",
    "granite3",
    "hermes3",
    "nemotron",
    "aya-expanse",
    "smollm2",
    "firefunction",
    "cogito",
)


def _guess_tool_use(tag: str) -> bool:
    t = tag.lower()
    # llama3.2-vision / llava etc. are multimodal, not tool-callers.
    if "vision" in t or "llava" in t or "moondream" in t:
        return False
    return any(fam in t for fam in _TOOL_FAMILIES)


def _extra_installed_row(tag: str) -> Dict[str, Any]:
    """A synthetic catalog row for a pulled model that isn't in the catalog.

    It's already on disk, so it always "fits"; we just can't know its exact
    size/context, and tool support is a best-effort guess from the name.
    """
    base = tag.split(":", 1)[0]
    return {
        "id": f"installed:{tag}",
        "name": tag,
        "family": base,
        "params_b": 0.0,
        "ollama": tag,
        "quant": "",
        "size_gb": 0.0,
        "min_vram_gb": 0.0,
        "min_ram_gb": 0.0,
        "context": 0,
        "tool_use": _guess_tool_use(tag),
        "use_case": "Pulled locally",
        "fit": {"mode": "cpu", "tier": "good", "reason": "already pulled"},
        "installed": True,
    }


def catalog_with_fit(
    hw: Optional[Dict[str, Any]] = None, installed: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Return the catalog enriched with a per-model fit verdict + installed flag.

    Sorted by: best fit → tool-capable first → larger first. Tool-capable wins
    within a tier because the agent needs function-calling for most tasks; a
    no-tools model (e.g. phi3, gemma2) errors the moment a tool is invoked.

    Any model you've already pulled that isn't in the curated catalog is appended
    too (so anything you `ollama pull` by free-text tag shows up with a Use
    button). The full Ollama library is browsable at ollama.com/library.
    """
    hw = hw or detect_hardware()
    installed_list = list(installed or [])
    installed_set = set(installed_list)
    rows: List[Dict[str, Any]] = []
    catalog_tags = set()
    for model in CATALOG:
        catalog_tags.add(model["ollama"])
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
    # Surface pulled-but-uncatalogued models at the top (they're what you have).
    extras = [
        _extra_installed_row(tag) for tag in installed_list if tag not in catalog_tags
    ]
    return extras + rows


def rows_with_fit(
    rows: List[Dict[str, Any]],
    hw: Optional[Dict[str, Any]] = None,
    installed: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Attach fit verdict + installed flag to arbitrary catalog-shaped rows.

    Used for the live Ollama-library search/browse results (which are already
    catalog-shaped). Rows with unknown size (e.g. a bare ``latest`` tag) get a
    neutral ``unknown`` fit instead of a misleading "fits everything".
    """
    hw = hw or detect_hardware()
    installed_set = set(installed or [])
    out: List[Dict[str, Any]] = []
    for model in rows:
        if model.get("size_gb"):
            fit = fit_model(model, hw)
        else:
            fit = {
                "mode": "unknown",
                "tier": "unknown",
                "reason": "size unknown until pulled",
            }
        out.append({
            **model,
            "fit": fit,
            "installed": model["ollama"] in installed_set,
        })
    out.sort(
        key=lambda r: (
            _TIER_RANK.get(r["fit"]["tier"], 9),
            0 if r["tool_use"] else 1,
            -r["params_b"],
        )
    )
    return out


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


def start_ollama_serve(wait_seconds: float = 12.0) -> bool:
    """Best-effort: ensure the Ollama daemon is running on THIS host (where clawk
    runs), starting it if it's installed but stopped. Returns True if running.

    Models pull/run on the clawk host, so the daemon must be up here. Prefer the
    systemd service the official installer sets up; fall back to spawning
    ``ollama serve`` detached.
    """
    if not ollama_installed():
        return False
    if ollama_running():
        return True
    try:
        subprocess.run(
            ["systemctl", "start", "ollama"], capture_output=True, timeout=15
        )
    except Exception:
        pass
    if not ollama_running():
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if ollama_running():
            return True
        time.sleep(0.5)
    return ollama_running()


# Background Ollama-install tracking (the "we ship Ollama with clawk" path:
# install it on the clawk host on demand so the Cookbook works out of the box).
_ollama_install_status = ""
_ollama_install_lock = threading.Lock()


def ollama_install_status() -> str:
    with _ollama_install_lock:
        return _ollama_install_status


def _do_install_ollama() -> None:
    try:
        sysname = platform.system()
        if sysname == "Linux":
            proc = subprocess.run(
                "curl -fsSL https://ollama.com/install.sh | sh",
                shell=True,
                capture_output=True,
                text=True,
                timeout=1800,
            )
            ok = proc.returncode == 0
            err = (proc.stderr or "install failed").strip()[:200]
        elif sysname == "Darwin" and shutil.which("brew"):
            proc = subprocess.run(
                ["brew", "install", "ollama"],
                capture_output=True,
                text=True,
                timeout=1800,
            )
            ok = proc.returncode == 0
            err = (proc.stderr or "install failed").strip()[:200]
        else:
            ok = False
            err = "Auto-install supported on Linux (and macOS w/ Homebrew). On this OS, install Ollama from ollama.com."
        with _ollama_install_lock:
            global _ollama_install_status
            _ollama_install_status = "done" if ok else ("error: " + err)
        if ok:
            start_ollama_serve()
    except Exception as exc:
        with _ollama_install_lock:
            _ollama_install_status = f"error: {exc}"


def start_ollama_install() -> Dict[str, Any]:
    """Install Ollama on the clawk host in the background. Poll install-status."""
    if ollama_installed():
        start_ollama_serve()
        return {"ok": True, "status": "done"}
    with _ollama_install_lock:
        global _ollama_install_status
        if _ollama_install_status == "installing":
            return {"ok": True, "status": "installing"}
        _ollama_install_status = "installing"
    threading.Thread(
        target=_do_install_ollama, name="ollama-install", daemon=True
    ).start()
    return {"ok": True, "status": "installing"}


# Background pull tracking: tag -> "pulling" | "done" | "error: ...".
_pull_status: Dict[str, str] = {}
_pull_lock = threading.Lock()


def pull_status(tag: str) -> str:
    with _pull_lock:
        return _pull_status.get(tag, "")


def _do_pull(tag: str) -> None:
    try:
        # The model installs on THIS host (where clawk runs). Make sure the
        # daemon is up first — `ollama pull` needs it.
        start_ollama_serve()
        proc = subprocess.run(
            ["ollama", "pull", tag], capture_output=True, text=True, timeout=3600
        )
        if proc.returncode != 0:
            with _pull_lock:
                _pull_status[tag] = (
                    "error: " + (proc.stderr or "pull failed").strip()[:200]
                )
            return
        # Pulled OK — now validate the model actually runs (a tiny generation).
        # "Installed" is not enough: a bad/corrupt pull or an unsupported arch
        # only surfaces when you try to run it. The user asked to validate this.
        with _pull_lock:
            _pull_status[tag] = "validating"
        result = validate_model(tag)
        with _pull_lock:
            _pull_status[tag] = (
                "done"
                if result.get("ok")
                else (
                    "error: pulled but failed to run: "
                    + str(result.get("error", ""))[:160]
                )
            )
    except Exception as exc:
        with _pull_lock:
            _pull_status[tag] = f"error: {exc}"


def start_pull(tag: str) -> Dict[str, Any]:
    """Kick off `ollama pull <tag>` in the background. Returns immediately."""
    if not ollama_installed():
        return {
            "ok": False,
            "error": "Ollama isn't installed on this host yet.",
            "needs_install": True,
        }
    with _pull_lock:
        if _pull_status.get(tag) == "pulling":
            return {"ok": True, "status": "pulling", "tag": tag}
        _pull_status[tag] = "pulling"
    threading.Thread(
        target=_do_pull, args=(tag,), name=f"ollama-pull-{tag}", daemon=True
    ).start()
    return {"ok": True, "status": "pulling", "tag": tag}


def pull_blocking(tag: str) -> Dict[str, Any]:
    """Pull synchronously (for the CLI), then validate it runs. Returns {ok, ...}."""
    if not ollama_installed():
        return {
            "ok": False,
            "error": "Ollama isn't installed. Run `clawk cookbook --install-ollama` or install from ollama.com.",
            "needs_install": True,
        }
    start_ollama_serve()  # model installs on this host; ensure the daemon is up
    try:
        proc = subprocess.run(["ollama", "pull", tag], timeout=3600)
        if proc.returncode != 0:
            return {"ok": False, "error": "pull failed"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    # Validate the pulled model actually runs.
    result = validate_model(tag)
    return {
        "ok": bool(result.get("ok")),
        "validated": bool(result.get("ok")),
        "sample": result.get("sample"),
        "error": result.get("error"),
    }


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


# ── Ollama library (full remote catalog + live search) ────────────────────────
#
# The curated CATALOG above is hand-vetted but tiny. The whole point of the
# Cookbook is "run ANY local model": Ollama's full library (hundreds of models)
# lives at ollama.com, which has no official JSON API, so we scrape its HTML
# (stable ``x-test-*`` markers). Results are shaped EXACTLY like CATALOG rows
# (one row per size tag) so the same fit-recommender + UI render them unchanged.
# Best-effort: every function returns [] if ollama.com is unreachable, so the
# curated catalog keeps working offline.

_OLLAMA_WEB = "https://ollama.com"
_WEB_HEADERS = {"User-Agent": "Mozilla/5.0 (clawksis-cookbook)"}

# TTL caches so repeated browse/search calls don't hammer ollama.com.
_lib_cache: Dict[str, tuple] = {}  # key -> (monotonic_ts, rows)
_LIB_TTL_SECONDS = 1800.0  # full library: 30 min
_SEARCH_TTL_SECONDS = 300.0  # per-query search: 5 min


def _web_fetch(url: str, timeout: float = 12.0) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers=_WEB_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if not (200 <= resp.status < 300):
                return None
            return resp.read().decode("utf-8", "replace")
    except Exception:
        return None


def _strip_tags(text: str) -> str:
    import html as _html

    return _html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _size_to_params_b(size: str) -> Optional[float]:
    """'7b'->7.0, '1.5b'->1.5, '500m'->0.5, '8x7b'->56.0. None if unparseable."""
    s = size.strip().lower()
    moe = re.fullmatch(r"(\d+)x(\d+(?:\.\d+)?)\s*b", s)  # MoE like 8x7b
    if moe:
        return round(int(moe.group(1)) * float(moe.group(2)), 1)
    b = re.fullmatch(r"(\d+(?:\.\d+)?)\s*b", s)
    if b:
        return float(b.group(1))
    mil = re.fullmatch(r"(\d+(?:\.\d+)?)\s*m", s)
    if mil:
        return round(float(mil.group(1)) / 1000.0, 3)
    return None


def _parse_model_cards(html: str) -> List[Dict[str, Any]]:
    """Parse ollama.com /library or /search HTML into raw model cards."""
    cards: List[Dict[str, Any]] = []
    for blk in re.split(r"<li x-test-model", html)[1:]:
        slug_m = re.search(r'href="/library/([a-zA-Z0-9._-]+)"', blk)
        if not slug_m:
            continue
        slug = slug_m.group(1)
        title_m = re.search(r"x-test-search-response-title[^>]*>([^<]+)<", blk)
        title = _strip_tags(title_m.group(1)) if title_m else slug
        desc_m = re.search(r'<p class="max-w-lg[^"]*"[^>]*>(.*?)</p>', blk, re.DOTALL)
        desc = _strip_tags(desc_m.group(1)) if desc_m else ""
        caps = [c.lower() for c in re.findall(r"x-test-capability[^>]*>([^<]+)<", blk)]
        sizes = [
            s.strip().lower() for s in re.findall(r"x-test-size[^>]*>([^<]+)<", blk)
        ]
        cards.append({
            "slug": slug,
            "title": title,
            "description": desc,
            "capabilities": caps,
            "sizes": sizes,
        })
    return cards


def _cards_to_rows(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Expand parsed cards into CATALOG-shaped rows (one per pullable size tag)."""
    rows: List[Dict[str, Any]] = []
    seen: set = set()
    for card in cards:
        slug = card["slug"]
        tool_use = "tools" in card["capabilities"]
        # Models with no size pills still get a 'latest' row so they're pullable.
        for size in card["sizes"] or ["latest"]:
            tag = slug if size == "latest" else f"{slug}:{size}"
            if tag in seen:
                continue
            seen.add(tag)
            pb = _size_to_params_b(size)
            sz_gb = round(pb * 0.6, 1) if pb else None
            rows.append({
                "id": tag.replace(":", "-"),
                "name": card["title"] + (f" {size}" if size != "latest" else ""),
                "family": card["title"],
                "params_b": pb if pb is not None else 0.0,
                "ollama": tag,
                "quant": "Q4_K_M",
                "size_gb": sz_gb if sz_gb is not None else 0.0,
                "min_vram_gb": round(sz_gb + 1.5, 1) if sz_gb else 0.0,
                "min_ram_gb": round(sz_gb + 2.5, 1) if sz_gb else 0.0,
                "context": 0,  # unknown from the library card
                "tool_use": tool_use,
                "use_case": card["description"][:120],
                "source": "library",
            })
    return rows


def search_ollama_library(query: str, limit: int = 80) -> List[Dict[str, Any]]:
    """Live search of the FULL Ollama library for models matching *query*.

    Returns CATALOG-shaped rows (one per size tag). Cached per-query; [] if
    ollama.com is unreachable.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    cached = _lib_cache.get(f"q:{q}")
    if cached and time.monotonic() - cached[0] < _SEARCH_TTL_SECONDS:
        return cached[1][:limit]
    html = _web_fetch(f"{_OLLAMA_WEB}/search?q={urllib.parse.quote(q)}")
    rows = _cards_to_rows(_parse_model_cards(html)) if html else []
    _lib_cache[f"q:{q}"] = (time.monotonic(), rows)
    return rows[:limit]


def full_ollama_library() -> List[Dict[str, Any]]:
    """All models in the Ollama library (live, scraped, cached ~30 min)."""
    cached = _lib_cache.get("__all__")
    if cached and time.monotonic() - cached[0] < _LIB_TTL_SECONDS:
        return cached[1]
    html = _web_fetch(f"{_OLLAMA_WEB}/library")
    rows = _cards_to_rows(_parse_model_cards(html)) if html else []
    _lib_cache["__all__"] = (time.monotonic(), rows)
    return rows


def validate_model(tag: str, timeout: float = 120.0) -> Dict[str, Any]:
    """Smoke-test that a pulled model actually RUNS: a tiny generation via Ollama.

    "Installed" isn't "works" — a corrupt pull or unsupported build only fails
    when you run it. The first generation also loads the model into memory (can
    be slow), so the timeout is generous. Returns {ok, sample?|error?}.
    """
    if not tag:
        return {"ok": False, "error": "no tag"}
    try:
        body = json.dumps({
            "model": tag,
            "prompt": "Reply with exactly: OK",
            "stream": False,
            "options": {"num_predict": 8, "temperature": 0},
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        sample = (data.get("response") or "").strip()
        if sample:
            return {"ok": True, "sample": sample[:80]}
        return {"ok": False, "error": "model loaded but returned an empty response"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
