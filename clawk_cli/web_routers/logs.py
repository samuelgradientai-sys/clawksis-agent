"""Logs dashboard routes: tail with filters, the per-profile log inventory, and file download.

Every path resolves inside ``_config_profile_scope(profile)`` through
:func:`clawk_cli.logs.log_file_path`, the same resolver ``clawk logs`` uses, so the dashboard
reads the SELECTED profile's ``logs/`` and the root home's update logs (``update``, ``handoff``
are written to the root whatever profile is active).
"""

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from clawk_cli.web_deps import late

router = APIRouter()

_config_profile_scope = late("_config_profile_scope", "clawk_cli.web_server_profiles")

# One request never returns more than this many lines; the over-read for filters is
# _read_tail's own business.
_MAX_TAIL_LINES = 500


def _log_path(file: str, profile: Optional[str]) -> Path:
    """Where log *file* lives for *profile*; 400 for a name ``clawk logs`` does not know."""
    from clawk_cli.logs import log_file_path

    with _config_profile_scope(profile):
        path = log_file_path(file)
    if path is None:
        raise HTTPException(status_code=400, detail=f"Unknown log file: {file}")
    return path


def _component_prefixes(component: Optional[str]):
    if not component or component.lower() == "all":
        return None
    from clawk_logging import COMPONENT_PREFIXES

    prefixes = COMPONENT_PREFIXES.get(component)
    if prefixes is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown component: {component}. "
            f"Available: {', '.join(sorted(COMPONENT_PREFIXES))}",
        )
    return prefixes


@router.get("/api/logs")
async def get_logs(
    file: str = "agent",
    lines: int = Query(100, ge=1),
    level: Optional[str] = None,
    component: Optional[str] = None,
    search: Optional[str] = None,
    profile: Optional[str] = None,
):
    from clawk_cli.logs import _read_tail

    log_path = _log_path(file, profile)
    if not log_path.exists():
        return {"file": file, "lines": []}
    # "ALL"/"all"/empty → no filter (None, not (): _matches_filters treats an empty tuple as
    # "must match a prefix", which silently drops every line).
    min_level = level if level and level.upper() != "ALL" else None
    comp_prefixes = _component_prefixes(component)
    want = min(lines, _MAX_TAIL_LINES)

    def _load_logs():
        result = _read_tail(
            log_path,
            want if not search else 2000,
            has_filters=bool(min_level or comp_prefixes or search),
            min_level=min_level,
            component_prefixes=comp_prefixes,
        )
        # _read_tail doesn't support free-text search, so post-filter (case-insensitive
        # substring) here and trim to the requested line count afterward.
        if search:
            needle = search.lower()
            result = [line for line in result if needle in line.lower()][-want:]
        return result

    result = await asyncio.to_thread(_load_logs)
    return {"file": file, "lines": result}


def _inventory(profile: Optional[str]) -> dict:
    from clawk_cli.logs import LOG_FILES, ROOT_HOME_LOGS
    from clawk_logging import COMPONENT_PREFIXES

    files = []
    for name, filename in LOG_FILES.items():
        path = _log_path(name, profile)
        try:
            st = path.stat()
        except OSError:
            st = None
        files.append(
            {
                "name": name,
                "filename": filename,
                "exists": st is not None,
                "size": st.st_size if st else None,
                "mtime": st.st_mtime if st else None,
                "root_home": name in ROOT_HOME_LOGS,
            }
        )
    return {"files": files, "components": sorted(COMPONENT_PREFIXES)}


@router.get("/api/logs/files")
async def list_log_files(profile: Optional[str] = None):
    """Every log ``clawk logs`` knows, with existence/size/mtime for *profile*, plus the
    component filters the tail endpoint accepts — so the page offers what the backend has."""
    return await asyncio.to_thread(_inventory, profile)


@router.get("/api/logs/download")
async def download_log(file: str, profile: Optional[str] = None):
    """The whole log file as an attachment (the tail endpoint caps at 500 lines)."""
    log_path = _log_path(file, profile)
    if not log_path.is_file():
        raise HTTPException(status_code=404, detail=f"No {file} log yet")
    return FileResponse(
        path=str(log_path), media_type="text/plain", filename=log_path.name
    )
