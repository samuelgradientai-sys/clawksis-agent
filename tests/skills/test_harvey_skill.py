"""harvey skill: its wrapper installs Harvey at the reviewed commit, finds a Claude CLI the way a
user's machine actually has one (PATH, else the copy bundled with an editor extension) and runs
Harvey from its own checkout with that CLI on PATH."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "optional-skills"
    / "email"
    / "harvey"
    / "scripts"
    / "harvey_cli.py"
)


def load():
    spec = importlib.util.spec_from_file_location("harvey_cli_skill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_claude_on_path_wins(tmp_path):
    mod = load()
    on_path = _exe(tmp_path / "bin" / ("claude" + mod._EXE))
    assert mod.find_claude(path=str(on_path.parent), user_home=tmp_path) == on_path


def test_without_claude_on_path_the_newest_editor_copy_is_used(tmp_path):
    mod = load()
    ext = tmp_path / ".vscode" / "extensions"
    tail = Path("resources") / "native-binary" / ("claude" + mod._EXE)
    old = _exe(ext / "anthropic.claude-code-2.1.0-linux-x64" / tail)
    new = _exe(ext / "anthropic.claude-code-2.1.311-linux-x64" / tail)
    os.utime(old, (1, 1))
    found = mod.find_claude(path=str(tmp_path / "empty"), user_home=tmp_path)
    assert found == new
    assert (
        mod.find_claude(path=str(tmp_path / "empty"), user_home=tmp_path / "x") is None
    )


def test_harvey_runs_from_its_checkout_with_claude_on_its_path(tmp_path, monkeypatch):
    mod = load()
    root = tmp_path / "harvey"
    _exe(mod.venv_bin(root, "harvey"))
    claude = _exe(tmp_path / "editor" / ("claude" + mod._EXE))
    monkeypatch.setenv("CLAWK_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(mod, "harvey_home", lambda home=None: root)
    monkeypatch.setattr(mod, "find_claude", lambda *a, **k: claude)
    with patch.object(mod.subprocess, "run") as run:
        run.return_value.returncode = 0
        assert mod.main(["run", "--", "discover", "--estimate"]) == 0
    cmd = run.call_args.args[0]
    assert cmd == [str(mod.venv_bin(root, "harvey")), "discover", "--estimate"]
    assert run.call_args.kwargs["cwd"] == root
    path = run.call_args.kwargs["env"]["PATH"].split(os.pathsep)
    assert path[0] == str(claude.parent)


def test_run_before_install_refuses_without_running_anything(tmp_path, monkeypatch):
    mod = load()
    monkeypatch.setattr(mod, "harvey_home", lambda home=None: tmp_path / "missing")
    with patch.object(mod.subprocess, "run") as run:
        assert mod.main(["run", "--", "status"]) == 2
    run.assert_not_called()


def test_install_checks_out_the_pinned_commit(tmp_path, monkeypatch):
    mod = load()
    root = tmp_path / "harvey"
    monkeypatch.setattr(mod, "find_python", lambda: "/usr/bin/python3")
    monkeypatch.setattr(mod, "status", lambda r: {"home": str(r)})
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "clone"]:
            (root / ".git").mkdir(parents=True)
            (root / ".env.example").write_text("KEY=\n")

        class Done:
            returncode = 0
            stdout = ""

        return Done()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod.install(root)
    assert ["git", "-C", str(root), "checkout", "--quiet", mod.HARVEY_COMMIT] in calls
    assert len(mod.HARVEY_COMMIT) == 40
    assert (root / ".env").read_text() == "KEY=\n"
