"""Settings form for skills: the ``metadata.clawk.config`` values a skill declares.

Values live under ``skills.config.<key>`` in the profile's config.yaml, the same place
``clawk config set skills.config.<key> ...`` writes and the skill's scripts read on every run, so
a change applies from the skill's next action without a restart.

A declaration can ask for confirmation (``confirm``): turning a bool on, raising a number, or
picking one of the named choices. :func:`plan_update` lists those changes, and the web route
refuses to save them until the user confirms.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from agent.skill_utils import SKILL_CONFIG_PREFIX

MAX_TEXT_LENGTH = 500


class SettingsError(ValueError):
    """A value the declaration does not accept; the message is shown to the user."""


def _stored(config: dict[str, Any], key: str) -> Any:
    node: Any = config
    for part in f"{SKILL_CONFIG_PREFIX}.{key}".split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "yes", "on", "1"):
        return True
    if text in ("false", "no", "off", "0", ""):
        return False
    return None


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(str(value).strip()) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def current_value(var: dict[str, Any], config: dict[str, Any]) -> Any:
    """What the skill sees now: the stored value, else the declared default (``None`` if neither)."""
    value = _stored(config, var["key"])
    if value is None or (isinstance(value, str) and not value.strip()):
        return var.get("default")
    if isinstance(
        value, list
    ):  # `clawk config set ... "[AAPL, BTC]"` stores a real list
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return value


def coerce(var: dict[str, Any], raw: Any) -> Any:
    """``raw`` (as the form sends it) converted to what the declaration accepts."""
    kind = var.get("type", "text")
    if kind == "bool":
        value = _as_bool(raw)
        if value is None:
            raise SettingsError(f"{var['key']}: expected on or off.")
        return value
    if kind in ("integer", "number"):
        number = _as_number(raw)
        if number is None:
            raise SettingsError(f"{var['key']}: expected a number.")
        if kind == "integer":
            if not number.is_integer():
                raise SettingsError(f"{var['key']}: expected a whole number.")
            number = int(number)
        low, high = var.get("min"), var.get("max")
        if low is not None and number < low:
            raise SettingsError(f"{var['key']}: must be at least {low}.")
        if high is not None and number > high:
            raise SettingsError(f"{var['key']}: must be at most {high}.")
        return number
    text = "" if raw is None else str(raw).strip()
    if kind == "choice":
        if text not in var.get("choices", []):
            raise SettingsError(
                f"{var['key']}: choose one of {', '.join(var.get('choices', []))}."
            )
        return text
    if len(text) > MAX_TEXT_LENGTH or "\n" in text:
        raise SettingsError(
            f"{var['key']}: one line of at most {MAX_TEXT_LENGTH} characters."
        )
    return text


def needs_confirmation(var: dict[str, Any], old: Any, new: Any) -> bool:
    """True when ``old`` → ``new`` is a change the declaration wants the user to confirm."""
    confirm = var.get("confirm")
    if not confirm or old == new:
        return False
    kind = var.get("type", "text")
    if isinstance(confirm, list):
        return kind == "choice" and new in confirm
    if kind == "bool":
        return new is True
    if kind in ("integer", "number"):
        before = _as_number(old)
        return before is None or new > before
    return True


def describe(var: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """One form field: the declaration plus the value the skill sees now."""
    field = {
        k: var[k]
        for k in (
            "key",
            "description",
            "default",
            "type",
            "choices",
            "min",
            "max",
            "label",
            "choice_labels",
            "confirm",
        )
        if k in var
    }
    field["value"] = current_value(var, config)
    field["is_set"] = _stored(config, var["key"]) is not None
    return field


def plan_update(
    variables: list[dict[str, Any]], config: dict[str, Any], values: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """``(changes, keys needing confirmation)`` for the submitted ``values``.

    Only keys the skill declares are accepted; unchanged values are left out of ``changes`` so a
    save never pins a default the user did not touch.
    """
    declared = {var["key"]: var for var in variables}
    unknown = sorted(set(values) - set(declared))
    if unknown:
        raise SettingsError(f"Not a setting of this skill: {', '.join(unknown)}.")
    changes: dict[str, Any] = {}
    confirm: list[str] = []
    for key, raw in values.items():
        var = declared[key]
        new = coerce(var, raw)
        old = current_value(var, config)
        if var.get("type") in ("integer", "number"):
            same = _as_number(old) == new
        elif var.get("type") == "bool":
            same = _as_bool(old) is new if old is not None else False
        else:
            same = ("" if old is None else str(old).strip()) == new
        if same:
            continue
        changes[key] = new
        if needs_confirmation(var, old, new):
            confirm.append(key)
    return changes, confirm


def apply_changes(config: dict[str, Any], changes: dict[str, Any]) -> None:
    """Write ``changes`` into ``config`` (the raw user mapping) under ``skills.config``."""
    for key, value in changes.items():
        node = config
        parts = f"{SKILL_CONFIG_PREFIX}.{key}".split(".")
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
