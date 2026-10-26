"""Live screencast of an agent browser over CDP, for the dashboard's "Navegador" panel.

Works on any browser the session reaches over CDP (agent-browser's local Chromium, which the Browser
Use backend also drives, or a cloud/CDP-override browser). It follows the tab the agent is working in
— the page that most recently navigated — so a Browser Use ``new_tab()`` is picked up, and streams
``Page.screencastFrame`` JPEGs plus the tab list. Viewer input (mouse, wheel, keys, touch) is
dispatched to the followed tab. Messages to the viewer are built here, never relayed raw.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

SendToViewer = Callable[[dict], Awaitable[None]]
_SCREENCAST = {
    "format": "jpeg",
    "quality": 60,
    "maxWidth": 1280,
    "maxHeight": 800,
    "everyNthFrame": 1,
}
_CALL_TIMEOUT_S = 10.0


def _is_page(info: dict) -> bool:
    return info.get("type") == "page" and not str(info.get("url", "")).startswith(
        ("chrome://", "devtools://", "chrome-untrusted://")
    )


def _is_blank(info: dict) -> bool:
    return str(info.get("url", "")) in ("", "about:blank")


def pick_target(pages: list[dict], recent: list[str]) -> Optional[str]:
    """The tab to follow: the most recently navigated real page, else any non-blank page, else any page."""
    by_id = {p["targetId"]: p for p in pages}
    for target_id in reversed(recent):
        if target_id in by_id and not _is_blank(by_id[target_id]):
            return target_id
    non_blank = [p for p in pages if not _is_blank(p)]
    chosen = (non_blank or pages)[-1:] if pages else []
    return chosen[0]["targetId"] if chosen else None


def tabs_message(pages: list[dict], followed: Optional[str]) -> dict:
    return {
        "type": "tabs",
        "tabs": [
            {
                "active": p["targetId"] == followed,
                "title": p.get("title") or None,
                "url": p.get("url", ""),
            }
            for p in pages
        ],
    }


def cdp_input(event: dict) -> Optional[tuple[str, dict]]:
    """A viewer input event as ``(CDP method, params)``, or None for anything else."""
    kind = event.get("type")
    if kind == "input_mouse":
        params = {
            k: event[k]
            for k in ("x", "y", "button", "clickCount", "modifiers", "deltaX", "deltaY")
            if k in event
        }
        return "Input.dispatchMouseEvent", {"type": event.get("eventType"), **params}
    if kind == "input_keyboard":
        params = {
            k: event[k]
            for k in ("key", "code", "text", "windowsVirtualKeyCode", "modifiers")
            if event.get(k) is not None
        }
        down = event.get("eventType") == "keyDown"
        return "Input.dispatchKeyEvent", {
            "type": ("keyDown" if params.get("text") else "rawKeyDown")
            if down
            else "keyUp",
            **params,
        }
    if kind == "input_touch":
        return "Input.dispatchTouchEvent", {
            "type": event.get("eventType"),
            "touchPoints": event.get("touchPoints") or [],
        }
    return None


class LiveScreencast:
    """One viewer's screencast over a browser-level CDP WebSocket."""

    def __init__(self, ws_url: str, send: SendToViewer):
        self._ws_url = ws_url
        self._send = send
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._pages: dict[str, dict] = {}
        self._recent: list[str] = []
        self._followed: Optional[str] = None
        self._session: Optional[str] = None
        self._conn: Any = None
        # Events are handled off the reader: a handler awaits CDP replies only the reader can deliver.
        self._events: asyncio.Queue = asyncio.Queue()

    async def call(
        self, method: str, params: Optional[dict] = None, session: Optional[str] = None
    ) -> dict:
        msg_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        frame = {"id": msg_id, "method": method, "params": params or {}}
        if session:
            frame["sessionId"] = session
        await self._conn.send(json.dumps(frame))
        try:
            return await asyncio.wait_for(future, _CALL_TIMEOUT_S)
        finally:
            self._pending.pop(msg_id, None)

    async def run(self, viewer_input: Callable[[], Awaitable[str]]) -> None:
        from websockets.asyncio.client import connect

        async with connect(self._ws_url, max_size=None) as conn:
            self._conn = conn
            reader = asyncio.create_task(self._read())
            tasks = [reader]
            try:
                targets = (await self.call("Target.getTargets")).get("targetInfos", [])
                self._pages = {t["targetId"]: t for t in targets if _is_page(t)}
                await self._send({"type": "status", "connected": True})
                await self._refollow()
                await self.call("Target.setDiscoverTargets", {"discover": True})
                tasks += [
                    asyncio.create_task(self._handle_events()),
                    asyncio.create_task(self._pump_input(viewer_input)),
                ]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in (
                    done
                ):  # the viewer left or the browser closed: either ends the view
                    if not task.cancelled() and task.exception() is not None:
                        logger.debug("live screencast ended: %r", task.exception())
            finally:
                for task in tasks:
                    task.cancel()
                with contextlib.suppress(Exception):
                    await self._send({"type": "status", "connected": False})

    async def _pump_input(self, viewer_input: Callable[[], Awaitable[str]]) -> None:
        while True:
            try:
                event = json.loads(await viewer_input())
            except ValueError:
                continue
            mapped = cdp_input(event) if isinstance(event, dict) else None
            if mapped and self._session:
                with contextlib.suppress(TimeoutError, RuntimeError):
                    await self.call(*mapped, session=self._session)

    async def _read(self) -> None:
        from websockets.exceptions import ConnectionClosed

        with contextlib.suppress(ConnectionClosed):
            await self._read_frames()

    async def _read_frames(self) -> None:
        async for raw in self._conn:
            message = json.loads(raw)
            if "id" in message:
                future = self._pending.get(message["id"])
                if future and not future.done():
                    future.set_result(message.get("result") or {})
                continue
            self._events.put_nowait(
                (
                    message.get("method", ""),
                    message.get("params") or {},
                    message.get("sessionId"),
                )
            )

    async def _handle_events(self) -> None:
        while True:
            await self._on_event(*await self._events.get())

    async def _on_event(
        self, method: str, params: dict, session: Optional[str]
    ) -> None:
        if method == "Page.screencastFrame":
            await self._on_frame(params, session)
            return
        info = params.get("targetInfo")
        if (
            method in ("Target.targetCreated", "Target.targetInfoChanged")
            and info
            and _is_page(info)
        ):
            previous = self._pages.get(info["targetId"], {})
            self._pages[info["targetId"]] = info
            if method == "Target.targetCreated" or previous.get("url") != info.get(
                "url"
            ):
                self._recent = [t for t in self._recent if t != info["targetId"]] + [
                    info["targetId"]
                ]
            await self._refollow()
        elif (
            method == "Target.targetDestroyed" and params.get("targetId") in self._pages
        ):
            self._pages.pop(params["targetId"])
            await self._refollow()

    async def _on_frame(self, params: dict, session: Optional[str]) -> None:
        if session != self._session:
            return
        meta = params.get("metadata") or {}
        await self._send(
            {
                "type": "frame",
                "data": params.get("data", ""),
                "metadata": {
                    "deviceWidth": meta.get("deviceWidth"),
                    "deviceHeight": meta.get("deviceHeight"),
                },
            }
        )
        with contextlib.suppress(TimeoutError, RuntimeError):
            await self.call(
                "Page.screencastFrameAck",
                {"sessionId": params.get("sessionId")},
                session=session,
            )

    async def _refollow(self) -> None:
        pages = list(self._pages.values())
        target = pick_target(pages, self._recent)
        if target != self._followed:
            await self._follow(target)
        await self._send(tabs_message(pages, self._followed))

    async def _follow(self, target: Optional[str]) -> None:
        if self._session:
            with contextlib.suppress(TimeoutError, RuntimeError):
                await self.call("Target.detachFromTarget", {"sessionId": self._session})
        self._followed, self._session = target, None
        if target is None:
            return
        attached = await self.call(
            "Target.attachToTarget", {"targetId": target, "flatten": True}
        )
        self._session = attached.get("sessionId")
        if self._session:
            await self.call("Page.enable", session=self._session)
            await self.call("Page.startScreencast", _SCREENCAST, session=self._session)
