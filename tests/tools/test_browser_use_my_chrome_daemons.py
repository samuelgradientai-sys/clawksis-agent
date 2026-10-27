"""Browser Use daemons on the user's own Chrome (Mi Chrome) do not outlive the agent's use of it.

A harness daemon stays attached to the tabs it drove for as long as it lives: on Mi Chrome that is
Chrome's "being debugged" bar on the user's tabs and the dashboard live view following them. So the
daemon a task drove there is stopped when that task's turn ends (and only that task's), and every
daemon a process drove is stopped when the process exits, even one that never opened a built-in
browser session (browser_exec registers none). Tasks running at once (parallel subagents) each
drive Mi Chrome with their own daemon, so each keeps its own tab instead of sharing one.
"""

from __future__ import annotations

import json
import subprocess

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


def test_parallel_tasks_on_mi_chrome_each_get_their_own_daemon(monkeypatch):
    mi_chrome = "ws://127.0.0.1:9119/my-chrome/cdp/s3cret"
    seen: list[dict] = []

    def route(env, *_a):
        env["BU_CDP_WS"] = mi_chrome
        return env, None, False, 0

    monkeypatch.setattr(bu_cli, "_find_cli", lambda: ["browser-harness"])
    monkeypatch.setattr(bu_cli, "_base_subprocess_env", dict)
    monkeypatch.setattr(bu_cli, "_route_exec_current", route)
    monkeypatch.setattr(bu_cli, "_attach_vault_supervisor", lambda *a: None)
    monkeypatch.setattr(
        "tools.browser_my_chrome_state.my_chrome_cdp_url", lambda: mi_chrome
    )
    monkeypatch.setattr(bu_cli, "_driven_daemons", {})
    monkeypatch.setattr(bu_cli, "_my_chrome_daemons", {})

    def run_cli(cmd, code, env, timeout):
        seen.append({**env, "code": code})
        return subprocess.CompletedProcess(cmd, 0, "ok\n", "")

    monkeypatch.setattr(bu_cli, "_run_cli_killing_process_group", run_cli)

    for task in ("subagent-0-aa", "subagent-1-bb", "subagent-0-aa"):
        assert json.loads(bu_cli.browser_exec("print(1)", task_id=task))["success"]
    bu_cli.browser_exec("print(1)", session="mine", task_id="subagent-1-bb")

    names = [e.get("BU_NAME") for e in seen]
    assert names[0] != names[1] and names[0] == names[2]  # one daemon per task, kept
    assert names[3] == "mine"  # a named session keeps its name
    # The harness starts a named daemon on a tab of its own: no second one is pinned for a task.
    assert seen[0]["code"] == "print(1)"
    assert sorted(set(bu_cli._my_chrome_daemons.values())) == [
        "subagent-0-aa",
        "subagent-1-bb",
    ]
