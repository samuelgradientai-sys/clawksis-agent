"""Skill dashboard snapshots: the JSON a skill writes for its mini dashboard in the web UI.

A skill that declares ``metadata.clawk.dashboard`` in its SKILL.md writes
``<CLAWK_HOME>/dashboards/<skill>.json`` (atomically) whenever its state changes; the dashboard
renders it. The web server never runs skill code: it only reads this file, so a hub skill gets a
dashboard with no new trust. Everything read is clipped to the documented shape (version 1)
before it reaches the browser, so a malformed or hostile snapshot renders as an error, never as
markup or an unbounded payload. Contract: ``website/docs/developer-guide/skill-dashboards.md``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

SNAPSHOT_VERSION = 1
MAX_SNAPSHOT_BYTES = 512 * 1024
MAX_PANELS = 24
MAX_STATS = 12
MAX_ROWS = 200
MAX_COLUMNS = 12
MAX_LIST_ITEMS = 100
MAX_SERIES = 4
MAX_POINTS = 500
TONES = ("positive", "negative", "warning", "neutral")
FORMATS = ("text", "number", "money", "percent", "datetime")

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class SnapshotError(ValueError):
    """The snapshot exists but cannot be shown; the message is safe to display."""


def snapshot_path(home: Path, name: str) -> Path | None:
    """``<home>/dashboards/<name>.json``, or None when *name* is not a plain skill name."""
    if not _NAME.match(name) or ".." in name:
        return None
    return home / "dashboards" / f"{name}.json"


def _text(value: Any, limit: int = 200) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()[:limit]


def _tone(value: Any) -> str:
    return value if value in TONES else "neutral"


def _scalar(value: Any) -> str | int | float | bool | None:
    """A table cell or stat value: numbers stay numbers, everything else becomes short text."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else None
    return _text(value, 400)


def _items(value: Any, limit: int) -> list[dict]:
    return (
        [item for item in value if isinstance(item, dict)][:limit]
        if isinstance(value, list)
        else []
    )


def _stats(panel: dict) -> dict:
    return {
        "items": [
            {
                "label": _text(item.get("label"), 80),
                "value": _scalar(item.get("value")),
                "hint": _text(item.get("hint"), 160),
                "tone": _tone(item.get("tone")),
            }
            for item in _items(panel.get("items"), MAX_STATS)
        ]
    }


def _table(panel: dict) -> dict:
    columns = [
        {
            "key": _text(column.get("key"), 64),
            "label": _text(column.get("label") or column.get("key"), 80),
            "align": "right" if column.get("align") == "right" else "left",
            "format": column.get("format")
            if column.get("format") in FORMATS
            else "text",
        }
        for column in _items(panel.get("columns"), MAX_COLUMNS)
        if _text(column.get("key"), 64)
    ]
    keys = [column["key"] for column in columns]
    rows = [
        {
            **{key: _scalar(row.get(key)) for key in keys},
            "_tone": _tone(row.get("_tone")),
        }
        for row in _items(panel.get("rows"), MAX_ROWS)
    ]
    return {"columns": columns, "rows": rows, "empty": _text(panel.get("empty"), 200)}


def _list(panel: dict) -> dict:
    return {
        "items": [
            {
                "title": _text(item.get("title"), 200),
                "body": _text(item.get("body"), 1000),
                "meta": _text(item.get("meta"), 120),
                "tone": _tone(item.get("tone")),
            }
            for item in _items(panel.get("items"), MAX_LIST_ITEMS)
        ],
        "empty": _text(panel.get("empty"), 200),
    }


def _point(point: Any) -> list | None:
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        return None
    x, y = point
    if isinstance(y, bool) or not isinstance(y, (int, float)) or y != y:
        return None
    if isinstance(x, bool) or not isinstance(x, (int, float, str)):
        return None
    return [x if not isinstance(x, str) else x[:40], y]


def _chart(panel: dict) -> dict:
    series = []
    for entry in _items(panel.get("series"), MAX_SERIES):
        raw = entry.get("points") if isinstance(entry.get("points"), list) else []
        points = [p for p in map(_point, raw[:MAX_POINTS]) if p is not None]
        series.append({"name": _text(entry.get("name"), 60), "points": points})
    return {
        "kind": "bar" if panel.get("kind") == "bar" else "line",
        "x_label": _text(panel.get("x_label"), 60),
        "y_label": _text(panel.get("y_label"), 60),
        "series": series,
    }


def _body(panel: dict) -> dict:
    return {"body": _text(panel.get("body"), 4000)}


_PANELS: dict[str, Callable[[dict], dict]] = {
    "stats": _stats,
    "table": _table,
    "list": _list,
    "chart": _chart,
    "text": _body,
}


def _panel(panel: dict, index: int) -> dict:
    kind = panel.get("type")
    shaped = (
        _PANELS[kind](panel) if kind in _PANELS else {"original_type": _text(kind, 40)}
    )
    return {
        "id": _text(panel.get("id"), 64) or f"panel-{index}",
        "type": kind if kind in _PANELS else "unsupported",
        "title": _text(panel.get("title"), 120),
        "description": _text(panel.get("description"), 300),
        "width": "half" if panel.get("width") == "half" else "full",
        **shaped,
    }


def normalize(raw: Any) -> dict:
    """The version-1 snapshot clipped to its documented shape; SnapshotError when unusable."""
    if not isinstance(raw, dict):
        raise SnapshotError("the snapshot is not a JSON object")
    if raw.get("version") != SNAPSHOT_VERSION:
        raise SnapshotError(
            f"unsupported snapshot version {raw.get('version')!r} (expected 1)"
        )
    panels = raw.get("panels")
    if not isinstance(panels, list):
        raise SnapshotError("the snapshot has no 'panels' list")
    return {
        "version": SNAPSHOT_VERSION,
        "title": _text(raw.get("title"), 120),
        "subtitle": _text(raw.get("subtitle"), 200),
        "updated_at": _text(raw.get("updated_at"), 40),
        "panels": [_panel(p, i) for i, p in enumerate(_items(panels, MAX_PANELS))],
    }


def read_snapshot(path: Path) -> dict | None:
    """The normalized snapshot at *path*; None when the skill has not written one yet."""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SnapshotError(f"cannot read the snapshot: {exc.strerror or exc}") from exc
    if size > MAX_SNAPSHOT_BYTES:
        raise SnapshotError(
            f"the snapshot is larger than {MAX_SNAPSHOT_BYTES // 1024} KiB"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"the snapshot is not valid JSON: {exc}") from exc
    return normalize(raw)


def snapshot_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None
