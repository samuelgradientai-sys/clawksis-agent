"""Live view of the agent's browser in the dashboard chat.

The dashboard is usually remote, so the browser's CDP endpoint (loopback on the server) is not
reachable from the viewer. This router opens it server-side and runs a screencast
(``tools/browser_live_screencast.py``) over the authenticated dashboard socket.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)

_CDP_URL_TIMEOUT_S = 15


def live_task_ids() -> list[str]:
    """Browser sessions open in this process, oldest first (never creates one)."""
    from tools import browser_tool as bt

    with bt._cleanup_lock:
        return list(bt._active_sessions)


def session_cdp_url(task_id: str) -> Optional[str]:
    """The CDP endpoint of ``task_id``'s open browser, or None (no session / no CDP surface)."""
    from tools import browser_tool as bt

    with bt._cleanup_lock:
        info = bt._active_sessions.get(task_id)
    if info is None:
        return None
    if info.get("cdp_url"):
        return str(info["cdp_url"])
    from tools.browser_tool_session import _run_browser_command

    result = _run_browser_command(
        task_id, "get", ["cdp-url"], timeout=_CDP_URL_TIMEOUT_S
    )
    url = ((result.get("data") or {}) if result.get("success") else {}).get("cdpUrl")
    return str(url) if url else None


@router.get("/api/browser/live")
async def list_live_browsers() -> dict[str, Any]:
    return {"sessions": [{"task_id": task_id} for task_id in live_task_ids()]}


@router.websocket("/api/browser/live/ws")
async def live_browser_ws(ws: WebSocket, task: str = "", thumb: bool = False) -> None:
    from clawk_cli.web_routers.chat_ws import _close_unless_sidecar_allowed
    from tools.browser_live_screencast import LiveScreencast

    if not await _close_unless_sidecar_allowed(ws):
        return
    cdp_url = await asyncio.to_thread(session_cdp_url, task) if task else None
    if cdp_url is None:
        await ws.close(code=4404, reason="no live browser for this session")
        return
    from websockets.exceptions import InvalidHandshake, InvalidURI

    await ws.accept()
    try:
        await LiveScreencast(cdp_url, ws.send_json, thumb=thumb).run(ws.receive_text)
    except (
        OSError,
        InvalidHandshake,
        InvalidURI,
    ) as exc:  # OSError covers a CDP call timeout
        logger.info("browser live view for %s ended: %s", task, exc)
    finally:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.close()
