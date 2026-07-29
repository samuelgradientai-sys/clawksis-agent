"""Regression harness for the dashboard auth gate.

Phase 0 — establish a baseline pin on the current (pre-OAuth) behavior so
later phases can prove they didn't break loopback mode.
"""
import pytest

# Phase 5 / Phase 6: these tests mutate ``web_server.app.state.auth_required``
# at module level. Run them in the same xdist worker so they don't race
# against each other (and against any other file that also touches
# ``app.state``) — the marker name is shared across all dashboard-auth test
# files that gate the app.
from fastapi.testclient import TestClient

from clawk_cli import web_server


@pytest.fixture
def client_loopback():
    # Pin the bound-host state for host_header_middleware so requests with
    # default Host: testclient pass the DNS-rebinding check.  TestClient
    # sends Host: testserver by default, but our middleware accepts the
    # loopback aliases when bound_host is loopback.
    prev_host = getattr(web_server.app.state, "bound_host", None)
    prev_port = getattr(web_server.app.state, "bound_port", None)
    web_server.app.state.bound_host = "127.0.0.1"
    web_server.app.state.bound_port = 9119
    client = TestClient(web_server.app, base_url="http://127.0.0.1:9119")
    yield client
    web_server.app.state.bound_host = prev_host
    web_server.app.state.bound_port = prev_port


def test_loopback_status_is_public(client_loopback):
    """`/api/status` must remain reachable without a token in loopback mode."""
    r = client_loopback.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body


def test_loopback_protected_route_requires_token(client_loopback):
    """Any non-public /api/ route must require the session token."""
    # /api/sessions exists and is auth-gated by auth_middleware.
    r = client_loopback.get("/api/sessions")
    assert r.status_code == 401


def test_loopback_protected_route_accepts_session_token(client_loopback):
    """The injected SPA token unlocks protected /api/ routes."""
    r = client_loopback.get(
        "/api/sessions",
        headers={"X-Clawksis-Session-Token": web_server._SESSION_TOKEN},
    )
    # 200 or 404 (no sessions yet) both prove the auth layer let it through.
    # 500 is also acceptable if there's a downstream issue unrelated to auth.
    assert r.status_code != 401, (
        f"Expected auth to succeed but got 401; body: {r.text}"
    )


def test_loopback_index_injects_session_token(client_loopback):
    """Loopback mode keeps injecting the SPA token into index.html.

    This is the property that the new auth gate MUST disable once a gated
    bind is detected. Phase 3 will add an inverse test for the gated path.
    """
    r = client_loopback.get("/")
    if r.status_code == 404:
        pytest.skip("WEB_DIST not built in this env")
    assert "__CLAWK_SESSION_TOKEN__" in r.text


def test_loopback_host_header_validation_still_enforced(client_loopback):
    """DNS-rebinding protection: a foreign Host header is rejected."""
    r = client_loopback.get("/api/status", headers={"Host": "evil.test"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# should_require_auth predicate (Task 0.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host,allow_public,expected", [
    ("127.0.0.1", False, False),
    ("127.0.0.1", True,  False),
    ("localhost", False, False),
    ("::1",       False, False),
    # Fork-specific: --insecure (allow_public=True) IS still the documented
    # escape hatch here — ``should_require_auth`` returns
    # ``(host not in loopback) and (not allow_public)``. Upstream dropped the
    # hatch in the June 2026 hardening; the fork keeps it.
    ("0.0.0.0",   True,  False),    # --insecure escape hatch
    ("0.0.0.0",   False, True),
    ("192.168.1.5", False, True),
    ("10.0.0.1",  True,  False),    # --insecure escape hatch
    ("100.64.0.1", False, True),    # Tailscale CGNAT — treated as public
    ("clawksis-agent-prod-abc.fly.dev", False, True),
])
def test_should_require_auth_truth_table(host, allow_public, expected):
    from clawk_cli.web_server import should_require_auth
    assert should_require_auth(host, allow_public) is expected


# ---------------------------------------------------------------------------
# start_server stashes auth_required on app.state (Task 0.3)
# ---------------------------------------------------------------------------


def _stub_uvicorn_run(monkeypatch):
    """Replace uvicorn.Config/Server with no-op fakes so start_server
    returns immediately (rather than blocking on the event loop). Returns the dict
    that will capture the keyword args.
    """
    import asyncio
    import contextlib
    import uvicorn
    captured: dict = {"kwargs": {}}

    class _FakeConfig:
        loaded = True
        host = "127.0.0.1"
        port = 8000

        def __init__(self, *args, **kwargs):
            captured["kwargs"] = kwargs

        def load(self):
            pass

        class lifespan_class:
            should_exit = False
            state: dict = {}

            def __init__(self, *a, **kw):
                pass

            async def startup(self):
                pass

            async def shutdown(self):
                pass

    class _FakeServer:
        should_exit = False
        started = True
        servers: list = []
        lifespan = None

        @staticmethod
        def capture_signals():
            return contextlib.nullcontext()

        async def startup(self, sockets=None):
            pass

        async def main_loop(self):
            pass

        async def shutdown(self, sockets=None):
            pass

    monkeypatch.setattr(uvicorn, "Config", _FakeConfig)
    monkeypatch.setattr(uvicorn, "Server", lambda config: _FakeServer())
    return captured


def test_start_server_loopback_sets_auth_required_false(monkeypatch):
    """Loopback bind: app.state.auth_required is False after start_server."""
    _stub_uvicorn_run(monkeypatch)
    # Force a fresh state to detect that start_server actually set it.
    web_server.app.state.auth_required = None
    web_server.start_server(
        host="127.0.0.1", port=9119,
        open_browser=False, allow_public=False,
    )
    assert web_server.app.state.auth_required is False


def test_start_server_insecure_public_sets_auth_required_false(monkeypatch):
    """Fork-specific: ``--insecure`` (allow_public=True) on a public host keeps
    the gate OFF. Upstream removed this escape hatch; the fork keeps it."""
    _stub_uvicorn_run(monkeypatch)
    web_server.app.state.auth_required = None
    web_server.start_server(
        host="0.0.0.0", port=9119,
        open_browser=False, allow_public=True,
    )
    assert web_server.app.state.auth_required is False


def test_start_server_public_without_insecure_records_auth_required(monkeypatch):
    """Public bind without --insecure: the gate engages and auth_required=True.

    Fork-specific: with no providers registered but first-run setup available,
    the server boots ANYWAY — the public /auth/setup page bootstraps the admin
    login on first visit (the documented `clawk dashboard domain` flow).
    Upstream fails closed with SystemExit here. The gate flag is still stashed
    so the rest of the system can branch on it.
    """
    from clawk_cli.dashboard_auth import clear_providers
    clear_providers()
    _stub_uvicorn_run(monkeypatch)
    web_server.app.state.auth_required = None
    web_server.start_server(
        host="0.0.0.0", port=9119,
        open_browser=False, allow_public=False,
    )
    assert web_server.app.state.auth_required is True


# ---------------------------------------------------------------------------
# Task 3.5: start_server fail-closed + proxy_headers + index-token suppression
# ---------------------------------------------------------------------------


def test_start_server_gate_with_provider_proceeds_and_sets_proxy_headers(monkeypatch):
    """With at least one provider, public bind + no --insecure starts the server.

    The SystemExit-refusing-to-bind guard is REPLACED in gated mode by
    "the gate engages", so as long as a provider is registered the bind
    succeeds.  uvicorn is called with proxy_headers=True so X-Forwarded-Proto
    from Fly's TLS terminator is honoured for cookie Secure-flag decisions.
    """
    from clawk_cli.dashboard_auth import clear_providers, register_provider
    from tests.clawk_cli.conftest_dashboard_auth import StubAuthProvider

    clear_providers()
    register_provider(StubAuthProvider())
    captured = _stub_uvicorn_run(monkeypatch)
    try:
        web_server.app.state.auth_required = None
        web_server.start_server(
            host="0.0.0.0", port=9119,
            open_browser=False, allow_public=False,
        )
        assert web_server.app.state.auth_required is True
        assert captured["kwargs"].get("host") == "0.0.0.0"
        assert captured["kwargs"].get("proxy_headers") is True
    finally:
        clear_providers()


def test_start_server_gate_without_provider_fails_closed(monkeypatch):
    """Fork-specific: no providers + first-run setup unavailable → SystemExit,
    clear message.

    When setup IS available the server boots with the /auth/setup page (see
    the with-setup test above); the fail-closed path only survives for the
    half-configured case where no provider registered AND the first-run page
    can't bootstrap a login.
    """
    from clawk_cli.dashboard_auth import clear_providers
    from clawk_cli.dashboard_auth import first_run

    clear_providers()
    monkeypatch.setattr(first_run, "setup_available", lambda: False)
    _stub_uvicorn_run(monkeypatch)
    web_server.app.state.auth_required = None
    with pytest.raises(SystemExit, match=r"setup page is unavailable"):
        web_server.start_server(
            host="0.0.0.0", port=9119,
            open_browser=False, allow_public=False,
        )


def test_start_server_loopback_keeps_proxy_headers_off(monkeypatch):
    """Loopback bind: proxy_headers stays False (no TLS terminator in front)."""
    captured = _stub_uvicorn_run(monkeypatch)
    web_server.start_server(
        host="127.0.0.1", port=9119,
        open_browser=False, allow_public=False,
    )
    assert captured["kwargs"].get("proxy_headers") is False


def test_start_server_insecure_keeps_proxy_headers_off(monkeypatch):
    """Fork-specific: --insecure keeps the gate off, so proxy_headers stays
    off too."""
    captured = _stub_uvicorn_run(monkeypatch)
    web_server.app.state.auth_required = None
    web_server.start_server(
        host="0.0.0.0", port=9119,
        open_browser=False, allow_public=True,
    )
    assert web_server.app.state.auth_required is False
    assert captured["kwargs"].get("proxy_headers") is False
