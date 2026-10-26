"""Mi Chrome in the dashboard: device pairing and the extension's socket.

Contract: the pairing string is shown once and only the token's hash is stored (0600, profile
home); the extension's socket refuses a missing, wrong or revoked token — and a disabled feature —
BEFORE the upgrade is accepted; a good token is accepted with the Mi Chrome subprotocol, publishes
the relay for the profile while connected and unpublishes it on close; the management routes sit
behind the dashboard's auth; the user's payments switch is saved to config.yaml.
"""

from __future__ import annotations

import base64
import json

import pytest

from tests.waiting import wait_until

SUBPROTOCOL = "clawk-mychrome.v1"
HELLO = {
    "type": "hello",
    "product": "Chrome/141.0",
    "userAgent": "UA",
    "version": "1.0.0",
    "tabs": [
        {
            "id": 7,
            "windowId": 1,
            "index": 0,
            "url": "https://vuelaya.example/",
            "title": "VuelaYa",
            "active": True,
        }
    ],
}


@pytest.fixture
def home(_isolate_clawk_home):
    from clawk_constants import get_clawk_home

    path = get_clawk_home()
    (path / "config.yaml").write_text(
        "browser:\n  my_chrome:\n    enabled: true\n", encoding="utf-8"
    )
    return path


@pytest.fixture
def client(home):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")
    from clawk_cli import web_server

    return TestClient(web_server.app, base_url="http://127.0.0.1")


def auth():
    from clawk_cli.web_server import _SESSION_TOKEN

    return {"X-Clawksis-Session-Token": _SESSION_TOKEN}


def pair(client) -> str:
    reply = client.post(
        "/api/my-chrome/pairing",
        json={"url": "https://vps.tailnet.ts.net"},
        headers=auth(),
    )
    assert reply.status_code == 200
    shown = reply.json()["pairing"]
    payload = json.loads(base64.urlsafe_b64decode(shown.split(":", 1)[1] + "==="))
    assert payload["u"] == "https://vps.tailnet.ts.net"
    return payload["t"]


def refused(client, protocols) -> bool:
    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect("/api/my-chrome/connect", subprotocols=protocols):
            return False
    except WebSocketDisconnect:
        return True


def test_only_the_tokens_hash_is_stored(client, home):
    token = pair(client)
    stored = (home / "my_chrome" / "pairing.json").read_text()
    assert token not in stored and "token_sha256" in stored
    assert oct((home / "my_chrome" / "pairing.json").stat().st_mode & 0o777) == "0o600"


def test_bad_revoked_or_disabled_tokens_never_get_a_socket(client, home):
    token = pair(client)
    assert refused(client, [SUBPROTOCOL])
    assert refused(client, [SUBPROTOCOL, "mc1." + "A" * 43])
    assert refused(client, [token])  # the token alone, without the protocol

    (home / "config.yaml").write_text(
        "browser:\n  my_chrome:\n    enabled: false\n", encoding="utf-8"
    )
    assert refused(client, [SUBPROTOCOL, token])
    (home / "config.yaml").write_text(
        "browser:\n  my_chrome:\n    enabled: true\n", encoding="utf-8"
    )

    assert client.delete("/api/my-chrome/pairing", headers=auth()).json() == {
        "revoked": True
    }
    assert refused(client, [SUBPROTOCOL, token])


def test_a_paired_extension_publishes_the_relay_while_connected(client, home):
    from tools.browser_my_chrome_state import relay_snapshot

    token = pair(client)
    with client.websocket_connect(
        "/api/my-chrome/connect", subprotocols=[SUBPROTOCOL, token]
    ) as ws:
        assert ws.accepted_subprotocol == SUBPROTOCOL
        ws.send_text(json.dumps(HELLO))
        ws.send_text(json.dumps({"type": "ping"}))
        assert json.loads(ws.receive_text()) == {"type": "pong"}
        published = wait_until(
            lambda: (snap := relay_snapshot(home))["live"] and snap,
            what="relay published",
        )
        assert published["cdp_url"].startswith("ws://127.0.0.1:")
        status = client.get("/api/my-chrome/status", headers=auth()).json()
        assert status["connected"] and [t["title"] for t in status["tabs"]] == [
            "VuelaYa"
        ]
    wait_until(
        lambda: relay_snapshot(home)["cdp_url"] == "", what="relay unpublished on close"
    )


def test_management_routes_need_the_dashboard_session(client):
    assert client.get("/api/my-chrome/status").status_code == 401
    assert (
        client.post(
            "/api/my-chrome/pairing", json={"url": "https://x.example"}
        ).status_code
        == 401
    )
    assert client.get("/api/my-chrome/extension.zip").status_code == 401


def test_the_payments_switch_is_the_users_config(client, home):
    status = client.put(
        "/api/my-chrome/settings", json={"confirm_payments": True}, headers=auth()
    ).json()
    assert status["confirm_payments"] is True and status["enabled"] is True
    assert "confirm_payments: true" in (home / "config.yaml").read_text()


def test_the_extension_download_is_a_loadable_folder(client):
    import io
    import zipfile

    reply = client.get("/api/my-chrome/extension.zip", headers=auth())
    bundle = zipfile.ZipFile(io.BytesIO(reply.content))
    names = set(bundle.namelist())
    manifest = json.loads(bundle.read("clawksis-mi-chrome/manifest.json"))
    referenced = {
        manifest["background"]["service_worker"],
        manifest["action"]["default_popup"],
        *manifest["icons"].values(),
        "lib/pairing.js",
        "lib/tabs.js",
    }
    # One top folder to pick in "Load unpacked", holding everything the manifest points at.
    assert {f"clawksis-mi-chrome/{path}" for path in referenced} <= names
