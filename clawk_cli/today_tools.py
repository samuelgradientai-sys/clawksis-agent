"""What a day's tool calls say the agent *did*: files it wrote, commands it ran, skills it changed.

Pure functions over the ``messages`` columns the dashboard's "Hoy" page reads (assistant
``tool_calls`` JSON and the head/tail of each tool result); no I/O. Whether a file was new is a
heuristic: the store keeps the call, not the disk before it, so a path whose FIRST touch of the day
is ``write_file`` (or a V4A ``Add File``) counts as created and anything else as edited.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Iterator, NamedTuple, Optional

# V4A headers, same grammar as tools/file_tools.py (_V4A_SINGLE_HEADER_RE / _V4A_MOVE_HEADER_RE).
_V4A_SINGLE = re.compile(r"^\*\*\*\s*(Update|Add|Delete)\s+File:\s*(.+)$", re.MULTILINE)
_V4A_MOVE = re.compile(r"^\*\*\*\s*Move\s+File:\s*(.+?)\s*->\s*(.+)$", re.MULTILINE)
_V4A_ACTION = {"Update": "edited", "Add": "created", "Delete": "deleted"}

# skill_manage op -> what happened to the skill.
_SKILL_ACTION = {
    "create": "created",
    "delete": "deleted",
    "patch": "updated",
    "edit": "updated",
    "write_file": "updated",
    "remove_file": "updated",
}

# A shell command that writes git history, and the `cd <dir> &&` it may start with.
_GIT_WRITE = re.compile(
    r"\bgit\b[^|;&]*?\b(?:commit|merge|cherry-pick|rebase|revert|am)\b"
)
_LEADING_CD = re.compile(r"""^\s*cd\s+("[^"]+"|'[^']+'|[^\s;&|]+)\s*(?:&&|;)""")

_ERROR_FIELD = re.compile(r'"error"\s*:\s*"((?:[^"\\]|\\.){1,400})')
_EXIT_CODE = re.compile(r'"exit_code"\s*:\s*(-?\d+)')
_RESOLVED_PATH = re.compile(r'"resolved_path"\s*:\s*"((?:[^"\\]|\\.)+)"')

COMMAND_MAX_CHARS = 200


class ToolCall(NamedTuple):
    name: str
    call_id: str
    args: dict


def _as_dict(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def iter_calls(raw: Any) -> Iterator[ToolCall]:
    """Every well-formed call in an assistant ``tool_calls`` column (JSON text or a list)."""
    calls = raw
    if isinstance(raw, str):
        try:
            calls = json.loads(raw)
        except ValueError:
            return
    if not isinstance(calls, list):
        return
    for call in calls:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") if isinstance(call.get("function"), dict) else call
        name = fn.get("name")
        if isinstance(name, str) and name:
            yield ToolCall(
                name, str(call.get("id") or ""), _as_dict(fn.get("arguments"))
            )


def _v4a_targets(patch: str) -> list[tuple[str, str]]:
    targets = [
        (m.group(2).strip(), _V4A_ACTION[m.group(1)])
        for m in _V4A_SINGLE.finditer(patch)
    ]
    targets += [(m.group(2).strip(), "edited") for m in _V4A_MOVE.finditer(patch)]
    return targets


def file_targets(call: ToolCall) -> list[tuple[str, str]]:
    """``[(path as the model wrote it, "written" | "edited" | "created" | "deleted")]``."""
    args = call.args
    if call.name == "write_file":
        path = args.get("path")
        return [(path, "written")] if isinstance(path, str) and path.strip() else []
    if call.name != "patch":
        return []
    if args.get("mode") == "patch" and isinstance(args.get("patch"), str):
        return _v4a_targets(args["patch"])
    path = args.get("path")
    return [(path, "edited")] if isinstance(path, str) and path.strip() else []


def _skill_ops(args: dict) -> list[dict]:
    ops = args.get("operations")
    if isinstance(ops, list):
        return [op for op in ops if isinstance(op, dict)]
    return [args] if args.get("action") else []  # legacy flat shape


def skill_changes(call: ToolCall) -> list[tuple[str, str]]:
    """``[(skill name, "created" | "updated" | "deleted")]`` for a ``skill_manage`` call."""
    if call.name != "skill_manage":
        return []
    changes = []
    for op in _skill_ops(call.args):
        name, action = op.get("name"), _SKILL_ACTION.get(str(op.get("action") or ""))
        if isinstance(name, str) and name.strip() and action:
            changes.append((name.strip(), action))
    return changes


def command_text(call: ToolCall) -> Optional[str]:
    """The shell command of a ``terminal`` call, one line, clipped."""
    if call.name != "terminal":
        return None
    command = call.args.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    one_line = " ".join(command.split())
    return one_line[:COMMAND_MAX_CHARS] + (
        "…" if len(one_line) > COMMAND_MAX_CHARS else ""
    )


def _json_string(escaped: str) -> str:
    try:
        return json.loads(f'"{escaped}"')
    except ValueError:
        return escaped


def result_error(text: str) -> Optional[str]:
    """The ``"error"`` message of a tool result, or None when it carries none (or an empty one)."""
    match = _ERROR_FIELD.search(text or "")
    if not match:
        return None
    message = _json_string(match.group(1)).strip()
    return message or None


def result_exit_code(text: str) -> Optional[int]:
    match = _EXIT_CODE.search(text or "")
    return int(match.group(1)) if match else None


def result_resolved_path(text: str) -> Optional[str]:
    match = _RESOLVED_PATH.search(text or "")
    return _json_string(match.group(1)) if match else None


def git_work_dir(command: str, cwd: Optional[str]) -> Optional[str]:
    """Where a command that writes git history ran (its leading ``cd`` target, else the session
    cwd); None for any other command — reading a repo is not working in it."""
    if not _GIT_WRITE.search(command):
        return None
    match = _LEADING_CD.match(command)
    if match:
        return absolute_path(match.group(1).strip("\"'"), cwd)
    return absolute_path(cwd, None) if cwd else None


def absolute_path(path: str, cwd: Optional[str]) -> str:
    """The path the tool most likely wrote: ``~`` expanded, relative paths joined to the session cwd."""
    expanded = os.path.expanduser(path.strip())
    if not os.path.isabs(expanded) and cwd:
        expanded = os.path.join(os.path.expanduser(cwd), expanded)
    return os.path.normpath(expanded)
