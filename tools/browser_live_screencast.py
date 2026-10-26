"""Live screencast of an agent browser over CDP, for the dashboard's "Navegador" panel.

Works on any browser the session reaches over CDP (agent-browser's local Chromium, which the Browser
Use backend also drives, or a cloud/CDP-override browser). It follows the tab the agent is working in
— the page that most recently navigated — so a Browser Use ``new_tab()`` is picked up, and streams
``Page.screencastFrame`` JPEGs plus the tab list. Viewer input (mouse, wheel, keys, touch) is
dispatched to the followed tab, and the viewer may pin a tab instead of following the agent.

The agent's cursor: a listener installed in an ISOLATED world (invisible to the page's own scripts)
reports where pointer and key events land — CDP-dispatched clicks fire real DOM events — through a
binding, so the viewer can draw the agent's pointer, clicks and typing over the frame.
Messages to the viewer are built here, never relayed raw. ``thumb`` streams a small, input-less
preview for the mosaic of all live browsers.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import logging
import time
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
_THUMB_SCREENCAST = {
    "format": "jpeg",
    "quality": 40,
    "maxWidth": 480,
    "maxHeight": 300,
    # Not 2: a static page paints once, so skipping frames can leave a thumbnail blank forever.
    "everyNthFrame": 1,
}
_CALL_TIMEOUT_S = 10.0
_WORLD = "clawk-live"
_BINDING = "__clawkLive"
# The viewer's own "Tomar control" input also fires DOM events; don't echo it back as the agent's cursor.
_OWN_INPUT_ECHO_S = 0.6
_DUPLICATE_S = 0.05
_CURSOR_KINDS = frozenset({"move", "down", "click", "focus", "type", "scroll"})
CURSOR_SCRIPT = """(() => {
  if (window.top !== window || window.__clawkLiveCursor) return;
  window.__clawkLiveCursor = true;
  const report = (kind, x, y) => {
    try { __clawkLive(JSON.stringify({ kind, x: Math.round(x), y: Math.round(y) })); } catch (_) {}
  };
  const centre = (el) => {
    const r = el && el.getBoundingClientRect ? el.getBoundingClientRect() : null;
    return r && r.width ? [r.left + r.width / 2, r.top + r.height / 2] : null;
  };
  const point = (e) => (e.clientX || e.clientY ? [e.clientX, e.clientY] : centre(e.target));
  let lastMove = 0;
  addEventListener("mousemove", (e) => {
    const now = Date.now();
    if (now - lastMove > 60) { lastMove = now; report("move", e.clientX, e.clientY); }
  }, true);
  for (const kind of ["mousedown", "click"]) {
    addEventListener(kind, (e) => { const p = point(e); if (p) report(kind === "click" ? "click" : "down", ...p); }, true);
  }
  addEventListener("focusin", (e) => { const p = centre(e.target); if (p) report("focus", ...p); }, true);
  let lastKey = 0;
  addEventListener("keydown", () => {
    const now = Date.now(), p = centre(document.activeElement);
    if (p && now - lastKey > 150) { lastKey = now; report("type", ...p); }
  }, true);
  addEventListener("wheel", (e) => report("scroll", e.clientX, e.clientY), { capture: true, passive: true });
})();"""


def _is_page(info: dict) -> bool:
    return info.get("type") == "page" and not str(info.get("url", "")).startswith(
        ("chrome://", "devtools://", "chrome-untrusted://")
    )


def _is_blank(info: dict) -> bool:
    return str(info.get("url", "")) in ("", "about:blank")


def pick_target(
    pages: list[dict], recent: list[str], pinned: Optional[str] = None
) -> Optional[str]:
    """The tab to show: the one the viewer pinned, else the most recently navigated real page, else any
    non-blank page, else any page."""
    by_id = {p["targetId"]: p for p in pages}
    if pinned in by_id:
        return pinned
    for target_id in reversed(recent):
        if target_id in by_id and not _is_blank(by_id[target_id]):
            return target_id
    non_blank = [p for p in pages if not _is_blank(p)]
    chosen = (non_blank or pages)[-1:] if pages else []
    return chosen[0]["targetId"] if chosen else None


def tabs_message(
    pages: list[dict], followed: Optional[str], pinned: bool = False
) -> dict:
    return {
        "type": "tabs",
        "pinned": pinned,
        "tabs": [
            {
                "id": p["targetId"],
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


def cursor_message(payload: str) -> Optional[dict]:
    """The isolated-world listener's report as a viewer ``cursor`` message, or None if malformed."""
    try:
        report = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(report, dict) or report.get("kind") not in _CURSOR_KINDS:
        return None
    x, y = report.get("x"), report.get("y")
    if not all(isinstance(v, (int, float)) for v in (x, y)):
        return None
    return {"type": "cursor", "kind": report["kind"], "x": x, "y": y}


class LiveScreencast:
    """One viewer's screencast over a browser-level CDP WebSocket."""

    def __init__(self, ws_url: str, send: SendToViewer, thumb: bool = False):
        self._ws_url = ws_url
        self._send = send
        self._thumb = thumb
        self._pinned: Optional[str] = None
        self._last_input = 0.0
        self._script_id: Optional[str] = None
        # Every install adds an isolated world, so a page re-attached keeps the earlier listener too.
        self._last_cursor: tuple[str, float] = ("", 0.0)
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
            if isinstance(event, dict):
                await self._on_viewer(event)

    async def _on_viewer(self, event: dict) -> None:
        kind = event.get("type")
        if kind in ("focus_tab", "follow_agent"):
            wanted = event.get("id") if kind == "focus_tab" else None
            self._pinned = wanted if wanted in self._pages else None
            await self._refollow()
            return
        mapped = None if self._thumb else cdp_input(event)
        if mapped and self._session:
            self._last_input = time.monotonic()
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
        handler = {
            "Page.screencastFrame": self._on_frame,
            "Runtime.bindingCalled": self._on_binding,
            "Target.targetCreated": self._on_target_info,
            "Target.targetInfoChanged": self._on_target_info,
            "Target.targetDestroyed": self._on_target_gone,
        }.get(method)
        if handler is not None:
            await handler(params, session)

    async def _on_target_info(self, params: dict, _session: Optional[str]) -> None:
        info = params.get("targetInfo")
        if not info or not _is_page(info):
            return
        previous = self._pages.get(info["targetId"])
        self._pages[info["targetId"]] = info
        if previous is None or previous.get("url") != info.get("url"):
            self._recent = [t for t in self._recent if t != info["targetId"]]
            self._recent.append(info["targetId"])
        await self._refollow()

    async def _on_target_gone(self, params: dict, _session: Optional[str]) -> None:
        if self._pages.pop(params.get("targetId"), None) is not None:
            await self._refollow()

    async def _on_binding(self, params: dict, session: Optional[str]) -> None:
        if session != self._session or params.get("name") != _BINDING:
            return
        now, payload = time.monotonic(), str(params.get("payload", ""))
        if now - self._last_input < _OWN_INPUT_ECHO_S:
            return
        if (
            self._last_cursor[0] == payload
            and now - self._last_cursor[1] < _DUPLICATE_S
        ):
            return
        self._last_cursor = (payload, now)
        message = cursor_message(payload)
        if message is not None:
            await self._send(message)

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
        target = pick_target(pages, self._recent, self._pinned)
        if target != self._followed:
            await self._follow(target)
        await self._send(tabs_message(pages, self._followed, self._pinned is not None))

    async def _follow(self, target: Optional[str]) -> None:
        if self._session:
            with contextlib.suppress(TimeoutError, RuntimeError):
                if self._script_id:
                    await self.call(
                        "Page.removeScriptToEvaluateOnNewDocument",
                        {"identifier": self._script_id},
                        session=self._session,
                    )
                await self.call("Target.detachFromTarget", {"sessionId": self._session})
        self._followed, self._session, self._script_id = target, None, None
        if target is None:
            return
        attached = await self.call(
            "Target.attachToTarget", {"targetId": target, "flatten": True}
        )
        self._session = attached.get("sessionId")
        if not self._session:
            return
        await self.call("Page.enable", session=self._session)
        if not self._thumb:
            await self._install_cursor()
        settings = _THUMB_SCREENCAST if self._thumb else _SCREENCAST
        await self.call("Page.startScreencast", settings, session=self._session)

    async def _install_cursor(self) -> None:
        # Binding calls are only reported to a session with the Runtime domain enabled.
        await self.call("Runtime.enable", session=self._session)
        await self.call(
            "Runtime.addBinding",
            {"name": _BINDING, "executionContextName": _WORLD},
            session=self._session,
        )
        added = await self.call(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": CURSOR_SCRIPT, "worldName": _WORLD, "runImmediately": True},
            session=self._session,
        )
        self._script_id = added.get("identifier")
