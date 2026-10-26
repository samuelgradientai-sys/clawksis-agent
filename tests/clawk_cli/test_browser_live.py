"""Live view of the agent's browser: the dashboard screencasts the session's browser over CDP.

Contract: the viewer sees the tab the agent is working in — including a tab Browser Use opened with
``new_tab()`` — as JPEG frames plus the tab list and the agent's cursor (reported from an isolated
world the page can't see); the viewer may pin another tab and go back to following the agent; only
mouse/keyboard/touch input reaches the browser, on the shown tab; thumbnails take no input and
install nothing; a session without a browser is a 4404 close; the socket needs dashboard auth.
"""

import asyncio
import json
import threading

import pytest

from clawk_cli.web_routers import browser_live
from tools import browser_live_screencast as sc

BLANK = {"targetId": "T1", "type": "page", "url": "about:blank", "title": ""}
NEWTAB = {
    "targetId": "TX",
    "type": "page",
    "url": "chrome://newtab/",
    "title": "New Tab",
}
PAGE1 = {
    "targetId": "T2",
    "type": "page",
    "url": "http://127.0.0.1:9880/page1.html",
    "title": "Mercado",
}


def test_follows_the_most_recently_navigated_real_page():
    pages = [BLANK, PAGE1]
    assert sc.pick_target(pages, recent=[]) == "T2"
    assert sc.pick_target([BLANK], recent=[]) == "T1"
    assert (
        sc.pick_target(pages, recent=["T2", "T1"]) == "T2"
    )  # a blank tab never steals the view
    other = {**PAGE1, "targetId": "T3", "url": "https://example.com/"}
    assert sc.pick_target([BLANK, PAGE1, other], recent=["T3", "T2"]) == "T2"
    assert sc.pick_target([], recent=["T2"]) is None


def test_a_pinned_tab_wins_while_it_exists():
    pages = [BLANK, PAGE1]
    assert sc.pick_target(pages, recent=["T2"], pinned="T1") == "T1"
    assert sc.pick_target(pages, recent=["T2"], pinned="gone") == "T2"


def test_cursor_reports_are_validated():
    assert sc.cursor_message('{"kind": "click", "x": 10, "y": 20.5}') == {
        "type": "cursor",
        "kind": "click",
        "x": 10,
        "y": 20.5,
    }
    for junk in (
        '{"kind": "steal", "x": 1, "y": 2}',
        '{"kind": "move", "x": "1"}',
        "[]",
        "nope",
    ):
        assert sc.cursor_message(junk) is None


def test_only_input_events_become_cdp_input():
    method, params = sc.cdp_input(
        {
            "type": "input_mouse",
            "eventType": "mousePressed",
            "x": 1,
            "y": 2,
            "button": "left",
        }
    )
    assert (
        method == "Input.dispatchMouseEvent"
        and params["type"] == "mousePressed"
        and params["x"] == 1
    )
    _, key = sc.cdp_input(
        {
            "type": "input_keyboard",
            "eventType": "keyDown",
            "key": "a",
            "code": "KeyA",
            "text": "a",
        }
    )
    assert key["type"] == "keyDown" and key["text"] == "a"
    _, enter = sc.cdp_input(
        {
            "type": "input_keyboard",
            "eventType": "keyDown",
            "key": "Enter",
            "code": "Enter",
        }
    )
    assert enter["type"] == "rawKeyDown"
    assert sc.cdp_input({"type": "Runtime.evaluate", "expression": "alert(1)"}) is None


class _FakeBrowser:
    """A browser-level CDP endpoint: one blank tab, then Browser Use opens page1 in a new one."""

    def __init__(self):
        self.calls: list[tuple[str, dict, str | None]] = []
        self.port = 0
        self._ready = threading.Event()
        threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True).start()
        assert self._ready.wait(10)

    async def _main(self):
        from websockets.asyncio.server import serve

        async def handler(conn):
            sessions = {}
            async for raw in conn:
                msg = json.loads(raw)
                method, params, session = (
                    msg["method"],
                    msg.get("params", {}),
                    msg.get("sessionId"),
                )
                self.calls.append((method, params, session))
                result = {}
                if method == "Target.getTargets":
                    result = {"targetInfos": [BLANK, NEWTAB]}
                elif method == "Target.attachToTarget":
                    result = {"sessionId": f"S-{params['targetId']}"}
                    sessions[result["sessionId"]] = params["targetId"]
                await conn.send(json.dumps({"id": msg["id"], "result": result}))
                if method == "Page.startScreencast":
                    data = "cGFnZTE=" if sessions[session] == "T2" else "Ymxhbms="
                    frame = {
                        "data": data,
                        "sessionId": 7,
                        "metadata": {"deviceWidth": 1280, "deviceHeight": 720},
                    }
                    await conn.send(
                        json.dumps(
                            {
                                "method": "Page.screencastFrame",
                                "params": frame,
                                "sessionId": session,
                            }
                        )
                    )
                if method == "Target.setDiscoverTargets":
                    await conn.send(
                        json.dumps(
                            {
                                "method": "Target.targetCreated",
                                "params": {"targetInfo": PAGE1},
                            }
                        )
                    )
                if (
                    method == "Page.addScriptToEvaluateOnNewDocument"
                    and sessions[session] == "T2"
                ):
                    click = {
                        "name": "__clawkLive",
                        "payload": '{"kind": "click", "x": 120, "y": 64}',
                    }
                    await conn.send(
                        json.dumps(
                            {
                                "method": "Runtime.bindingCalled",
                                "params": click,
                                "sessionId": session,
                            }
                        )
                    )

        async with serve(handler, "127.0.0.1", 0) as server:
            self.port = server.sockets[0].getsockname()[1]
            self._ready.set()
            await asyncio.Future()


@pytest.fixture
def client(monkeypatch, _isolate_clawk_home):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")
    from clawk_cli import web_server

    monkeypatch.setattr(web_server, "_DASHBOARD_EMBEDDED_CHAT_ENABLED", True)
    return TestClient(web_server.app, base_url="http://127.0.0.1")


def _url(task):
    from clawk_cli.web_server import _SESSION_TOKEN

    return f"/api/browser/live/ws?task={task}&token={_SESSION_TOKEN}"


LOOPBACK = {"host": "127.0.0.1"}


def test_streams_the_tab_browser_use_opened_and_forwards_input(client, monkeypatch):
    browser = _FakeBrowser()
    monkeypatch.setattr(
        browser_live,
        "session_cdp_url",
        lambda task: (
            f"ws://127.0.0.1:{browser.port}/devtools/browser/x"
            if task == "chat-1"
            else None
        ),
    )

    with client.websocket_connect(_url("chat-1"), headers=LOOPBACK) as ws:
        seen = []
        while not any(
            m.get("type") == "frame" and m["data"] == "cGFnZTE=" for m in seen
        ):
            seen.append(ws.receive_json())
        while not any(m.get("type") == "cursor" for m in seen):
            seen.append(ws.receive_json())
        assert [m for m in seen if m["type"] == "cursor"] == [
            {"type": "cursor", "kind": "click", "x": 120, "y": 64}
        ]
        tabs = [m for m in seen if m["type"] == "tabs"][-1]["tabs"]
        assert [(t["url"], t["active"]) for t in tabs] == [
            ("about:blank", False),
            (PAGE1["url"], True),
        ]
        frames = [m for m in seen if m["type"] == "frame"]
        assert frames[-1]["metadata"] == {"deviceWidth": 1280, "deviceHeight": 720}

        ws.send_text(json.dumps({"type": "Runtime.evaluate", "expression": "alert(1)"}))
        ws.send_text(
            json.dumps(
                {
                    "type": "input_mouse",
                    "eventType": "mousePressed",
                    "x": 5,
                    "y": 6,
                    "button": "left",
                }
            )
        )
        for _ in range(100):
            if any(c[0] == "Input.dispatchMouseEvent" for c in browser.calls):
                break
            threading.Event().wait(0.05)

    methods = [c[0] for c in browser.calls]
    assert "Runtime.evaluate" not in methods
    script = next(
        c[1] for c in browser.calls if c[0] == "Page.addScriptToEvaluateOnNewDocument"
    )
    assert script["worldName"] == "clawk-live" and script["runImmediately"] is True
    binding = next(c[1] for c in browser.calls if c[0] == "Runtime.addBinding")
    assert binding == {"name": "__clawkLive", "executionContextName": "clawk-live"}
    mouse = next(c for c in browser.calls if c[0] == "Input.dispatchMouseEvent")
    assert mouse[2] == "S-T2" and mouse[1]["type"] == "mousePressed"
    assert ("Page.screencastFrameAck", {"sessionId": 7}, "S-T2") in browser.calls


def _receive_until(ws, predicate):
    seen = []
    while not seen or not predicate(seen[-1]):
        seen.append(ws.receive_json())
    return seen


def test_the_viewer_pins_a_tab_and_goes_back_to_following_the_agent(
    client, monkeypatch
):
    browser = _FakeBrowser()
    monkeypatch.setattr(
        browser_live, "session_cdp_url", lambda task: f"ws://127.0.0.1:{browser.port}/x"
    )

    with client.websocket_connect(_url("chat-1"), headers=LOOPBACK) as ws:
        _receive_until(
            ws, lambda m: m.get("type") == "frame" and m["data"] == "cGFnZTE="
        )
        ws.send_text(json.dumps({"type": "focus_tab", "id": "T1"}))
        pinned = _receive_until(ws, lambda m: m.get("type") == "tabs" and m["pinned"])[
            -1
        ]
        assert [t["id"] for t in pinned["tabs"] if t["active"]] == ["T1"]
        ws.send_text(json.dumps({"type": "follow_agent"}))
        following = _receive_until(
            ws, lambda m: m.get("type") == "tabs" and not m["pinned"]
        )[-1]
        assert [t["id"] for t in following["tabs"] if t["active"]] == ["T2"]


def test_a_thumbnail_takes_no_input_and_installs_nothing(client, monkeypatch):
    browser = _FakeBrowser()
    monkeypatch.setattr(
        browser_live, "session_cdp_url", lambda task: f"ws://127.0.0.1:{browser.port}/x"
    )

    with client.websocket_connect(_url("chat-1") + "&thumb=1", headers=LOOPBACK) as ws:
        _receive_until(
            ws, lambda m: m.get("type") == "frame" and m["data"] == "cGFnZTE="
        )
        ws.send_text(
            json.dumps(
                {"type": "input_mouse", "eventType": "mousePressed", "x": 5, "y": 6}
            )
        )
        ws.send_text(json.dumps({"type": "focus_tab", "id": "T1"}))
        _receive_until(ws, lambda m: m.get("type") == "tabs" and m["pinned"])

    methods = [c[0] for c in browser.calls]
    assert "Input.dispatchMouseEvent" not in methods
    assert (
        "Runtime.addBinding" not in methods
        and "Page.addScriptToEvaluateOnNewDocument" not in methods
    )
    casts = [c[1] for c in browser.calls if c[0] == "Page.startScreencast"]
    assert casts and all(c["maxWidth"] <= 480 for c in casts)


def test_a_session_without_a_browser_is_refused(client, monkeypatch):
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr(browser_live, "session_cdp_url", lambda task: None)
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect(_url("nobody"), headers=LOOPBACK) as ws:
            ws.receive_json()
    assert refused.value.code == 4404


def test_the_socket_needs_dashboard_auth(client, monkeypatch):
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr(
        browser_live, "session_cdp_url", lambda task: "ws://127.0.0.1:1/x"
    )
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect(
            "/api/browser/live/ws?task=chat-1", headers=LOOPBACK
        ) as ws:
            ws.receive_json()
    assert refused.value.code == 4401


def test_listing_names_open_sessions_without_creating_one(client, monkeypatch):
    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN
    from tools import browser_tool

    monkeypatch.setattr(
        browser_tool,
        "_active_sessions",
        {"chat-1": {"session_name": "h_1", "cdp_url": "ws://cloud/x"}},
    )
    res = client.get(
        "/api/browser/live", headers={_SESSION_HEADER_NAME: _SESSION_TOKEN}
    )
    assert res.json() == {"sessions": [{"task_id": "chat-1"}]}
    assert browser_live.session_cdp_url("chat-1") == "ws://cloud/x"
    assert browser_live.session_cdp_url("not-open") is None
    assert list(browser_tool._active_sessions) == ["chat-1"]
