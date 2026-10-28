"""``read_pages``: read several pages at once, each in its own tab, for ``browser_exec``.

Opening tabs one after another and reading them with ``js(..., target_id=...)`` is slow and can
mix pages up: the read races the navigation (a fresh tab is a finished ``about:blank`` before the
real page starts loading), and Chrome freezes the tabs that are not in front. Here every tab is
attached once, kept running with focus emulation (what Playwright does for its pages), navigated,
and read only when its own URL has loaded and its text has stopped changing, so each result is the
page that was asked for. At most ``concurrency`` tabs are open at a time and every tab is closed.

Its source runs inside the browser-harness process (see ``preamble``); ``cdp`` is the harness's raw CDP helper
(``cdp(method, session_id=None, **params)``). Only reads: sending or clicking stays one page at a
time in the agent's own code.
"""

from __future__ import annotations

import contextlib
import functools
import json
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Optional

MAX_CONCURRENCY = 8
# What the harness's cdp() raises: RuntimeError (a CDP error reply), OSError (daemon socket,
# TimeoutError included) and KeyError (a reply without the expected id).
CDP_ERRORS = (RuntimeError, OSError, KeyError)
# A loaded page this long without the awaited element will not get it.
GIVE_UP_S = 5.0

_PROBE = """(() => {
  const el = (%(selector)s && document.querySelector(%(selector)s)) || document.body;
  const text = el ? el.innerText || "" : "";
  return {href: location.href, state: document.readyState, title: document.title,
          found: !%(wait_for)s || !!document.querySelector(%(wait_for)s),
          n: text.length, text: %(with_text)s ? text.slice(0, %(max_chars)d) : ""};
})()"""


def _probe(
    selector: Optional[str], wait_for: Optional[str], max_chars: int, with_text: bool
) -> str:
    return _PROBE % {
        "selector": json.dumps(selector),
        "wait_for": json.dumps(wait_for),
        "with_text": "true" if with_text else "false",
        "max_chars": max_chars,
    }


class _Tab:
    def __init__(self, index: int, url: str, now: float):
        self.index, self.url, self.started = index, url, now
        self.target = self.session = None
        self.last_n, self.stable_since = -1, now


def _evaluate(cdp: Callable, session: str, expression: str) -> dict:
    reply = cdp(
        "Runtime.evaluate",
        session_id=session,
        expression=expression,
        returnByValue=True,
    )
    return (reply.get("result") or {}).get("value") or {}


def _open(cdp: Callable, tab: _Tab) -> None:
    tab.target = cdp("Target.createTarget", url="about:blank", background=True)[
        "targetId"
    ]
    tab.session = cdp("Target.attachToTarget", targetId=tab.target, flatten=True)[
        "sessionId"
    ]
    with contextlib.suppress(
        *CDP_ERRORS
    ):  # a browser without it still reads, only slower
        cdp("Emulation.setFocusEmulationEnabled", session_id=tab.session, enabled=True)
    cdp("Page.navigate", session_id=tab.session, url=tab.url)


def _close(cdp: Callable, tab: _Tab) -> None:
    if tab.target:
        with contextlib.suppress(*CDP_ERRORS):  # already closed by the page or the user
            cdp("Target.closeTarget", targetId=tab.target)


def _settled(
    tab: _Tab, state: dict, now: float, settle: float
) -> tuple[bool, Optional[str]]:
    """``(done, error)``: done once its own URL loaded and the text stopped changing; when the
    awaited element is still missing after the page sat still for ``GIVE_UP_S`` (a 404, a login
    wall, a removed profile) it is done with an error instead of eating the whole timeout."""
    if (
        state.get("href") in (None, "", "about:blank")
        or state.get("state") != "complete"
    ):
        return False, None
    n = int(state.get("n") or 0)
    if n != tab.last_n:
        tab.last_n, tab.stable_since = n, now
        return False, None
    still = now - tab.stable_since
    if not state.get("found"):
        return (True, "not found") if still >= GIVE_UP_S else (False, None)
    return n > 0 and still >= settle, None


def _result(tab: _Tab, state: dict, now: float, error: Optional[str]) -> dict[str, Any]:
    return {
        "url": tab.url,
        "final_url": state.get("href") or "",
        "title": state.get("title") or "",
        "text": state.get("text") or "",
        "ok": error is None,
        "seconds": round(now - tab.started, 1),
        "error": error,
    }


def read_pages(
    cdp: Callable,
    urls: list[str],
    selector: Optional[str] = None,
    wait_for: Optional[str] = None,
    max_chars: int = 8000,
    concurrency: int = 4,
    timeout: float = 30.0,
    settle: float = 0.6,
    poll: float = 0.25,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Read ``urls`` in parallel tabs; one dict per URL, in the same order.

    ``selector`` limits the text to one element (default the whole page); ``wait_for`` is a CSS
    selector that must exist before the page counts as loaded. Each result has ``url``,
    ``final_url`` (after redirects), ``title``, ``text`` (up to ``max_chars``), ``ok``,
    ``seconds`` and ``error`` (``None``; ``"timeout"`` or ``"not found"`` — ``wait_for`` never
    appeared, e.g. a 404 — with ``text`` as far as it loaded; or the CDP error).
    """
    pending = deque(enumerate(urls))
    width = max(1, min(int(concurrency), MAX_CONCURRENCY))
    probe = _probe(selector, wait_for, max_chars, with_text=False)
    read = _probe(selector, wait_for, max_chars, with_text=True)
    results: list[Optional[dict]] = [None] * len(urls)
    active: list[_Tab] = []
    while pending or active:
        while pending and len(active) < width:
            index, url = pending.popleft()
            tab = _Tab(index, url, clock())
            try:
                _open(cdp, tab)
                active.append(tab)
            except CDP_ERRORS as exc:  # reported per URL
                _close(cdp, tab)
                results[index] = _result(
                    tab, {}, clock(), str(exc) or type(exc).__name__
                )
        for tab in list(active):
            now = clock()
            error = None
            try:
                state = _evaluate(cdp, tab.session, probe)
                done, error = _settled(tab, state, now, settle)
                if not done and now - tab.started >= timeout:
                    done, error = True, "timeout"
                if done:
                    state = _evaluate(cdp, tab.session, read)
            except CDP_ERRORS as exc:  # the tab crashed or was closed
                done, error, state = True, str(exc) or type(exc).__name__, {}
            if done:
                results[tab.index] = _result(tab, state, now, error)
                _close(cdp, tab)
                active.remove(tab)
        if active:
            sleep(poll)
    return [r for r in results if r is not None]


# The harness runs on a bare interpreter whose path does not include Clawksis's source, so
# browser_exec ships this module's own source along with the code that calls read_pages, loaded
# into a private module (the agent's globals only gain ``read_pages``).
_BIND = """
import types as _clawk_types
_clawk_read_pages_module = _clawk_types.ModuleType("clawk_read_pages")
exec(%r, _clawk_read_pages_module.__dict__)
def read_pages(urls, **options):
    return _clawk_read_pages_module.read_pages(cdp, urls, **options)
del _clawk_types
"""


DIGEST = (
    " read_pages(urls, selector=None, wait_for=None) reads many pages AT ONCE in parallel tabs "
    "(up to 4 open, each closed after) and returns [{url, final_url, title, text, ok, seconds, "
    "error}] in order — use it whenever you need the text of several URLs (profiles, products, "
    "results) instead of visiting them one by one; act (click, type, send) one page at a time."
)


@functools.cache
def preamble() -> str:
    """The code that defines ``read_pages`` inside the harness, bound to its ``cdp``."""
    return _BIND % Path(__file__).read_text(encoding="utf-8")


def with_helper(code: str) -> str:
    """``code`` with ``read_pages`` defined in front, only when it calls it."""
    return preamble() + code if "read_pages" in code else code
