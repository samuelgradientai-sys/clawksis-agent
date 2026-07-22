"""Tests del first-run setup del login del dashboard.

Cubre las tres piezas:

  * ``first_run.save_basic_auth_credentials`` — persiste hash scrypt +
    secret (nunca texto plano) en ``dashboard.basic_auth``.

  * ``GET /login`` + ``POST /auth/setup`` — con gate activo y nada
    configurado, crear el login registra el provider en vivo, setea
    cookies de sesión y el segundo intento da 409.

  * ``first_run.setup_available`` — apagado en cuanto hay provider o
    credenciales configuradas.
"""

from __future__ import annotations


import pytest


# Comparte worker con los demás tests que mutan ``app.state`` del dashboard.

pytestmark = pytest.mark.xdist_group("dashboard_auth_app_state")

from fastapi.testclient import TestClient


from clawk_cli import web_server

from clawk_cli.dashboard_auth import clear_providers, list_providers

from clawk_cli.dashboard_auth import first_run

from clawk_cli.dashboard_auth.cookies import SESSION_AT_COOKIE

from clawk_cli.dashboard_auth.routes import _reset_password_rate_limit


@pytest.fixture
def fake_config(monkeypatch):
    """Config in-memory: load/save no tocan ~/.clawksis del entorno real."""

    store: dict = {}

    import clawk_cli.config as config_mod

    monkeypatch.setattr(config_mod, "load_config", lambda: store)

    monkeypatch.setattr(config_mod, "save_config", lambda cfg: store.update(cfg))

    # Sin env overrides colándose del entorno del dev/CI.

    for var in (
        "CLAWK_DASHBOARD_BASIC_AUTH_USERNAME",
        "CLAWK_DASHBOARD_BASIC_AUTH_PASSWORD",
        "CLAWK_DASHBOARD_BASIC_AUTH_PASSWORD_HASH",
        "CLAWK_DASHBOARD_BASIC_AUTH_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)

    return store


@pytest.fixture
def gated_no_providers(fake_config):
    """Gate activo, cero providers, rate-limit limpio."""

    clear_providers()

    _reset_password_rate_limit()

    prev_host = getattr(web_server.app.state, "bound_host", None)

    prev_required = getattr(web_server.app.state, "auth_required", None)

    web_server.app.state.bound_host = "fly-app.fly.dev"

    web_server.app.state.auth_required = True

    try:
        yield TestClient(web_server.app, base_url="https://fly-app.fly.dev")

    finally:
        web_server.app.state.bound_host = prev_host

        web_server.app.state.auth_required = prev_required

        clear_providers()

        _reset_password_rate_limit()


# ---------------------------------------------------------------------------

# Persistencia

# ---------------------------------------------------------------------------


def test_save_credentials_persists_hash_not_plaintext(fake_config):

    password_hash, secret = first_run.save_basic_auth_credentials(
        "samuel", "super-secreta-123"
    )

    section = fake_config["dashboard"]["basic_auth"]

    assert section["username"] == "samuel"

    assert section["password_hash"] == password_hash

    assert password_hash.startswith("scrypt$")

    assert "super-secreta-123" not in str(fake_config)

    assert "password" not in section  # nunca texto plano at rest

    assert len(secret) >= 16 and section["secret"]


def test_save_credentials_validates_lengths(fake_config):

    with pytest.raises(ValueError):
        first_run.save_basic_auth_credentials("ab", "super-secreta-123")

    with pytest.raises(ValueError):
        first_run.save_basic_auth_credentials("samuel", "corta")


def test_clear_credentials_roundtrip(fake_config):

    first_run.save_basic_auth_credentials("samuel", "super-secreta-123")

    assert first_run.basic_auth_configured() is True

    assert first_run.clear_basic_auth_credentials() is True

    assert first_run.basic_auth_configured() is False

    assert first_run.clear_basic_auth_credentials() is False


# ---------------------------------------------------------------------------

# Disponibilidad del setup

# ---------------------------------------------------------------------------


def test_setup_available_lifecycle(fake_config):

    clear_providers()

    assert first_run.setup_available() is True

    first_run.save_basic_auth_credentials("samuel", "super-secreta-123")

    assert first_run.setup_available() is False


def test_env_credentials_disable_setup(fake_config, monkeypatch):

    clear_providers()

    monkeypatch.setenv("CLAWK_DASHBOARD_BASIC_AUTH_USERNAME", "ops")

    assert first_run.basic_auth_configured() is True

    assert first_run.setup_available() is False


# ---------------------------------------------------------------------------

# HTTP end-to-end

# ---------------------------------------------------------------------------


def test_first_run_setup_end_to_end(gated_no_providers):

    client = gated_no_providers

    # 1. /login sirve el formulario de primera vez.

    r = client.get("/login")

    assert r.status_code == 200

    assert 'class="provider-form setup-form"' in r.text

    # 2. POST /auth/setup crea el login, registra el provider y loguea.

    r = client.post(
        "/auth/setup",
        json={"username": "samuel", "password": "super-secreta-123"},
    )

    assert r.status_code == 200

    assert r.json()["ok"] is True

    # En HTTPS la cookie sale con prefijo __Host-; alcanza con el sufijo.

    assert any(SESSION_AT_COOKIE in name for name in r.cookies.keys())

    assert [p.name for p in list_providers()] == ["basic"]

    # 3. Con el provider vivo, el login normal funciona sin reiniciar.

    r = client.post(
        "/auth/password-login",
        json={
            "provider": "basic",
            "username": "samuel",
            "password": "super-secreta-123",
        },
    )

    assert r.status_code == 200

    # 4. El setup queda deshabilitado: segundo intento → 409.

    r = client.post(
        "/auth/setup",
        json={"username": "intruso", "password": "otra-clave-123"},
    )

    assert r.status_code == 409

    # 5. Y /login vuelve a ser la página de sign-in normal.

    r = client.get("/login")

    assert "setup-form" not in r.text

    assert 'data-provider="basic"' in r.text


def test_setup_rejects_short_password(gated_no_providers):

    client = gated_no_providers

    r = client.post(
        "/auth/setup",
        json={"username": "samuel", "password": "corta"},
    )

    assert r.status_code == 400

    # Nada quedó configurado ni registrado.

    assert list_providers() == []

    assert first_run.setup_available() is True
