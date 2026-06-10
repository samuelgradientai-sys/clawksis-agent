"""Unit tests for the `clawk dashboard --remote` SSH-tunnel argv builder.

Covers the pure, side-effect-free `_build_dashboard_ssh_cmd` only — no network,
no real ssh, and none of the tunnel/browser/threading machinery in
`_run_dashboard_remote`.
"""

from clawk_cli.main import _build_dashboard_ssh_cmd


def test_tunnel_only_mode_holds_the_forward_open_with_dash_N():
    cmd = _build_dashboard_ssh_cmd("user@host", 9119, start=False, extra_ssh=None)
    assert cmd == [
        "ssh",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        "-L",
        "9119:127.0.0.1:9119",
        "-N",
        "user@host",
    ]


def test_start_mode_allocates_a_tty_and_launches_the_remote_dashboard():
    cmd = _build_dashboard_ssh_cmd("me@box", 8080, start=True, extra_ssh=[])
    assert cmd == [
        "ssh",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        "-L",
        "8080:127.0.0.1:8080",
        "-t",
        "me@box",
        "clawk dashboard --no-open --host 127.0.0.1 --port 8080",
    ]
    # --start launches a remote command, so it must NOT also pass -N.
    assert "-N" not in cmd


def test_port_is_threaded_through_the_forward_and_remote_command():
    cmd = _build_dashboard_ssh_cmd("u@h", 12345, start=True, extra_ssh=None)
    assert cmd[cmd.index("-L") + 1] == "12345:127.0.0.1:12345"
    assert cmd[-1] == "clawk dashboard --no-open --host 127.0.0.1 --port 12345"


def test_extra_ssh_opts_are_forwarded_after_the_tunnel_and_before_the_target():
    cmd = _build_dashboard_ssh_cmd(
        "user@host",
        9119,
        start=False,
        extra_ssh=["-i", "~/.ssh/id_ed25519", "-p", "2222"],
    )
    forward_idx = cmd.index("9119:127.0.0.1:9119")
    target_idx = cmd.index("-N")
    assert cmd[forward_idx + 1 : target_idx] == [
        "-i",
        "~/.ssh/id_ed25519",
        "-p",
        "2222",
    ]
