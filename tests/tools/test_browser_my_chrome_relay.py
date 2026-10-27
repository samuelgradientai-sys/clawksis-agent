"""Mi Chrome relay: browser-level CDP emulated over the extension's tab-level chrome.debugger.

Contract, driven over a REAL loopback WebSocket against a fake extension: drivers see the user's
debuggable tabs (pre-existing ones included, chrome:// pages never) as page targets, the agent's
own tabs first; flatten attach hands out a relay session whose commands reach the right tab and
whose events arrive only for the domains that session enabled; a second driver joining a tab
gets the execution contexts Chrome reported before it; createTarget opens a grouped agent tab in
front; the user's tabs are never closed and Browser.close is a no-op; the endpoint refuses web
pages and wrong secrets; the live view's traffic is not agent activity, it is told which tab
the agent is driving, and it only ever sees the agent's own tabs and the user's tabs the agent is
working in (never the rest of the user's tabs, and not one the agent has let go of).
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

import pytest

from tests.waiting import async_wait_until
from tools.browser_my_chrome_relay import MyChromeRelay, is_debuggable_url
from tools.browser_my_chrome_server import LoopbackCdpServer

USER_TABS = [
    {
        "id": 11,
        "windowId": 1,
        "index": 0,
        "url": "https://news.example/",
        "title": "Diario",
        "active": False,
    },
    {
        "id": 12,
        "windowId": 1,
        "index": 1,
        "url": "https://vuelaya.example/",
        "title": "VuelaYa",
        "active": True,
    },
    {
        "id": 13,
        "windowId": 1,
        "index": 2,
        "url": "chrome://newtab/",
        "title": "New Tab",
        "active": False,
    },
]


class FakeExtension:
    """Answers the relay's requests the way background.js does, and records them."""

    def __init__(self, relay: MyChromeRelay):
        self.relay = relay
        self.calls: list[dict] = []
        self.next_tab = 20

    async def run(self):
        while True:
            msg = await self.relay.outbox.get()
            self.calls.append(msg)
            result = await self.answer(msg)
            await self.relay.on_extension_message(
                {"type": "result", "id": msg["id"], "result": result}
            )

    async def answer(self, msg: dict) -> dict:
        if msg["type"] == "create_tab":
            self.next_tab += 1
            tab = {
                "id": self.next_tab,
                "windowId": 1,
                "index": 3,
                "url": msg["url"],
                "title": "",
                "active": True,
                "agent": True,
            }
            await self.relay.on_extension_message(
                {"type": "tab", "event": "created", "tab": {**tab, "agent": False}}
            )
            return {"tab": tab}
        if msg["type"] == "close_tab":
            await self.relay.on_extension_message(
                {"type": "tab", "event": "removed", "tabId": msg["tabId"]}
            )
        if msg["type"] == "cdp" and msg["method"] == "Runtime.evaluate":
            return {"result": {"type": "string", "value": f"tab {msg['tabId']}"}}
        return {}

    def sent(self, kind: str, method: str | None = None) -> list[dict]:
        return [
            c
            for c in self.calls
            if c["type"] == kind and (method is None or c.get("method") == method)
        ]


class Driver:
    """A browser-level CDP client (what agent-browser / Browser Use / the live view are)."""

    def __init__(self, conn):
        self.conn = conn
        self.ids = 0
        self.events: list[dict] = []

    async def call(
        self, method: str, params: dict | None = None, session: str | None = None
    ) -> dict:
        self.ids += 1
        frame = {"id": self.ids, "method": method, "params": params or {}}
        if session:
            frame["sessionId"] = session
        await self.conn.send(json.dumps(frame))
        while True:
            msg = json.loads(await asyncio.wait_for(self.conn.recv(), 5))
            if msg.get("id") == self.ids:
                return msg
            self.events.append(msg)

    async def drain(self, seconds: float = 0.2) -> None:
        try:
            while True:
                self.events.append(
                    json.loads(await asyncio.wait_for(self.conn.recv(), seconds))
                )
        except TimeoutError:
            return

    def named(self, method: str) -> list[dict]:
        return [e for e in self.events if e.get("method") == method]


def run_relay(scenario):
    """Run ``scenario(relay, extension, server, connect)`` against a live loopback endpoint."""

    async def main():
        from websockets.asyncio.client import connect

        relay = MyChromeRelay()
        extension = FakeExtension(relay)
        pump = asyncio.create_task(extension.run())
        await relay.on_extension_message(
            {
                "type": "hello",
                "product": "Chrome/141.0",
                "userAgent": "UA",
                "version": "1.0.0",
                "tabs": USER_TABS,
            }
        )
        server = LoopbackCdpServer(relay)
        await server.start()

        async def open_driver(viewer: bool = False):
            url = server.ws_url + ("?viewer=1" if viewer else "")
            return Driver(await connect(url, max_size=None))

        try:
            await scenario(relay, extension, server, open_driver)
        finally:
            pump.cancel()
            await relay.shutdown()
            await server.stop()

    asyncio.run(main())


def test_drivers_see_the_users_tabs_as_targets_and_agent_tabs_first():
    async def scenario(relay, extension, server, open_driver):
        driver = await open_driver()
        version = (await driver.call("Browser.getVersion"))["result"]
        assert version["product"] == "Chrome/141.0"
        infos = (await driver.call("Target.getTargets"))["result"]["targetInfos"]
        assert [i["url"] for i in infos] == [
            "https://vuelaya.example/",
            "https://news.example/",
        ]
        assert all(
            i["type"] == "page" for i in infos
        )  # chrome://newtab is not a target

        created = (
            await driver.call("Target.createTarget", {"url": "https://fares.example/"})
        )["result"]
        assert (
            extension.sent("create_tab")[-1]["active"] is True
        )  # in front: background tabs never paint
        infos = (await driver.call("Target.getTargets"))["result"]["targetInfos"]
        assert (
            infos[0]["targetId"] == created["targetId"]
        )  # drivers that take "the first page" get the agent's

    run_relay(scenario)


def test_flatten_attach_routes_commands_and_filters_events_per_session():
    async def scenario(relay, extension, server, open_driver):
        driver = await open_driver()
        infos = (await driver.call("Target.getTargets"))["result"]["targetInfos"]
        airline = next(i for i in infos if "vuelaya" in i["url"])
        reply = await driver.call(
            "Target.attachToTarget", {"targetId": airline["targetId"], "flatten": True}
        )
        sid = reply["result"]["sessionId"]
        assert [
            e["params"]["sessionId"] for e in driver.named("Target.attachedToTarget")
        ] == [sid]
        assert extension.sent("attach")[-1]["tabId"] == 12

        value = await driver.call("Runtime.evaluate", {"expression": "1"}, session=sid)
        assert (
            value["sessionId"] == sid and value["result"]["result"]["value"] == "tab 12"
        )
        await driver.call("Page.enable", session=sid)

        for method in ("Page.frameNavigated", "Network.requestWillBeSent"):
            await relay.on_extension_message(
                {"type": "event", "tabId": 12, "method": method, "params": {}}
            )
        await driver.drain()
        assert [e["sessionId"] for e in driver.named("Page.frameNavigated")] == [sid]
        assert (
            driver.named("Network.requestWillBeSent") == []
        )  # Network was never enabled here

    run_relay(scenario)


def test_a_second_driver_gets_the_execution_contexts_chrome_reported_before_it():
    async def scenario(relay, extension, server, open_driver):
        first, second = await open_driver(), await open_driver()
        target = (await first.call("Target.getTargets"))["result"]["targetInfos"][0][
            "targetId"
        ]
        sid1 = (
            await first.call(
                "Target.attachToTarget", {"targetId": target, "flatten": True}
            )
        )["result"]["sessionId"]
        await first.call("Runtime.enable", session=sid1)
        context = {
            "id": 3,
            "uniqueId": "u3",
            "origin": "https://vuelaya.example",
            "name": "",
            "auxData": {"isDefault": True},
        }
        await relay.on_extension_message(
            {
                "type": "event",
                "tabId": 12,
                "method": "Runtime.executionContextCreated",
                "params": {"context": context},
            }
        )

        sid2 = (
            await second.call(
                "Target.attachToTarget", {"targetId": target, "flatten": True}
            )
        )["result"]["sessionId"]
        await second.call(
            "Runtime.enable", session=sid2
        )  # Chrome would not report it again
        replayed = second.named("Runtime.executionContextCreated")
        assert [(e["sessionId"], e["params"]["context"]["id"]) for e in replayed] == [
            (sid2, 3)
        ]

        await second.call("Runtime.disable", session=sid2)
        assert (
            extension.sent("cdp", "Runtime.disable") == []
        )  # the first driver still needs it

    run_relay(scenario)


def test_users_tabs_and_chrome_are_never_closed_but_agent_tabs_are():
    async def scenario(relay, extension, server, open_driver):
        driver = await open_driver()
        infos = (await driver.call("Target.getTargets"))["result"]["targetInfos"]
        user_tab = infos[0]["targetId"]
        refused = await driver.call("Target.closeTarget", {"targetId": user_tab})
        assert "error" in refused and extension.sent("close_tab") == []

        assert (await driver.call("Browser.close"))["result"] == {}
        assert [
            c for c in extension.calls if c.get("method", "").startswith("Browser.")
        ] == []

        await driver.call("Target.setDiscoverTargets", {"discover": True})
        agent_tab = (await driver.call("Target.createTarget", {"url": "about:blank"}))[
            "result"
        ]["targetId"]
        closed = await driver.call("Target.closeTarget", {"targetId": agent_tab})
        assert closed["result"] == {"success": True}
        await driver.drain()
        assert agent_tab in [
            e["params"]["targetId"] for e in driver.named("Target.targetDestroyed")
        ]

    run_relay(scenario)


def test_a_closed_tab_detaches_its_sessions_and_is_announced_gone():
    async def scenario(relay, extension, server, open_driver):
        driver = await open_driver()
        await driver.call("Target.setDiscoverTargets", {"discover": True})
        target = (await driver.call("Target.getTargets"))["result"]["targetInfos"][0][
            "targetId"
        ]
        sid = (
            await driver.call(
                "Target.attachToTarget", {"targetId": target, "flatten": True}
            )
        )["result"]["sessionId"]
        await relay.on_extension_message(
            {"type": "tab", "event": "removed", "tabId": 12}
        )
        await driver.drain()
        assert [
            e["params"]["sessionId"] for e in driver.named("Target.detachedFromTarget")
        ] == [sid]
        assert [
            e["params"]["targetId"] for e in driver.named("Target.targetDestroyed")
        ] == [target]
        gone = await driver.call("Runtime.evaluate", {"expression": "1"}, session=sid)
        assert "Session with given id not found" in gone["error"]["message"]

    run_relay(scenario)


def test_the_live_view_only_sees_the_users_tabs_the_agent_works_in():
    async def scenario(relay, extension, server, open_driver):
        viewer = await open_driver(viewer=True)
        await viewer.call("Target.setDiscoverTargets", {"discover": True})
        assert (await viewer.call("Target.getTargets"))["result"]["targetInfos"] == []
        assert relay.focus_target_id() is None

        agent = await open_driver()
        infos = (await agent.call("Target.getTargets"))["result"]["targetInfos"]
        by_url = {i["url"]: i["targetId"] for i in infos}
        front, news = (
            by_url["https://vuelaya.example/"],
            by_url["https://news.example/"],
        )
        # A driver's setup traffic on the tab the user has in front is not the agent working there.
        idle = (
            await agent.call(
                "Target.attachToTarget", {"targetId": front, "flatten": True}
            )
        )["result"]["sessionId"]
        await agent.call("Page.enable", session=idle)
        assert relay.agent_active() is False

        sid = (
            await agent.call(
                "Target.attachToTarget", {"targetId": news, "flatten": True}
            )
        )["result"]["sessionId"]
        await agent.call("Runtime.evaluate", {"expression": "1"}, session=sid)
        assert relay.agent_active() is True
        await viewer.drain()
        created = viewer.named("Target.targetCreated")
        assert [e["params"]["targetInfo"]["targetId"] for e in created] == [news]
        assert [e["params"]["targetId"] for e in viewer.named("Clawk.agentFocus")] == [
            news
        ]
        assert relay.focus_target_id() == news
        seen = (await viewer.call("Target.getTargets"))["result"]["targetInfos"]
        assert [i["targetId"] for i in seen] == [news]
        refused = await viewer.call(
            "Target.attachToTarget", {"targetId": front, "flatten": True}
        )
        assert "error" in refused

    run_relay(scenario)


def test_when_the_agent_lets_go_the_live_view_releases_the_users_tab():
    async def scenario(relay, extension, server, open_driver):
        viewer = await open_driver(viewer=True)
        await viewer.call("Target.setDiscoverTargets", {"discover": True})
        agent = await open_driver()
        infos = (await agent.call("Target.getTargets"))["result"]["targetInfos"]
        news = next(i for i in infos if "news" in i["url"])["targetId"]
        sid = (
            await agent.call(
                "Target.attachToTarget", {"targetId": news, "flatten": True}
            )
        )["result"]["sessionId"]
        await agent.call("Runtime.evaluate", {"expression": "1"}, session=sid)
        own = (await agent.call("Target.createTarget", {"url": "https://a.example/"}))[
            "result"
        ]["targetId"]
        watch = (
            await viewer.call(
                "Target.attachToTarget", {"targetId": news, "flatten": True}
            )
        )["result"]["sessionId"]
        await viewer.call("Page.enable", session=watch)

        await agent.conn.close()
        await async_wait_until(
            lambda: 11 in [c["tabId"] for c in extension.sent("detach")],
            what="Chrome detached from the user's tab",
        )
        await viewer.drain()

        assert news in [
            e["params"]["targetId"] for e in viewer.named("Target.targetDestroyed")
        ]
        assert watch in [
            e["params"]["sessionId"] for e in viewer.named("Target.detachedFromTarget")
        ]
        assert 11 in [c["tabId"] for c in extension.sent("detach")]
        # The agent's own tab stays on screen; the user's tab is gone from the live view.
        seen = (await viewer.call("Target.getTargets"))["result"]["targetInfos"]
        assert [i["targetId"] for i in seen] == [own]
        assert relay.focus_target_id() == own

    run_relay(scenario)


def test_the_endpoint_refuses_web_pages_and_wrong_secrets():
    async def scenario(relay, extension, server, open_driver):
        root = f"http://127.0.0.1:{server.port}"

        def status(path, headers=None):
            request = urllib.request.Request(root + path, headers=headers or {})
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.status, json.loads(response.read() or b"null")
            except urllib.error.HTTPError as exc:
                return exc.code, None

        code, version = await asyncio.to_thread(
            status, f"/{server.secret}/json/version"
        )
        assert code == 200 and version["webSocketDebuggerUrl"] == server.ws_url
        assert (await asyncio.to_thread(status, "/json/version"))[0] == 404
        assert (await asyncio.to_thread(status, "/wrong-secret/json/list"))[0] == 404
        page = {"Origin": "https://evil.example"}
        assert (
            await asyncio.to_thread(status, f"/{server.secret}/json/version", page)
        )[0] == 403

    run_relay(scenario)


@pytest.mark.parametrize(
    ("url", "debuggable"),
    [
        ("https://vuelaya.example/", True),
        ("about:blank", True),
        ("chrome://settings/", False),
        ("chrome-extension://abc/popup.html", False),
        ("https://chromewebstore.google.com/detail/x", False),
        ("", False),
    ],
)
def test_debuggable_urls(url, debuggable):
    assert is_debuggable_url(url) is debuggable
