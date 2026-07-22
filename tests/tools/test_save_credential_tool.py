"""Tests for the agent-callable save_credential tool.

Closes the gap where a credential the user typed in chat never reached the
cron job: the agent now persists it to ~/.clawksis/.env (which crons reload
before every run).
"""

import pathlib

import pytest


@pytest.fixture
def clawk_home(tmp_path, monkeypatch):
    """Point CLAWK_HOME at a temp dir so .env writes are isolated."""

    home = tmp_path / ".clawksis"
    home.mkdir()
    monkeypatch.setenv("CLAWK_HOME", str(home))
    # Don't let a real managed-deployment marker affect the test.
    monkeypatch.delenv("CLAWK_MANAGED", raising=False)
    return home


def _read_env(home: pathlib.Path) -> str:
    env = home / ".env"
    return env.read_text(encoding="utf-8") if env.exists() else ""


def test_saves_secret_to_env_file(clawk_home, monkeypatch):
    """Happy path: the secret lands in .env and the current environment."""

    from tools.save_credential_tool import save_credential_tool

    result = save_credential_tool("SUPABASE_SERVICE_ROLE_KEY", "sk-secret-123")

    assert "Saved SUPABASE_SERVICE_ROLE_KEY" in result
    assert "SUPABASE_SERVICE_ROLE_KEY=sk-secret-123" in _read_env(clawk_home)


def test_secret_value_never_echoed(clawk_home):
    """The raw secret must not appear in the tool's returned string."""

    from tools.save_credential_tool import save_credential_tool

    secret = "super-secret-token-value-xyz"
    result = save_credential_tool("MY_API_KEY", secret)

    assert secret not in result


def test_sets_current_process_env(clawk_home, monkeypatch):
    """The value is available immediately in os.environ for this session."""

    import os

    from tools.save_credential_tool import save_credential_tool

    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    save_credential_tool("STRIPE_API_KEY", "sk_live_abc")

    assert os.environ.get("STRIPE_API_KEY") == "sk_live_abc"


def test_rejects_invalid_name(clawk_home):
    """A non-env-var name is rejected with a clear, value-free error."""

    from tools.save_credential_tool import save_credential_tool

    result = save_credential_tool("123 not valid", "x")

    assert result.startswith("Error")
    assert "SUPABASE_SERVICE_ROLE_KEY=" not in _read_env(clawk_home)


def test_rejects_denylisted_name(clawk_home):
    """Denylisted variables (e.g. LD_PRELOAD) cannot be written."""

    from tools.save_credential_tool import save_credential_tool

    result = save_credential_tool("LD_PRELOAD", "/tmp/evil.so")

    assert result.startswith("Error")
    assert "LD_PRELOAD" not in _read_env(clawk_home)


def test_requires_name_and_value(clawk_home):
    """Missing name or value returns an error without writing anything."""

    from tools.save_credential_tool import save_credential_tool

    assert save_credential_tool("", "x").startswith("Error")
    assert save_credential_tool("FOO", "").startswith("Error")
    assert _read_env(clawk_home) == ""


def test_tool_is_registered():
    """The tool self-registers and is discoverable under the credentials toolset."""

    import tools.save_credential_tool  # noqa: F401 — triggers registration

    from tools.registry import registry

    entry = registry._tools.get("save_credential")

    assert entry is not None
    assert entry.toolset == "credentials"
