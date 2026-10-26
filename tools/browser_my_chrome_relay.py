"""Browser-level CDP emulated on top of the "Mi Chrome" extension's tab-level relay.

The extension (``apps/chrome-extension``) drives the user's own Chrome through ``chrome.debugger``,
which attaches to one TAB at a time and refuses browser-level methods (``Browser.*``, most of
``Target.*``). Every agent browser driver speaks browser-level CDP (agent-browser, Browser Use's
harness, the dashboard live view, the CDP supervisor), so this relay plays the browser:

- targets are the user's debuggable tabs (``chrome://`` pages and the Web Store cannot be debugged);
  ``Target.getTargets`` / ``setDiscoverTargets`` / ``setAutoAttach`` / ``getTargetInfo`` and the
  ``targetCreated`` / ``targetInfoChanged`` / ``targetDestroyed`` events are synthesized from the
  extension's ``chrome.tabs`` reports;
- ``Target.attachToTarget(flatten)`` hands out a relay session id per client; every client shares
  the extension's single ``chrome.debugger`` attachment to that tab, so domain enables are
  refcounted, events go only to the sessions that enabled their domain, and the state a second
  session would miss (live execution contexts, auto-attached frames) is replayed to it;
- ``Target.createTarget`` opens a tab in the user's window, grouped under "Clawksis";
  ``Target.closeTarget`` / ``Page.close`` close only tabs the agent opened; ``Browser.close`` is a
  no-op — agent cleanup never closes the user's Chrome or their tabs.

Transport-neutral: the extension link is an outbox queue plus :meth:`MyChromeRelay.on_extension_message`;
each CDP client is a :class:`RelayClient` with its own outbox. Logs carry method names only, never
params (typed text and page content stay out of the logs).
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CDP_CALL_TIMEOUT_S = 60.0
# A driver command this recent means the agent is using the user's Chrome right now.
_ACTIVE_WINDOW_S = 20.0
_TAB_CALL_TIMEOUT_S = 20.0
DEFAULT_CONTEXT_ID = "C1A0C0DE000000000000000000000001"

_UNDEBUGGABLE_PREFIXES = (
    "chrome://",
    "chrome-extension://",
    "chrome-untrusted://",
    "chrome-search://",
    "devtools://",
    "edge://",
    "brave://",
    "opera://",
    "vivaldi://",
    "view-source:",
    "https://chrome.google.com/webstore",
    "https://chromewebstore.google.com",
)
_SCREENCAST_EVENTS = frozenset(
    {"Page.screencastFrame", "Page.screencastVisibilityChanged"}
)
_ALWAYS_DELIVERED = frozenset({"Inspector"})
# Commands that switch a domain on for the session that sent them (beyond ``<Domain>.enable``).
_IMPLICIT_ENABLES = {
    "DOM.getDocument": "DOM",
    "DOM.getFlattenedDocument": "DOM",
    "Page.startScreencast": "Page.screencast",
}
# How to switch a refcounted key off in Chrome once no session wants it.
_DISABLE_COMMANDS = {
    "Page.screencast": ("Page.stopScreencast", {}),
    "Target": (
        "Target.setAutoAttach",
        {"autoAttach": False, "waitForDebuggerOnStart": False},
    ),
}


class CdpError(Exception):
    """A CDP error reply (``{"code", "message"}``)."""

    def __init__(self, message: str, code: int = -32000):
        super().__init__(message)
        self.code = code


class ExtensionGone(CdpError):
    def __init__(self) -> None:
        super().__init__("Mi Chrome se desconectó (la extensión ya no está conectada).")


def is_debuggable_url(url: str) -> bool:
    """Whether ``chrome.debugger`` can attach to a tab showing ``url``."""
    return bool(url) and not url.startswith(_UNDEBUGGABLE_PREFIXES)


def _new_id() -> str:
    return secrets.token_hex(16).upper()


def _event_key(method: str) -> str:
    """The refcounted key a session must hold to receive ``method``."""
    if method in _SCREENCAST_EVENTS:
        return "Page.screencast"
    return method.split(".", 1)[0]


def _enabled_key(method: str, params: dict) -> Optional[str]:
    if method == "Target.setAutoAttach":
        return "Target" if params.get("autoAttach") else None
    if method in _IMPLICIT_ENABLES:
        return _IMPLICIT_ENABLES[method]
    return method[: -len(".enable")] if method.endswith(".enable") else None


def _disabled_key(method: str, params: dict) -> Optional[str]:
    if method == "Target.setAutoAttach":
        return None if params.get("autoAttach") else "Target"
    if method == "Page.stopScreencast":
        return "Page.screencast"
    return method[: -len(".disable")] if method.endswith(".disable") else None


@dataclass
class TabTarget:
    """One of the user's tabs, as a CDP page target."""

    tab_id: int
    target_id: str
    url: str = ""
    title: str = ""
    window_id: int = -1
    index: int = 0
    active: bool = False
    agent: bool = False
    opened_by_agent: bool = False
    opener_tab_id: Optional[int] = None

    def update(self, tab: dict) -> None:
        self.url = str(tab.get("url") or "")
        self.title = str(tab.get("title") or "")
        self.window_id = int(tab.get("windowId", self.window_id))
        self.index = int(tab.get("index", self.index))
        self.active = bool(tab.get("active"))
        self.agent = bool(tab.get("agent"))
        opener = tab.get("openerTabId")
        self.opener_tab_id = opener if isinstance(opener, int) else None

    @property
    def agent_owned(self) -> bool:
        return self.agent or self.opened_by_agent


@dataclass(eq=False)
class _Session:
    """A client's view of one channel: a tab (``child`` None) or an iframe/worker inside it."""

    id: str
    client: RelayClient
    tab_id: int
    child: Optional[str] = None
    wants: set[str] = field(default_factory=set)


@dataclass
class _Channel:
    """What the shared ``chrome.debugger`` attachment already reported on one channel."""

    contexts: dict[Any, dict] = field(default_factory=dict)
    children: dict[str, dict] = field(default_factory=dict)


class RelayClient:
    """One browser-level CDP connection to the relay. A ``viewer`` (the dashboard live view)
    only watches: its commands do not count as the agent using the browser."""

    def __init__(self, viewer: bool = False) -> None:
        self.viewer = viewer
        self.outbox: asyncio.Queue = asyncio.Queue()
        self.discover = False
        self.auto_attach: Optional[dict] = None
        self.sessions: dict[str, _Session] = {}
        self.closed = False

    def send(self, message: dict) -> None:
        if not self.closed:
            self.outbox.put_nowait(message)


class MyChromeRelay:
    """Browser-level CDP for every client, over one extension connection."""

    def __init__(self) -> None:
        self.outbox: asyncio.Queue = asyncio.Queue()
        self.browser_target_id = _new_id()
        self.product = "Chrome"
        self.user_agent = ""
        self.extension_version = ""
        self.tabs: dict[int, TabTarget] = {}
        self.clients: set[RelayClient] = set()
        self.gone = False
        self.ready = asyncio.Event()
        self.last_agent_command = 0.0
        self._agent_focus: Optional[int] = None
        self._by_target: dict[str, int] = {}
        self._pending: dict[int, asyncio.Future] = {}
        self._ids = itertools.count(1)
        self._attached: set[int] = set()
        self._tab_locks: dict[int, asyncio.Lock] = {}
        self._channels: dict[tuple[int, Optional[str]], _Channel] = {}
        self._child_tabs: dict[str, int] = {}
        self._browser_handlers = {
            "Browser.getVersion": self._get_version,
            "Browser.close": self._browser_close,
            "Browser.getWindowForTarget": self._window_for_target,
            "Browser.setDownloadBehavior": self._noop,
            "Browser.grantPermissions": self._noop,
            "Browser.resetPermissions": self._noop,
            "Target.getTargets": self._get_targets,
            "Target.getTargetInfo": self._get_target_info,
            "Target.setDiscoverTargets": self._set_discover_targets,
            "Target.setAutoAttach": self._set_browser_auto_attach,
            "Target.attachToTarget": self._attach_to_target,
            "Target.detachFromTarget": self._detach_from_target,
            "Target.createTarget": self._create_target,
            "Target.closeTarget": self._close_target,
            "Target.activateTarget": self._activate_target,
            "Target.getBrowserContexts": self._browser_contexts,
            "Target.setRemoteLocations": self._noop,
        }

    # ── extension side ──────────────────────────────────────────────────────

    async def ext_call(
        self, kind: str, timeout: float = _TAB_CALL_TIMEOUT_S, **payload
    ) -> dict:
        """One request to the extension; its ``result`` or a :class:`CdpError`."""
        if self.gone:
            raise ExtensionGone()
        call_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[call_id] = future
        self.outbox.put_nowait({"id": call_id, "type": kind, **payload})
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            raise CdpError(f"Mi Chrome no respondió a {kind} a tiempo.") from None
        finally:
            self._pending.pop(call_id, None)

    async def on_extension_message(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind in ("result", "error"):
            self._settle(msg)
            return
        handler = {
            "hello": self._on_hello,
            "tab": self._on_tab_event,
            "event": self._on_cdp_event,
            "detached": self._on_debugger_detached,
        }.get(kind)
        if handler is not None:
            await handler(msg)

    def _settle(self, msg: dict) -> None:
        future = self._pending.get(msg.get("id"))
        if future is None or future.done():
            return
        if msg.get("type") == "result":
            future.set_result(msg.get("result") or {})
            return
        error = msg.get("error") or {}
        future.set_exception(
            CdpError(
                str(error.get("message") or "error"), int(error.get("code") or -32000)
            )
        )

    async def shutdown(self) -> None:
        """The extension went away: fail pending calls and drop every client."""
        self.gone = True
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ExtensionGone())
        for client in list(self.clients):
            client.closed = True
            client.outbox.put_nowait(None)
        self.clients.clear()

    async def _on_hello(self, msg: dict) -> None:
        self.product = str(msg.get("product") or "Chrome")
        self.user_agent = str(msg.get("userAgent") or "")
        self.extension_version = str(msg.get("version") or "")
        for tab in msg.get("tabs") or []:
            self._upsert_tab(tab)
        self.ready.set()

    async def _on_tab_event(self, msg: dict) -> None:
        event = msg.get("event")
        if event in ("created", "updated"):
            self._upsert_tab(msg.get("tab") or {})
        elif event == "removed":
            self._remove_tab(msg.get("tabId"))
        elif event == "activated":
            self._activate_tab(msg.get("tabId"), msg.get("windowId"))

    # ── tab registry ────────────────────────────────────────────────────────

    def target_info(self, tab: TabTarget) -> dict:
        info = {
            "targetId": tab.target_id,
            "type": "page",
            "title": tab.title,
            "url": tab.url,
            "attached": any(s.tab_id == tab.tab_id for s in self._all_sessions()),
            "canAccessOpener": False,
            "browserContextId": DEFAULT_CONTEXT_ID,
        }
        opener = self.tabs.get(tab.opener_tab_id) if tab.opener_tab_id else None
        if opener is not None:
            info["openerId"] = opener.target_id
        return info

    def _visible(self, tab: Optional[TabTarget]) -> bool:
        return tab is not None and is_debuggable_url(tab.url)

    def ordered_targets(self) -> list[TabTarget]:
        """Debuggable tabs: the agent's own first (drivers attach to the first page), then the
        tab the user is looking at, then the rest in tab-strip order."""
        tabs = [t for t in self.tabs.values() if self._visible(t)]
        return sorted(
            tabs, key=lambda t: (not t.agent_owned, not t.active, t.window_id, t.index)
        )

    def _upsert_tab(
        self, raw: dict, opened_by_agent: bool = False
    ) -> Optional[TabTarget]:
        tab_id = raw.get("id")
        if not isinstance(tab_id, int):
            return None
        tab = self.tabs.get(tab_id)
        was_visible = self._visible(tab)
        if tab is None:
            tab = TabTarget(tab_id=tab_id, target_id=_new_id())
            self.tabs[tab_id] = tab
            self._by_target[tab.target_id] = tab_id
        before = (tab.url, tab.title)
        tab.update(raw)
        tab.opened_by_agent = tab.opened_by_agent or opened_by_agent
        visible = self._visible(tab)
        if visible and not was_visible:
            self._announce_created(tab)
        elif was_visible and not visible:
            self._announce_destroyed(tab)
        elif visible and before != (tab.url, tab.title):
            self._broadcast_discovery(
                "Target.targetInfoChanged", {"targetInfo": self.target_info(tab)}
            )
        return tab

    def _remove_tab(self, tab_id: Any) -> None:
        tab = self.tabs.pop(tab_id, None) if isinstance(tab_id, int) else None
        if tab is None:
            return
        self._by_target.pop(tab.target_id, None)
        self._attached.discard(tab.tab_id)
        if is_debuggable_url(tab.url):
            self._announce_destroyed(tab)

    def _activate_tab(self, tab_id: Any, window_id: Any) -> None:
        for tab in self.tabs.values():
            if tab.window_id == window_id:
                tab.active = tab.tab_id == tab_id

    def _announce_created(self, tab: TabTarget) -> None:
        self._broadcast_discovery(
            "Target.targetCreated", {"targetInfo": self.target_info(tab)}
        )
        for client in list(self.clients):
            if client.auto_attach is not None:
                self._auto_attach_tab(client, tab)

    def _announce_destroyed(self, tab: TabTarget) -> None:
        """The target is gone (closed, or now showing a page Chrome won't let us debug)."""
        for session in [s for s in self._all_sessions() if s.tab_id == tab.tab_id]:
            self._drop_session(session, notify=True)
        self._reset_tab(tab.tab_id)
        self._broadcast_discovery("Target.targetDestroyed", {"targetId": tab.target_id})

    def _broadcast_discovery(self, method: str, params: dict) -> None:
        for client in list(self.clients):
            if client.discover:
                client.send({"method": method, "params": params})

    def tab_for_target(self, target_id: Any) -> TabTarget:
        tab = self.tabs.get(self._by_target.get(target_id, -1))
        if not self._visible(tab):
            raise CdpError(f"No target with given id found: {target_id}")
        return tab  # type: ignore[return-value]

    # ── sessions ────────────────────────────────────────────────────────────

    def _all_sessions(self) -> list[_Session]:
        return [s for c in self.clients for s in c.sessions.values()]

    def _channel_sessions(self, tab_id: int, child: Optional[str]) -> list[_Session]:
        return [
            s for s in self._all_sessions() if s.tab_id == tab_id and s.child == child
        ]

    def _channel(self, tab_id: int, child: Optional[str]) -> _Channel:
        return self._channels.setdefault((tab_id, child), _Channel())

    def _new_session(self, client: RelayClient, tab: TabTarget) -> _Session:
        session = _Session(id=_new_id(), client=client, tab_id=tab.tab_id)
        client.sessions[session.id] = session
        return session

    def _attached_event(
        self, session: _Session, tab: TabTarget, waiting: bool = False
    ) -> dict:
        return {
            "method": "Target.attachedToTarget",
            "params": {
                "sessionId": session.id,
                "targetInfo": {**self.target_info(tab), "attached": True},
                "waitingForDebugger": waiting,
            },
        }

    def _auto_attach_tab(self, client: RelayClient, tab: TabTarget) -> None:
        if any(
            s.tab_id == tab.tab_id and s.child is None for s in client.sessions.values()
        ):
            return
        session = self._new_session(client, tab)
        client.send(self._attached_event(session, tab))

    def _drop_session(self, session: _Session, notify: bool) -> None:
        client = session.client
        client.sessions.pop(session.id, None)
        if session.child is None:
            for child in [
                s
                for s in client.sessions.values()
                if s.tab_id == session.tab_id and s.child
            ]:
                client.sessions.pop(child.id, None)
        if notify:
            tab = self.tabs.get(session.tab_id)
            client.send(
                {
                    "method": "Target.detachedFromTarget",
                    "params": {
                        "sessionId": session.id,
                        "targetId": tab.target_id if tab else "",
                    },
                }
            )

    def _release_channel_keys(self, session: _Session) -> None:
        """Switch off in Chrome what only ``session`` still wanted (after it was dropped)."""
        if session.child is not None:
            return
        remaining = self._channel_sessions(session.tab_id, None)
        if not remaining:
            self._spawn(self._detach_tab(session.tab_id))
            return
        still = set().union(*(s.wants for s in remaining))
        for key in session.wants - still:
            method, params = _DISABLE_COMMANDS.get(key, (f"{key}.disable", {}))
            if key == "Runtime":
                self._channel(session.tab_id, None).contexts.clear()
            self._spawn(self._forward_quietly(session.tab_id, None, method, params))

    async def _forward_quietly(
        self, tab_id: int, child: Optional[str], method: str, params: dict
    ) -> None:
        with contextlib.suppress(CdpError):
            await self._forward(tab_id, child, method, params)

    def _spawn(self, coro) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        task.add_done_callback(lambda t: t.cancelled() or t.exception())

    async def remove_client(self, client: RelayClient) -> None:
        client.closed = True
        self.clients.discard(client)
        for session in list(client.sessions.values()):
            client.sessions.pop(session.id, None)
            self._release_channel_keys(session)

    def add_client(self, viewer: bool = False) -> RelayClient:
        client = RelayClient(viewer=viewer)
        self.clients.add(client)
        return client

    # ── chrome.debugger attachment ──────────────────────────────────────────

    async def _ensure_attached(self, tab_id: int) -> None:
        lock = self._tab_locks.setdefault(tab_id, asyncio.Lock())
        async with lock:
            if tab_id not in self._attached:
                await self.ext_call("attach", tabId=tab_id)
                self._attached.add(tab_id)

    async def _detach_tab(self, tab_id: int) -> None:
        lock = self._tab_locks.setdefault(tab_id, asyncio.Lock())
        async with lock:
            if self._channel_sessions(tab_id, None) or tab_id not in self._attached:
                return
            self._attached.discard(tab_id)
            self._reset_tab(tab_id)
            with contextlib.suppress(CdpError):
                await self.ext_call("detach", tabId=tab_id)

    def _reset_tab(self, tab_id: int) -> None:
        for key in [k for k in self._channels if k[0] == tab_id]:
            self._channels.pop(key, None)
        for child in [c for c, t in self._child_tabs.items() if t == tab_id]:
            self._child_tabs.pop(child, None)

    async def _on_debugger_detached(self, msg: dict) -> None:
        tab_id = msg.get("tabId")
        if not isinstance(tab_id, int):
            return
        self._attached.discard(tab_id)
        logger.info("Mi Chrome: debugger detached from a tab (%s)", msg.get("reason"))
        for session in [
            s for s in self._all_sessions() if s.tab_id == tab_id and s.child is None
        ]:
            self._drop_session(session, notify=True)
        self._reset_tab(tab_id)

    async def _forward(
        self, tab_id: int, child: Optional[str], method: str, params: dict
    ) -> dict:
        if child is None:
            await self._ensure_attached(tab_id)
        payload = {"tabId": tab_id, "method": method, "params": params}
        if child is not None:
            payload["sessionId"] = child
        return await self.ext_call("cdp", timeout=_CDP_CALL_TIMEOUT_S, **payload)

    # ── events from Chrome ──────────────────────────────────────────────────

    async def _on_cdp_event(self, msg: dict) -> None:
        tab_id, child = msg.get("tabId"), msg.get("sessionId") or None
        method, params = str(msg.get("method") or ""), msg.get("params") or {}
        if not isinstance(tab_id, int):
            return
        self._track(tab_id, child, method, params)
        key = _event_key(method)
        for session in self._channel_sessions(tab_id, child):
            if key in _ALWAYS_DELIVERED or key in session.wants:
                self._deliver_event(session, method, params)

    def _deliver_event(self, session: _Session, method: str, params: dict) -> None:
        session.client.send(
            {"method": method, "params": params, "sessionId": session.id}
        )
        if method == "Target.attachedToTarget" and session.child is None:
            self._adopt_child(session.client, session.tab_id, params)
        elif method == "Target.detachedFromTarget" and session.child is None:
            session.client.sessions.pop(str(params.get("sessionId")), None)

    def _adopt_child(self, client: RelayClient, tab_id: int, params: dict) -> None:
        child = str(params.get("sessionId") or "")
        if child and child not in client.sessions:
            client.sessions[child] = _Session(
                id=child, client=client, tab_id=tab_id, child=child
            )

    def _track(
        self, tab_id: int, child: Optional[str], method: str, params: dict
    ) -> None:
        channel = self._channel(tab_id, child)
        if method == "Runtime.executionContextCreated":
            context = params.get("context") or {}
            channel.contexts[context.get("id")] = context
        elif method == "Runtime.executionContextDestroyed":
            channel.contexts.pop(params.get("executionContextId"), None)
        elif method == "Runtime.executionContextsCleared":
            channel.contexts.clear()
        elif method == "Target.attachedToTarget" and child is None:
            sid = str(params.get("sessionId") or "")
            channel.children[sid] = params
            self._child_tabs[sid] = tab_id
        elif method == "Target.detachedFromTarget" and child is None:
            sid = str(params.get("sessionId") or "")
            channel.children.pop(sid, None)
            self._child_tabs.pop(sid, None)
            self._channels.pop((tab_id, sid), None)

    def _replay(self, session: _Session, key: str) -> None:
        """Hand a session that joined an already-enabled channel what Chrome reported before it."""
        channel = self._channel(session.tab_id, session.child)
        if key == "Runtime":
            for context in list(channel.contexts.values()):
                self._deliver_event(
                    session, "Runtime.executionContextCreated", {"context": context}
                )
        elif key == "Target":
            for params in list(channel.children.values()):
                self._deliver_event(session, "Target.attachedToTarget", params)

    # ── commands from clients ───────────────────────────────────────────────

    async def handle_client_message(self, client: RelayClient, msg: dict) -> None:
        """Answer one CDP command from ``client`` (replies are queued on its outbox)."""
        msg_id, session_id = msg.get("id"), msg.get("sessionId")
        method, params = str(msg.get("method") or ""), msg.get("params") or {}
        if not client.viewer:
            self.last_agent_command = time.monotonic()
        try:
            if session_id:
                result = await self._session_command(
                    client, str(session_id), method, params
                )
            else:
                result = await self._browser_command(client, method, params)
            reply: dict = {"id": msg_id, "result": result}
        except CdpError as exc:
            reply = {"id": msg_id, "error": {"code": exc.code, "message": str(exc)}}
        if session_id:
            reply["sessionId"] = session_id
        client.send(reply)

    async def _browser_command(
        self, client: RelayClient, method: str, params: dict
    ) -> dict:
        handler = self._browser_handlers.get(method)
        if handler is None:
            logger.debug("Mi Chrome relay: unsupported browser-level %s", method)
            raise CdpError(f"'{method}' wasn't found", -32601)
        return await handler(client, params)

    async def _session_command(
        self, client: RelayClient, session_id: str, method: str, params: dict
    ) -> dict:
        session = client.sessions.get(session_id)
        if session is None:
            raise CdpError("Session with given id not found.", -32001)
        if not client.viewer and session.child is None:
            self._note_agent_focus(session.tab_id)
        if method.startswith(
            "Browser."
        ):  # Chrome answers the browser domain on any session
            return await self._browser_command(client, method, params)
        if method.startswith("Target.") and method != "Target.setAutoAttach":
            return await self._session_target_command(client, session, method, params)
        if method == "Page.close" and session.child is None:
            return await self._close_tab(session.tab_id)
        if method == "Page.captureScreenshot" and session.child is None:
            await self._bring_to_front(session.tab_id)
        off = _disabled_key(method, params)
        if off is not None:
            session.wants.discard(off)
            if any(
                off in s.wants
                for s in self._channel_sessions(session.tab_id, session.child)
            ):
                return {}
        on = _enabled_key(method, params)
        already = on is not None and any(
            on in s.wants
            for s in self._channel_sessions(session.tab_id, session.child)
            if s is not session
        )
        result = await self._forward(session.tab_id, session.child, method, params)
        if on is not None:
            session.wants.add(on)
            if already:
                self._replay(session, on)
        return result

    async def _session_target_command(
        self, client: RelayClient, session: _Session, method: str, params: dict
    ) -> dict:
        """``Target.*`` sent on a page session: answer for that page, or as the browser would."""
        if method == "Target.getTargetInfo" and not params.get("targetId"):
            tab = self.tabs.get(session.tab_id)
            if tab is None:
                raise CdpError("No target with given id found")
            return {"targetInfo": self.target_info(tab)}
        if (
            method == "Target.detachFromTarget"
            and params.get("sessionId") in self._child_tabs
        ):
            client.sessions.pop(str(params["sessionId"]), None)
            return {}
        return await self._browser_command(client, method, params)

    async def _bring_to_front(self, tab_id: int) -> None:
        """A background tab never paints, so its screenshot would hang (as puppeteer does)."""
        tab = self.tabs.get(tab_id)
        if tab is not None and not tab.active:
            with contextlib.suppress(CdpError):
                await self.ext_call("activate_tab", tabId=tab_id)

    # ── browser-level handlers ──────────────────────────────────────────────

    async def _noop(self, _client: RelayClient, _params: dict) -> dict:
        return {}

    async def _browser_close(self, _client: RelayClient, _params: dict) -> dict:
        logger.info(
            "Mi Chrome relay: Browser.close ignored (the user's Chrome stays open)"
        )
        return {}

    async def _get_version(self, _client: RelayClient, _params: dict) -> dict:
        return {
            "protocolVersion": "1.3",
            "product": self.product,
            "revision": "",
            "userAgent": self.user_agent,
            "jsVersion": "",
        }

    async def _window_for_target(self, _client: RelayClient, params: dict) -> dict:
        tab = (
            self.tab_for_target(params.get("targetId"))
            if params.get("targetId")
            else None
        )
        return {
            "windowId": tab.window_id if tab else 1,
            "bounds": {"windowState": "normal"},
        }

    async def _browser_contexts(self, _client: RelayClient, _params: dict) -> dict:
        return {"browserContextIds": []}

    async def _get_targets(self, _client: RelayClient, _params: dict) -> dict:
        return {"targetInfos": [self.target_info(t) for t in self.ordered_targets()]}

    async def _get_target_info(self, _client: RelayClient, params: dict) -> dict:
        if (
            not params.get("targetId")
            or params.get("targetId") == self.browser_target_id
        ):
            return {
                "targetInfo": {
                    "targetId": self.browser_target_id,
                    "type": "browser",
                    "title": "",
                    "url": "",
                    "attached": True,
                    "canAccessOpener": False,
                }
            }
        return {"targetInfo": self.target_info(self.tab_for_target(params["targetId"]))}

    async def _set_discover_targets(self, client: RelayClient, params: dict) -> dict:
        client.discover = bool(params.get("discover"))
        if client.discover:
            for tab in self.ordered_targets():
                client.send(
                    {
                        "method": "Target.targetCreated",
                        "params": {"targetInfo": self.target_info(tab)},
                    }
                )
        return {}

    async def _set_browser_auto_attach(self, client: RelayClient, params: dict) -> dict:
        if not params.get("autoAttach"):
            client.auto_attach = None
            return {}
        if params.get("flatten") is False:
            raise CdpError("Mi Chrome only supports flatten sessions")
        client.auto_attach = dict(params)
        for tab in self.ordered_targets():
            self._auto_attach_tab(client, tab)
        return {}

    async def _attach_to_target(self, client: RelayClient, params: dict) -> dict:
        if params.get("flatten") is False:
            raise CdpError("Mi Chrome only supports flatten sessions")
        tab = self.tab_for_target(params.get("targetId"))
        await self._ensure_attached(tab.tab_id)
        session = self._new_session(client, tab)
        client.send(self._attached_event(session, tab))
        return {"sessionId": session.id}

    async def _detach_from_target(self, client: RelayClient, params: dict) -> dict:
        sid = params.get("sessionId")
        if sid is None and params.get("targetId"):
            tab = self.tab_for_target(params["targetId"])
            sid = next(
                (
                    s.id
                    for s in client.sessions.values()
                    if s.tab_id == tab.tab_id and s.child is None
                ),
                None,
            )
        session = client.sessions.get(str(sid)) if sid else None
        if session is None:
            raise CdpError("No session with given id")
        self._drop_session(session, notify=True)
        self._release_channel_keys(session)
        return {}

    async def _create_target(self, client: RelayClient, params: dict) -> dict:
        # Always in front: a background tab never paints, so screenshots and the live view would
        # stall. The tab joins the "Clawksis" group so the user sees which tabs are the agent's.
        url = str(params.get("url") or "about:blank")
        result = await self.ext_call("create_tab", url=url, active=True)
        tab = self._upsert_tab(result.get("tab") or {}, opened_by_agent=True)
        if tab is None:
            raise CdpError("Mi Chrome no pudo abrir la pestaña.")
        return {"targetId": tab.target_id}

    async def _close_target(self, _client: RelayClient, params: dict) -> dict:
        tab = self.tab_for_target(params.get("targetId"))
        await self._close_tab(tab.tab_id)
        return {"success": True}

    async def _close_tab(self, tab_id: int) -> dict:
        tab = self.tabs.get(tab_id)
        if tab is None:
            raise CdpError("No target with given id found")
        if not tab.agent_owned:
            raise CdpError(
                "Mi Chrome no cierra pestañas del usuario: solo las que abrió el agente (grupo Clawksis)."
            )
        await self.ext_call("close_tab", tabId=tab_id)
        return {}

    async def _activate_target(self, client: RelayClient, params: dict) -> dict:
        tab = self.tab_for_target(params.get("targetId"))
        await self.ext_call("activate_tab", tabId=tab.tab_id)
        if not client.viewer:
            self._note_agent_focus(tab.tab_id)
        return {}

    def _note_agent_focus(self, tab_id: int) -> None:
        """The tab an agent driver is working in now; live viewers follow it (``Clawk.agentFocus``,
        a relay-only event: on the user's Chrome a form filled in place never navigates)."""
        tab = self.tabs.get(tab_id)
        if tab_id == self._agent_focus or not self._visible(tab):
            return
        self._agent_focus = tab_id
        for viewer in [c for c in self.clients if c.viewer and c.discover]:
            viewer.send(
                {"method": "Clawk.agentFocus", "params": {"targetId": tab.target_id}}
            )

    # ── status ──────────────────────────────────────────────────────────────

    def agent_active(self) -> bool:
        """Whether an agent driver (not the live view) sent a command in the last few seconds."""
        return bool(self.last_agent_command) and (
            time.monotonic() - self.last_agent_command < _ACTIVE_WINDOW_S
        )

    def focus_target_id(self) -> Optional[str]:
        """The tab a viewer should see first: the one an agent is driving, else the agent's tab in
        front, else the agent's newest tab, else the tab the user is looking at."""
        tabs = self.ordered_targets()
        agent = [t for t in tabs if t.agent_owned]
        for pool in (
            [t for t in tabs if t.tab_id == self._agent_focus],
            [t for t in agent if t.active],
            sorted(agent, key=lambda t: t.tab_id)[-1:],
            [t for t in tabs if t.active],
            tabs,
        ):
            if pool:
                return pool[0].target_id
        return None

    def tab_summaries(self) -> list[dict]:
        """The tabs the agent can use, for the dashboard (titles and URLs only)."""
        return [
            {
                "id": t.target_id,
                "title": t.title,
                "url": t.url,
                "active": t.active,
                "agent": t.agent_owned,
                "attached": t.tab_id in self._attached,
            }
            for t in self.ordered_targets()
        ]
