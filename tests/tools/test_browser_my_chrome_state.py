"""Mi Chrome endpoint across processes, per profile.

Contract: the dashboard publishes the relay's loopback URL under the profile home and every
process of THAT profile (the messaging gateway is a separate process) uses it as its CDP override
right after a live ``/browser connect``; another profile, a disabled feature, a cleared or a dead
publisher's endpoint is never used; an older connection closing does not wipe a newer one; a
change reaps the profile's browsers once so the next call lands on the new endpoint (or back on
the VPS browser); the model's note says the payments mode the user chose and is repeated when the
user flips it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools import browser_my_chrome_state as state
from tools import browser_tool_my_chrome as my_chrome

REPO = Path(__file__).resolve().parents[2]
URL = "ws://127.0.0.1:41234/devtools/browser/secret-a"


def make_home(root: Path, name: str, *, enabled=True, confirm=False) -> Path:
    home = root / name
    home.mkdir()
    (home / "config.yaml").write_text(
        f"browser:\n  my_chrome:\n    enabled: {str(enabled).lower()}\n"
        f"    confirm_payments: {str(confirm).lower()}\n",
        encoding="utf-8",
    )
    return home


def override_in_child(home: Path) -> str:
    """``_get_cdp_override_raw()`` as a separate process of ``home``'s profile sees it."""
    env = {k: v for k, v in os.environ.items() if k != "BROWSER_CDP_URL"}
    env.update(CLAWK_HOME=str(home), PYTHONPATH=str(REPO))
    code = "from tools.browser_tool_cdp import _get_cdp_override_raw; print(_get_cdp_override_raw())"
    out = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""


def test_the_published_endpoint_reaches_another_process_of_that_profile_only(tmp_path):
    work, other = make_home(tmp_path, "work"), make_home(tmp_path, "other")
    state.publish_relay(work, URL, browser="Chrome/141")
    assert override_in_child(work) == URL
    assert override_in_child(other) == ""
    state.clear_relay(work)
    assert override_in_child(work) == ""


def test_a_disabled_feature_or_a_dead_publisher_is_never_used(tmp_path, monkeypatch):
    off = make_home(tmp_path, "off", enabled=False)
    state.publish_relay(off, URL)
    monkeypatch.setenv("CLAWK_HOME", str(off))
    assert state.my_chrome_cdp_url() == ""

    on = make_home(tmp_path, "on")
    state.publish_relay(on, URL)
    monkeypatch.setenv("CLAWK_HOME", str(on))
    assert state.my_chrome_cdp_url() == URL
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait(timeout=60)
    record = state.relay_state_path(on)
    record.write_text(
        record.read_text().replace(f'"pid": {os.getpid()}', f'"pid": {gone.pid}')
    )
    assert state.my_chrome_cdp_url() == ""  # a crashed dashboard's endpoint


def test_an_older_connection_closing_keeps_the_newer_endpoint(tmp_path, monkeypatch):
    home = make_home(tmp_path, "home")
    monkeypatch.setenv("CLAWK_HOME", str(home))
    newer = URL.replace("secret-a", "secret-b")
    state.publish_relay(home, URL)
    state.publish_relay(home, newer)
    state.clear_relay(home, URL)
    assert state.my_chrome_cdp_url() == newer
    assert oct(state.relay_state_path(home).stat().st_mode & 0o777) == "0o600"


def test_an_endpoint_change_reaps_the_profiles_browsers_once(tmp_path, monkeypatch):
    from tools import browser_tool_cdp, browser_tool_lifecycle
    from clawk_constants import clawk_home_key

    home = make_home(tmp_path, "home")
    monkeypatch.setenv("CLAWK_HOME", str(home))
    monkeypatch.setattr(state, "_seen", {})
    reaped: list[str] = []
    monkeypatch.setattr(
        browser_tool_lifecycle, "cleanup_profile_browsers", reaped.append
    )
    before = browser_tool_cdp.live_cdp_generation()

    state.publish_relay(home, URL)
    assert state.sync_relay_endpoint() is True
    assert state.sync_relay_endpoint() is False
    state.clear_relay(home)
    assert state.sync_relay_endpoint() is True
    assert reaped == [clawk_home_key(), clawk_home_key()]
    assert browser_tool_cdp.live_cdp_generation() == before + 2


def test_sessions_on_the_relay_are_marked_and_get_the_payments_note(
    tmp_path, monkeypatch
):
    from tools import browser_tool_session

    home = make_home(tmp_path, "home")
    monkeypatch.setenv("CLAWK_HOME", str(home))
    state.publish_relay(home, URL)
    session = browser_tool_session._create_cdp_session("t1", URL)
    assert session["features"]["my_chrome"] is True
    assert (
        "my_chrome"
        not in browser_tool_session._create_cdp_session(
            "t2", "ws://other/devtools/browser/x"
        )["features"]
    )

    first = my_chrome.session_note(session)["my_chrome"]
    assert "Payments: AUTONOMOUS" in first and "never change it" in first
    assert my_chrome.session_note(session) == {}  # told once

    (home / "config.yaml").write_text(
        "browser:\n  my_chrome:\n    enabled: true\n    confirm_payments: true\n",
        encoding="utf-8",
    )
    flipped = my_chrome.session_note(session)["my_chrome"]
    assert "Payments: CONFIRM FIRST" in flipped  # the user flipped it: said again


@pytest.mark.parametrize("first", [True, False])
def test_built_in_tools_open_their_own_tab_on_the_users_chrome(first):
    on_chrome = {"features": {"my_chrome": True}}
    command = my_chrome.navigate_command(on_chrome, "https://vuelaya.example/", first)
    assert command == (
        (("tab", ["new", "https://vuelaya.example/"]))
        if first
        else ("open", ["https://vuelaya.example/"])
    )
    assert my_chrome.navigate_command({"features": {}}, "https://x.example/", True) == (
        "open",
        ["https://x.example/"],
    )


def test_browser_use_on_the_users_chrome_pins_its_own_tab_and_gets_the_note(
    tmp_path, monkeypatch
):
    from tools import browser_use_cli

    home = make_home(tmp_path, "home")
    monkeypatch.setenv("CLAWK_HOME", str(home))
    monkeypatch.setattr(browser_use_cli, "_my_chrome_note_modes", {})
    state.publish_relay(home, URL)
    on_chrome, elsewhere = {"BU_CDP_WS": URL}, {"BU_CDP_WS": "ws://127.0.0.1:9/x"}

    # Its own tab, not whichever one the user has in front, and their pages are never retitled.
    scoped = browser_use_cli._scope_to_own_tab("print(1)", "", on_chrome, None)
    assert scoped.startswith(browser_use_cli._OWN_TAB_PREAMBLE)
    assert on_chrome["BH_TAB_MARKER"] == "0"
    assert (
        browser_use_cli._scope_to_own_tab("print(1)", "", elsewhere, None) == "print(1)"
    )
    assert "BH_TAB_MARKER" not in elsewhere
    note = browser_use_cli._take_my_chrome_note("t", on_chrome)["my_chrome"]
    assert "Payments: AUTONOMOUS" in note
    assert browser_use_cli._take_my_chrome_note("t", on_chrome) == {}  # told once
    assert browser_use_cli._take_my_chrome_note("t", elsewhere) == {}

    (home / "config.yaml").write_text(
        "browser:\n  my_chrome:\n    enabled: true\n    confirm_payments: true\n",
        encoding="utf-8",
    )
    flipped = browser_use_cli._take_my_chrome_note("t", on_chrome)["my_chrome"]
    assert "Payments: CONFIRM FIRST" in flipped
