"""Behaviour contracts for the optional extras of ``finance/kronos`` setup (``kronos_setup.py``).

statsforecast (AutoETS baseline), pandas_market_calendars (NYSE holidays) and quantstats (HTML
tear sheet) go into the skill's own venv, one by one and best effort: every part of the skill
works without them, so a failed extra is reported and never fails the install, an extra can
never move numpy/pandas outside the core bounds, and an extra that breaks the core runtime is
an error. Fake runner only: nothing is installed.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "skills" / "finance" / "kronos" / "scripts"
)


def _load(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # siblings import each other by these names
    spec.loader.exec_module(module)
    return module


kc = _load("_kronos_common")
setup = _load("kronos_setup")


class FakeRunner:
    """Answers the extras probe with *present*; installs fail for names in *broken*."""

    def __init__(self, present=(), broken=()):
        self.present, self.broken, self.calls = set(present), set(broken), []

    def __call__(self, cmd, timeout):
        self.calls.append(list(cmd))
        if setup._EXTRAS_PROBE in cmd:
            names = cmd[cmd.index(setup._EXTRAS_PROBE) + 1 :]
            found = {n: n in self.present for n in names}
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps(found), stderr=""
            )
        if "install" in cmd:
            package = next(c for c in cmd if c in setup.EXTRA_REQUIREMENTS.values())
            name = package.split(">=")[0]
            if name in self.broken:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no wheel")
            self.present.add(name)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def installs(self):
        return [c for c in self.calls if "install" in c]


@pytest.fixture
def venv_python(tmp_path):
    python = kc.venv_python_path(tmp_path / "venv")
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return python


def test_extras_install_one_by_one_and_a_failure_is_only_reported(venv_python):
    runner = FakeRunner(present={"statsforecast"}, broken={"quantstats"})
    status = setup.ensure_extras(venv_python, runner)
    assert status["statsforecast"] == "ok"  # already there: not reinstalled
    assert status["pandas_market_calendars"] == "ok"
    assert status["quantstats"].startswith("failed")
    installs = runner.installs()
    assert len(installs) == 2
    for cmd in installs:
        assert set(setup.CORE_BOUNDS) <= set(
            cmd
        )  # numpy/pandas stay inside the core bounds
    assert all("<" in req for req in setup.EXTRA_REQUIREMENTS.values())


def test_check_reports_extras_once_the_core_runtime_imports(tmp_path, venv_python):
    home = venv_python.parent.parent.parent
    runner = FakeRunner(present={"pandas_market_calendars"})
    status = setup.check_status(home, runner)
    assert status["extras"] == {
        "statsforecast": "missing",
        "pandas_market_calendars": "ok",
        "quantstats": "missing",
    }
    broken_core = setup.check_status(
        home, lambda cmd, timeout: subprocess.CompletedProcess(cmd, 1)
    )
    assert broken_core["dependencies"] == "missing" and broken_core["extras"] == {}


def _fake_install(monkeypatch, python, core_ok_after_extras=True):
    calls = {"extras": 0}
    monkeypatch.setattr(
        setup, "install_upstream_code", lambda home, force: home / "src"
    )
    monkeypatch.setattr(setup, "ensure_venv", lambda home, runner, force: python)
    monkeypatch.setattr(setup, "ensure_deps", lambda *a, **k: None)
    monkeypatch.setattr(setup, "install_model", lambda *a: {"model_dir": "/m"})

    def extras(_python, _runner):
        calls["extras"] += 1
        return {"statsforecast": "ok"}

    monkeypatch.setattr(setup, "ensure_extras", extras)
    monkeypatch.setattr(setup, "deps_ok", lambda *a: core_ok_after_extras)
    return calls


def _args(*flags):
    return setup.build_parser().parse_args(list(flags))


def test_install_adds_extras_unless_told_not_to(tmp_path, monkeypatch, venv_python):
    calls = _fake_install(monkeypatch, venv_python)
    result = setup.install(_args(), tmp_path / "kronos", runner=None)
    assert result["extras"] == {"statsforecast": "ok"} and calls["extras"] == 1
    result = setup.install(_args("--no-extras"), tmp_path / "kronos", runner=None)
    assert result["extras"] == {} and calls["extras"] == 1


def test_an_extra_that_breaks_the_runtime_is_an_error(
    tmp_path, monkeypatch, venv_python
):
    _fake_install(monkeypatch, venv_python, core_ok_after_extras=False)
    with pytest.raises(kc.SkillError, match="broke the Kronos runtime") as caught:
        setup.install(_args(), tmp_path / "kronos", runner=None)
    assert "--no-extras" in caught.value.hint
