""" "Mi Chrome" in the dashboard: the extension's socket, pairing, status, the on/off switch and
the extension download.

The extension (``apps/chrome-extension``) connects OUT to ``/api/my-chrome/connect``, so the
user's laptop needs no open port or tunnel. That socket is the one dashboard endpoint that does
not take the session token: the extension holds a durable device token instead (the session token
dies with the server), offered as a WebSocket subprotocol and checked BEFORE the upgrade is
accepted, so a bad or revoked token never gets a socket. Every other route here is an ordinary
``/api/*`` route behind the dashboard's auth middleware.

While an extension is connected this process serves its relay on a loopback CDP endpoint
(``tools/browser_my_chrome_server.py``) and publishes it for the profile
(``tools/browser_my_chrome_state.py``), which every agent of that profile — dashboard chat and the
messaging gateway — then uses as its browser.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel

from clawk_cli.web_routers._common import config_scoped_to_thread, config_write_scope

router = APIRouter()
logger = logging.getLogger(__name__)

EXTENSION_DIR = Path(__file__).resolve().parents[2] / "apps" / "chrome-extension"
_EXTENSION_FILES = ("*.json", "*.js", "*.html", "*.css", "lib/*.js", "icons/*.png")
_HELLO_TIMEOUT_S = 15.0
# Close codes the extension treats as final (no automatic reconnect).
CLOSE_REVOKED, CLOSE_DISABLED, CLOSE_REPLACED = 4401, 4403, 4409


@dataclass
class ExtensionLink:
    """One connected extension: its socket, relay and loopback endpoint."""

    home: Path
    ws: WebSocket
    relay: Any
    server: Any
    connected_at: float = field(default_factory=time.time)

    @property
    def cdp_url(self) -> str:
        return self.server.ws_url

    async def close(self, code: int) -> None:
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await self.ws.close(code=code)


# clawk_home_key(profile home) -> its connected extension (one per profile).
_links: dict[str, ExtensionLink] = {}


def _key(home: Path) -> str:
    from clawk_constants import clawk_home_key

    return clawk_home_key(home)


def links() -> list[ExtensionLink]:
    return list(_links.values())


def link_for_home(home: Path) -> Optional[ExtensionLink]:
    return _links.get(_key(home))


# ── the extension's socket ───────────────────────────────────────────────────


def _candidate_homes() -> list[Path]:
    """This dashboard's own home plus every installed profile's."""
    from clawk_cli.profiles import profiles_to_serve
    from clawk_constants import get_process_clawk_home

    homes = [get_process_clawk_home()]
    homes += [
        home
        for _name, home in profiles_to_serve(
            True, include_standalone=True, include_parked=True
        )
    ]
    unique: dict[str, Path] = {}
    for home in homes:
        unique.setdefault(_key(home), Path(home))
    return list(unique.values())


def _setting_for(home: Path, key: str) -> bool:
    from clawk_cli.web_server_profiles import _clawk_home_scope
    from tools.browser_my_chrome_state import my_chrome_setting

    with _clawk_home_scope(home):
        return my_chrome_setting(key)


def _enabled_for(home: Path) -> bool:
    return _setting_for(home, "enabled")


def paired_home(token: Optional[str]) -> Optional[Path]:
    """The profile home a device token belongs to, when Mi Chrome is enabled there."""
    from clawk_cli.my_chrome_pairing import home_for_token

    if not token:
        return None
    home = home_for_token(token, _candidate_homes())
    return home if home is not None and _enabled_for(home) else None


@router.websocket("/api/my-chrome/connect")
async def extension_socket(ws: WebSocket) -> None:
    from clawk_cli.my_chrome_pairing import SUBPROTOCOL, offered_token

    token = offered_token(ws.scope.get("subprotocols") or [])
    home = await asyncio.to_thread(paired_home, token)
    if home is None:
        # Before accept(): the upgrade is refused outright (HTTP 403), no socket is opened.
        await ws.close(code=CLOSE_REVOKED)
        return
    await ws.accept(subprotocol=SUBPROTOCOL)
    await serve_extension(ws, home)


async def _pump_to_extension(ws: WebSocket, relay) -> None:
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        while True:
            await ws.send_text(json.dumps(await relay.outbox.get()))


async def _read_from_extension(ws: WebSocket, relay) -> None:
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        while True:
            try:
                message = json.loads(await ws.receive_text())
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("type") == "ping":
                relay.outbox.put_nowait({"type": "pong"})
                continue
            await relay.on_extension_message(message)


async def serve_extension(ws: WebSocket, home: Path) -> None:
    """Run one accepted extension connection until it closes."""
    from tools.browser_my_chrome_relay import MyChromeRelay
    from tools.browser_my_chrome_server import LoopbackCdpServer
    from tools.browser_my_chrome_state import clear_relay, publish_relay

    relay = MyChromeRelay()
    server = LoopbackCdpServer(relay)
    link = ExtensionLink(home=home, ws=ws, relay=relay, server=server)
    previous = _links.get(_key(home))
    if previous is not None:
        await previous.close(CLOSE_REPLACED)
    await server.start()
    _links[_key(home)] = link
    tasks = [
        asyncio.create_task(_pump_to_extension(ws, relay)),
        asyncio.create_task(_read_from_extension(ws, relay)),
    ]
    try:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(relay.ready.wait(), _HELLO_TIMEOUT_S)
        if relay.ready.is_set():
            await asyncio.to_thread(
                publish_relay, home, link.cdp_url, browser=relay.product
            )
            logger.info(
                "Mi Chrome connected (%s, %d tabs)", relay.product, len(relay.tabs)
            )
            await tasks[1]
    finally:
        # Unpublish first, so every agent of the profile falls back on its next call while the
        # loopback endpoint is still closing its drivers' sockets. Synchronous on purpose (one
        # small file write): an await here is skipped when the connection task is cancelled
        # (dashboard shutdown), which would leave the profile pointed at a dead endpoint.
        clear_relay(home, link.cdp_url)
        if _links.get(_key(home)) is link:
            _links.pop(_key(home), None)
        for task in tasks:
            task.cancel()
        await relay.shutdown()
        await server.stop()
        logger.info("Mi Chrome disconnected")


# ── management routes (behind the dashboard auth middleware) ─────────────────


class PairingRequest(BaseModel):
    url: str  # the dashboard as the browser sees it (origin + base path)


class MyChromeSettings(BaseModel):
    """The user's Mi Chrome switches (``browser.my_chrome.*``); omitted fields keep their value."""

    enabled: Optional[bool] = None
    confirm_payments: Optional[bool] = None


def _current_home() -> Path:
    from clawk_constants import get_clawk_home

    return get_clawk_home()


def _status_for(home: Path, link: Optional[ExtensionLink]) -> dict:
    from clawk_cli.my_chrome_pairing import pairing_info
    from tools.browser_my_chrome_state import relay_snapshot

    pairing = pairing_info(home)
    snapshot = relay_snapshot(home)
    relay = link.relay if link else None
    return {
        "enabled": _enabled_for(home),
        "confirm_payments": _setting_for(home, "confirm_payments"),
        "paired": pairing is not None,
        "paired_at": (pairing or {}).get("created_at"),
        "connected": link is not None or bool(snapshot.get("live")),
        "active": bool(relay and relay.agent_active()),
        "connected_at": link.connected_at if link else snapshot.get("connected_at"),
        "browser": relay.product if relay else snapshot.get("browser") or None,
        "extension_version": relay.extension_version if relay else None,
        "tabs": relay.tab_summaries() if relay else [],
    }


@router.get("/api/my-chrome/status")
async def my_chrome_status(profile: Optional[str] = None) -> dict:
    home = await config_scoped_to_thread(profile, _current_home)
    return await asyncio.to_thread(_status_for, home, link_for_home(home))


@router.get("/api/my-chrome/activity")
async def my_chrome_activity(profile: Optional[str] = None) -> dict:
    """Cheap poll for the dashboard shell: is the agent using the user's Chrome right now?"""
    home = await config_scoped_to_thread(profile, _current_home)
    link = link_for_home(home)
    return {
        "connected": link is not None,
        "active": bool(link and link.relay.agent_active()),
    }


@router.put("/api/my-chrome/settings")
async def update_my_chrome_settings(
    body: MyChromeSettings, profile: Optional[str] = None
) -> dict:
    """The dashboard is a user surface (session-token / login gated); the agent only reads these."""
    from clawk_cli.config import load_config, save_config

    changes = body.model_dump(exclude_none=True)

    def _write() -> Path:
        with config_write_scope(profile):
            config = load_config()
            browser = config.setdefault("browser", {})
            section = browser.get("my_chrome")
            if not isinstance(section, dict):
                section = browser["my_chrome"] = {}
            section.update(changes)
            save_config(config)
            return _current_home()

    home = await asyncio.to_thread(_write)
    link = link_for_home(home)
    if link is not None and changes.get("enabled") is False:
        await link.close(CLOSE_DISABLED)
    return await asyncio.to_thread(_status_for, home, link_for_home(home))


@router.post("/api/my-chrome/pairing")
async def create_my_chrome_pairing(
    body: PairingRequest, profile: Optional[str] = None
) -> dict:
    from clawk_cli.my_chrome_pairing import dashboard_base, new_pairing

    try:
        base_url = dashboard_base(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    home = await config_scoped_to_thread(profile, _current_home)
    pairing = await asyncio.to_thread(new_pairing, home, base_url)
    link = link_for_home(home)
    if link is not None:  # its token was just replaced
        await link.close(CLOSE_REVOKED)
    return {"pairing": pairing}


@router.delete("/api/my-chrome/pairing")
async def revoke_my_chrome_pairing(profile: Optional[str] = None) -> dict:
    from clawk_cli.my_chrome_pairing import revoke_pairing

    home = await config_scoped_to_thread(profile, _current_home)
    revoked = await asyncio.to_thread(revoke_pairing, home)
    link = link_for_home(home)
    if link is not None:
        await link.close(CLOSE_REVOKED)
    return {"revoked": revoked}


def extension_zip(root: Path = EXTENSION_DIR) -> bytes:
    """The unpacked extension as a zip with one top-level folder to pick in chrome://extensions."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for pattern in _EXTENSION_FILES:
            for path in sorted(root.glob(pattern)):
                archive.write(
                    path, f"clawksis-mi-chrome/{path.relative_to(root).as_posix()}"
                )
    return buffer.getvalue()


@router.get("/api/my-chrome/extension.zip")
async def download_extension() -> Response:
    if not (EXTENSION_DIR / "manifest.json").is_file():
        raise HTTPException(
            status_code=404,
            detail="This install does not include the Mi Chrome extension (apps/chrome-extension).",
        )
    payload = await asyncio.to_thread(extension_zip)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="clawksis-mi-chrome.zip"'
        },
    )
