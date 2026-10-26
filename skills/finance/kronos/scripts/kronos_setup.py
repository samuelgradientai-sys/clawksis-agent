#!/usr/bin/env python3
"""One-time, idempotent install of the Kronos runtime into ``$CLAWK_HOME/kronos/``.

Layout (per Clawksis profile; never touches Clawksis' own environment):
  venv/                  dedicated interpreter: CPU PyTorch + pandas + einops + hf_hub ...,
                         plus best-effort extras (statsforecast, pandas_market_calendars,
                         quantstats): a failed extra never fails the install
  src/<sha>/model/*.py   upstream shiyu-coder/Kronos code at UPSTREAM_SHA (+ LICENSE),
                         every file verified against a pinned sha256 (fail closed)
  models/<repo>@<rev>/   weights (config.json + *.safetensors only) at pinned revisions
  state.json             what is installed, read by the forecast/backtest scripts

Usage:
  kronos_setup.py --check                  # JSON status, installs nothing, no network
  kronos_setup.py [--model small]          # install / repair (default model: small)
  kronos_setup.py --model mini --pin-on-first-use
  kronos_setup.py --force                  # rebuild the venv and re-download code
  kronos_setup.py --no-extras              # skip the optional extras (~300 MB)
Network is used only by an install run: pypi.org, download.pytorch.org (CPU wheels),
codeload.github.com (upstream tarball) and huggingface.co (weights).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Sequence

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_common import (
    MAX_CONTEXT,
    MODEL_NAMES,
    UPSTREAM_FILES,
    UPSTREAM_REPO,
    UPSTREAM_SHA,
    UTC,
    SkillError,
    dump_json,
    kronos_home,
    run_cli,
    venv_python_path,
)

UPSTREAM_TARBALL_URL = (
    f"https://codeload.github.com/{UPSTREAM_REPO}/tar.gz/{UPSTREAM_SHA}"
)
MAX_TARBALL_BYTES = 64 * 1024 * 1024
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
TORCH_REQUIREMENT = "torch>=2.4,<3"
RUNTIME_REQUIREMENTS = (
    "numpy>=1.26,<3",
    "pandas>=2.2,<3",
    "einops>=0.8.1,<0.9",
    "safetensors>=0.4.3,<1",
    "huggingface_hub>=0.33.1,<2",
    "tqdm>=4.66,<5",
    "matplotlib>=3.9,<4",
)
IMPORT_PROBE = (
    "import torch, numpy, pandas, einops, safetensors, huggingface_hub, matplotlib"
)
# Optional: each makes one part more honest or complete, and each part degrades without it.
# statsforecast: the AutoETS baseline in backtests (else a built-in Holt fit);
# pandas_market_calendars: NYSE holidays (else the built-in rules); quantstats: the strategy
# replay's HTML tear sheet (else metrics only). Installed one by one; a failure is reported.
EXTRA_REQUIREMENTS = {
    "statsforecast": "statsforecast>=2.1,<3",
    "pandas_market_calendars": "pandas_market_calendars>=5.5,<6",
    "quantstats": "quantstats>=0.0.86,<0.1",
}
CORE_BOUNDS = tuple(
    r for r in RUNTIME_REQUIREMENTS if r.startswith(("numpy", "pandas", "matplotlib"))
)
_EXTRAS_PROBE = (
    "import importlib.util, json, sys; "
    "print(json.dumps({n: bool(importlib.util.find_spec(n)) for n in sys.argv[1:]}))"
)
HF_PATTERNS = ["config.json", "*.safetensors"]  # never pickled .bin weights

# Hugging Face revisions. small + Tokenizer-base are the commits upstream's own regression
# test pins. The others could not be looked up when this skill was written: they stay None
# and the install refuses them unless --pin-on-first-use resolves the current commit once
# and records it in state.json (later runs load exactly that commit).
TOKENIZERS = {
    "base": (
        "NeoQuasar/Kronos-Tokenizer-base",
        "0e0117387f39004a9016484a186a908917e22426",
    ),
    "2k": ("NeoQuasar/Kronos-Tokenizer-2k", None),
}
MODELS = {
    "small": (
        "NeoQuasar/Kronos-small",
        "901c26c1332695a2a8f243eb2f37243a37bea320",
        "base",
    ),
    "mini": ("NeoQuasar/Kronos-mini", None, "2k"),
    "base": ("NeoQuasar/Kronos-base", None, "base"),
}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

_HF_RESOLVE = "import sys; from huggingface_hub import HfApi; print(HfApi().model_info(sys.argv[1]).sha)"
_HF_DOWNLOAD = (
    "import json, sys; from huggingface_hub import snapshot_download; s = json.loads(sys.argv[1]); "
    "snapshot_download(repo_id=s['repo'], revision=s['revision'], local_dir=s['local_dir'], "
    "allow_patterns=s['patterns'])"
)

Runner = Callable[[Sequence[str], float], subprocess.CompletedProcess]


class PinError(SkillError):
    """Upstream code failed pin verification; nothing was installed."""


def _log(message: str) -> None:
    print(f"[kronos-setup] {message}", file=sys.stderr, flush=True)


def run_command(cmd: Sequence[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd), check=False, timeout=timeout, capture_output=True, text=True
    )


def _checked(runner: Runner, cmd: Sequence[str], timeout: float, what: str) -> str:
    try:
        proc = runner(cmd, timeout)
    except subprocess.TimeoutExpired as exc:
        raise SkillError(f"{what} timed out after {int(timeout)} s.") from exc
    if proc.returncode != 0:
        tail = "\n".join(
            (proc.stdout or "").splitlines()[-15:]
            + (proc.stderr or "").splitlines()[-15:]
        )
        raise SkillError(
            f"{what} failed (exit {proc.returncode}).", hint=tail[-2000:] or None
        )
    return proc.stdout or ""


# ── Upstream code: pinned tarball, per-file sha256, fail closed ──


def verify_upstream_files(
    files: dict[str, bytes], expected: dict[str, str] = UPSTREAM_FILES
) -> None:
    unpinned = [name for name, digest in expected.items() if not _is_sha256(digest)]
    if unpinned:
        raise PinError(
            f"Upstream pin is incomplete (no sha256 for {', '.join(unpinned)}); refusing to install."
        )
    missing = sorted(set(expected) - set(files))
    if missing:
        raise PinError(f"Upstream archive lacks pinned file(s): {', '.join(missing)}.")
    bad = [
        name
        for name, digest in expected.items()
        if hashlib.sha256(files[name]).hexdigest() != digest
    ]
    if bad:
        raise PinError(
            f"sha256 mismatch for {', '.join(bad)} (expected {UPSTREAM_REPO}@{UPSTREAM_SHA[:12]}).",
            hint="The download was altered or the pin is wrong; nothing was installed.",
        )


def _is_sha256(value: str | None) -> bool:
    return bool(value) and re.fullmatch(r"[0-9a-f]{64}", str(value)) is not None


def extract_pinned_members(
    archive: bytes, expected: dict[str, str] = UPSTREAM_FILES
) -> dict[str, bytes]:
    """Read ONLY the allow-listed files from the tarball, in memory (nothing extracted to disk)."""
    files: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            for member in tar:
                parts = PurePosixPath(member.name).parts
                if member.name.startswith("/") or ".." in parts:
                    raise PinError(f"Unsafe path in upstream archive: {member.name!r}.")
                relative = "/".join(parts[1:])  # strip "<repo>-<sha>/"
                if member.isfile() and relative in expected:
                    handle = tar.extractfile(member)
                    files[relative] = handle.read() if handle else b""
    except tarfile.TarError as exc:
        raise PinError(f"Upstream archive is not a valid tarball: {exc}") from exc
    return files


def download(url: str, timeout: float = 120.0, limit: int = MAX_TARBALL_BYTES) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "clawksis-kronos-setup"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(limit + 1)
    except OSError as exc:
        raise SkillError(f"Download failed for {url}: {exc}") from exc
    if len(data) > limit:
        raise SkillError(
            f"Download from {url} exceeds {limit // (1024 * 1024)} MB; refusing."
        )
    return data


def src_dir(home: Path) -> Path:
    return home / "src" / UPSTREAM_SHA


def installed_code_problems(
    directory: Path, expected: dict[str, str] = UPSTREAM_FILES
) -> list[str]:
    problems = []
    for name, digest in expected.items():
        path = directory / name
        if not path.is_file():
            problems.append(f"missing {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"sha256 mismatch {name}")
    return problems


def install_upstream_code(
    home: Path,
    *,
    fetch: Callable[[str], bytes] = download,
    force: bool = False,
    expected: dict[str, str] = UPSTREAM_FILES,
) -> Path:
    target = src_dir(home)
    if not force and target.is_dir() and not installed_code_problems(target, expected):
        _log(f"upstream code OK at {target}")
        return target
    _log(f"downloading {UPSTREAM_REPO}@{UPSTREAM_SHA[:12]}")
    files = extract_pinned_members(fetch(UPSTREAM_TARBALL_URL), expected)
    verify_upstream_files(files, expected)
    staging = target.with_name(target.name + ".partial")
    shutil.rmtree(staging, ignore_errors=True)
    for name, content in files.items():
        path = staging / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    shutil.rmtree(target, ignore_errors=True)
    staging.rename(target)
    return target


# ── venv + dependencies ──


def ensure_venv(home: Path, runner: Runner, *, force: bool = False) -> Path:
    venv_dir = home / "venv"
    python = venv_python_path(venv_dir)
    if force and venv_dir.exists():
        shutil.rmtree(venv_dir)
    if python.exists():
        return python
    uv = shutil.which("uv")
    cmd = (
        [uv, "venv", "--python", sys.executable, str(venv_dir)]
        if uv
        else [sys.executable, "-m", "venv", str(venv_dir)]
    )
    _log(f"creating venv with {'uv' if uv else 'python -m venv'} at {venv_dir}")
    _checked(
        runner,
        cmd,
        600,
        "Creating the venv (on Debian/Ubuntu install python3-venv or uv)",
    )
    return python


def install_commands(python: Path, device: str, uv: str | None) -> list[list[str]]:
    """Two steps so CPU torch comes from the PyTorch CPU index and nothing else does."""
    base = (
        [uv, "pip", "install", "--python", str(python)]
        if uv
        else [str(python), "-m", "pip", "install"]
    )
    torch_step = [*base, TORCH_REQUIREMENT]
    if device == "cpu":
        torch_step = [*base, "--index-url", TORCH_CPU_INDEX, TORCH_REQUIREMENT]
    return [torch_step, [*base, *RUNTIME_REQUIREMENTS]]


def extras_status(python: Path, runner: Runner) -> dict[str, str]:
    """``ok`` or ``missing`` per optional extra in the venv (``unknown`` when it cannot say)."""
    names = list(EXTRA_REQUIREMENTS)
    if not python.exists():
        return dict.fromkeys(names, "missing")
    try:
        proc = runner([str(python), "-c", _EXTRAS_PROBE, *names], 120)
        found = json.loads(proc.stdout or "{}") if proc.returncode == 0 else None
    except (subprocess.TimeoutExpired, ValueError):
        found = None
    if not isinstance(found, dict):
        return dict.fromkeys(names, "unknown")
    return {name: "ok" if found.get(name) else "missing" for name in names}


def ensure_extras(python: Path, runner: Runner) -> dict[str, str]:
    """Install each missing extra on its own; a failure is reported, never raised."""
    status = extras_status(python, runner)
    uv = shutil.which("uv")
    base = (
        [uv, "pip", "install", "--python", str(python)]
        if uv
        else [str(python), "-m", "pip", "install"]
    )
    for name, requirement in EXTRA_REQUIREMENTS.items():
        if status.get(name) == "ok":
            continue
        _log(f"installing optional {requirement}")
        try:
            # The core bounds ride along so an extra can never move numpy/pandas out of them.
            cmd = [*base, requirement, *CORE_BOUNDS]
            _checked(runner, cmd, 1800, f"Installing {name}")
        except SkillError as exc:
            _log(f"optional {name} not installed: {exc}")
            status[name] = f"failed: {exc}"
            continue
        status[name] = "ok"
    return status


def deps_ok(python: Path, runner: Runner) -> bool:
    if not python.exists():
        return False
    try:
        return runner([str(python), "-c", IMPORT_PROBE], 180).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def ensure_deps(
    python: Path, device: str, runner: Runner, *, force: bool = False
) -> None:
    if not force and deps_ok(python, runner):
        _log("dependencies OK")
        return
    for cmd in install_commands(python, device, shutil.which("uv")):
        _log("installing: " + " ".join(cmd[-3:]))
        _checked(runner, cmd, 3600, "Installing Python packages")
    if not deps_ok(python, runner):
        raise SkillError(
            "Packages installed but `import torch` still fails in the Kronos venv."
        )


# ── Weights ──


def resolve_revision(
    repo: str,
    pinned: str | None,
    recorded: str | None,
    python: Path,
    runner: Runner,
    pin_on_first_use: bool,
) -> tuple[str, str]:
    """(revision, origin): the skill's pin, else one recorded by an earlier first-use run."""
    if pinned:
        return pinned, "skill"
    if recorded and _SHA_RE.match(recorded):
        return recorded, "first-use"
    if not pin_on_first_use:
        raise SkillError(
            f"No pinned Hugging Face revision for {repo} in this skill yet.",
            hint="Use --model small (fully pinned), or re-run with --pin-on-first-use to "
            "resolve the current commit once and record it in state.json.",
        )
    revision = _checked(
        runner, [str(python), "-c", _HF_RESOLVE, repo], 120, f"Resolving {repo}"
    ).strip()
    if not _SHA_RE.match(revision):
        raise SkillError(
            f"Hugging Face returned an unexpected revision for {repo}: {revision!r}."
        )
    return revision, "first-use"


def _weights_present(directory: Path) -> bool:
    return (directory / "config.json").is_file() and any(
        directory.glob("*.safetensors")
    )


def fetch_weights(
    repo: str, revision: str, home: Path, python: Path, runner: Runner
) -> Path:
    target = home / "models" / f"{repo.split('/')[-1]}@{revision[:12]}"
    if _weights_present(target):
        return target
    spec = {
        "repo": repo,
        "revision": revision,
        "local_dir": str(target),
        "patterns": HF_PATTERNS,
    }
    _log(f"downloading {repo}@{revision[:12]}")
    _checked(
        runner,
        [str(python), "-c", _HF_DOWNLOAD, json.dumps(spec)],
        1800,
        f"Downloading {repo}",
    )
    if not _weights_present(target):
        raise SkillError(
            f"{repo}@{revision[:12]} has no config.json + .safetensors weights; refusing pickled formats."
        )
    return target


def install_model(
    name: str,
    home: Path,
    python: Path,
    runner: Runner,
    previous: dict[str, Any],
    pin_on_first_use: bool,
) -> dict[str, Any]:
    repo, pinned, tokenizer_key = MODELS[name]
    tok_repo, tok_pinned = TOKENIZERS[tokenizer_key]
    known = previous.get(name) or {}
    model_rev, model_pin = resolve_revision(
        repo, pinned, known.get("model_revision"), python, runner, pin_on_first_use
    )
    tok_rev, tok_pin = resolve_revision(
        tok_repo,
        tok_pinned,
        known.get("tokenizer_revision"),
        python,
        runner,
        pin_on_first_use,
    )
    return {
        "model_repo": repo,
        "model_revision": model_rev,
        "model_dir": str(fetch_weights(repo, model_rev, home, python, runner)),
        "tokenizer_repo": tok_repo,
        "tokenizer_revision": tok_rev,
        "tokenizer_dir": str(fetch_weights(tok_repo, tok_rev, home, python, runner)),
        "max_context": MAX_CONTEXT[name],
        "pinned_by": "skill" if model_pin == tok_pin == "skill" else "first-use",
    }


# ── State + status ──


def read_state(home: Path) -> dict[str, Any]:
    try:
        data = json.loads((home / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(home: Path, state: dict[str, Any]) -> None:
    path = home / "state.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(dump_json(state), encoding="utf-8")
    os.replace(tmp, path)


def check_status(
    home: Path, runner: Runner = run_command, probe_deps: bool = True
) -> dict[str, Any]:
    state = read_state(home)
    python = Path(state.get("venv_python") or venv_python_path(home / "venv"))
    code_dir = src_dir(home)
    problems = installed_code_problems(code_dir) if code_dir.is_dir() else ["missing"]
    models = {
        name: "ok"
        if _weights_present(Path(entry.get("model_dir", "")))
        and _weights_present(Path(entry.get("tokenizer_dir", "")))
        else "broken"
        for name, entry in (state.get("models") or {}).items()
    }
    deps = (
        ("ok" if deps_ok(python, runner) else "missing") if probe_deps else "unchecked"
    )
    extras = extras_status(python, runner) if probe_deps and deps == "ok" else {}
    ok = (
        python.exists()
        and deps in {"ok", "unchecked"}
        and not problems
        and "ok" in models.values()
    )
    return {
        "ok": ok,
        "setup_needed": not ok,
        "kronos_home": str(home),
        "venv": python.exists(),
        "dependencies": deps,
        "upstream_code": "ok" if not problems else "; ".join(problems),
        "upstream": f"{UPSTREAM_REPO}@{UPSTREAM_SHA}",
        "models": models,
        "extras": extras,
        "next_step": None
        if ok
        else f"python3 {Path(__file__).resolve()} --model small",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install the Kronos runtime for this Clawksis profile."
    )
    parser.add_argument(
        "--check", action="store_true", help="report status as JSON; install nothing"
    )
    parser.add_argument(
        "--model",
        choices=MODEL_NAMES,
        default="small",
        help="checkpoint to install (default small)",
    )
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda"),
        default="cpu",
        help="cpu installs the small CPU-only torch wheel",
    )
    parser.add_argument(
        "--pin-on-first-use",
        action="store_true",
        help="resolve and record a revision for models this skill has not pinned",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="rebuild the venv and re-download the upstream code",
    )
    parser.add_argument(
        "--no-extras",
        action="store_true",
        help="skip the optional statsforecast, pandas_market_calendars and quantstats",
    )
    return parser


def install(
    args: argparse.Namespace, home: Path, runner: Runner = run_command
) -> dict[str, Any]:
    home.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = (
        "1"  # inherited by the venv download children
    )
    code = install_upstream_code(home, force=args.force)  # cheapest, fails closed first
    python = ensure_venv(home, runner, force=args.force)
    ensure_deps(python, args.device, runner, force=args.force)
    extras = {} if args.no_extras else ensure_extras(python, runner)
    if extras and not deps_ok(python, runner):
        raise SkillError(
            "Installing the optional extras broke the Kronos runtime (`import torch` fails).",
            hint=f"Re-run `{Path(__file__).resolve()} --force --no-extras`.",
        )
    state = read_state(home)
    models = dict(state.get("models") or {})
    models[args.model] = install_model(
        args.model, home, python, runner, models, args.pin_on_first_use
    )
    state.update(
        {
            "version": 1,
            "upstream_sha": UPSTREAM_SHA,
            "src_dir": str(code),
            "venv_dir": str(home / "venv"),
            "venv_python": str(python),
            "device": args.device,
            "models": models,
            "installed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
    )
    write_state(home, state)
    return {
        "ok": True,
        "state_file": str(home / "state.json"),
        "installed_model": args.model,
        **models[args.model],
        "extras": extras,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    def _run() -> int:
        home = kronos_home()
        result = check_status(home) if args.check else install(args, home)
        print(dump_json(result))
        return 0 if result["ok"] else 1

    return run_cli(_run)


if __name__ == "__main__":
    sys.exit(main())
