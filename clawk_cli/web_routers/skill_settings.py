"""Skill settings form: read and save the ``metadata.clawk.config`` values a skill declares.

Mounted through ``web_routers.skills.router`` (same auth and ``?profile=`` scope as the rest of
``/api/skills``). Only keys the skill declares are written, under ``skills.config.<key>`` in the
profile's config.yaml; nothing from the skill is executed. Changes the declaration marks with
``confirm`` (turning trading on, a real-money account, a higher limit) are refused with 409 until
the request carries ``confirm: true``.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from clawk_cli.web_deps import LateState, late
from clawk_cli.web_routers._common import destructive_profile, http_failure

router = APIRouter()

_profile_scope = late("_profile_scope", "clawk_cli.web_server_profiles")
load_config = late("load_config", "clawk_cli.config")
save_config = late("save_config", "clawk_cli.config")
_CONFIG_MUTATION_LOCK = LateState("_CONFIG_MUTATION_LOCK")


class SkillSettingsUpdate(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False


def _variables(name: str) -> list[dict[str, Any]]:
    from tools.skills_tool import find_skill_config_vars

    variables = find_skill_config_vars(name)
    if variables is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return variables


def _fields(variables: list[dict[str, Any]], config: dict[str, Any]) -> list[dict]:
    from clawk_cli.skill_settings import describe

    return [describe(var, config) for var in variables]


@router.get("/api/skills/settings/{name}")
def get_skill_settings(name: str, profile: Optional[str] = None):
    with http_failure(
        f"GET /api/skills/settings/{name} failed", 500, detail="Could not read settings"
    ):
        with _profile_scope(profile):
            variables = _variables(name)
            return {"name": name, "fields": _fields(variables, load_config())}


@router.put("/api/skills/settings/{name}")
def update_skill_settings(
    name: str, body: SkillSettingsUpdate, profile: Optional[str] = None
):
    from clawk_cli.config import require_readable_config_before_write
    from clawk_cli.skill_settings import SettingsError, apply_changes, plan_update

    profile = destructive_profile(profile, "PUT /api/skills/settings/{name}")
    with http_failure(
        f"PUT /api/skills/settings/{name} failed", 500, detail="Could not save settings"
    ):
        with _profile_scope(profile), _CONFIG_MUTATION_LOCK:
            variables = _variables(name)
            try:
                changes, confirm = plan_update(variables, load_config(), body.values)
            except SettingsError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
            if confirm and not body.confirm:
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "These changes need confirmation.",
                        "needs_confirmation": confirm,
                    },
                )
            if changes:
                # The raw user mapping, not the defaulted one: defaults are never dumped back.
                raw = require_readable_config_before_write()
                apply_changes(raw, changes)
                save_config(raw)
            return {
                "ok": True,
                "changed": sorted(changes),
                "fields": _fields(variables, load_config()),
            }
