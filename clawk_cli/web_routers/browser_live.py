"""Live view of the agent's browser in the dashboard chat.

The dashboard is usually remote, so the browser's CDP endpoint (loopback on the server) is not
reachable from the viewer. This router opens it server-side and runs a screencast
(``tools/browser_live_screencast.py``) over the authenticated dashboard socket.

A connected "Mi Chrome" extension (``my_chrome.py``) is listed as its own entry, whichever
process drives it (dashboard chat or the messaging gateway); agent sessions in this process that
run on it are folded into that entry instead of showing the same Chrome twice.
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


MY_CHROME_PREFIX = "mi-chrome:"


def my_chrome_entries() -> list[dict[str, Any]]:
    """One live-view entry per Mi Chrome extension connected to this process."""
    from clawk_cli.web_routers.my_chrome import links

    return [
        {
            "task_id": f"{MY_CHROME_PREFIX}{index}",
            "kind": "my_chrome",
            "label": "Mi Chrome",
            "cdp_url": link.cdp_url,
        }
        for index, link in enumerate(links())
    ]


def _my_chrome_target(task: str) -> Optional[tuple[str, Optional[str]]]:
    """``(cdp_url, tab to show first)`` for a Mi Chrome entry, or None when it is gone. The
    viewer flag keeps the live view's own traffic from counting as the agent's."""
    from clawk_cli.web_routers.my_chrome import links

    index, current = task[len(MY_CHROME_PREFIX) :], links()
    if not index.isdigit() or int(index) >= len(current):
        return None
    link = current[int(index)]
    return f"{link.cdp_url}?viewer=1", link.relay.focus_target_id()


def _runs_on(task_id: str, cdp_urls: set[str]) -> bool:
    from tools import browser_tool as bt

    with bt._cleanup_lock:
        info = bt._active_sessions.get(task_id) or {}
    return str(info.get("cdp_url") or "") in cdp_urls


@router.get("/api/browser/live")
async def list_live_browsers() -> dict[str, Any]:
    mine = my_chrome_entries()
    relay_urls = {entry.pop("cdp_url") for entry in mine}
    own = [
        {"task_id": task_id}
        for task_id in live_task_ids()
        if not _runs_on(task_id, relay_urls)
    ]
    return {"sessions": own + mine}


@router.websocket("/api/browser/live/ws")
async def live_browser_ws(ws: WebSocket, task: str = "", thumb: bool = False) -> None:
    from clawk_cli.web_routers.chat_ws import _close_unless_sidecar_allowed
    from tools.browser_live_screencast import LiveScreencast

    if not await _close_unless_sidecar_allowed(ws):
        return
    focus: Optional[str] = None
    if task.startswith(MY_CHROME_PREFIX):
        cdp_url, focus = _my_chrome_target(task) or (None, None)
    else:
        cdp_url = await asyncio.to_thread(session_cdp_url, task) if task else None
    if cdp_url is None:
        await ws.close(code=4404, reason="no live browser for this session")
        return
    from websockets.exceptions import InvalidHandshake, InvalidURI

    await ws.accept()
    try:
        screencast = LiveScreencast(cdp_url, ws.send_json, thumb=thumb, focus=focus)
        await screencast.run(ws.receive_text)
    except (
        OSError,
        InvalidHandshake,
        InvalidURI,
    ) as exc:  # OSError covers a CDP call timeout
        logger.info("browser live view for %s ended: %s", task, exc)
    finally:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.close()


from clawk_cli.web_routers.my_chrome import router as _my_chrome_router

router.include_router(_my_chrome_router)
