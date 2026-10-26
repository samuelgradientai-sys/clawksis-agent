"""`clawk config permissions`: one switch between the shipped guardrails and full agent access.

Driven end to end against a temp CLAWK_HOME: the switch writes real config.yaml keys, the real
approval guard honours them (dangerous commands run without a prompt, cron runs approve), and
the hardline floor still blocks what has no recovery path.
"""

import argparse
import io

import pytest

import clawk_cli.config as hc
from clawk_cli import config_permissions as cp


@pytest.fixture
def home(tmp_path, monkeypatch):
    clawk_home = tmp_path / "clawk"
    clawk_home.mkdir()
    (clawk_home / "config.yaml").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("CLAWK_HOME", str(clawk_home))
    hc._LOAD_CONFIG_CACHE.clear()
    yield clawk_home
    hc._LOAD_CONFIG_CACHE.clear()


def _run(level, **kw):
    cp.cmd_config_permissions(argparse.Namespace(level=level, yes=kw.get("yes", False)))
    hc._LOAD_CONFIG_CACHE.clear()


def test_full_then_default_round_trips_the_config(home):
    _run("full", yes=True)
    current = cp._current_values()
    assert cp.access_level(current) == "full"
    assert current["approvals.mode"] == "off"
    assert current["security.protected_instruction_files"] == "false"

    _run("default")
    assert cp.access_level(cp._current_values()) == "default"


def test_full_access_lets_risky_commands_run_but_keeps_the_hardline_floor(home):
    from tools.approval import check_all_command_guards
    from tools.approval_context import _get_cron_approval_mode

    _run("full", yes=True)

    assert check_all_command_guards("rm -rf ./build", "local")["approved"] is True
    assert _get_cron_approval_mode() == "approve"
    floor = check_all_command_guards("rm -rf /", "local")
    assert floor["approved"] is False and floor.get("hardline") is True


def test_full_without_a_terminal_needs_explicit_yes(home, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    _run("full")

    assert "--yes" in capsys.readouterr().out
    assert cp.access_level(cp._current_values()) == "default"
