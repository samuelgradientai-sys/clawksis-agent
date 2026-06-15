"""Regression tests for _apply_profile_override CLAWK_HOME guard (issue #22502).



When CLAWK_HOME is set to the clawk root (e.g. systemd hardcodes

CLAWK_HOME=/root/.clawksis), _apply_profile_override must still read

active_profile and update CLAWK_HOME to the profile directory.



When CLAWK_HOME is already a profile directory (.../profiles/<name>),

_apply_profile_override must trust it and return without re-reading

active_profile (child-process inheritance contract).

"""

from __future__ import annotations


import os

import sys

from pathlib import Path
from types import SimpleNamespace


def _run_apply_profile_override(
    tmp_path,
    monkeypatch,
    *,
    clawk_home: str | None,
    active_profile: str | None,
    argv: list[str] | None = None,
):
    """Run _apply_profile_override in isolation.



    Returns the value of os.environ["CLAWK_HOME"] after the call,

    or None if unset.

    """

    clawk_root = tmp_path / ".clawksis"

    clawk_root.mkdir(parents=True, exist_ok=True)

    if active_profile is not None:
        (clawk_root / "active_profile").write_text(active_profile)

    if active_profile and active_profile != "default":
        (clawk_root / "profiles" / active_profile).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    if clawk_home is not None:
        monkeypatch.setenv("CLAWK_HOME", clawk_home)

    else:
        monkeypatch.delenv("CLAWK_HOME", raising=False)

    monkeypatch.setattr(sys, "argv", argv or ["clawk", "gateway", "start"])

    from clawk_cli.main import _apply_profile_override

    _apply_profile_override()

    return os.environ.get("CLAWK_HOME")


class TestApplyProfileOverrideClawkHomeGuard:
    """Regression guard for issue #22502.



    Verifies that CLAWK_HOME pointing to the clawk root does NOT suppress

    the active_profile check, while CLAWK_HOME already pointing to a

    profile directory IS trusted as-is.

    """

    def test_clawk_home_at_root_with_active_profile_is_redirected(
        self, tmp_path, monkeypatch
    ):
        """CLAWK_HOME=/root/.clawksis + active_profile=coder must redirect

        CLAWK_HOME to .../profiles/coder.



        Bug scenario from #22502: systemd sets CLAWK_HOME to the clawk root

        and the user switches to a profile via `clawk profile use`.

        Before the fix, the guard returned early and active_profile was ignored.

        """

        clawk_root = tmp_path / ".clawksis"

        clawk_root.mkdir(parents=True, exist_ok=True)

        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            clawk_home=str(clawk_root),
            active_profile="coder",
        )

        assert result is not None, "CLAWK_HOME must be set after profile redirect"

        assert "profiles" in result, (
            f"Expected CLAWK_HOME to point into profiles/ dir, got: {result!r}"
        )

        assert result.endswith("coder"), (
            f"Expected CLAWK_HOME to end with 'coder', got: {result!r}"
        )

    def test_clawk_home_already_profile_dir_is_trusted(self, tmp_path, monkeypatch):
        """CLAWK_HOME=.../profiles/coder must not be overridden even when

        active_profile says something different.



        Preserves the child-process inheritance contract: a subprocess spawned

        with CLAWK_HOME already set to a specific profile must stay in that

        profile.

        """

        clawk_root = tmp_path / ".clawksis"

        profile_dir = clawk_root / "profiles" / "coder"

        profile_dir.mkdir(parents=True, exist_ok=True)

        (clawk_root / "active_profile").write_text("other")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        monkeypatch.setenv("CLAWK_HOME", str(profile_dir))

        monkeypatch.setattr(sys, "argv", ["clawk", "gateway", "start"])

        from clawk_cli.main import _apply_profile_override

        _apply_profile_override()

        assert os.environ.get("CLAWK_HOME") == str(profile_dir), (
            "CLAWK_HOME must remain unchanged when already pointing to a profile dir"
        )

    def test_clawk_home_unset_reads_active_profile(self, tmp_path, monkeypatch):
        """Classic case: CLAWK_HOME unset + active_profile=coder must set

        CLAWK_HOME to the profile directory (existing behaviour must not regress).

        """

        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            clawk_home=None,
            active_profile="coder",
        )

        assert result is not None

        assert "coder" in result

    def test_sudo_explicit_profile_resolves_invoking_users_profile(
        self, tmp_path, monkeypatch
    ):
        """sudo elias ... should resolve `-p elias` under SUDO_USER, not root."""
        root_home = tmp_path / "root"
        user_home = tmp_path / "home" / "clawk"
        profile_dir = user_home / ".clawk" / "profiles" / "elias"
        profile_dir.mkdir(parents=True, exist_ok=True)
        (root_home / ".clawk").mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "home", lambda: root_home)
        monkeypatch.setenv("SUDO_USER", "clawk")
        monkeypatch.delenv("CLAWK_HOME", raising=False)
        monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
        monkeypatch.setattr(
            sys, "argv", ["clawk", "-p", "elias", "gateway", "install", "--system"]
        )

        import pwd

        monkeypatch.setattr(
            pwd, "getpwnam", lambda name: SimpleNamespace(pw_dir=str(user_home))
        )

        from clawk_cli.main import _apply_profile_override

        _apply_profile_override()

        assert os.environ.get("CLAWK_HOME") == str(profile_dir)
        assert sys.argv == ["clawk", "gateway", "install", "--system"]

    def test_clawk_home_unset_default_profile_no_redirect(self, tmp_path, monkeypatch):
        """active_profile=default must not redirect CLAWK_HOME."""

        clawk_root = tmp_path / ".clawksis"

        clawk_root.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        monkeypatch.delenv("CLAWK_HOME", raising=False)

        monkeypatch.setattr(sys, "argv", ["clawk", "gateway", "start"])

        (clawk_root / "active_profile").write_text("default")

        from clawk_cli.main import _apply_profile_override

        _apply_profile_override()

        assert os.environ.get("CLAWK_HOME") is None

    def test_subcommand_profile_flag_is_not_consumed(self, tmp_path, monkeypatch):
        """Command argv flags named --profile must stay with that command.

        Docker Desktop's MCP Toolkit uses `docker mcp gateway run --profile ...`.
        When that argv is passed through `clawk mcp add --args`, the early
        profile pre-parser must not interpret the Docker profile as a Clawksis
        profile.
        """
        clawk_root = tmp_path / ".clawk"
        clawk_root.mkdir(parents=True, exist_ok=True)
        argv = [
            "clawk",
            "mcp",
            "add",
            "docker-research",
            "--command",
            "docker",
            "--args",
            "mcp",
            "gateway",
            "run",
            "--profile",
            "research",
        ]

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("CLAWK_HOME", raising=False)
        monkeypatch.setattr(sys, "argv", list(argv))

        from clawk_cli.main import _apply_profile_override

        _apply_profile_override()

        assert os.environ.get("CLAWK_HOME") is None
        assert sys.argv == argv

    def test_profile_after_chat_subcommand_is_still_consumed(
        self, tmp_path, monkeypatch
    ):
        """Profile flags historically work after normal Clawksis subcommands."""
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            clawk_home=None,
            active_profile="coder",
            argv=["clawk", "chat", "-p", "coder", "-q", "hello"],
        )

        assert result is not None
        assert result.endswith("coder")
        assert sys.argv == ["clawk", "chat", "-q", "hello"]

    def test_top_level_profile_after_value_flag_is_consumed(
        self, tmp_path, monkeypatch
    ):
        """Top-level --profile still works after other top-level value flags."""
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            clawk_home=None,
            active_profile="coder",
            argv=["clawk", "-m", "gpt-5", "--profile", "coder", "chat"],
        )

        assert result is not None
        assert result.endswith("coder")
        assert sys.argv == ["clawk", "-m", "gpt-5", "chat"]

    def test_top_level_profile_after_continue_flag_is_consumed(
        self, tmp_path, monkeypatch
    ):
        """--continue has an optional value, so a following --profile is a flag."""
        result = _run_apply_profile_override(
            tmp_path,
            monkeypatch,
            clawk_home=None,
            active_profile="coder",
            argv=["clawk", "--continue", "--profile", "coder"],
        )

        assert result is not None
        assert result.endswith("coder")
        assert sys.argv == ["clawk", "--continue"]
