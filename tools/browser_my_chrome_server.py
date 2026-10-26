"""Loopback CDP endpoint for a "Mi Chrome" relay (``tools/browser_my_chrome_relay.py``).

Serves what agent browser drivers expect from a Chrome started with ``--remote-debugging-port``,
bound to 127.0.0.1 only and behind an unguessable path segment: the user's real Chrome (their
logins, their tabs) must not be one port scan away for other local users or a page in a browser.

- ``ws://127.0.0.1:<port>/devtools/browser/<secret>`` — browser-level CDP;
- ``http://127.0.0.1:<port>/<secret>/json/version`` and ``/json/list`` — discovery, so the
  HTTP root ``http://127.0.0.1:<port>/<secret>`` also works as a CDP URL.

The dashboard live view connects with ``?viewer=1``: it only watches, so its traffic does not
count as the agent using the user's Chrome (:meth:`MyChromeRelay.agent_active`).

A request carrying an ``Origin`` header (a web page) or a foreign ``Host`` (DNS rebinding) is
refused, as Chrome itself does without ``--remote-allow-origins``.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import secrets
from http import HTTPStatus
from typing import Any, Optional

from tools.browser_my_chrome_relay import MyChromeRelay, RelayClient

logger = logging.getLogger(__name__)


class LoopbackCdpServer:
    """One relay's loopback endpoint; :meth:`start` returns its WebSocket URL."""

    def __init__(self, relay: MyChromeRelay):
        self.relay = relay
        self.secret = secrets.token_urlsafe(24)
        self.port = 0
        self._server: Any = None
        self._tasks: set[asyncio.Task] = set()

    @property
    def ws_url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/devtools/browser/{self.secret}"

    async def start(self) -> str:
        from websockets.asyncio.server import serve

        self._server = await serve(
            self._serve_client,
            "127.0.0.1",
            0,
            process_request=self._process_request,
            max_size=None,
            close_timeout=2,  # a driver that never answers the close must not hold the shutdown
        )
        self.port = self._server.sockets[0].getsockname()[1]
        return self.ws_url

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # ── HTTP side ───────────────────────────────────────────────────────────

    def _secret_matches(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate.encode(), self.secret.encode())

    def _route(self, path: str) -> Optional[str]:
        """``"ws"``, ``"version"``, ``"list"`` for an authorized path, else None."""
        parts = path.split("?", 1)[0].strip("/").split("/")
        if (
            len(parts) == 3
            and parts[:2] == ["devtools", "browser"]
            and self._secret_matches(parts[2])
        ):
            return "ws"
        if len(parts) >= 2 and self._secret_matches(parts[0]) and parts[1] == "json":
            return {"version": "version", "list": "list", "": "list"}.get(
                parts[2] if len(parts) > 2 else ""
            )
        return None

    def _json_response(self, connection, payload: Any):
        response = connection.respond(HTTPStatus.OK, json.dumps(payload))
        del response.headers["Content-Type"]
        response.headers["Content-Type"] = "application/json; charset=UTF-8"
        return response

    def _version(self) -> dict:
        return {
            "Browser": self.relay.product,
            "Protocol-Version": "1.3",
            "User-Agent": self.relay.user_agent,
            "V8-Version": "",
            "WebKit-Version": "",
            "webSocketDebuggerUrl": self.ws_url,
        }

    def _process_request(self, connection, request):
        allowed_hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        if (
            request.headers.get("Origin")
            or request.headers.get("Host") not in allowed_hosts
        ):
            return connection.respond(HTTPStatus.FORBIDDEN, "Forbidden\n")
        route = self._route(request.path)
        if route == "ws":
            return None
        if route == "version":
            return self._json_response(connection, self._version())
        if route == "list":
            targets = [
                {
                    **self.relay.target_info(t),
                    "id": t.target_id,
                    "devtoolsFrontendUrl": "",
                }
                for t in self.relay.ordered_targets()
            ]
            return self._json_response(connection, targets)
        return connection.respond(HTTPStatus.NOT_FOUND, "Not Found\n")

    # ── WebSocket side ──────────────────────────────────────────────────────

    async def _serve_client(self, connection) -> None:
        from websockets.exceptions import ConnectionClosed

        query = connection.request.path.partition("?")[2]
        client = self.relay.add_client(viewer="viewer=1" in query.split("&"))
        writer = asyncio.create_task(self._pump(connection, client))
        try:
            with contextlib.suppress(ConnectionClosed):
                async for raw in connection:
                    self._dispatch(client, raw)
        finally:
            writer.cancel()
            await self.relay.remove_client(client)

    def _dispatch(self, client: RelayClient, raw: Any) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            return
        if not isinstance(message, dict) or "id" not in message:
            return
        task = asyncio.create_task(self.relay.handle_client_message(client, message))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _pump(self, connection, client: RelayClient) -> None:
        from websockets.exceptions import ConnectionClosed

        with contextlib.suppress(ConnectionClosed):
            while True:
                message = await client.outbox.get()
                if message is None:  # the extension went away
                    await connection.close(1001, "Mi Chrome disconnected")
                    return
                await connection.send(json.dumps(message))
