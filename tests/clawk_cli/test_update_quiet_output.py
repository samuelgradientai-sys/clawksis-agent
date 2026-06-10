"""Tests for the clean `clawk update` output helpers.

`_quiet_step` hides routine phase output behind a spinner so the run reads as
"progress + commits", but it must NEVER hide problems: warning/error lines are
surfaced even on success, and on any exception the whole captured buffer is
flushed before the exception propagates. `_print_new_commits` renders the
What's-new list.
"""

from __future__ import annotations

import subprocess

import pytest

from clawk_cli.main import _print_new_commits, _quiet_step


def test_quiet_step_hides_routine_but_surfaces_warnings(capsys):
    with _quiet_step("Building dashboard", verbose=False):
        print("routine progress detail")
        print("  ⚠ a warning worth seeing")
        print("✗ an error worth seeing")
        print("more routine detail")

    out = capsys.readouterr().out
    # Routine chatter is hidden…
    assert "routine progress detail" not in out
    assert "more routine detail" not in out
    # …but warnings/errors are always surfaced…
    assert "a warning worth seeing" in out
    assert "an error worth seeing" in out
    # …and the spinner label stands in for the phase (non-tty fallback).
    assert "Building dashboard" in out


def test_quiet_step_flushes_everything_on_exception(capsys):
    with pytest.raises(RuntimeError, match="boom"):
        with _quiet_step("Installing deps", verbose=False):
            print("detail that must surface when the phase fails")
            raise RuntimeError("boom")

    out = capsys.readouterr().out
    # On failure the captured buffer is flushed so the cause stays visible.
    assert "detail that must surface when the phase fails" in out


def test_quiet_step_does_not_swallow_systemexit(capsys):
    with pytest.raises(SystemExit):
        with _quiet_step("Pulling", verbose=False):
            print("rollback guidance line")
            raise SystemExit(1)

    out = capsys.readouterr().out
    assert "rollback guidance line" in out


def test_quiet_step_verbose_streams_everything(capsys):
    with _quiet_step("Phase X", verbose=True):
        print("verbose detail visible")

    out = capsys.readouterr().out
    assert "verbose detail visible" in out
    assert "Phase X" in out


def _init_repo(root):
    git = ["git"]
    subprocess.run(git + ["init", "-q"], cwd=root, check=True)
    subprocess.run(
        git + ["config", "user.email", "t@example.com"], cwd=root, check=True
    )
    subprocess.run(git + ["config", "user.name", "Tester"], cwd=root, check=True)
    subprocess.run(git + ["config", "commit.gpgsign", "false"], cwd=root, check=True)
    return git


def _head(git, root):
    return subprocess.run(
        git + ["rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()


def test_print_new_commits_lists_pulled_commits(capsys, tmp_path):
    git = _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    subprocess.run(git + ["add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(git + ["commit", "-qm", "first"], cwd=tmp_path, check=True)
    old = _head(git, tmp_path)

    (tmp_path / "b.txt").write_text("2", encoding="utf-8")
    subprocess.run(git + ["add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        git + ["commit", "-qm", "feat: second thing"], cwd=tmp_path, check=True
    )

    _print_new_commits(git, tmp_path, old)
    out = capsys.readouterr().out
    assert "What's new" in out
    assert "1 new commit" in out
    assert "feat: second thing" in out


def test_print_new_commits_noop_when_range_empty(capsys, tmp_path):
    git = _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    subprocess.run(git + ["add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(git + ["commit", "-qm", "only"], cwd=tmp_path, check=True)
    head = _head(git, tmp_path)

    _print_new_commits(git, tmp_path, head)  # old == HEAD -> empty range
    assert "What's new" not in capsys.readouterr().out


def test_print_new_commits_noop_when_sha_missing(capsys, tmp_path):
    _print_new_commits(["git"], tmp_path, None)
    assert capsys.readouterr().out == ""
