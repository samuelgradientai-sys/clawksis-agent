"""Tests for _verify_reapable_browser_daemon() — the fail-closed psutil
identity/binding gate that guards the orphan reaper's tree-kill (A1 of the
Hermes→Clawksis audit). A planted .pid file or a recycled PID must NOT be
killed unless the live process genuinely looks like THIS session's
agent-browser daemon."""

from unittest.mock import MagicMock, patch

import psutil

import tools.browser_tool as bt

SOCKET_DIR = "/tmp/agent-browser-h_abc1234567"


def _fake_proc(name="agent-browser", cmdline=None, environ=None):
    proc = MagicMock()
    proc.name.return_value = name
    proc.cmdline.return_value = (
        cmdline
        if cmdline is not None
        else ["node", "agent-browser", "--dir", SOCKET_DIR]
    )
    proc.environ.return_value = environ or {}
    return proc


class TestVerifyReapableBrowserDaemon:
    def test_confirmed_browser_bound_to_socket_dir(self):
        proc = _fake_proc(cmdline=["node", "agent-browser", "--dir", SOCKET_DIR])
        with patch("psutil.Process", return_value=proc):
            assert (
                bt._verify_reapable_browser_daemon(12345, SOCKET_DIR, "h_abc1234567")
                is True
            )

    def test_bound_via_environ(self):
        # cmdline doesn't reference the dir, but AGENT_BROWSER_SOCKET_DIR does.
        proc = _fake_proc(
            cmdline=["agent-browser", "--headless"],
            environ={"AGENT_BROWSER_SOCKET_DIR": SOCKET_DIR},
        )
        with patch("psutil.Process", return_value=proc):
            assert (
                bt._verify_reapable_browser_daemon(12345, SOCKET_DIR, "h_abc1234567")
                is True
            )

    def test_not_agent_browser_refused(self):
        proc = _fake_proc(name="python", cmdline=["python", "server.py"])
        with patch("psutil.Process", return_value=proc):
            assert (
                bt._verify_reapable_browser_daemon(12345, SOCKET_DIR, "h_abc1234567")
                is False
            )

    def test_not_bound_to_this_session_refused(self):
        # Looks like agent-browser but bound to a DIFFERENT session's dir
        # (recycled PID / planted pid file pointing at another live daemon).
        proc = _fake_proc(
            cmdline=["node", "agent-browser", "--dir", "/tmp/agent-browser-h_other999"],
        )
        with patch("psutil.Process", return_value=proc):
            assert (
                bt._verify_reapable_browser_daemon(12345, SOCKET_DIR, "h_abc1234567")
                is False
            )

    def test_no_such_process_refused(self):
        with patch("psutil.Process", side_effect=psutil.NoSuchProcess(12345)):
            assert (
                bt._verify_reapable_browser_daemon(12345, SOCKET_DIR, "h_abc1234567")
                is False
            )

    def test_access_denied_refused(self):
        with patch("psutil.Process", side_effect=psutil.AccessDenied(12345)):
            assert (
                bt._verify_reapable_browser_daemon(12345, SOCKET_DIR, "h_abc1234567")
                is False
            )
