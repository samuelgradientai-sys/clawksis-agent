"""On the user's own Chrome (Mi Chrome) the CDP supervisor never hooks into one of the user's tabs:
its dialog bridge (an init script, a Fetch interceptor and an evaluate) would run in the page the
user is on, and the live view would show that tab as the agent's. It takes a tab the agent opened,
or, with none yet, attaches nothing (and opens nothing) until the vault needs a page."""

from __future__ import annotations

import asyncio

from tools import browser_supervisor as bs

USER = {
    "targetId": "U1",
    "type": "page",
    "url": "https://web.whatsapp.com/",
    "clawkUserTab": True,
}
AGENT = {"targetId": "A1", "type": "page", "url": "https://a.example/"}


def _attach(targets):
    supervisor = bs.CDPSupervisor(task_id="users-chrome", cdp_url="ws://127.0.0.1:9")
    sent: list[tuple[str, dict]] = []

    async def cdp(method, params=None, *, session_id=None, timeout=10.0):
        sent.append((method, params or {}))
        if method == "Target.getTargets":
            return {"result": {"targetInfos": targets}}
        if method == "Target.attachToTarget":
            return {"result": {"sessionId": "S-" + params["targetId"]}}
        return {"result": {}}

    supervisor._cdp = cdp
    asyncio.run(supervisor._attach_initial_page())
    return supervisor, sent


def test_only_the_users_tabs_open_means_nothing_is_attached_or_opened():
    supervisor, sent = _attach([USER])
    assert [m for m, _ in sent] == ["Target.getTargets"]
    assert supervisor._page_session_id is None


def test_a_tab_the_agent_opened_is_taken_over_the_users_tab_listed_first():
    supervisor, sent = _attach([USER, AGENT])
    assert ("Target.attachToTarget", {"targetId": "A1", "flatten": True}) in sent
    assert supervisor._page_session_id == "S-A1"
    assert all(p.get("targetId") != "U1" for _, p in sent)


def test_any_other_browser_still_attaches_its_first_page():
    supervisor, _ = _attach([dict(AGENT, targetId="P1")])
    assert supervisor._page_session_id == "S-P1"
