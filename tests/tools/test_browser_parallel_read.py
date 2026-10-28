"""read_pages: several pages read at once, each result the page that was asked for.

A fake browser behind the harness's ``cdp(method, session_id=None, **params)``: a new tab is a
finished ``about:blank`` until its navigation commits, then its text grows for a few polls (a
single-page app rendering) before it settles. read_pages must not read the blank page, must wait
for the text to settle, keep at most ``concurrency`` tabs open, close every tab, keep tabs running
with focus emulation, and report a slow or broken page per URL without losing the others.
"""

from __future__ import annotations

import itertools

import pytest

from tools.browser_parallel_read import MAX_CONCURRENCY, PREAMBLE, read_pages


class FakeBrowser:
    def __init__(
        self, render_polls: dict[str, int] | None = None, broken: set[str] = frozenset()
    ):
        self.render_polls = render_polls or {}
        self.broken = broken
        self.tabs: dict[str, dict] = {}
        self.sessions: dict[str, str] = {}
        self.ids = itertools.count(1)
        self.max_open = 0
        self.focus: list[str] = []
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def cdp(self, method, session_id=None, **params):
        if method == "Target.createTarget":
            tid = f"T{next(self.ids)}"
            self.tabs[tid] = {"url": "about:blank", "polls": 0}
            self.max_open = max(self.max_open, len(self.tabs))
            return {"targetId": tid}
        if method == "Target.attachToTarget":
            sid = f"S-{params['targetId']}"
            self.sessions[sid] = params["targetId"]
            return {"sessionId": sid}
        if method == "Target.closeTarget":
            self.tabs.pop(params["targetId"], None)
            return {}
        tab = self.tabs[self.sessions[session_id]]
        if method == "Emulation.setFocusEmulationEnabled":
            self.focus.append(session_id)
            return {}
        if method == "Page.navigate":
            if params["url"] in self.broken:
                raise RuntimeError("net::ERR_NAME_NOT_RESOLVED")
            tab["next"] = params["url"]
            return {}
        if method == "Runtime.evaluate":
            return {"result": {"value": self.state(tab, params["expression"])}}
        raise AssertionError(method)

    def state(self, tab: dict, expression: str) -> dict:
        if (
            "next" in tab
        ):  # the navigation commits one poll later: first read sees about:blank
            tab["url"] = tab.pop("next")
            return {
                "href": "about:blank",
                "state": "complete",
                "title": "",
                "found": True,
                "n": 0,
                "text": "",
            }
        tab["polls"] += 1
        url = tab["url"]
        grown = min(tab["polls"], self.render_polls.get(url, 2))
        text = f"profile of {url} " * grown
        with_text = "? text.slice" in expression and "true ? text.slice" in expression
        return {
            "href": url,
            "state": "complete",
            "title": f"Title {url}",
            "found": True,
            "n": len(text),
            "text": text if with_text else "",
        }


def run(browser: FakeBrowser, urls: list[str], **kw) -> list[dict]:
    return read_pages(browser.cdp, urls, clock=browser.clock, sleep=browser.sleep, **kw)


URLS = [f"https://site.example/in/person-{i}" for i in range(6)]


def test_each_result_is_the_page_asked_for_in_order():
    browser = FakeBrowser(render_polls={URLS[1]: 6, URLS[3]: 4})
    results = run(browser, URLS)
    assert [r["url"] for r in results] == URLS
    for r in results:
        assert r["ok"] and r["error"] is None
        assert r["final_url"] == r["url"]
        assert r["text"].startswith(f"profile of {r['url']} ")
        assert r["title"] == f"Title {r['url']}"


def test_waits_for_the_text_to_stop_growing():
    browser = FakeBrowser(render_polls={URLS[0]: 5})
    (result,) = run(browser, URLS[:1])
    assert result["text"].count("profile of") == 5


def test_never_more_tabs_than_concurrency_and_every_tab_closed():
    browser = FakeBrowser()
    run(browser, URLS, concurrency=2)
    assert browser.max_open == 2
    assert browser.tabs == {}
    assert len(browser.focus) == len(URLS)  # every tab kept running


def test_concurrency_is_capped():
    browser = FakeBrowser()
    run(browser, [f"https://x.example/{i}" for i in range(20)], concurrency=50)
    assert browser.max_open == MAX_CONCURRENCY


def test_a_slow_page_times_out_with_what_loaded_and_the_rest_still_read():
    browser = FakeBrowser(render_polls={URLS[0]: 10_000})
    results = run(browser, URLS[:3], timeout=3.0)
    assert results[0]["ok"] is False and results[0]["error"] == "timeout"
    assert results[0]["text"].startswith(f"profile of {URLS[0]}")
    assert all(r["ok"] for r in results[1:])
    assert browser.tabs == {}


def test_a_broken_url_is_reported_and_its_tab_closed():
    browser = FakeBrowser(broken={URLS[1]})
    results = run(browser, URLS[:3])
    assert results[1]["ok"] is False and "ERR_NAME_NOT_RESOLVED" in results[1]["error"]
    assert results[0]["ok"] and results[2]["ok"]
    assert browser.tabs == {}


def test_parallel_beats_one_by_one():
    """Four pages that each take ~2 s of polls finish in about the time of one."""
    browser = FakeBrowser(render_polls={u: 8 for u in URLS[:4]})
    results = run(browser, URLS[:4], concurrency=4)
    assert max(r["seconds"] for r in results) < 4.0
    assert browser.now < 4.0


@pytest.mark.parametrize("missing", [True, False])
def test_preamble_binds_the_harness_cdp(missing, monkeypatch):
    calls = []

    def cdp(method, session_id=None, **params):
        calls.append(method)
        raise RuntimeError("boom")

    scope = {"cdp": cdp}
    if missing:
        import builtins

        real_import = builtins.__import__

        def no_module(name, *args, **kwargs):
            if name == "tools.browser_parallel_read":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_module)
    exec(PREAMBLE, scope)
    if missing:
        assert "read_pages" not in scope
        return
    (result,) = scope["read_pages"](["https://a.example/"])
    assert calls == ["Target.createTarget"] and result["error"] == "boom"


def test_a_page_without_the_awaited_element_gives_up_early():
    """A removed profile (a 404 page) never shows ``wait_for``: report it once the page sits still,
    not after the whole timeout."""

    class NotFound(FakeBrowser):
        def state(self, tab, expression):
            value = super().state(tab, expression)
            return {**value, "found": False} if tab["url"] == URLS[0] else value

    browser = NotFound()
    results = run(browser, URLS[:2], wait_for="main h1", timeout=30.0)
    assert results[0]["error"] == "not found" and results[0]["seconds"] < 8
    assert results[0]["text"].startswith(f"profile of {URLS[0]}")
    assert results[1]["ok"]


def test_helper_is_bound_only_for_code_that_calls_it():
    from tools.browser_parallel_read import with_helper

    assert with_helper("print(page_info())") == "print(page_info())"
    assert with_helper("print(read_pages(['https://a.example/']))").startswith(PREAMBLE)
