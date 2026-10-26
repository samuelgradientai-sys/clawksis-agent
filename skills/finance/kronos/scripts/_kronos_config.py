"""config.yaml reads shared by the Kronos scripts.

The skill's settings live under ``skills.config.kronos`` (declared in SKILL.md
``metadata.clawk.config``): ``trading.*`` are limits only the user changes, ``goals.*`` are the
user's objectives (watchlist, objective, risk, horizon, schedule) that the agent saves when the
user states them. An unreadable file raises ``ConfigError`` so callers can fail closed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from _kronos_common import SkillError, clawk_home

GOAL_KEYS = ("watchlist", "objective", "risk", "horizon", "schedule")
# Share of the account a single trade may lose at its stop, per risk profile.
RISK_PCT = {"low": 0.5, "medium": 1.0, "high": 2.0}
DEFAULT_RISK = "low"
_RISK_ALIASES = {
    "bajo": "low",
    "baja": "low",
    "conservative": "low",
    "conservador": "low",
    "medio": "medium",
    "media": "medium",
    "moderate": "medium",
    "moderado": "medium",
    "alto": "high",
    "alta": "high",
    "aggressive": "high",
    "agresivo": "high",
}


class ConfigError(SkillError):
    """config.yaml exists but cannot be read or parsed."""


def config_path() -> Path:
    return clawk_home() / "config.yaml"


def _yaml_loader() -> tuple[Callable[[str], Any], type[Exception]]:
    """(safe loader, its parse-error class): ruamel.yaml (ships with Clawksis), else PyYAML."""
    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError
    except ImportError:
        try:
            import yaml
        except ImportError:
            raise ConfigError(
                "Cannot read config.yaml (neither ruamel.yaml nor PyYAML is importable)",
                hint="Run the script with the python3 that ships with Clawksis.",
            ) from None
        return yaml.safe_load, yaml.YAMLError
    return YAML(typ="safe").load, YAMLError


def load_config(path: Path | None = None) -> dict[str, Any]:
    """The whole config.yaml as a dict; ``{}`` when the file does not exist."""
    path = path or config_path()
    if not path.exists():
        return {}
    load, parse_error = _yaml_loader()
    try:
        data = load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, parse_error) as exc:
        raise ConfigError(f"config.yaml could not be read ({exc})") from None
    return data if isinstance(data, dict) else {}


def _node(data: Any, *keys: str) -> dict[str, Any]:
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
    return data if isinstance(data, dict) else {}


def kronos_settings(config: dict[str, Any]) -> dict[str, Any]:
    return _node(config, "skills", "config", "kronos")


def display_language(config: dict[str, Any]) -> str:
    """``es`` when ``display.language`` starts with "es", else ``en``."""
    raw = str(_node(config, "display").get("language") or "").strip().lower()
    return "es" if raw.startswith("es") else "en"


def _as_text(value: Any) -> str:
    """Goal values as text; `clawk config set ... "[AAPL, BTC]"` stores a real list."""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return "" if value is None else str(value).strip()


def goals(config: dict[str, Any]) -> dict[str, str]:
    raw = _node(kronos_settings(config), "goals")
    return {key: _as_text(raw.get(key)) for key in GOAL_KEYS}


def watchlist(goal_values: dict[str, str]) -> list[str]:
    """Symbols from a comma/space separated watchlist, upper-cased, de-duplicated."""
    seen: list[str] = []
    for token in re.split(r"[,\s;]+", goal_values.get("watchlist", "")):
        symbol = token.strip().upper()
        if symbol and symbol not in seen:
            seen.append(symbol)
    return seen


def risk_profile(goal_values: dict[str, str]) -> str:
    value = goal_values.get("risk", "").strip().lower()
    value = _RISK_ALIASES.get(value, value)
    return value if value in RISK_PCT else DEFAULT_RISK
