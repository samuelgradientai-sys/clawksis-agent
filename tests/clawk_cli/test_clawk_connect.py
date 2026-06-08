"""Unit tests for `clawk connect` / `clawk disconnect` (personal Clawksis API key).

No network: the portal verification path is exercised with a mocked
`urllib.request.urlopen`. CLAWK_HOME is redirected to a temp dir by the autouse
`_isolate_clawk_home` fixture in tests/conftest.py, so `save_env_value` writes
into an isolated `~/.clawksis/.env`.
"""

import json
from types import SimpleNamespace

from clawk_cli.config import get_env_value, save_env_value
from clawk_cli.main import cmd_connect, cmd_disconnect


def test_connect_saves_key_and_never_echoes_it(monkeypatch, capsys):
    monkeypatch.delenv("CLAWKSIS_PORTAL_URL", raising=False)
    monkeypatch.delenv("CLAWKSIS_API_KEY", raising=False)

    cmd_connect(
        SimpleNamespace(key="sk-clawksis-secret", no_verify=False, timeout=15.0)
    )

    assert get_env_value("CLAWKSIS_API_KEY") == "sk-clawksis-secret"
    out = capsys.readouterr().out
    assert "sk-clawksis-secret" not in out  # the secret is never printed


def test_disconnect_removes_the_key(monkeypatch):
    monkeypatch.delenv("CLAWKSIS_API_KEY", raising=False)
    save_env_value("CLAWKSIS_API_KEY", "sk-to-remove")

    cmd_disconnect(SimpleNamespace())

    assert get_env_value("CLAWKSIS_API_KEY") in (None, "")


def test_connect_verifies_against_portal_when_configured(monkeypatch, capsys):
    monkeypatch.setenv("CLAWKSIS_PORTAL_URL", "https://clawksis.com")
    monkeypatch.delenv("CLAWKSIS_API_KEY", raising=False)

    captured = {}

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _Resp(json.dumps({"valid": True, "user": "me@clawksis.com"}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    cmd_connect(SimpleNamespace(key="sk-verified", no_verify=False, timeout=5.0))

    assert captured["url"] == "https://clawksis.com/api/keys/verify"
    assert captured["body"] == {"api_key": "sk-verified"}
    assert get_env_value("CLAWKSIS_API_KEY") == "sk-verified"
    out = capsys.readouterr().out
    assert "me@clawksis.com" in out
    assert "sk-verified" not in out


def test_connect_skips_verify_with_no_verify_flag(monkeypatch):
    monkeypatch.setenv("CLAWKSIS_PORTAL_URL", "https://clawksis.com")
    monkeypatch.delenv("CLAWKSIS_API_KEY", raising=False)

    def boom(*a, **k):  # must NOT be called when --no-verify is set
        raise AssertionError("verify should be skipped with --no-verify")

    monkeypatch.setattr("urllib.request.urlopen", boom)

    cmd_connect(SimpleNamespace(key="sk-noverify", no_verify=True, timeout=5.0))

    assert get_env_value("CLAWKSIS_API_KEY") == "sk-noverify"
