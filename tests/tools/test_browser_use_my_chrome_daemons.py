"""Browser Use daemons on the user's own Chrome (Mi Chrome) do not outlive the agent's use of it.

A harness daemon stays attached to the tabs it drove for as long as it lives: on Mi Chrome that is
Chrome's "being debugged" bar on the user's tabs and the dashboard live view following them. So the
daemon a task drove there is stopped when that task's turn ends (and only that task's), and every
daemon a process drove is stopped when the process exits, even one that never opened a built-in
browser session (browser_exec registers none).
"""

from __future__ import annotations

import pytest

from tools import browser_tool, browser_tool_lifecycle as lifecycle
from tools import browser_use_cli as bu_cli


@pytest.fixture
def stopped(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        bu_cli, "_reload_daemons", lambda daemons: calls.extend(daemons)
    )
    monkeypatch.setattr(bu_cli, "_driven_daemons", {})
    monkeypatch.setattr(bu_cli, "_my_chrome_daemons", {})
    return calls


def _drive(daemon, task_id, *, on_my_chrome):
    bu_cli._driven_daemons[daemon] = "home"
    if on_my_chrome:
        bu_cli._my_chrome_daemons[daemon] = task_id


def test_a_turn_end_stops_the_daemon_that_task_drove_on_mi_chrome_and_no_other(stopped):
    _drive(("d", "t1"), "t1", on_my_chrome=True)
    _drive(("d", "t2"), "t2", on_my_chrome=True)  # another chat still mid-turn
    _drive(("d", "t1-local"), "t1", on_my_chrome=False)  # the server's own browser

    lifecycle.cleanup_browser("t1")

    assert stopped == [("d", "t1")]
    assert set(bu_cli._driven_daemons) == {("d", "t2"), ("d", "t1-local")}


def test_process_exit_stops_browser_use_daemons_even_with_no_browser_session(
    stopped, monkeypatch
):
    monkeypatch.setattr(browser_tool, "_cleanup_done", False)
    monkeypatch.setattr(browser_tool, "_active_sessions", {})
    monkeypatch.setattr(lifecycle, "_reap_orphaned_browser_sessions", lambda: None)
    monkeypatch.setattr(lifecycle, "_stop_all_lightpanda", lambda: None)
    _drive(("d", "cli-run"), "default", on_my_chrome=True)

    lifecycle._emergency_cleanup_all_sessions()

    assert stopped == [("d", "cli-run")]
    assert bu_cli._driven_daemons == {} and bu_cli._my_chrome_daemons == {}
