"""Skill mini dashboards: list the skills that declare one and serve their snapshot.

Mounted through ``web_routers.skills.router`` (same auth, same ``?profile=`` scope as the rest of
``/api/skills``). Read-only: the snapshot is data the skill wrote under the profile's home, clipped
by ``clawk_cli.skill_dashboard_snapshot`` before it is returned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from clawk_cli.web_deps import late
from clawk_cli.web_routers._common import scoped_to_thread

router = APIRouter()

load_config = late("load_config", "clawk_cli.config")


def _declared() -> tuple[dict[str, dict], set[str]]:
    from clawk_cli.skills_config import get_disabled_skills
    from tools.skills_tool import find_skill_dashboards

    return find_skill_dashboards(skip_disabled=True), get_disabled_skills(load_config())


def _iso(timestamp: Optional[float]) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat(timespec="seconds")


def _entry(name: str, declaration: dict, disabled: set[str]) -> dict:
    from clawk_cli.skill_dashboard_snapshot import snapshot_mtime, snapshot_path
    from clawk_constants import display_clawk_home, get_clawk_home

    path = snapshot_path(get_clawk_home(), name)
    return {
        "name": name,
        "title": declaration.get("title") or name,
        "description": declaration.get("description", ""),
        "category": declaration.get("category") or "",
        "emoji": declaration.get("emoji", ""),
        "enabled": name not in disabled,
        "snapshot_file": f"{display_clawk_home()}/dashboards/{name}.json"
        if path
        else "",
        "modified_at": _iso(snapshot_mtime(path)) if path else "",
    }


@router.get("/api/skills/dashboards")
async def list_skill_dashboards(profile: Optional[str] = None):
    def _run():
        declared, disabled = _declared()
        entries = [_entry(name, decl, disabled) for name, decl in declared.items()]
        return {
            "dashboards": sorted(
                entries, key=lambda e: (not e["enabled"], e["title"].lower())
            )
        }

    return await scoped_to_thread(profile, _run)


@router.get("/api/skills/dashboards/{name}")
async def get_skill_dashboard(name: str, profile: Optional[str] = None):
    from clawk_cli.skill_dashboard_snapshot import (
        SnapshotError,
        read_snapshot,
        snapshot_path,
    )
    from clawk_constants import get_clawk_home

    def _run():
        declared, disabled = _declared()
        if name not in declared:
            raise HTTPException(
                status_code=404, detail=f"Skill '{name}' has no dashboard."
            )
        entry = _entry(name, declared[name], disabled)
        path = snapshot_path(get_clawk_home(), name)
        if path is None:
            return {
                **entry,
                "snapshot": None,
                "error": "the skill name cannot be a file name",
            }
        try:
            return {**entry, "snapshot": read_snapshot(path), "error": None}
        except SnapshotError as exc:
            return {**entry, "snapshot": None, "error": str(exc)}

    return await scoped_to_thread(profile, _run)
