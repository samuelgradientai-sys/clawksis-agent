"""Shared helpers for the external coding-CLI tools.

The ``codex_exec`` / ``claude_code`` / ``opencode_run`` tools each shell out to
a best-in-class coding agent in NON-INTERACTIVE mode and return its output to
the calling model. They share the subprocess plumbing, PATH resolution, and
result shaping that lives here.

This module deliberately has **no** top-level ``registry.register()`` call, so
the tool auto-discovery in ``tools/registry.py`` (which only imports files that
register a tool) skips it. It is imported explicitly by the three coding-CLI
tool modules.

Design notes:

* Non-interactive by construction — stdin is wired to ``DEVNULL`` so a CLI that
  tries to prompt for confirmation fails fast instead of hanging the parent
  agent forever.
* Each CLI is gated by a ``check_fn`` that only reports the tool as available
  when the binary is installed (``cli_available``). This is what makes the
  "install once, then toggle on/off in ``clawk tools``" UX work: an enabled but
  uninstalled CLI simply doesn't expose its tool schema to the model.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import List, Optional

from tools.registry import tool_result

# Coding agents can churn for a while; the default is generous but bounded so a
# wedged CLI can't hang the parent agent indefinitely.
DEFAULT_TIMEOUT = 600
MAX_TIMEOUT = 3600

# How much stdout/stderr to keep when a run fails or times out. Successful runs
# return full stdout (the registry truncates to max_result_size_chars).
_TAIL_CHARS = 8000


def resolve_cli(binary: str) -> Optional[str]:
    """Return the absolute path to *binary* on PATH, or None if not installed.

    Honors a ``CLAWK_<BINARY>_CMD`` env override (e.g. ``CLAWK_CODEX_CMD``) so
    a user can point at a pinned/wrapped executable.
    """
    override = os.environ.get(f"CLAWK_{binary.upper()}_CMD", "").strip()
    if override:
        return shutil.which(override) or (
            override if os.path.isfile(override) else None
        )
    return shutil.which(binary)


def cli_available(binary: str) -> bool:
    """``check_fn`` helper: True when *binary* is installed on PATH."""
    return resolve_cli(binary) is not None


def run_coding_cli(
    *,
    cli_label: str,
    argv: List[str],
    workdir: Optional[str],
    timeout: Optional[int],
    prompt: str,
) -> str:
    """Run a coding-agent CLI non-interactively and shape the result.

    Returns a ``tool_result()`` JSON string with the agent's stdout, exit
    status, and (on failure) stderr. Never raises into the dispatcher.
    """
    try:
        eff_timeout = int(timeout) if timeout else DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        eff_timeout = DEFAULT_TIMEOUT
    eff_timeout = max(10, min(eff_timeout, MAX_TIMEOUT))

    cwd = None
    if workdir:
        if not os.path.isdir(workdir):
            return tool_result(
                ok=False, cli=cli_label, error=f"workdir does not exist: {workdir}"
            )
        cwd = workdir

    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=eff_timeout,
            # Never inherit a stdin the CLI could block on waiting for input.
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return tool_result(
            ok=False,
            cli=cli_label,
            error=f"{cli_label} CLI not found (argv[0]={argv[0]!r}). Is it installed and on PATH?",
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout if isinstance(exc.stdout, str) else ""
        return tool_result(
            ok=False,
            cli=cli_label,
            timed_out=True,
            timeout_seconds=eff_timeout,
            error=f"{cli_label} run exceeded {eff_timeout}s and was killed.",
            output=(partial or "")[-_TAIL_CHARS:],
        )

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    ok = proc.returncode == 0
    payload = {
        "ok": ok,
        "cli": cli_label,
        "returncode": proc.returncode,
        "prompt": prompt,
        "output": stdout,
    }
    if not ok or stderr:
        payload["stderr"] = stderr[-_TAIL_CHARS:]
    return tool_result(payload)
