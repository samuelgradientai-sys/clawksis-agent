#!/usr/bin/env python3
"""
Clawk Safe Ops

Portable bridge between Clawksis and Hermes Lite.

Security principles:
- Does not execute arbitrary shell commands.
- Does not use shell=True.
- Delegates only to Hermes Lite allowlisted intents.
- Supports repo-local Hermes Lite for reproducible installs.
- Supports HERMES_LITE_CMD override for deployments.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


VERSION = "0.1.0"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_hermes_command() -> list[str]:
    """
    Resolve Hermes Lite command in a portable order:

    1. HERMES_LITE_CMD env var, for deployments.
    2. Repo-local hermes_lite/hermes_lite.py, for cloned repos.
    3. /opt/hermes-agent/hermes-lite, for this VPS deployment.
    """

    env_cmd = os.getenv("HERMES_LITE_CMD", "").strip()
    if env_cmd:
        return shlex.split(env_cmd)

    local_script = repo_root() / "hermes_lite" / "hermes_lite.py"
    if local_script.exists():
        return ["python3", str(local_script)]

    deployed_script = Path("/opt/hermes-agent/hermes-lite")
    if deployed_script.exists():
        return [str(deployed_script)]

    deployed_py = Path("/opt/hermes-agent/hermes_lite.py")
    if deployed_py.exists():
        return ["python3", str(deployed_py)]

    raise FileNotFoundError(
        "Hermes Lite not found. Expected repo-local hermes_lite/hermes_lite.py "
        "or set HERMES_LITE_CMD."
    )


def run_hermes_lite(
    text: str, *, json_output: bool, dry_run: bool, timeout: int
) -> tuple[int, str, str]:
    cmd = default_hermes_command()

    if json_output:
        cmd.append("--json")

    if dry_run:
        cmd.append("--dry-run")

    cmd.append(text)

    result = subprocess.run(
        cmd,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(repo_root()),
    )

    return result.returncode, result.stdout.strip(), result.stderr.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Clawk Safe Ops bridge to Hermes Lite")
    parser.add_argument(
        "text", nargs="+", help="Natural-language safe operation request"
    )
    parser.add_argument(
        "--json", action="store_true", help="Return Hermes Lite JSON output"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Detect intent without executing"
    )
    parser.add_argument(
        "--timeout", type=int, default=15, help="Execution timeout in seconds"
    )
    parser.add_argument("--version", action="store_true", help="Show version and exit")

    args = parser.parse_args()

    if args.version:
        print(VERSION)
        return 0

    text = " ".join(args.text)

    try:
        code, stdout, stderr = run_hermes_lite(
            text,
            json_output=args.json,
            dry_run=args.dry_run,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        if args.json:
            print(
                json.dumps(
                    {
                        "version": VERSION,
                        "status": "timeout",
                        "message": "Hermes Lite execution timed out.",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print("STATUS=timeout")
            print("MENSAJE=Hermes Lite execution timed out.")
        return 124
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "version": VERSION,
                        "status": "error",
                        "message": f"{type(exc).__name__}: {exc}",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print("STATUS=error")
            print(f"MENSAJE={type(exc).__name__}: {exc}")
        return 1

    if stdout:
        print(stdout)

    if stderr:
        print(stderr, file=sys.stderr)

    return code


if __name__ == "__main__":
    raise SystemExit(main())
