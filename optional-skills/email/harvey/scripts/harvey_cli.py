#!/usr/bin/env python3
"""Install and run Harvey (github.com/ethanplusai/harvey, MIT) for Clawksis.

Harvey is repo-centric: its config (harvey.yaml, harvey.local.yaml, .env) and its state (data/)
live in its own checkout, so it is installed at ``$CLAWK_HOME/tools/harvey`` pinned to a reviewed
commit, with a private venv. Its model calls go through the Claude Code CLI (or Codex); this
wrapper finds a ``claude`` on PATH, or the one bundled with the VS Code / Cursor extension, and puts
it on Harvey's PATH for the call only.

    harvey_cli.py install            # clone (pinned), venv, pip install -e, seed .env
    harvey_cli.py doctor             # JSON status: installed, commit, python, claude, .env
    harvey_cli.py run -- status      # any harvey command, run from its checkout
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

HARVEY_REPO = "https://github.com/ethanplusai/harvey.git"
HARVEY_COMMIT = "8023a9495eb46d644f03da8c8f4d2b9e41e5836e"
MIN_PYTHON = (3, 11)
INSTALL_TIMEOUT_S = 900  # clone / venv / pip, each
RUN_TIMEOUT_S = 3600  # one harvey command (train and discover can take a while)
_EXE = ".exe" if os.name == "nt" else ""


def clawk_home() -> Path:
    return Path(os.environ.get("CLAWK_HOME") or Path.home() / ".clawksis")


def harvey_home(home: Optional[Path] = None) -> Path:
    return (home or clawk_home()) / "tools" / "harvey"


def venv_bin(root: Path, name: str) -> Path:
    sub = "Scripts" if os.name == "nt" else "bin"
    return root / ".venv" / sub / f"{name}{_EXE}"


def _extension_claudes(user_home: Path) -> list[Path]:
    """The Claude CLIs bundled with editor extensions, newest extension first."""
    found = []
    for editor in (".vscode", ".vscode-server", ".cursor", ".windsurf"):
        pattern = "anthropic.claude-code-*/resources/native-binary/claude" + _EXE
        found.extend((user_home / editor / "extensions").glob(pattern))
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def find_claude(
    path: Optional[str] = None, user_home: Optional[Path] = None
) -> Optional[Path]:
    """A ``claude`` executable: PATH first, then the usual install spots, then an editor's."""
    on_path = shutil.which("claude", path=path)
    if on_path:
        return Path(on_path)
    user_home = user_home or Path.home()
    for candidate in (
        user_home / ".local" / "bin" / f"claude{_EXE}",
        user_home / ".claude" / "local" / f"claude{_EXE}",
        *_extension_claudes(user_home),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _python_version(exe: str) -> Optional[tuple[int, int]]:
    try:
        out = subprocess.run(
            [exe, "-c", "import sys; print('%d %d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        ).stdout.split()
        return int(out[0]), int(out[1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def find_python() -> Optional[str]:
    """A Python >= 3.11 to build Harvey's venv (it refuses older ones)."""
    for name in ("python3.13", "python3.12", "python3.11", "python3", "python"):
        exe = shutil.which(name)
        version = _python_version(exe) if exe else None
        if version and version >= MIN_PYTHON:
            return exe
    return sys.executable if sys.version_info[:2] >= MIN_PYTHON else None


def harvey_env(base: Optional[dict] = None, claude: Optional[Path] = None) -> dict:
    """``base`` with the Claude CLI's folder first on PATH (Harvey looks it up there)."""
    env = dict(os.environ if base is None else base)
    if claude is not None:
        env["PATH"] = os.pathsep.join(
            p for p in (str(claude.parent), env.get("PATH", "")) if p
        )
    return env


def _sh(cmd: list[str], **kwargs) -> None:
    subprocess.run(cmd, check=True, timeout=INSTALL_TIMEOUT_S, **kwargs)


def _git(root: Path, *args: str) -> None:
    _sh(["git", "-C", str(root), *args])


def install(root: Path) -> dict:
    """Clone Harvey at the pinned commit (or move an existing checkout to it) and build its venv."""
    if not (root / ".git").is_dir():
        root.parent.mkdir(parents=True, exist_ok=True)
        _sh(["git", "clone", "--quiet", HARVEY_REPO, str(root)])
    _git(root, "fetch", "--quiet", "origin", HARVEY_COMMIT)
    _git(root, "checkout", "--quiet", HARVEY_COMMIT)
    python = find_python()
    if python is None:
        raise SystemExit("Harvey needs Python 3.11 or newer; none was found.")
    if not venv_bin(root, "python").exists():
        _sh([python, "-m", "venv", str(root / ".venv")])
    pip = [str(venv_bin(root, "python")), "-m", "pip", "install", "--quiet"]
    _sh([*pip, "--upgrade", "pip"])
    _sh([*pip, "-e", str(root)])
    env_file = root / ".env"
    if not env_file.exists() and (root / ".env.example").exists():
        shutil.copyfile(root / ".env.example", env_file)
        if os.name != "nt":
            env_file.chmod(0o600)
    return status(root)


def status(root: Path) -> dict:
    commit = None
    if (root / ".git").is_dir():
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        ).stdout.strip()
    claude = find_claude()
    return {
        "home": str(root),
        "installed": venv_bin(root, "harvey").exists(),
        "commit": commit,
        "pinned": commit == HARVEY_COMMIT,
        "claude": str(claude) if claude else None,
        "env_file": (root / ".env").exists(),
        "trained": (root / "harvey.local.yaml").exists(),
    }


def run(root: Path, args: list[str]) -> int:
    harvey = venv_bin(root, "harvey")
    if not harvey.exists():
        print(
            "Harvey is not installed: run `harvey_cli.py install` first.",
            file=sys.stderr,
        )
        return 2
    env = harvey_env(claude=find_claude())
    try:
        done = subprocess.run(
            [str(harvey), *args], cwd=root, env=env, check=False, timeout=RUN_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        print(
            f"harvey {' '.join(args)} ran past {RUN_TIMEOUT_S}s and was stopped; "
            "run long loops (`harvey run`) in the background instead.",
            file=sys.stderr,
        )
        return 124
    return done.returncode


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("install")
    sub.add_parser("doctor")
    runner = sub.add_parser("run")
    runner.add_argument("harvey_args", nargs=argparse.REMAINDER)
    opts = parser.parse_args(argv)
    root = harvey_home()
    if opts.cmd == "install":
        print(json.dumps(install(root), indent=2))
        return 0
    if opts.cmd == "doctor":
        print(json.dumps(status(root), indent=2))
        return 0
    args = opts.harvey_args
    return run(root, args[1:] if args[:1] == ["--"] else args)


if __name__ == "__main__":
    sys.exit(main())
