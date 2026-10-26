"""Clawksis — Web UI server: FastAPI app assembly, auth/host middleware, ``start_server``.

Route handlers live in ``web_routers/``; their helpers live in the sibling
``web_server_<concern>`` modules and are re-imported here so ``web_server.<name>``
stays the single late-binding seam tests monkeypatch (``web_deps.late``).
Usage: ``python -m clawk_cli.main web [--port 8080]``.
"""

from contextlib import asynccontextmanager

import asyncio
from collections import deque
import hmac
import logging
import os
import re
import secrets
import subprocess
import sys
import sysconfig
import threading
import time
import urllib.parse

from clawk_cli.install_identity import get_install_id as _shared_get_install_id
from clawk_cli.process_identity import is_desktop_owned_backend
from clawk_cli.pty_session import run_reaper
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clawk_cli.config import get_clawk_home, load_config
from clawk_cli.version_info import get_version_info

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.gzip import GZipMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from pydantic import BaseModel
except ImportError:
    # First try lazy-installing the dashboard extras. Only the user actually
    # running `clawk dashboard` needs fastapi+uvicorn; lazy install keeps
    # them out of every other install path. After install, re-import.
    try:
        from pm import ensure_import

        ensure_import("web")
        from fastapi import (
            FastAPI,
            HTTPException,
            Request,
        )
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.middleware.gzip import GZipMiddleware
        from fastapi.responses import FileResponse, JSONResponse
        from pydantic import BaseModel
    except Exception:
        raise SystemExit(
            "Web UI requires fastapi and uvicorn.\n"
            "Run clawk pm repair, then restart Clawksis."
        )

WEB_DIST = (
    Path(os.environ["CLAWK_WEB_DIST"])
    if "CLAWK_WEB_DIST" in os.environ
    else Path(__file__).parent / "web_dist"
)
_log = logging.getLogger(__name__)


from clawk_cli.web_server_lifecycle import (
    PORT_IN_USE_EXIT_CODE,
    _dashboard_forwarded_allow_ips,
    _eager_reconcile_own_session_db,
    _maybe_open_browser,
    _port_bind_conflict,
    _read_bound_port,
    _report_port_in_use,
    _start_parent_death_watchdog,
    _uvicorn_console_logging,
    _warm_gateway_module,
    _write_dashboard_ready_file,
    _write_machine_sentinel_line,
)


def _gateway_owns_cron(name: str, home) -> bool:
    """A gateway already ticks this profile's store with live adapters: its OWN process, or the
    live default multiplexer (a served satellite has no gateway.pid of its own). Winning the
    tick-lock race here would deliver through the standalone path (#52202, #100489, #107485)."""
    from clawk_cli.profiles import (
        _check_gateway_running,
        _served_by_running_multiplexer,
    )

    return _check_gateway_running(Path(home)) or (
        name != "default" and _served_by_running_multiplexer(name)
    )


def _start_desktop_cron_ticker(stop_event: threading.Event, interval: int = 60) -> None:
    """Tick the cron scheduler from inside the desktop dashboard backend.

    The desktop spawns a ``clawk dashboard`` backend, not a gateway, so without
    this a cron created in the app would never fire (no live adapters; delivery
    falls back to the per-platform send path). The primary backend outlives the
    per-profile pool (reaped after ~10 idle minutes), so it ticks EVERY local
    profile's store like a multiplex gateway; external providers keep the
    single-store behavior (registries are not profile-scoped). Cross-process
    safe: the built-in tick takes the per-store ``cron/.tick.lock``.

    Every local profile's store is ticked, not just this backend's own (#69377's desktop sibling): the
    desktop pools per-profile backends and reaps them after ~10 idle minutes, so a secondary profile's
    ticker dies with its backend and that profile's jobs silently stop firing until the user next opens it
    ("tasks on the sleeping profile could be idle" — community report, Aug 2026).
    """
    from cron.scheduler_provider import InProcessCronScheduler, resolve_cron_scheduler
    from clawk_constants import get_clawk_home, profile_name_for_home

    provider = resolve_cron_scheduler()
    own_home = Path(get_clawk_home())
    own_name = profile_name_for_home(own_home) or "default"
    # Ownership is re-checked every tick, not once at startup, so Desktop takes over when the
    # gateway stops (#126822).
    profile_gate = lambda name, home: not _gateway_owns_cron(name, home)

    start_kwargs: dict = {"interval": interval}
    if isinstance(provider, InProcessCronScheduler):
        try:
            from clawk_cli.profiles import profiles_to_serve

            # Same served set as the multiplexer: default + every live profile under profiles/.
            # The ticker re-enumerates this callable every cycle. Passing a
            # startup snapshot leaves deleted profiles in the scheduler until
            # restart, which both writes their removed stores and keeps stale
            # profiles alive in Desktop's background work.
            profile_homes = lambda: list(profiles_to_serve(multiplex=True))
            initial_profile_homes = profile_homes()
            if initial_profile_homes:
                # Even one profile needs the per-tick gateway gate; otherwise
                # Desktop races its dedicated gateway for the same cron store.
                start_kwargs["profile_homes"] = profile_homes
                start_kwargs["profile_gate"] = profile_gate
                from clawk_logging import enable_profile_log_routing

                enable_profile_log_routing(initial_profile_homes)
                _log.info(
                    "Desktop cron scheduler will tick %d profile(s): %s",
                    len(initial_profile_homes),
                    [name for name, _home in initial_profile_homes],
                )
        except Exception:
            # Fail open to the single-store ticker so the active profile keeps firing.
            _log.exception(
                "Desktop cron: profile enumeration failed; ticking active profile only"
            )
        if "profile_homes" not in start_kwargs:
            # Fail open to this backend's own store behind the same gate. A gated-out profile is
            # neither ticked nor heartbeated, so Desktop never marks the gateway's store healthy.
            start_kwargs["profile_homes"] = lambda: [(own_name, own_home)]
            start_kwargs["profile_gate"] = profile_gate
    else:
        # External providers take no per-tick gate: defer their start until the gateway is gone.
        def _owned() -> bool:
            try:
                return _gateway_owns_cron(own_name, own_home)
            except Exception:
                # Start the ticker rather than silently stand down.
                _log.warning(
                    "Desktop cron: gateway-ownership probe failed; starting the ticker",
                    exc_info=True,
                )
                return False

        if _owned():
            _log.info(
                "Desktop cron scheduler waiting: live gateway owns cron on this CLAWK_HOME; "
                "the gateway ticks with live adapters (re-probing every %ds)",
                interval,
            )
            while True:
                if stop_event.wait(interval):
                    return
                if not _owned():
                    break

    _log.info(
        "Desktop cron scheduler started (provider=%s, interval=%ds)",
        provider.name,
        interval,
    )
    provider.start(stop_event, **start_kwargs)


# Desktop `serve` only (start_server(start_mcp_discovery_after_bind=True)):
# seconds after the READY sentinel before the MCP discovery thread starts.
_DESKTOP_MCP_DISCOVERY_DELAY_S = 1.0


from clawk_cli.web_server_app import app_lifespan


def _app_state_default(app: FastAPI, name: str, factory):
    """Return ``app.state.<name>``, lazily creating it for non-``with`` TestClient usages.

    The lifespan normally initialises these on the running event loop (an
    asyncio.Lock created at import time binds to whatever loop was active then).
    """
    try:
        return getattr(app.state, name)
    except AttributeError:
        value = factory()
        setattr(app.state, name, value)
        return value


def _get_chat_argv_lock(app: FastAPI) -> asyncio.Lock:
    return _app_state_default(app, "chat_argv_lock", asyncio.Lock)


def _get_pty_active_session_files(app: FastAPI) -> dict[str, Path]:
    return _app_state_default(app, "pty_active_session_files", dict)


app = FastAPI(
    title="Clawksis", version=get_version_info().base_version, lifespan=app_lifespan
)

from clawk_cli.dashboard_auth.body_limit import AuthBodyLimitMiddleware

# Register first (innermost): auth gates run before this, JSON parsing after it.
app.add_middleware(AuthBodyLimitMiddleware)


# Memory-provider OAuth connect routes live in the memory layer, not here.
from clawk_cli.memory_oauth import router as _memory_oauth_router

app.include_router(_memory_oauth_router)


# Session token for sensitive endpoints. The desktop shell mints it via
# CLAWK_DASHBOARD_SESSION_TOKEN; otherwise fresh per server start. It dies with
# the process and is injected into the SPA HTML so only the web UI can use it.
def _resolve_session_token() -> str:
    return os.environ.get("CLAWK_DASHBOARD_SESSION_TOKEN") or secrets.token_urlsafe(32)


_SESSION_TOKEN = _resolve_session_token()
_SESSION_HEADER_NAME = "X-Clawksis-Session-Token"
_SSH_OWNER_NONCE: Optional[str] = None
_SSH_RUNTIME_PURELIB: Optional[tuple[str, int, int]] = None
_SSH_RUNTIME_MARKER: Optional[str] = None


def _apply_ssh_session_token(token: str) -> None:
    global _SESSION_TOKEN
    if token:
        _SESSION_TOKEN = token


def _apply_ssh_owner_nonce(nonce: Optional[str]) -> None:
    global _SSH_OWNER_NONCE, _SSH_RUNTIME_PURELIB, _SSH_RUNTIME_MARKER
    _SSH_OWNER_NONCE = nonce
    _SSH_RUNTIME_PURELIB = None
    _SSH_RUNTIME_MARKER = None
    if nonce:
        try:
            purelib = sysconfig.get_paths()["purelib"]
        except (KeyError, OSError):
            return
        # Primary identity: a marker FILE in site-packages. A replaced venv
        # loses it deterministically; pip installs leave it. A bare (dev, ino)
        # snapshot alone is NOT enough: ext4 reuses directory inodes at once,
        # so `rm -rf venv && uv venv` can land on the same inode undetected.
        try:
            marker = os.path.join(purelib, f".clawk-ssh-runtime-{nonce}")
            with open(marker, "w", encoding="utf-8") as fh:
                fh.write(f"pid={os.getpid()}\n")
            _SSH_RUNTIME_MARKER = marker
        except OSError:
            pass  # read-only site-packages — fall back to the stat snapshot
        try:
            st = os.stat(purelib)
            _SSH_RUNTIME_PURELIB = (purelib, st.st_dev, st.st_ino)
        except OSError:
            pass


def _ssh_runtime_intact() -> bool:
    if _SSH_RUNTIME_MARKER is not None:
        return os.path.isfile(_SSH_RUNTIME_MARKER)
    # Fallback (read-only site-packages): directory identity snapshot — weaker
    # (inode reuse) but catches cross-device moves and version-bump paths.
    if _SSH_RUNTIME_PURELIB is None:
        return True
    purelib, device, inode = _SSH_RUNTIME_PURELIB
    try:
        st = os.stat(purelib)
    except OSError:
        return False
    return (st.st_dev, st.st_ino) == (device, inode)


# In-browser Chat tab (/chat, /api/pty, /api/ws): always enabled. A module
# constant (not an inlined True) so the WS endpoints and SPA token injection
# share one testable seam.
_DASHBOARD_EMBEDDED_CHAT_ENABLED = True

# Endpoints that do NOT require the session token; everything else under /api/
# is gated below. Shared with the OAuth gate so the two allowlists cannot
# drift (/api/status once 401'd under the OAuth gate, breaking the portal probe).
from clawk_cli.dashboard_auth.public_paths import PUBLIC_API_PATHS as _PUBLIC_API_PATHS


def _has_valid_session_token(request: Request) -> bool:
    """True if the request carries a valid dashboard session token.

    The dedicated header avoids collisions with reverse proxies that already use
    ``Authorization`` (Caddy ``basic_auth``); the legacy Bearer path stays for
    older dashboard bundles.
    """
    session_header = request.headers.get(_SESSION_HEADER_NAME, "")
    if session_header and hmac.compare_digest(
        session_header.encode(), _SESSION_TOKEN.encode()
    ):
        return True
    auth = request.headers.get("authorization", "")
    return hmac.compare_digest(auth.encode(), f"Bearer {_SESSION_TOKEN}".encode())


# Routes that may also authenticate via ``?token=`` (download links opened by
# the OS shell / a new tab, where no header can be set). Kept narrow.
_QUERY_TOKEN_API_PATHS: frozenset[str] = frozenset({"/api/files/download"})


def _has_valid_query_token(request: Request, path: str) -> bool:
    if path not in _QUERY_TOKEN_API_PATHS:
        return False
    token = request.query_params.get("token", "")
    return bool(token) and hmac.compare_digest(token.encode(), _SESSION_TOKEN.encode())


def _require_token(request: Request) -> None:
    """Authorize a sensitive endpoint, raising 401 if the caller isn't allowed.

    Loopback mode (``auth_required`` False): validate the SPA-injected
    ``_SESSION_TOKEN``. Gated mode: the token is NOT injected (cookie auth), and
    ``gated_auth_middleware`` already 401'd anything without a verified
    ``request.state.session`` — requiring the absent token here would make every
    ``_require_token`` endpoint unreachable behind the gate, so defer to it.
    A verified native owner (``authenticate_native_http``) is the same-user
    principal the outer seams already accepted; local Desktop runs with no
    static token, so that principal must satisfy route-local policy too.
    Hosted plugins receive this guard's decision via private IPC and request-local
    state, not via a forwarded gateway credential or a process-wide bypass.
    """
    if (
        getattr(request.state, "native_http_principal", None)
        or getattr(request.state, "hosted_http_authenticated", None) is True
    ):
        return
    if getattr(request.app.state, "auth_required", False):
        ok = getattr(request.state, "session", None) is not None
    else:
        ok = _has_valid_session_token(request)
    if not ok:
        raise HTTPException(status_code=401, detail="Unauthorized")


from clawk_cli.web_server_boundary import (  # re-exported: web_server.<name> stays the public seam
    _DESKTOP_ATTACHMENT_WS_MAX_BYTES,
    _LOOPBACK_HOST_VALUES,
    _dashboard_public_hosts,
    _desktop_loopback_auth_exempt,
    _host_header_hostname,
    _is_accepted_host,
    public_hosts_engage_gate,
    should_require_auth,
)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _public_proxy_hosts() -> frozenset[str]:
    """Hostnames extra aceptados en el Host header (modo reverse-proxy).

    ``CLAWK_DASHBOARD_PUBLIC_HOST`` — lista separada por comas de dominios por
    los que un proxy local (Caddy) publica el dashboard; los setea la unit que
    escribe ``clawk dashboard domain``. Se suman a ``trusted_public_hosts`` (como
    ``dashboard.public_url``), así el anti-rebinding sigue activo para el resto
    y un dominio público engancha el auth gate aunque el bind sea loopback.
    """
    raw = os.environ.get("CLAWK_DASHBOARD_PUBLIC_HOST", "")
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def _resolve_trusted_public_hosts() -> frozenset[str]:
    """``dashboard.public_url`` host plus the ``clawk dashboard domain`` hosts."""
    return _dashboard_public_hosts() | _public_proxy_hosts()


def should_require_dashboard_auth(
    host: str,
    trusted_public_hosts: Optional[frozenset[str]] = None,
    allow_public: bool = False,
) -> bool:
    """Gate required for a non-loopback bind (without ``--insecure``) OR a non-loopback
    ``dashboard.public_url``.

    Callers may pass the already-resolved host set so startup and request
    validation share one snapshot. ``CLAWK_DASHBOARD_FORCE_GATE`` (written by
    ``clawk dashboard domain``) engages the gate even on a loopback bind: the
    dashboard listens on 127.0.0.1 but a local reverse proxy publishes it.
    ``allow_public`` (``--insecure``, the fork's escape hatch) lifts only the bind trigger.
    """
    if trusted_public_hosts is None:
        trusted_public_hosts = _resolve_trusted_public_hosts()
    if _env_truthy("CLAWK_DASHBOARD_FORCE_GATE"):
        return True
    return should_require_auth(host, allow_public) or public_hosts_engage_gate(
        trusted_public_hosts
    )


@app.middleware("http")
async def host_header_middleware(request: Request, call_next):
    """Reject requests whose Host header doesn't match the bound interface (DNS rebinding, GHSA-ppp5-vxwm-4cf7)."""
    # app.state.bound_host is set by start_server() at listen time.
    bound_host = getattr(app.state, "bound_host", None)
    if bound_host and not _is_accepted_host(
        request.headers.get("host", ""),
        bound_host,
        getattr(app.state, "trusted_public_hosts", frozenset()),
    ):
        return JSONResponse(
            status_code=400,
            content={
                "detail": (
                    "Invalid Host header. Dashboard requests must use the "
                    "bound hostname or the configured public hostname."
                ),
            },
        )
    return await call_next(request)


# Imported here, beside the plugin gates that use it, like the other mid-module web_server_*
# groups. Not an import cycle: web_server_dashboard reaches back into this module only inside
# functions, so the position is not load-bearing. What is load-bearing is the middleware
# registration order below (the HTTP gate before the auth middlewares, so it runs after them).
from clawk_cli.web_server_dashboard import (
    PluginApiWebSocketGate,
    _plugin_api_name,
    _plugin_api_request_refused,
)
from clawk_cli.web_server_plugin_profiles import (
    forward_secondary_plugin_request,
    plugin_request_scope,
)


@app.middleware("http")
async def _plugin_api_runtime_gate(request: Request, call_next):
    """Block requests to disabled plugin API routes at request time
    (:func:`_plugin_api_request_refused`).

    Registered BEFORE the auth middlewares (runs AFTER them): an unauthenticated
    caller must get auth's 401, never this 404, or the status code becomes a
    plugin-name oracle.
    """
    path = request.url.path
    plugin_name = _plugin_api_name(request.scope)
    # Only gate authenticated requests. Unauthenticated ones fall through so
    # auth_middleware / the OAuth gate return 401 first and this route can't
    # be used as a plugin-name oracle. Desktop authenticates with a native ticket.
    if plugin_name and (
        getattr(request.state, "token_authenticated", False)
        or getattr(request.state, "native_http_principal", None)
        or getattr(request.app.state, "auth_required", False)
        or _has_valid_session_token(request)
        or _has_valid_query_token(request, path)
    ):
        with plugin_request_scope(
            request.scope
        ):  # a secondary profile's plugins run in its host
            if await _plugin_api_request_refused(plugin_name):
                return JSONResponse(
                    status_code=404, content={"detail": "Plugin not found"}
                )
            hosted = await forward_secondary_plugin_request(request, plugin_name)
        if hosted is not None:
            return hosted
    return await call_next(request)


# The same gate for WebSocket upgrades: ``@app.middleware("http")`` passes those through untouched.
app.add_middleware(PluginApiWebSocketGate)


@app.middleware("http")
async def _dashboard_auth_gate(request: Request, call_next):
    """OAuth gate — active only when start_server flags ``auth_required``; pass-through on loopback.

    Registered between host_header and auth_middleware: host check → cookie auth → token auth.
    """
    from clawk_cli.dashboard_auth.middleware import gated_auth_middleware

    return await gated_auth_middleware(request, call_next)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Require the session token on all /api/ routes except the public list.

    Skipped for requests the token-auth seam already authenticated
    (``token_authenticated``) and when the OAuth gate is active — cookie auth is
    then authoritative and the loopback-only token path must not override it.
    """
    path = request.url.path
    if (
        not getattr(request.state, "token_authenticated", False)
        and not getattr(request.state, "native_http_principal", None)
        and not getattr(request.app.state, "auth_required", False)
        and path.startswith("/api/")
        and path not in _PUBLIC_API_PATHS
        and not path.startswith("/api/mcp/oauth/callback/")
        and not _has_valid_session_token(request)
        and not _has_valid_query_token(request, path)
    ):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.middleware("http")
async def _token_auth_seam(request: Request, call_next):
    """Outermost auth seam: bearer-token auth for opted-in routes (registered LAST = runs FIRST).

    A registered token route is owned here — authenticate, attach the principal
    + ``token_authenticated`` so downstream gates skip enforcement. Non-token
    routes pass through untouched.
    """
    from clawk_cli.dashboard_auth.native_http import (
        authenticate_native_http,
        native_profile_scope,
    )
    from clawk_cli.dashboard_auth.token_auth import token_auth_middleware

    rejection = await authenticate_native_http(request)
    if rejection is not None:
        return rejection
    with native_profile_scope(request):
        return await token_auth_middleware(request, call_next)


_DASHBOARD_HEALTH_WINDOW_SECONDS = 300.0


class DashboardHealth:
    """Dashboard-process health: rolling unhandled-error/5xx window + periodic self-test result.

    Feeds ``components`` on the PUBLIC ``/api/status``, so :meth:`snapshot`
    exports counts and enums only — never ``last_error_type``/``last_error_path``.
    """

    def __init__(
        self, window_seconds: float = _DASHBOARD_HEALTH_WINDOW_SECONDS
    ) -> None:
        self.window_seconds = window_seconds
        self._error_times: deque[float] = deque(maxlen=256)
        self.last_error_type: Optional[str] = None
        self.last_error_path: Optional[str] = None  # internal-only, never serialized
        self.last_error_at: Optional[float] = None
        self.selftest_status: str = "unknown"  # unknown | ok | failing
        self.selftest_http_status: Optional[int] = None
        self.selftest_at: Optional[float] = None

    def record_error(self, exc_type: str, path: str) -> None:
        now = time.time()
        self._error_times.append(now)
        self.last_error_type = exc_type
        self.last_error_path = path
        self.last_error_at = now

    def record_selftest(self, passed: bool, http_status: Optional[int]) -> None:
        self.selftest_status = "ok" if passed else "failing"
        self.selftest_http_status = http_status
        self.selftest_at = time.time()

    def recent_error_count(self) -> int:
        cutoff = time.time() - self.window_seconds
        while self._error_times and self._error_times[0] < cutoff:
            self._error_times.popleft()
        return len(self._error_times)

    def snapshot(self) -> dict[str, Any]:
        """Public component payload: status enum + counts + timestamps only."""
        errors = self.recent_error_count()
        status = "degraded" if (errors or self.selftest_status == "failing") else "ok"
        return {
            "status": status,
            "recent_unhandled_errors": errors,
            "last_error_at": self.last_error_at,
            "selftest": self.selftest_status,
        }


DASHBOARD_HEALTH = DashboardHealth()


@app.middleware("http")
async def _dashboard_health_middleware(request: Request, call_next):
    """Outermost non-CORS middleware: count unhandled exceptions and 5xx; re-raises, never alters."""
    try:
        response = await call_next(request)
    except Exception as exc:
        DASHBOARD_HEALTH.record_error(type(exc).__name__, request.url.path)
        raise
    if response.status_code >= 500:
        DASHBOARD_HEALTH.record_error(f"http_{response.status_code}", request.url.path)
    return response


@app.middleware("http")
async def _immutable_asset_cache(request: Request, call_next):
    """Mark Vite's content-hashed assets immutable so the browser stops doing a
    conditional GET + 304 for every chunk on each reload. The filename changes
    when the content changes, and index.html is forced to ``no-cache`` (always
    revalidate) so it always re-resolves the current hashes — without an
    explicit header, browsers apply heuristic caching to the SPA shell and a
    stale index keeps pointing at deleted chunks after a server-side rebuild
    (frozen navigation until a hard refresh).

    Only a fallback: a response that already chose its policy keeps it. The SPA index and the
    login page are served ``no-store`` (``web_server_dashboard._NO_STORE``,
    ``dashboard_auth.routes``), which a blanket ``no-cache`` would weaken."""
    response = await call_next(request)
    if response.status_code != 200 or "cache-control" in response.headers:
        return response
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# Gzip JS/CSS/JSON on the wire. The dashboard ships ~1MB of hashed JS/CSS per
# cold load; gzip cuts that ~3-4x (e.g. the 405KB index chunk → ~131KB),
# which dominates first-load time over a tunnel.
app.add_middleware(GZipMiddleware, minimum_size=1024)


# CORS: restrict to localhost origins only.  The web UI is intended to run
# locally; binding to 0.0.0.0 with allow_origins=["*"] would let any website
# read/modify config and secrets.
#
# Registered AFTER all ``@app.middleware("http")`` decorators so it is the
# *outermost* middleware (Starlette's onion: last-added runs first).
# Without this, an OPTIONS preflight from a cross-origin SPA hits the auth
# middlewares before CORS can answer, producing 401 instead of 204 + headers.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)


# Authenticated-route self-test: one in-process request per minute against a
# cheap DB-touching route, catching "liveness fine but every authed request 500s".
_DASHBOARD_SELFTEST_INTERVAL_SECONDS = 60.0
_DASHBOARD_SELFTEST_ROUTE = "/api/sessions?limit=1"


async def _dashboard_selftest_once() -> None:
    """Run one authenticated in-process self-test request and record it."""
    try:
        import httpx
    except ImportError:
        return  # optional dependency — leave status "unknown"
    try:
        # Loopback base_url so the Host-header middleware accepts the request.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            resp = await client.get(
                _DASHBOARD_SELFTEST_ROUTE,
                headers={_SESSION_HEADER_NAME: _SESSION_TOKEN},
            )
        DASHBOARD_HEALTH.record_selftest(resp.status_code == 200, resp.status_code)
    except Exception:
        DASHBOARD_HEALTH.record_selftest(False, None)


async def _dashboard_selftest_loop() -> None:
    """Periodic self-test driver started from the lifespan."""
    try:
        import httpx
    except ImportError:
        _log.debug("httpx unavailable — dashboard self-test disabled")
        return
    while True:
        await asyncio.sleep(_DASHBOARD_SELFTEST_INTERVAL_SECONDS)
        # OAuth-gated binds don't honour the session token; the probe would false-alarm 401.
        if getattr(app.state, "auth_required", False):
            continue
        await _dashboard_selftest_once()


# Action registries/spawner are owned by web_server_gateway; routers and tests reach them
# there, so this module reads them through the module too (one patch seam).
from clawk_cli import web_server_gateway as _gateway_mod
from clawk_cli.web_server_gateway import (
    _ACTION_LOG_FILES,
    _terminate_desktop_managed_gateway,
)
from clawk_cli.web_server_sessions import _auto_archive_ticker_loop
from clawk_cli.web_server_chat import PTY_REGISTRY
from clawk_cli.web_server_dashboard import (
    _discover_dashboard_plugins,
    _mount_plugin_api_routes,
    mount_spa,
)


_GATEWAY_HEALTH_URL = os.getenv("GATEWAY_HEALTH_URL")
_GATEWAY_HEALTH_TIMEOUT_MAX = 1.0
try:
    _GATEWAY_HEALTH_TIMEOUT = float(os.getenv("GATEWAY_HEALTH_TIMEOUT", "1"))
except (ValueError, TypeError):
    _log.warning(
        "Invalid GATEWAY_HEALTH_TIMEOUT value %r — using default 1.0s",
        os.getenv("GATEWAY_HEALTH_TIMEOUT"),
    )
    _GATEWAY_HEALTH_TIMEOUT = 1.0
if _GATEWAY_HEALTH_TIMEOUT <= 0:
    _log.warning(
        "Invalid non-positive GATEWAY_HEALTH_TIMEOUT value %.3fs — using default 1.0s",
        _GATEWAY_HEALTH_TIMEOUT,
    )
    _GATEWAY_HEALTH_TIMEOUT = 1.0
elif _GATEWAY_HEALTH_TIMEOUT > _GATEWAY_HEALTH_TIMEOUT_MAX:
    _log.warning(
        "Capping GATEWAY_HEALTH_TIMEOUT %.3fs to %.3fs for dashboard liveness probes",
        _GATEWAY_HEALTH_TIMEOUT,
        _GATEWAY_HEALTH_TIMEOUT_MAX,
    )
    _GATEWAY_HEALTH_TIMEOUT = _GATEWAY_HEALTH_TIMEOUT_MAX


_MANAGED_FILE_MAX_BYTES = 100 * 1024 * 1024
_FS_DATA_URL_MAX_BYTES = 16 * 1024 * 1024
# Multipart uploads stream to a temp file in fixed chunks and rename into
# place: constant memory, no base64 inflation, no proxy body-size 502s (NS-501).
_UPLOAD_CHUNK_BYTES = 1024 * 1024

# Stable install identity for /api/status: one uuid4 hex per physical install,
# persisted under the ROOT Clawksis home (not the profile CLAWK_HOME) so every
# profile reports the same id and the desktop can collapse duplicate roster rows
# for one backend. Must never change across restarts, so cached per process.
_INSTALL_ID_CACHE: dict[str, Optional[str]] = {"root": None, "value": None}


def get_install_id() -> Optional[str]:
    """Process-lifetime-cached stable install id."""
    return _shared_get_install_id(cache=_INSTALL_ID_CACHE)


# Serializes config.yaml read-modify-write cycles for handlers on worker threads
# (asyncio.to_thread): config.py's _CONFIG_LOCK covers each load/save call, not
# the span between them, so two off-loop updates could drop each other's writes.
# RLock so nested helpers that also take it can't self-deadlock.
_CONFIG_MUTATION_LOCK = threading.RLock()

# A finished ``gateway-restart`` child does not mean the gateway is back (it
# exits once the restart is handed off), so in-flight reuse stops coalescing
# exactly when a stale frontend re-fires every few seconds (#89034: 77 restarts,
# state.db corrupted mid-FTS5-write). MAINTAINER DECISION: a fixed window, not
# "until healthy" — a gateway that never returns must not leave the action
# inert. 10s is above the ~3.5s storm spacing and below an operator's retry.
GATEWAY_RESTART_COOLDOWN_SECONDS = 10.0

# ``(monotonic spawn time, Popen, command)`` of the last restart. Deliberately
# NOT read from ``_ACTION_PROCS``: entries there vanish when the child exits.
_LAST_GATEWAY_RESTART: Optional[tuple[float, subprocess.Popen, tuple[str, ...]]] = None


def _spawn_gateway_restart(
    profile: Optional[str] = None, *, interrupt: bool = False
) -> tuple[subprocess.Popen, bool]:
    """Spawn ``clawk gateway restart``, reusing an in-flight or recent restart.

    Concurrent children race each other on the kill-and-start path, so a live
    child is reused; requests within ``GATEWAY_RESTART_COOLDOWN_SECONDS`` for the
    same profile coalesce onto the last spawn too (#89034). This process stops
    nothing itself: the child decides whether the restart is even allowed
    (``_cmd_restart``'s multiplexer guard), so the orphan reap (#77276) runs
    there, after that guard — reaping here killed the profile's gateway and then
    the child refused to start a replacement (#125394). Returns ``(proc, reused)``.
    """
    global _LAST_GATEWAY_RESTART

    # ``interrupt``: ``POST /api/gateway/restart`` is the user-commanded force path that supersedes a
    # drain (D6 of the safe-shutdown plan, 19b26244046); a config-save auto-restart is not, and its
    # child refuses while sessions are live.
    subcommand = (
        _gateway_mod._gateway_subcommand(profile, "restart")
        + ["--interrupt"] * interrupt
    )
    existing = _gateway_mod._ACTION_PROCS.get("gateway-restart")
    if existing is not None and existing.poll() is None:
        existing_command = _gateway_mod._ACTION_COMMANDS.get("gateway-restart")
        if existing_command is None or existing_command == tuple(subcommand):
            return existing, True
        raise RuntimeError("gateway restart already in progress for another profile")

    recent = _LAST_GATEWAY_RESTART
    if recent is not None:
        spawned_at, recent_proc, recent_command = recent
        age = (
            time.monotonic() - spawned_at
            if recent_command == tuple(subcommand)
            else None
        )
        if age is not None and age < GATEWAY_RESTART_COOLDOWN_SECONDS:
            _log.info(
                "Coalescing gateway restart: one was started %.1fs ago "
                "(pid %s) and the gateway may still be coming back; not "
                "spawning another (#89034).",
                age,
                getattr(recent_proc, "pid", "?"),
            )
            return recent_proc, True

    proc = _gateway_mod._spawn_clawk_action(subcommand, "gateway-restart")
    _LAST_GATEWAY_RESTART = (time.monotonic(), proc, tuple(subcommand))
    return proc, False


# Collapses repeated identical ElevenLabs voice-list failures (the desktop
# re-polls on every settings focus) to one log line; re-arms on success or a
# changed signature.
_voice_list_last_error: Optional[str] = None


def _voice_list_error_logged_once(signature: Optional[str]) -> bool:
    """True if ``signature`` is new and should be logged now; ``None`` clears the latch."""
    global _voice_list_last_error
    if signature is None:
        _voice_list_last_error = None
        return False
    if signature == _voice_list_last_error:
        return False
    _voice_list_last_error = signature
    return True


_ACTION_LOG_FILES.setdefault("computer-use-grant", "action-computer-use-grant.log")

# Cache discovered plugins per-process (refresh on explicit re-scan).
_dashboard_plugins_cache: Optional[list] = None


def _get_dashboard_plugins(force_rescan: bool = False) -> list:
    """The active scope's dashboard plugins: a secondary profile's are its own (PLG-3)."""
    global _dashboard_plugins_cache
    from clawk_cli.web_server_plugin_profiles import (
        profile_dashboard_plugins,
        secondary_profile_home,
    )

    home = secondary_profile_home()
    if home is not None:
        return profile_dashboard_plugins(home, force_rescan)
    stale = (
        _dashboard_plugins_cache is None
        or force_rescan
        or any(not Path(p["_dir"]).is_dir() for p in _dashboard_plugins_cache)
    )
    if stale:
        _dashboard_plugins_cache = _discover_dashboard_plugins()
    return _dashboard_plugins_cache


# ===========================================================================
# Clawksis dashboard routes (fork-only). Registered HERE — before the
# ``web_routers`` mounting below — so their literal paths win over templated
# upstream siblings (e.g. GET /api/sessions/running before
# /api/sessions/{session_id}) and nothing lands behind the SPA catch-all.
# ===========================================================================


# ---------------------------------------------------------------------------
# Media gallery — serve locally cached files from ~/.clawksis/media/
# ---------------------------------------------------------------------------
#
# Companion to the media_generations table (populated by
# tools/media_persistence.py). The DB stores absolute file_path; this
# endpoint validates and serves it with correct MIME type.
#
# This route intentionally lives outside /api/ (mirrors /artifacts/download):
# direct <img src="/media/file/xxx"> in the React gallery cannot attach the
# session token header. Security is kept by strict loopback-only access and
# a narrow allowlist of the media root + extensions.
# ---------------------------------------------------------------------------


_MEDIA_ALLOWED_EXT_TO_MIME: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}


@app.get("/media/file/{media_id}")
async def get_media_file(media_id: str, request: Request):
    """Serve a media file registered in media_generations by ID.

    Security model (mirrors /artifacts/download):
    - loopback / SSH-tunnel only
    - file_path comes from the DB (not user-controllable directly)
    - path validated to be inside ~/.clawksis/media/
    - only allowed extensions are served (image/video MIME)
    - symlinks resolved before allowlist check
    """
    import sqlite3
    from pathlib import Path

    if not _artifact_is_loopback_request(request):
        raise HTTPException(
            status_code=403,
            detail="Media files are only available from local or SSH-tunnel dashboard access.",
        )

    if not media_id or len(media_id) > 128 or "/" in media_id or ".." in media_id:
        raise HTTPException(status_code=400, detail="Invalid media id.")

    db_path = Path.home() / ".clawksis" / "state.db"
    if not db_path.exists():
        raise HTTPException(status_code=503, detail="State DB unavailable.")

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT file_path, media_type, status FROM media_generations WHERE id = ?",
            (media_id,),
        )
        row = cur.fetchone()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    if not row:
        raise HTTPException(status_code=404, detail="Media not found.")

    file_path_str, _media_type, status = row

    if status == "expired":
        raise HTTPException(status_code=410, detail="Media URL expired before caching.")

    if status != "ready":
        raise HTTPException(
            status_code=409, detail=f"Media not ready (status={status})."
        )

    media_root = (Path.home() / ".clawksis" / "media").resolve(strict=False)
    candidate = Path(file_path_str).expanduser().resolve(strict=False)

    # register_media descarga a ~/.clawksis/media/, pero register_local_media
    # registra archivos in-place (cache/images de image_gen, audio_cache de
    # TTS, artifacts) — mismos roots que sirve /media/local.
    allowed_roots = [media_root, *_local_media_allowed_roots()]
    if not any(_artifact_is_within_root(candidate, root) for root in allowed_roots):
        raise HTTPException(
            status_code=403,
            detail="Media file is outside the allowed media directory.",
        )

    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Media file missing on disk.")

    if not candidate.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file.")

    ext = candidate.suffix.lower()
    # El mapa extendido cubre también audio (TTS en audio_cache).
    mime = _MEDIA_ALLOWED_EXT_TO_MIME.get(ext) or _LOCAL_MEDIA_EXT_TO_MIME.get(ext)
    if not mime:
        raise HTTPException(status_code=400, detail=f"Extension not allowed: {ext}")

    return FileResponse(
        str(candidate),
        media_type=mime,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{candidate.name}"',
        },
    )


# ---------------------------------------------------------------------------
# Local media bridge — el agente referencia archivos locales en sus respuestas
# (líneas "MEDIA:/root/.clawksis/audio_cache/briefing_x.ogg" de TTS y markdown
# ![](/root/.clawksis/cache/images/x.png)). El chat Modern reescribe esas
# referencias a GET /media/local?path=… y este endpoint las sirve.
#
# Security model (espejo de /media/file y /artifacts/download):
# - loopback / SSH-tunnel only; con el OAuth gate activo la cookie de sesión
#   sigue aplicando (la ruta NO está en _GATE_PUBLIC_PREFIXES a propósito);
# - symlinks resueltos ANTES del chequeo de allowlist (sin escape vía link);
# - traversal (..) neutralizado por resolve();
# - SOLO archivos bajo ~/.clawksis/{audio_cache, cache/images, artifacts};
# - solo extensiones allowlisted, MIME inferido del mapa (sin .svg: servirlo
#   inline same-origin permitiría XSS).
# Vive fuera de /api/ porque <img src>/<audio src> no pueden adjuntar el
# session token header.
# ---------------------------------------------------------------------------


_LOCAL_MEDIA_EXT_TO_MIME: dict[str, str] = {
    # audio (TTS briefings, notas de voz)
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/opus",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    # imágenes
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
    # video
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
    ".ogv": "video/ogg",
}


def _local_media_allowed_roots() -> "list[Path]":
    """Roots servibles por /media/local (resueltos para comparar post-symlink)."""
    home = get_clawk_home()
    return [
        (home / "audio_cache").resolve(strict=False),
        (home / "cache" / "images").resolve(strict=False),
        (home / "artifacts").resolve(strict=False),
    ]


@app.get("/media/local")
async def get_local_media(path: str, request: Request):
    """Serve a local media file referenced by the agent, by absolute path.

    Security model (mirrors /media/file and /artifacts/download):
    - loopback / SSH-tunnel only;
    - symlinks resolved BEFORE the allowlist check;
    - only files under ~/.clawksis/{audio_cache, cache/images, artifacts};
    - only allowlisted media extensions (MIME inferred from the map).
    """
    from pathlib import Path
    from urllib.parse import unquote

    if not _artifact_is_loopback_request(request):
        raise HTTPException(
            status_code=403,
            detail="Local media is only available from local or SSH-tunnel dashboard access.",
        )

    raw_path = unquote(str(path or "")).strip()
    raw_path = raw_path.removeprefix("file://")
    if not raw_path:
        raise HTTPException(status_code=400, detail="Missing media path.")

    # resolve() colapsa ".." y resuelve symlinks ANTES del chequeo de roots.
    candidate = Path(raw_path).expanduser().resolve(strict=False)

    if not any(
        _artifact_is_within_root(candidate, root)
        for root in _local_media_allowed_roots()
    ):
        raise HTTPException(
            status_code=403,
            detail="Media path is outside the allowed local media directories.",
        )

    ext = candidate.suffix.lower()
    local_mime = _LOCAL_MEDIA_EXT_TO_MIME.get(ext)
    if not local_mime:
        raise HTTPException(
            status_code=400, detail=f"Extension not allowed: {ext or '(none)'}"
        )

    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Media file not found.")

    if not candidate.is_file():
        raise HTTPException(status_code=400, detail="Media path is not a file.")

    return FileResponse(
        str(candidate),
        media_type=local_mime,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{candidate.name}"',
        },
    )


# REST endpoints for the gallery UI (consumed by MediaPage.tsx).
# Path: /api/gallery (NOT /api/media — that's taken by the equipo's endpoint
# that serves images from cache/screenshots as base64 data URLs).
# These live under /api/ so the auth middleware protects them like other
# dashboard data endpoints. The file-serving endpoint above is outside /api/
# because <img src="..."> can't attach the session token.


@app.get("/api/gallery")
async def get_media_list(
    limit: int = 60,
    offset: int = 0,
    media_type: Optional[str] = None,
    date_from: Optional[float] = None,
    date_to: Optional[float] = None,
    model: Optional[str] = None,
    session_id: Optional[str] = None,
    search: Optional[str] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
):
    """List media with filters + pagination.

    All filters are optional. Sorts by created_at DESC.
    Returns: {items: [...], total: int, has_more: bool}
    """
    import sqlite3
    from pathlib import Path

    limit = min(max(int(limit), 1), 200)
    offset = max(int(offset), 0)

    where_clauses = []
    args: list = []

    if media_type in ("image", "video"):
        where_clauses.append("media_type = ?")
        args.append(media_type)

    if date_from is not None:
        where_clauses.append("created_at >= ?")
        args.append(float(date_from))

    if date_to is not None:
        where_clauses.append("created_at <= ?")
        args.append(float(date_to))

    if model:
        where_clauses.append("model = ?")
        args.append(str(model))

    if session_id:
        where_clauses.append("session_id = ?")
        args.append(str(session_id))

    if search:
        where_clauses.append("LOWER(prompt) LIKE ?")
        args.append(f"%{str(search).lower()}%")

    if min_size is not None:
        where_clauses.append("file_size_bytes >= ?")
        args.append(int(min_size))

    if max_size is not None:
        where_clauses.append("file_size_bytes <= ?")
        args.append(int(max_size))

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    db_path = Path.home() / ".clawksis" / "state.db"
    if not db_path.exists():
        return JSONResponse(status_code=503, content={"detail": "State DB unavailable"})

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(f"SELECT COUNT(*) as c FROM media_generations{where_sql}", args)
        total = cur.fetchone()["c"]

        cur.execute(
            f"SELECT id, session_id, message_id, media_type, status, "
            f"file_path, original_url, file_size_bytes, width, height, "
            f"prompt, model, provider, created_at "
            f"FROM media_generations{where_sql} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            args + [limit, offset],
        )
        items = [dict(row) for row in cur.fetchall()]
        conn.close()

        return {
            "items": items,
            "total": total,
            "has_more": offset + len(items) < total,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"DB error: {e}"})


@app.get("/api/gallery/stats")
async def get_media_stats():
    """Aggregate stats for the gallery header."""
    import sqlite3
    from pathlib import Path

    db_path = Path.home() / ".clawksis" / "state.db"
    if not db_path.exists():
        return JSONResponse(status_code=503, content={"detail": "State DB unavailable"})

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM media_generations WHERE media_type = 'image'")
        total_images = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM media_generations WHERE media_type = 'video'")
        total_videos = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(file_size_bytes), 0) FROM media_generations")
        total_size = cur.fetchone()[0]

        seven_days_ago = time.time() - (7 * 86400)
        cur.execute(
            "SELECT COUNT(*) FROM media_generations WHERE created_at >= ?",
            (seven_days_ago,),
        )
        last_7 = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM media_generations WHERE status = 'expired'")
        expired = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM media_generations WHERE status = 'ready'")
        ready = cur.fetchone()[0]

        conn.close()

        return {
            "total_images": total_images,
            "total_videos": total_videos,
            "total_size_bytes": total_size,
            "last_7_days": last_7,
            "expired_count": expired,
            "ready_count": ready,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"DB error: {e}"})


@app.delete("/api/gallery/{media_id}")
async def delete_media(media_id: str):
    """Delete a media entry: removes DB row + file from disk."""
    import sqlite3
    from pathlib import Path

    if not media_id or len(media_id) > 128 or "/" in media_id or ".." in media_id:
        raise HTTPException(status_code=400, detail="Invalid media id")

    db_path = Path.home() / ".clawksis" / "state.db"
    if not db_path.exists():
        return JSONResponse(status_code=503, content={"detail": "State DB unavailable"})

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()

        cur.execute(
            "SELECT file_path, file_size_bytes FROM media_generations WHERE id = ?",
            (media_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Media not found")

        file_path_str, file_size = row
        freed = int(file_size or 0)
        file_missing = False

        try:
            fp = Path(file_path_str)
            if fp.exists():
                fp.unlink()
            else:
                file_missing = True
        except Exception:
            _log.exception("Failed to delete file %s", file_path_str)

        cur.execute("DELETE FROM media_generations WHERE id = ?", (media_id,))
        conn.commit()
        conn.close()

        return {
            "deleted": True,
            "freed_bytes": freed,
            "file_missing": file_missing,
        }
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"DB error: {e}"})


# ---------------------------------------------------------------------------
# Local artifact downloads — artifact-download-v1
# ---------------------------------------------------------------------------
#
# This route intentionally lives outside /api because direct Markdown links in
# the chat cannot attach the X-Clawksis-Session-Token header. Security is kept
# by strict local-only access and a narrow export-directory allowlist.
# ---------------------------------------------------------------------------

_ARTIFACT_ALLOWED_SUFFIXES = {
    ".xlsx",
    ".csv",
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".mp4",
    ".webm",
    ".mov",
    ".m4v",
    ".zip",
}

# Media types served INLINE so the dashboard chat can render images/videos the
# agent "sends" (markdown ![](/artifacts/download?path=…)) instead of forcing a
# download. Everything else stays application/octet-stream (download).
_ARTIFACT_INLINE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
}

_ARTIFACT_BLOCKED_NAMES = {
    ".env",
    "env",
    "id_rsa",
    "id_ed25519",
    "authorized_keys",
    "known_hosts",
    "config.yaml",
    "auth.json",
    "credentials.json",
    "token.json",
}


def _artifact_allowed_root() -> "Path":
    from pathlib import Path

    return (Path.home() / "clawksis_exports").resolve()


def _artifact_is_loopback_request(request: "Request") -> bool:
    # Modo gated (OAuth / `clawk dashboard domain`): estas rutas NO están en
    # _GATE_PUBLIC_PREFIXES, así que gated_auth_middleware ya exigió una sesión
    # válida antes de llegar acá, y start_server rehúsa arrancar gated sin auth
    # provider. Además, con el gate activo uvicorn corre con proxy_headers=True
    # y reescribe request.client.host a la IP REAL del navegador (vía el
    # X-Forwarded-For que setea Caddy/Nginx), así que el peer NUNCA es loopback
    # aunque el proxy sí lo sea — sin este short-circuit, toda la media del
    # agente (imágenes/video del chat, galería, audio TTS) daría 403 a usuarios
    # ya autenticados. La sesión del gate ES la credencial equivalente al peer
    # loopback.
    if getattr(getattr(request, "app", None), "state", None) is not None and getattr(
        request.app.state, "auth_required", False
    ):
        return True

    client = getattr(request, "client", None)
    host = getattr(client, "host", "") if client else ""
    host = str(host or "").strip().lower()

    return host == "localhost" or host == "::1" or host.startswith("127.")


def _artifact_is_within_root(candidate: "Path", root: "Path") -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


@app.get("/artifacts/download")
async def download_local_artifact(path: str, request: Request):
    """Download a generated local artifact from the Clawksis exports directory.

    Security model:
    - direct chat links work without custom headers;
    - only loopback / SSH-tunnel access is allowed;
    - only files under ~/clawksis_exports are allowed;
    - symlinks are resolved before the allowlist check;
    - only safe export file extensions are allowed.
    """

    from pathlib import Path
    from urllib.parse import unquote

    if not _artifact_is_loopback_request(request):
        raise HTTPException(
            status_code=403,
            detail="Artifact downloads are only available from local or SSH-tunnel dashboard access.",
        )

    raw_path = unquote(str(path or "")).strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="Missing artifact path.")

    root = _artifact_allowed_root()
    candidate = Path(raw_path).expanduser().resolve(strict=False)

    if not _artifact_is_within_root(candidate, root):
        # El agente también manda media generada como
        # ![](/artifacts/download?path=~/.clawksis/cache/images/…). Esos
        # archivos viven fuera de exports; delegar al bridge de media local,
        # que aplica sus propias reglas (loopback, symlinks resueltos antes
        # del allowlist, roots de media y extensiones de media solamente).
        if any(
            _artifact_is_within_root(candidate, media_root)
            for media_root in _local_media_allowed_roots()
        ):
            return await get_local_media(path=raw_path, request=request)
        raise HTTPException(
            status_code=403,
            detail="Artifact path is outside the allowed exports directory.",
        )

    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Artifact not found.")

    if not candidate.is_file():
        raise HTTPException(status_code=400, detail="Artifact path is not a file.")

    if candidate.suffix.lower() not in _ARTIFACT_ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400, detail="Artifact file type is not allowed."
        )

    parts_lower = {part.lower() for part in candidate.parts}
    if parts_lower & _ARTIFACT_BLOCKED_NAMES:
        raise HTTPException(
            status_code=403, detail="Sensitive file names are not downloadable."
        )

    inline_media_type = _ARTIFACT_INLINE_MEDIA_TYPES.get(candidate.suffix.lower())
    if inline_media_type:
        # Serve media inline (correct Content-Type + inline disposition) so the
        # chat's <img>/<video> render it instead of triggering a download.
        return FileResponse(
            str(candidate),
            media_type=inline_media_type,
            headers={
                "Cache-Control": "private, no-store",
                "Content-Disposition": f'inline; filename="{candidate.name}"',
            },
        )

    return FileResponse(
        str(candidate),
        filename=candidate.name,
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )


# ---------------------------------------------------------------------------
# Chat projects / folders — chat-projects-v1
# ---------------------------------------------------------------------------


class ChatProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    instructions: Optional[str] = None


class ChatProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    archived: Optional[bool] = None


class SessionProjectUpdate(BaseModel):
    project_id: Optional[str] = None


def _chat_projects_db_path():
    from clawk_constants import get_clawk_home

    return get_clawk_home() / "state.db"


def _chat_projects_connect():
    import sqlite3

    conn = sqlite3.connect(_chat_projects_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _chat_project_clean_text(
    value: Any, *, field: str, max_len: int, required: bool = False
) -> str:
    text = str(value or "").strip()

    if required and not text:
        raise HTTPException(status_code=400, detail=f"{field} is required")

    if len(text) > max_len:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be at most {max_len} characters",
        )

    if any(ord(ch) < 32 and ch not in ("\t", "\n", "\r") for ch in text):
        raise HTTPException(
            status_code=400, detail=f"{field} contains control characters"
        )

    return text


def _ensure_chat_projects_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            instructions TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    project_cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(chat_projects)").fetchall()
    }

    if "instructions" not in project_cols:
        conn.execute("ALTER TABLE chat_projects ADD COLUMN instructions TEXT")

    session_cols = {
        row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
    }

    if "project_id" not in session_cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN project_id TEXT")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_projects_archived_name "
        "ON chat_projects(archived, name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id)"
    )
    conn.commit()


def _project_row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "instructions": row["instructions"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "archived": bool(row["archived"]),
        "session_count": int(row["session_count"] or 0),
    }


def _project_exists(conn, project_id: str, *, include_archived: bool = False) -> bool:
    if include_archived:
        row = conn.execute(
            "SELECT id FROM chat_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM chat_projects WHERE id = ? AND archived = 0",
            (project_id,),
        ).fetchone()

    return row is not None


def _attach_session_projects(
    sessions: list[dict[str, Any]], db_path: Optional[Path] = None
) -> None:
    """Tag session rows with their chat project (``db_path``: the store they were listed from;
    default the active home's state.db). READ-ONLY on purpose: it backs the GET /api/sessions
    poll, which must never write (or checkpoint another writer's WAL), so a store without the
    projects schema yet simply tags every row unassigned."""
    if not sessions:
        return
    for session in sessions:
        session.setdefault("project_id", None)
        session.setdefault("project_name", None)
        session.setdefault("project_archived", False)

    import sqlite3

    db_path = Path(db_path) if db_path is not None else _chat_projects_db_path()
    if not db_path.exists():
        return
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        has_projects = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chat_projects'"
        ).fetchone()
        session_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if not has_projects or "project_id" not in session_cols:
            return

        ids = [str(s.get("id") or "") for s in sessions if s.get("id")]
        if not ids:
            return

        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"""
            SELECT
                s.id AS session_id,
                s.project_id AS project_id,
                p.name AS project_name,
                p.archived AS project_archived
            FROM sessions s
            LEFT JOIN chat_projects p ON p.id = s.project_id
            WHERE s.id IN ({placeholders})
            """,
            ids,
        ).fetchall()

        project_map = {
            row["session_id"]: {
                "project_id": row["project_id"],
                "project_name": row["project_name"],
                "project_archived": bool(row["project_archived"])
                if row["project_archived"] is not None
                else False,
            }
            for row in rows
        }

        for session in sessions:
            meta = project_map.get(str(session.get("id") or ""), {})
            session["project_id"] = meta.get("project_id")
            session["project_name"] = meta.get("project_name")
            session["project_archived"] = bool(meta.get("project_archived", False))

    finally:
        conn.close()


@app.get("/api/projects")
async def list_chat_projects(include_archived: bool = False):
    conn = _chat_projects_connect()
    try:
        _ensure_chat_projects_schema(conn)

        where = "" if include_archived else "WHERE p.archived = 0"
        rows = conn.execute(
            f"""
            SELECT
                p.id,
                p.name,
                p.description,
                p.instructions,
                p.created_at,
                p.updated_at,
                p.archived,
                COUNT(s.id) AS session_count
            FROM chat_projects p
            LEFT JOIN sessions s ON s.project_id = p.id
            {where}
            GROUP BY p.id
            ORDER BY p.archived ASC, LOWER(p.name) ASC
            """
        ).fetchall()

        return {"projects": [_project_row_to_dict(row) for row in rows]}

    finally:
        conn.close()


@app.post("/api/projects")
async def create_chat_project(body: ChatProjectCreate):
    import time
    import uuid

    name = _chat_project_clean_text(body.name, field="name", max_len=80, required=True)
    description = _chat_project_clean_text(
        body.description,
        field="description",
        max_len=500,
        required=False,
    )
    instructions = _chat_project_clean_text(
        body.instructions,
        field="instructions",
        max_len=4000,
        required=False,
    )

    conn = _chat_projects_connect()
    try:
        _ensure_chat_projects_schema(conn)

        duplicate = conn.execute(
            "SELECT id FROM chat_projects WHERE LOWER(name) = LOWER(?) AND archived = 0",
            (name,),
        ).fetchone()
        if duplicate:
            raise HTTPException(
                status_code=409, detail="A project with that name already exists"
            )

        now = time.time()
        project_id = uuid.uuid4().hex[:12]

        conn.execute(
            """
            INSERT INTO chat_projects (id, name, description, instructions, created_at, updated_at, archived)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (project_id, name, description, instructions, now, now),
        )
        conn.commit()

        row = conn.execute(
            """
            SELECT
                p.id,
                p.name,
                p.description,
                p.instructions,
                p.created_at,
                p.updated_at,
                p.archived,
                COUNT(s.id) AS session_count
            FROM chat_projects p
            LEFT JOIN sessions s ON s.project_id = p.id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (project_id,),
        ).fetchone()

        return _project_row_to_dict(row)

    finally:
        conn.close()


@app.patch("/api/projects/{project_id}")
async def update_chat_project(project_id: str, body: ChatProjectUpdate):
    import time

    conn = _chat_projects_connect()
    try:
        _ensure_chat_projects_schema(conn)

        row = conn.execute(
            "SELECT * FROM chat_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")

        updates = []
        params: list[Any] = []

        if body.name is not None:
            name = _chat_project_clean_text(
                body.name, field="name", max_len=80, required=True
            )
            duplicate = conn.execute(
                """
                SELECT id FROM chat_projects
                WHERE LOWER(name) = LOWER(?) AND archived = 0 AND id <> ?
                """,
                (name, project_id),
            ).fetchone()
            if duplicate:
                raise HTTPException(
                    status_code=409, detail="A project with that name already exists"
                )
            updates.append("name = ?")
            params.append(name)

        if body.description is not None:
            description = _chat_project_clean_text(
                body.description,
                field="description",
                max_len=500,
                required=False,
            )
            updates.append("description = ?")
            params.append(description)

        if body.instructions is not None:
            instructions = _chat_project_clean_text(
                body.instructions,
                field="instructions",
                max_len=4000,
                required=False,
            )
            updates.append("instructions = ?")
            params.append(instructions)

        if body.archived is not None:
            updates.append("archived = ?")
            params.append(1 if body.archived else 0)

        if not updates:
            raise HTTPException(status_code=400, detail="Nothing to update")

        updates.append("updated_at = ?")
        params.append(time.time())
        params.append(project_id)

        conn.execute(
            f"UPDATE chat_projects SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()

        updated = conn.execute(
            """
            SELECT
                p.id,
                p.name,
                p.description,
                p.instructions,
                p.created_at,
                p.updated_at,
                p.archived,
                COUNT(s.id) AS session_count
            FROM chat_projects p
            LEFT JOIN sessions s ON s.project_id = p.id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (project_id,),
        ).fetchone()

        return _project_row_to_dict(updated)

    finally:
        conn.close()


@app.delete("/api/projects/{project_id}")
async def delete_chat_project(project_id: str):
    import time

    conn = _chat_projects_connect()
    try:
        _ensure_chat_projects_schema(conn)

        if not _project_exists(conn, project_id, include_archived=True):
            raise HTTPException(status_code=404, detail="Project not found")

        # Safe delete semantics: do not delete chats. Unassign sessions, then archive the project.
        conn.execute(
            "UPDATE sessions SET project_id = NULL WHERE project_id = ?", (project_id,)
        )
        conn.execute(
            "UPDATE chat_projects SET archived = 1, updated_at = ? WHERE id = ?",
            (time.time(), project_id),
        )
        conn.commit()

        return {"ok": True}

    finally:
        conn.close()


@app.patch("/api/sessions/{session_id}/project")
async def move_session_to_project(session_id: str, body: SessionProjectUpdate):
    from clawk_state import SessionDB

    db = SessionDB()
    try:
        sid = db.resolve_session_id(session_id)
        if not sid:
            raise HTTPException(status_code=404, detail="Session not found")
    finally:
        db.close()

    project_id = str(body.project_id or "").strip() or None

    conn = _chat_projects_connect()
    try:
        _ensure_chat_projects_schema(conn)

        if project_id is not None and not _project_exists(conn, project_id):
            raise HTTPException(status_code=404, detail="Project not found")

        conn.execute(
            "UPDATE sessions SET project_id = ? WHERE id = ?",
            (project_id, sid),
        )
        conn.commit()

        row = conn.execute(
            """
            SELECT
                s.id,
                s.project_id,
                p.name AS project_name
            FROM sessions s
            LEFT JOIN chat_projects p ON p.id = s.project_id
            WHERE s.id = ?
            """,
            (sid,),
        ).fetchone()

        return {
            "ok": True,
            "session_id": row["id"],
            "project_id": row["project_id"],
            "project_name": row["project_name"],
        }

    finally:
        conn.close()


@app.get("/api/sessions/running")
async def get_running_sessions():
    """DB session_ids that currently have an in-flight turn.

    Powers the sidebar's per-conversation running indicator (a spinner while a
    turn runs, even for conversations the user is not viewing — the turn runs in
    a worker thread independent of the WebSocket). Best-effort: returns an empty
    list if the in-process gateway is unavailable (e.g. nothing has run yet).
    """
    try:
        from tui_gateway.server import get_running_session_ids

        return {"running": get_running_session_ids()}
    except Exception:
        return {"running": []}


# ---------------------------------------------------------------------------
# Filtered session cleanup (free space by channel / model / age / size)
# ---------------------------------------------------------------------------


class SessionCleanup(BaseModel):
    source: Optional[str] = None
    model: Optional[str] = None
    older_than_days: Optional[int] = None
    max_messages: Optional[int] = None
    dry_run: bool = True


@app.post("/api/sessions/cleanup")
async def cleanup_sessions_endpoint(body: SessionCleanup):
    """Filtered bulk session cleanup to free space.

    Deletes sessions matching ANY combination of: ``source`` (cron / cli /
    telegram…), ``model`` (substring — e.g. a model that no longer works),
    ``older_than_days``, and ``max_messages`` (empty / near-empty junk).
    ``dry_run`` (default True) returns the match count + total messages so the
    dashboard can preview before committing. Matches the same logical-session
    listing the sessions page shows, then reuses ``delete_sessions``.
    """
    has_filter = (
        bool((body.source or "").strip())
        or bool((body.model or "").strip())
        or body.older_than_days is not None
        or body.max_messages is not None
    )
    if not has_filter:
        raise HTTPException(status_code=400, detail="at least one filter is required")

    import time as _time

    from clawk_state import SessionDB

    db = SessionDB()
    try:
        src = (body.source or "").strip().lower()
        # Enumerate RAW rows (not the display projection): the cleanup panel
        # frees disk, so it must see every deletable row — children (sub-agent,
        # compression continuations, branches) included — not just the surfaced
        # logical tips. The display defaults (include_children=False,
        # project_compression_tips=True) made preview undercount and "Eliminar"
        # leave most of the garbage on disk. This matches the surface that
        # count_empty_sessions/delete_empty_sessions already operate on.
        rows = db.list_sessions_rich(
            source=src or None,
            limit=1_000_000,
            offset=0,
            include_archived=True,
            include_children=True,
            project_compression_tips=False,
        )
        now = _time.time()
        model_q = (body.model or "").strip().lower()
        matched_ids: list[str] = []
        matched_msgs = 0
        for s in rows:
            if model_q and model_q not in str(s.get("model") or "").lower():
                continue
            mc = int(s.get("message_count") or 0)
            if body.max_messages is not None and mc > body.max_messages:
                continue
            if body.older_than_days is not None:
                last = (
                    s.get("last_active")
                    or s.get("ended_at")
                    or s.get("started_at")
                    or 0
                )
                try:
                    last = float(last)
                except (TypeError, ValueError):
                    last = 0.0
                if not last or (now - last) < body.older_than_days * 86400:
                    continue
            sid = s.get("id")
            if sid:
                matched_ids.append(sid)
                matched_msgs += mc

        if body.dry_run:
            return {"ok": True, "matched": len(matched_ids), "messages": matched_msgs}

        if len(matched_ids) > 2000:
            raise HTTPException(
                status_code=400,
                detail="too many matches (>2000) — narrow the filter or delete in batches",
            )
        deleted = db.delete_sessions(matched_ids)
        return {"ok": True, "deleted": deleted}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Cron calendar view — per-job firing days
# ---------------------------------------------------------------------------
from clawk_cli.web_server_cron import _call_cron_for_profile, _cron_profile_dicts


@app.get("/api/cron/occurrences")
async def cron_occurrences(start: str, end: str, profile: str = "all"):
    """Per-job firing days within [start, end] (YYYY-MM-DD) for the calendar
    view. Enumerates each enabled job's schedule with the canonical scheduler
    logic (croniter / interval phase / one-shot) and buckets by local date."""
    from datetime import datetime as _dt
    from cron.jobs import compute_occurrences, _ensure_aware

    try:
        win_start = _ensure_aware(_dt.fromisoformat(f"{start}T00:00:00"))
        win_end = _ensure_aware(_dt.fromisoformat(f"{end}T23:59:59"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid start/end (use YYYY-MM-DD): {exc}"
        )

    requested = (profile or "all").strip()
    jobs: list[dict[str, Any]] = []
    if requested.lower() != "all":
        jobs = _call_cron_for_profile(requested, "list_jobs", True)
    else:
        for item in _cron_profile_dicts():
            name = str(item.get("name") or "")
            if not name:
                continue
            try:
                jobs.extend(_call_cron_for_profile(name, "list_jobs", True))
            except Exception:
                _log.exception("Failed to list cron jobs for profile %s", name)

    result: list[dict[str, Any]] = []
    for job in jobs:
        if not job.get("enabled", True) or job.get("state") == "paused":
            continue
        schedule = job.get("schedule") or {}
        if not isinstance(schedule, dict):
            continue
        anchor = job.get("next_run_at") or job.get("created_at")
        try:
            occ = compute_occurrences(schedule, win_start, win_end, anchor=anchor)
        except Exception:
            _log.exception("occurrences failed for job %s", job.get("id"))
            occ = []
        days: dict[str, int] = {}
        for dt in occ:
            key = dt.strftime("%Y-%m-%d")
            days[key] = days.get(key, 0) + 1
        if days:
            result.append(
                {
                    "id": job.get("id"),
                    "name": job.get("name") or job.get("id"),
                    "profile": job.get("profile"),
                    "schedule_display": job.get("schedule_display")
                    or schedule.get("display"),
                    "days": days,
                }
            )

    return {"start": start, "end": end, "jobs": result}


# ---------------------------------------------------------------------------
# Visualization section (pixel office + comms graph)
# ---------------------------------------------------------------------------


def _visualization_layout_path() -> Path:
    """Path to the persisted pixel-office layout (~/.clawksis/visualization/)."""
    vdir = get_clawk_home() / "visualization"
    vdir.mkdir(parents=True, exist_ok=True)
    return vdir / "office-layout.json"


# Cap the persisted layout to a sane size — a 64x64 office with furniture
# serializes well under this; the bound just stops a malformed/huge PUT from
# writing an unbounded blob to disk.
_MAX_LAYOUT_BYTES = 2 * 1024 * 1024


def _read_visualization_layout() -> Any:
    """Blocking read+parse of the saved layout (run via to_thread)."""
    import json as _json

    path = _visualization_layout_path()
    if not path.exists():
        return None
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_visualization_layout(payload: str) -> None:
    """Blocking write of the serialized layout (run via to_thread)."""
    _visualization_layout_path().write_text(payload, encoding="utf-8")


@app.get("/api/visualization/layout")
async def get_visualization_layout():
    """Return the saved pixel-office layout, or ``{"layout": null}`` if none."""
    layout = await asyncio.to_thread(_read_visualization_layout)
    return {"layout": layout}


class VisualizationLayoutBody(BaseModel):
    layout: Any


@app.put("/api/visualization/layout")
async def set_visualization_layout(body: VisualizationLayoutBody):
    """Persist the pixel-office layout edited in the dashboard."""
    import json as _json

    if body.layout is None:
        raise HTTPException(status_code=400, detail="layout is required")
    payload = _json.dumps(body.layout)
    if len(payload.encode("utf-8")) > _MAX_LAYOUT_BYTES:
        raise HTTPException(status_code=413, detail="layout too large")
    try:
        await asyncio.to_thread(_write_visualization_layout, payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to save layout: {exc}")
    return {"ok": True}


@app.get("/api/visualization/agent-messages")
async def get_visualization_agent_messages(limit: int = 100, since_id: int = 0):
    """Return recent peer-to-peer agent messages (for the comms graph).

    Reads the same ``agent_comms.db`` the ``agent_message`` tool writes to.
    Returns an empty list when the agent-messaging toolset has never run.
    """
    try:
        from tools.agent_comms_tool import read_recent_messages

        # Offload the synchronous SQLite I/O so it doesn't block the event loop
        # (matches the convention used elsewhere in this file).
        messages = await asyncio.to_thread(
            read_recent_messages,
            limit=limit,
            since_id=since_id if since_id > 0 else None,
        )
    except Exception:
        messages = []
    return {"messages": messages}


# Session metadata (title/source/model) cache for the Visualization office.
# Rebuilt at most every TTL seconds so the per-1.5s events poll stays cheap.
_VIZ_SESSION_META: dict[str, Any] = {"ts": 0.0, "data": {}}
_VIZ_SESSION_META_TTL = 10.0


def _build_viz_session_meta() -> dict[str, dict[str, str]]:
    """Map session_id -> {title, source, model} from the sessions store (blocking)."""
    out: dict[str, dict[str, str]] = {}
    try:
        from clawk_state import SessionDB

        db = SessionDB()
        try:
            rows = db.list_sessions_rich(
                limit=300,
                offset=0,
                min_message_count=0,
                include_archived=True,
                archived_only=False,
                order_by_last_active=True,
            )
            for s in rows:
                sid = s.get("id")
                if not sid:
                    continue
                out[sid] = {
                    "title": (s.get("title") or "").strip(),
                    "source": (s.get("source") or "").strip(),
                    "model": (s.get("model") or "").strip(),
                }
        finally:
            db.close()
    except Exception:
        _log.debug("viz session meta build failed", exc_info=True)
    return out


async def _viz_session_meta_cached() -> dict[str, dict[str, str]]:
    now = time.time()
    if (
        now - _VIZ_SESSION_META["ts"] > _VIZ_SESSION_META_TTL
        or not _VIZ_SESSION_META["data"]
    ):
        data = await asyncio.to_thread(_build_viz_session_meta)
        if data:
            _VIZ_SESSION_META["data"] = data
            _VIZ_SESSION_META["ts"] = now
    return _VIZ_SESSION_META["data"]


@app.get("/api/visualization/agent-events")
async def get_visualization_agent_events(limit: int = 300, since_id: int = 0):
    """Return recent tool-activity events across ALL agents (oldest-first).

    Reads the cross-process ``agent_events.db`` that every agent (chat, gateway
    platforms, cron) writes to via ``model_tools.handle_function_call``. This is
    what lets the Visualization office show agents from every channel, not just
    the dashboard chat PTY. Also returns a ``sessions`` map (session_id ->
    {title, source, model}) so the office can label desks with the real session
    name + model instead of the raw id. Returns empties when nothing has run.
    """
    try:
        import agent_events

        events = await asyncio.to_thread(
            agent_events.read_recent,
            limit=limit,
            since_id=since_id if since_id > 0 else None,
        )
    except Exception:
        events = []
    sessions: dict[str, dict[str, str]] = {}
    try:
        sids = {e.get("session_id") for e in events if e.get("session_id")}
        if sids:
            meta = await _viz_session_meta_cached()
            sessions = {sid: meta[sid] for sid in sids if sid in meta}
    except Exception:
        sessions = {}
    return {"events": events, "sessions": sessions}


# ---------------------------------------------------------------------------
# Cookbook — local models (run open LLMs locally via Ollama)
# ---------------------------------------------------------------------------


@app.get("/api/cookbook/hardware")
async def get_cookbook_hardware():
    """Detected hardware (RAM / CPU / GPU + VRAM) for the fit recommender."""
    try:
        from clawk_cli import cookbook

        hw = await asyncio.to_thread(cookbook.detect_hardware)
    except Exception:
        hw = {}
    return {"hardware": hw}


@app.get("/api/cookbook/catalog")
async def get_cookbook_catalog():
    """Curated local-model catalog enriched with a per-model fit verdict.

    Each entry carries ``fit`` ({mode, tier, reason}) for the detected hardware
    and an ``installed`` flag (already pulled into the local Ollama).
    """
    try:
        from clawk_cli import cookbook

        def _build():
            hw = cookbook.detect_hardware()
            installed = cookbook.ollama_models()
            return {
                "hardware": hw,
                "ollama": cookbook.ollama_status(),
                "models": cookbook.catalog_with_fit(hw, installed),
            }

        return await asyncio.to_thread(_build)
    except Exception:
        return {"hardware": {}, "ollama": {}, "models": []}


@app.get("/api/cookbook/search")
async def get_cookbook_search(q: str):
    """Live search of the FULL Ollama library (scraped) for models matching *q*.

    Returns catalog-shaped rows (one per size tag) with fit + installed flags,
    so ANY model in ollama.com/library is findable — not just the curated set.
    Returns [] if ollama.com is unreachable.
    """
    query = (q or "").strip()
    if not query:
        return {"models": []}
    try:
        from clawk_cli import cookbook

        def _build():
            hw = cookbook.detect_hardware()
            installed = cookbook.ollama_models()
            return {
                "models": cookbook.rows_with_fit(
                    cookbook.search_ollama_library(query), hw, installed
                )
            }

        return await asyncio.to_thread(_build)
    except Exception:
        return {"models": []}


@app.get("/api/cookbook/library")
async def get_cookbook_library():
    """The FULL Ollama library (scraped, cached ~30 min) with fit + installed."""
    try:
        from clawk_cli import cookbook

        def _build():
            hw = cookbook.detect_hardware()
            installed = cookbook.ollama_models()
            return {
                "hardware": hw,
                "ollama": cookbook.ollama_status(),
                "models": cookbook.rows_with_fit(
                    cookbook.full_ollama_library(), hw, installed
                ),
            }

        return await asyncio.to_thread(_build)
    except Exception:
        return {"hardware": {}, "ollama": {}, "models": []}


@app.get("/api/cookbook/ollama")
async def get_cookbook_ollama():
    """Ollama status (installed / running / pulled models)."""
    try:
        from clawk_cli import cookbook

        return await asyncio.to_thread(cookbook.ollama_status)
    except Exception:
        return {"installed": False, "running": False, "models": []}


class CookbookTagBody(BaseModel):
    tag: str


@app.post("/api/cookbook/pull")
async def post_cookbook_pull(body: CookbookTagBody):
    """Start `ollama pull <tag>` in the background. Poll /pull-status for progress."""
    tag = (body.tag or "").strip()
    if not tag:
        raise HTTPException(status_code=400, detail="tag is required")
    from clawk_cli import cookbook

    return await asyncio.to_thread(cookbook.start_pull, tag)


@app.get("/api/cookbook/pull-status")
async def get_cookbook_pull_status(tag: str):
    """Background pull status for a tag: pulling / validating / done / error.

    Incluye el progreso real del streaming pull (bytes, %, velocidad, ETA).
    """
    from clawk_cli import cookbook

    progress = cookbook.pull_progress(tag)
    return {"tag": tag, "status": cookbook.pull_status(tag), **progress}


@app.post("/api/cookbook/pull-cancel")
async def post_cookbook_pull_cancel(body: CookbookTagBody):
    """Cancela un `ollama pull` en curso (los blobs parciales se conservan)."""
    from clawk_cli import cookbook

    return await asyncio.to_thread(cookbook.cancel_pull, (body.tag or "").strip())


@app.post("/api/cookbook/install-ollama")
async def post_cookbook_install_ollama():
    """Install Ollama on the clawk host (background) so the Cookbook works here.

    "We ship Ollama with clawk" — install it on demand on the machine where the
    agent runs. Poll /install-ollama-status. Best-effort (Linux / macOS-brew).
    """
    from clawk_cli import cookbook

    return await asyncio.to_thread(cookbook.start_ollama_install)


@app.get("/api/cookbook/install-ollama-status")
async def get_cookbook_install_ollama_status():
    """Ollama install progress: installing / done / error / "" (unknown)."""
    from clawk_cli import cookbook

    return {"status": cookbook.ollama_install_status()}


@app.post("/api/cookbook/use")
async def post_cookbook_use(body: CookbookTagBody):
    """Set a local Ollama model as the agent's active model."""
    tag = (body.tag or "").strip()
    if not tag:
        raise HTTPException(status_code=400, detail="tag is required")
    from clawk_cli import cookbook

    result = await asyncio.to_thread(cookbook.use_model, tag)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "failed"))
    return result


# ── Cookbook: provider architecture (Ollama + llama.cpp + futuros) ──────────
#
# Los endpoints de arriba quedan por compatibilidad (Ollama directo). Los de
# abajo hablan con clawk_cli.cookbook_providers — la superficie común que
# permite agregar backends (LM Studio, vLLM, MLX…) sin tocar el frontend.


@app.get("/api/cookbook/providers")
async def get_cookbook_providers():
    """Estado de todos los backends de modelos locales (ollama, llamacpp…)."""
    from clawk_cli import cookbook_providers

    return await asyncio.to_thread(cookbook_providers.providers_status)


class CookbookProviderBody(BaseModel):
    provider: str


@app.post("/api/cookbook/provider-install")
async def post_cookbook_provider_install(body: CookbookProviderBody):
    """Instala un backend en este host, en background. Poll provider-install-status."""
    from clawk_cli import cookbook_providers

    p = cookbook_providers.get_provider(body.provider)
    if p is None:
        raise HTTPException(
            status_code=404, detail=f"unknown provider: {body.provider}"
        )
    return await asyncio.to_thread(p.start_install)


@app.get("/api/cookbook/provider-install-status")
async def get_cookbook_provider_install_status(provider: str):
    from clawk_cli import cookbook_providers

    p = cookbook_providers.get_provider(provider)
    if p is None:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")
    return {"provider": provider, "status": p.install_status()}


@app.get("/api/cookbook/hf-search")
async def get_cookbook_hf_search(q: str):
    """Búsqueda EN VIVO de repos GGUF en Hugging Face (para llama.cpp)."""
    query = (q or "").strip()
    if not query:
        return {"models": []}
    from clawk_cli import cookbook_hf

    rows = await asyncio.to_thread(cookbook_hf.search_gguf, query)
    return {"models": rows}


@app.get("/api/cookbook/hf-files")
async def get_cookbook_hf_files(repo: str):
    """Archivos .gguf de un repo HF con tamaño y cuantización (elegir variante)."""
    r = (repo or "").strip()
    if not r:
        raise HTTPException(status_code=400, detail="repo is required")
    from clawk_cli import cookbook_hf

    files = await asyncio.to_thread(cookbook_hf.repo_gguf_files, r)
    return {"repo": r, "files": files}


class CookbookDownloadBody(BaseModel):
    repo: str
    file: str


@app.post("/api/cookbook/download")
async def post_cookbook_download(body: CookbookDownloadBody):
    """Descarga un GGUF de HF directo a la carpeta de modelos de llama.cpp.

    Devuelve {download_id}; el progreso (bytes, %, velocidad, ETA, cancel) se
    consulta con /download-status. Con un .part previo, RESUME donde quedó.
    """
    from clawk_cli import cookbook_llamacpp

    result = await asyncio.to_thread(
        cookbook_llamacpp.start_download, body.repo, body.file
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "failed"))
    return result


@app.get("/api/cookbook/download-status")
async def get_cookbook_download_status(id: str):
    from clawk_cli import cookbook_llamacpp

    return {"download_id": id, **cookbook_llamacpp.download_progress(id)}


class CookbookDownloadIdBody(BaseModel):
    id: str


@app.post("/api/cookbook/download-cancel")
async def post_cookbook_download_cancel(body: CookbookDownloadIdBody):
    """Cancela una descarga GGUF (el .part queda para reanudar después)."""
    from clawk_cli import cookbook_llamacpp

    return await asyncio.to_thread(cookbook_llamacpp.cancel_download, body.id)


@app.get("/api/cookbook/active")
async def get_cookbook_active():
    """Descargas GGUF y pulls de Ollama EN CURSO (server-side, en background).

    Las descargas corren en threads del server y NO dependen del navegador:
    al volver a la pestaña, la UI llama esto para re-engancharse al progreso
    en vez de dar por muerta la instalación.
    """
    from clawk_cli import cookbook, cookbook_llamacpp

    downloads = await asyncio.to_thread(cookbook_llamacpp.active_downloads)
    pulls = await asyncio.to_thread(cookbook.active_pulls)
    interrupted = await asyncio.to_thread(cookbook_llamacpp.interrupted_downloads)
    return {"downloads": downloads, "pulls": pulls, "interrupted": interrupted}


@app.get("/api/cookbook/installed")
async def get_cookbook_installed():
    """Modelos instalados de TODOS los providers (tamaño, ruta, quant, origen)."""
    from clawk_cli import cookbook_providers

    models = await asyncio.to_thread(cookbook_providers.all_installed_models)
    return {"models": models}


class CookbookModelBody(BaseModel):
    provider: str
    id: str


@app.post("/api/cookbook/model-delete")
async def post_cookbook_model_delete(body: CookbookModelBody):
    from clawk_cli import cookbook_providers

    p = cookbook_providers.get_provider(body.provider)
    if p is None:
        raise HTTPException(
            status_code=404, detail=f"unknown provider: {body.provider}"
        )
    result = await asyncio.to_thread(p.delete_model, body.id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "failed"))
    return result


@app.post("/api/cookbook/model-use")
async def post_cookbook_model_use(body: CookbookModelBody):
    """Deja un modelo instalado (de cualquier provider) como modelo del agente.

    Para llamacpp además arranca el servidor OpenAI-compatible si hace falta.
    Aplica en todo lo que usa el modelo del agente: chat, agentes, skills,
    workflows, crons.
    """
    from clawk_cli import cookbook_providers

    p = cookbook_providers.get_provider(body.provider)
    if p is None:
        raise HTTPException(
            status_code=404, detail=f"unknown provider: {body.provider}"
        )
    result = await asyncio.to_thread(p.use_model, body.id)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "failed"))
    return result


class CookbookRenameBody(BaseModel):
    id: str
    name: str


@app.post("/api/cookbook/model-rename")
async def post_cookbook_model_rename(body: CookbookRenameBody):
    """Renombra el display-name de un GGUF registrado (solo llamacpp)."""
    from clawk_cli import cookbook_llamacpp

    result = await asyncio.to_thread(cookbook_llamacpp.rename_model, body.id, body.name)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "failed"))
    return result


class CookbookIdBody(BaseModel):
    id: str


@app.post("/api/cookbook/model-verify")
async def post_cookbook_model_verify(body: CookbookIdBody):
    """Chequeo de integridad de un GGUF (existencia, tamaño, magic bytes)."""
    from clawk_cli import cookbook_llamacpp

    return await asyncio.to_thread(cookbook_llamacpp.verify_model, body.id)


@app.post("/api/cookbook/llamacpp-stop")
async def post_cookbook_llamacpp_stop():
    """Frena el llama-server en curso (libera la RAM del modelo)."""
    from clawk_cli import cookbook_llamacpp

    return await asyncio.to_thread(cookbook_llamacpp.stop_server)


# Router mounting. ORDER IS ROUTE-MATCHING ORDER: literal paths must land before
# templated siblings (e.g. /api/sessions/bulk-delete before /api/sessions/{id}).
from clawk_cli.web_routers import (
    files as _files_routes,
    git as _git_routes,
    local_models as _local_models_routes,
    status as _status_routes,
    actions as _actions_routes,
    audio as _audio_routes,
    display as _display_routes,
    sessions as _sessions_routes,
    profiles as _profiles_routes,
    memory_providers as _memory_providers_routes,
    config_env as _config_env_routes,
    models as _models_routes,
    messaging as _messaging_routes,
    oauth as _oauth_routes,
    cron as _cron_routes,
    mcp as _mcp_routes,
    ops as _ops_routes,
    skills as _skills_routes,
    tools as _tools_routes,
    analytics as _analytics_routes,
    chat_ws as _chat_ws_routes,
    chat_workspaces as _chat_workspaces_routes,
    dashboard_ui as _dashboard_ui_routes,
    shared_metrics as _shared_metrics_routes,
    delegation as _delegation_routes,
)

app.include_router(_files_routes.router)
app.include_router(_git_routes.router)
app.include_router(_local_models_routes.router)
app.include_router(_status_routes.router)
app.include_router(_actions_routes.router)
app.include_router(_audio_routes.router)
app.include_router(_display_routes.router)
app.include_router(_actions_routes.status_router)
app.include_router(_sessions_routes.list_router)
app.include_router(_profiles_routes.sessions_router)
app.include_router(_sessions_routes.search_router)
app.include_router(_memory_providers_routes.router)
app.include_router(_config_env_routes.config_router)
app.include_router(_models_routes.router)
app.include_router(_config_env_routes.router)
app.include_router(_messaging_routes.router)
app.include_router(_oauth_routes.router)
app.include_router(_sessions_routes.manage_router)
app.include_router(_status_routes.logs_router)
app.include_router(_cron_routes.router)
app.include_router(_mcp_routes.router)
app.include_router(_ops_routes.router)
app.include_router(_skills_routes.hub_router)
app.include_router(_profiles_routes.router)
app.include_router(_skills_routes.router)
app.include_router(_tools_routes.router)
app.include_router(_analytics_routes.router)
app.include_router(_chat_ws_routes.router)
app.include_router(_chat_workspaces_routes.router)
app.include_router(_dashboard_ui_routes.router)
app.include_router(_shared_metrics_routes.router)
app.include_router(_delegation_routes.router)

# The dashboard SPA calls the update endpoints under the Clawksis-branded path;
# the upstream router keeps ``/api/clawk/update``. Same handlers, both paths.
app.add_api_route(
    "/api/clawksis/update", _actions_routes.update_clawk, methods=["POST"]
)
app.add_api_route(
    "/api/clawksis/update/check", _actions_routes.check_clawk_update, methods=["GET"]
)

# Plugin API routes and the dashboard auth routes (/login, /auth/*, /api/auth/*)
# mount before the SPA catch-all so /{full_path:path} doesn't swallow them. Auth
# routes are always mounted — the gate middleware decides enforcement.
_mount_plugin_api_routes()
from clawk_cli.dashboard_auth.routes import router as _dashboard_auth_router

app.include_router(_dashboard_auth_router)
mount_spa(app)


def _no_auth_provider_message(host: str) -> str:
    """Actionable SystemExit text for a gated bind with no registered auth provider.

    Names the exact trigger: on a loopback bind the ONLY trigger is
    dashboard.public_url, so print the offending URL and the remove-it exit.
    Bundled providers expose ``LAST_SKIP_REASON`` so an installed-but-
    unconfigured provider is not reported as merely "no providers".
    """
    import importlib

    skip_reasons: list[str] = []
    for _label in ("basic", "self_hosted"):
        try:
            _plugin = importlib.import_module(f"plugins.dashboard_auth.{_label}")
            if getattr(_plugin, "LAST_SKIP_REASON", ""):
                skip_reasons.append(f"  • {_label}: {_plugin.LAST_SKIP_REASON}")
        except Exception:
            pass

    if host in _LOOPBACK_HOST_VALUES:
        public_url = ""
        try:
            from clawk_cli.dashboard_auth.prefix import resolve_public_url

            public_url = resolve_public_url()
        except Exception:
            pass
        gate_reason = (
            f"dashboard.public_url is set to "
            f"{public_url or '<a non-loopback URL>'} — an "
            f"operator-declared external URL engages the auth gate "
            f"even on a loopback bind"
        )
        fix_hint = (
            "If this dashboard should be LOCAL-ONLY (no reverse "
            "proxy), remove dashboard.public_url from config.yaml "
            "(and unset CLAWK_DASHBOARD_PUBLIC_URL) to restore the "
            "unauthenticated loopback mode.\n"
        )
    else:
        gate_reason = f"the auth gate engages on non-loopback binds ({host})"
        fix_hint = ""

    fix_hint += (
        "Configure an auth provider before exposing the dashboard:\n"
        "  • Password: run `clawk dashboard password` (or set "
        "dashboard.basic_auth.username + password_hash in config.yaml)\n"
        "  • OAuth: install a DashboardAuthProvider plugin (e.g. the "
        "bundled self_hosted OIDC provider).\n"
        "There is no unauthenticated public-dashboard option. For "
        "local-only use, bind 127.0.0.1 and leave dashboard.public_url "
        "unset; a configured external public URL requires auth even "
        "when a local reverse proxy reaches a loopback backend."
    )
    # Credentials exist but the bundled provider is disabled (#54489). Basic
    # auth needs a username AND a credential; a half-configured block is silent.
    try:
        from clawk_cli.config import load_config as _load_cfg
        from clawk_cli.plugins_cmd import _BASIC_AUTH_PLUGIN_KEYS

        cfg = _load_cfg()
        ba = (cfg.get("dashboard") or {}).get("basic_auth") or {}
        disabled = (cfg.get("plugins") or {}).get("disabled") or []
        has_creds = bool(ba.get("username")) and bool(
            ba.get("password_hash") or ba.get("password")
        )
        if has_creds and (set(disabled) & _BASIC_AUTH_PLUGIN_KEYS):
            fix_hint = (
                "The 'basic' dashboard-auth plugin is in "
                "plugins.disabled but dashboard.basic_auth is "
                "configured.\n"
                "Remove 'basic' from plugins.disabled (or run "
                "`clawk plugins enable basic`), then restart the "
                "dashboard.\n\n"
            ) + fix_hint
    except Exception:
        pass
    msg = (
        f"Refusing to bind dashboard to {host} — {gate_reason}, "
        f"but no auth providers are registered.\n\n"
    )
    if skip_reasons:
        msg += (
            "Bundled providers reported these issues:\n"
            + "\n".join(skip_reasons)
            + "\n\n"
        )
    return msg + fix_hint


def _configure_auth_gate(
    host: str,
    allow_public: bool,
    ssh_session_token: Optional[str],
    ssh_owner_nonce: Optional[str],
) -> None:
    """Resolve the trusted public hosts + auth-gate flag onto ``app.state``.

    Fails closed (``SystemExit`` with an actionable message) when the gate
    engages but no dashboard auth provider is registered — unless the
    first-run setup page can create the login (``first_run.setup_available``).
    """
    # dashboard.public_url is also the exact Host/Origin trust declaration for
    # reverse-proxy deployments; resolved once so middleware never reloads
    # config. A non-loopback public hostname engages the gate even on a loopback
    # backend, else the SPA's local session token becomes remotely reachable.
    app.state.trusted_public_hosts = _resolve_trusted_public_hosts()
    # auth_required drives middleware, SPA-token injection, WS auth, the
    # startup refusal, the gate-on banner and uvicorn proxy_headers.
    if _desktop_loopback_auth_exempt(host, ssh_session_token, ssh_owner_nonce):
        # public_url describes the operator's PUBLIC deployment, not this
        # Desktop-owned loopback backend (#96490), which authenticates with the
        # per-spawn session token the ticket-only gate would refuse.
        app.state.auth_required = should_require_auth(host)
        _log.info(
            "Desktop-owned loopback backend: dashboard.public_url does not "
            "engage the ticket gate for this process; the public deployment "
            "keeps its own gate.",
        )
    else:
        app.state.auth_required = should_require_dashboard_auth(
            host, app.state.trusted_public_hosts, allow_public
        )

    # Clawksis keeps ``--insecure`` as the explicit escape hatch for a non-loopback bind
    # (upstream made it a no-op in its June 2026 hardening): no gate, loud warning.
    if allow_public and host not in _LOOPBACK_HOST_VALUES:
        if app.state.auth_required:
            _log.warning(
                "--insecure does not bypass the auth gate engaged by "
                "dashboard.public_url / CLAWK_DASHBOARD_FORCE_GATE on %s.",
                host,
            )
        else:
            _log.warning(
                "Binding to %s with --insecure — the dashboard has no robust "
                "authentication. Only use on trusted networks.",
                host,
            )

    if app.state.auth_required:
        # No escape hatch serves a gated dashboard without a provider.
        from clawk_cli.dashboard_auth import list_providers
        from clawk_cli.dashboard_auth.first_run import setup_available

        if not list_providers():
            # First run (Clawksis): no login configured yet → the gate stays
            # ON and the first visit shows the setup page that creates it
            # (/auth/setup), instead of refusing to start (a forced gate with
            # no login used to deadlock `clawk dashboard domain` boots).
            if setup_available():
                _log.warning(
                    "Dashboard binding to %s with the auth gate ON but no login "
                    "configured yet. The first visit will show the setup page "
                    "and create the admin login — open the dashboard and set it "
                    "IMMEDIATELY so nobody else claims it, or set it now with "
                    "`clawk dashboard password`.",
                    host,
                )
                return
            raise SystemExit(_no_auth_provider_message(host))
        _log.info(
            "Dashboard binding to %s with auth gate enabled. Providers: %s",
            host,
            ", ".join(p.name for p in list_providers()),
        )


def _build_uvicorn_server(host: str, port: int, *, ssh_isolated: bool = False):
    """Build the uvicorn ``Config`` + ``Server`` for this bind (reads ``app.state.auth_required``).

    uvicorn.Server is driven directly (not uvicorn.run) so startup is split from
    the main loop: after startup() the socket is bound and held by uvicorn, so the
    OS-assigned port can be read with no pre-bind-then-close TOCTOU. Explicit
    taken ports are caught by the #93608 preflight probe; uvicorn's own bind
    error stays the fallback for races.
    """
    import uvicorn

    # WS keepalive ping runs ON the agent event loop; a GIL-holding worker call
    # can starve it for minutes, so uvicorn misses the pong and drops a healthy
    # local socket (#53773/#48445/#50005). The ping only detects half-open
    # connections (proxy 524, dropped tunnels), impossible on loopback where a
    # dead client sends a real FIN/RST -> WebSocketDisconnect. So: no ping on
    # loopback; non-loopback sits behind a Cloudflare Tunnel (~100s idle) and
    # keeps a config-driven cadence (dashboard.ws_ping_interval/_timeout,
    # #79635) defaulting to 20/20.
    _is_loopback = host in _LOOPBACK_HOST_VALUES
    try:
        _dash_cfg = load_config().get("dashboard") or {}
    except Exception:
        _dash_cfg = {}

    def _ws_ping_setting(key: str, default: float = 20.0) -> float:
        try:
            return float(_dash_cfg.get(key, default))
        except (TypeError, ValueError):
            return default

    # A Desktop-owned SSH-isolated backend is loopback on the SERVER, but the client sits at the far
    # end of a tunnel: the local socket stays healthy while the laptop sleeps, so only a slow WS ping
    # notices the half-open tunnel (#101626). Its client count is tracked at the ASGI boundary so
    # the idle watchdog can retire the backend once nothing is connected.
    served_app = app
    ping_interval, ping_timeout = (
        (None, None)
        if _is_loopback
        else (_ws_ping_setting("ws_ping_interval"), _ws_ping_setting("ws_ping_timeout"))
    )
    if ssh_isolated:
        from clawk_cli.web_server_idle_exit import (
            TUNNEL_WS_PING_INTERVAL_S,
            TUNNEL_WS_PING_TIMEOUT_S,
            IdleClientTracker,
            wrap_asgi_with_ws_tracking,
        )

        app.state.ssh_isolated_clients = IdleClientTracker()
        served_app = wrap_asgi_with_ws_tracking(app, app.state.ssh_isolated_clients)
        ping_interval, ping_timeout = (
            TUNNEL_WS_PING_INTERVAL_S,
            TUNNEL_WS_PING_TIMEOUT_S,
        )

    _uvicorn_console_logging()  # log_config=None: uvicorn's dictConfig would close every live handler

    config = uvicorn.Config(
        served_app,
        host=host,
        port=port,
        log_level="warning",
        log_config=None,
        # Off by default so _ws_client_is_allowed sees the real peer, not
        # X-Forwarded-For. Gated mode runs behind a TLS terminator and needs
        # X-Forwarded-Proto for cookie Secure flags.
        proxy_headers=bool(app.state.auth_required),
        # Loopback-only unless the operator trusts a bounded upstream proxy, so
        # spoofed X-Forwarded-* from arbitrary callers is never honoured.
        forwarded_allow_ips=_dashboard_forwarded_allow_ips(_dash_cfg),
        ws_ping_interval=ping_interval,
        ws_ping_timeout=ping_timeout,
        ws_max_size=_DESKTOP_ATTACHMENT_WS_MAX_BYTES,
        # Desktop sends a single SIGTERM and escalates to SIGKILL ~5s later;
        # uvicorn's default (None) waits on lingering ASGI tasks forever, so a
        # mid-turn request orphans the backend past that budget (#76244). 3s
        # leaves room for lifespan shutdown + cron_stop before the kill.
        timeout_graceful_shutdown=3,
    )
    return config, uvicorn.Server(config)


def _best_effort(what: str, fn) -> None:
    """Run a best-effort startup step; any failure (import included) is a debug line."""
    try:
        fn()
    except Exception as exc:
        _log.debug("%s skipped: %s", what, exc)


def _reclaim_host_from_orphaned_owner(role: str) -> bool:
    """True when the conflicting host owner was reaped/cleared and the claim is worth retrying.

    HELD_BY_OTHER helper for #121964. A stale record with no live owner is retracted via
    ``discard_dead_record`` (which only removes provably-gone owners); a live owner is reaped
    only when the spawn ledger proves it is a dead session's orphan. Anything else returns
    False and the caller stays observe-only. Never raises.
    """
    from gateway import host_rendezvous as hr
    from clawk_cli.process_identity import reap_orphaned_backend_owner

    try:
        owner = hr.read_record(role)
    except Exception:
        return False
    if owner is None:
        try:
            return bool(hr.discard_dead_record(role))
        except Exception:
            return False
    if owner.pid == os.getpid():
        return False  # never reap our own incarnation on a re-entrant claim
    try:
        if reap_orphaned_backend_owner(owner.pid, owner.create_time) is None:
            return False
    except Exception:
        return False
    try:
        hr.discard_dead_record(role)
    except Exception:
        pass
    return True


def _publish_host_rendezvous(host: str, port: int) -> None:
    """Publish this backend's host record: ``ROLE_SERVE`` for the machine-level owner,
    ``ROLE_DESKTOP_SERVE`` for a Desktop-owned child."""
    # Desktop-spawned backends (flag + per-spawn credential; the bare flag is inherited by every
    # Desktop shell) are loopback, random-port and per-profile. Recording one as the HOST owner
    # made a later independently supervised `dashboard --host 0.0.0.0 --port N` refuse behind
    # the private child on every restart (#119824): the attach/refuse ladder reads ROLE_SERVE
    # only. They still publish under their own role so `clawk plugins install` from a terminal
    # can reach the backend hosting the open chats on a Desktop-only box (#119644).
    from gateway import host_rendezvous as hr

    desktop_child = is_desktop_owned_backend()
    role = hr.ROLE_DESKTOP_SERVE if desktop_child else hr.ROLE_SERVE

    outcome, error = hr.claim_host_lock(role)
    if outcome is hr.HostLockOutcome.COULD_NOT_OPEN:
        _log.warning(
            "Host backend lock could not be opened (%s); this backend is not discoverable. "
            "This is NOT another backend holding it.",
            error,
        )
        return
    if outcome is hr.HostLockOutcome.HELD_BY_OTHER and not desktop_child:
        # A prior backend whose session died (dead spawner, PID re-parented to init) is still
        # alive, so it still holds the flock and its record passes every staleness check: the
        # pre-#121964 code returned observe-only here forever, and every attach retried against
        # the same orphan. Reap exactly that corpse and re-claim instead.
        if _reclaim_host_from_orphaned_owner(role):
            outcome, error = hr.claim_host_lock(role)
    if outcome is hr.HostLockOutcome.HELD_BY_OTHER:
        owner = hr.read_record(role)
        if desktop_child:
            # A second pool child is Desktop's own topology, not a conflict.
            _log.debug(
                "another Desktop backend holds the %s record (%s)",
                role,
                hr.describe(owner) if owner else "owner unknown",
            )
            return
        _log.warning(
            "Another backend already owns this host (%s); this one bound anyway "
            "(observe-only). Multiplex-only expects exactly one backend per host.",
            hr.describe(owner) if owner else "owner unknown",
        )
        return
    app.state.host_role = role
    hr.publish_record(
        role,
        host=host,
        port=port,
        profiles=hr.served_profiles(),
        # The live session token, so an attaching client of the same OS user can
        # authenticate even when the backend is gated and `GET /` withholds it.
        token=_SESSION_TOKEN,
    )
    # SIGTERM included: it is the normal stop, and it does not run atexit here.
    hr.cleanup_on_exit(role)


def print_dashboard_remote_hint(port):
    """Brand-purple SSH-tunnel access notice for a loopback dashboard reached
    over SSH (a remote server). Prints the Clawksis wordmark above it. Purple is
    used only on what matters — the headline and the command to copy."""
    _ssh_parts = os.environ.get("SSH_CONNECTION", "").split()
    _server_ip = _ssh_parts[2] if len(_ssh_parts) >= 3 else "<este-servidor>"
    _ssh_user = os.environ.get("USER") or "root"
    _p = "\033[38;2;108;79;214m"  # Clawksis brand purple (#6C4FD6)
    _b = "\033[1m"
    _x = "\033[0m"
    try:
        from clawk_cli.banner import print_clawksis_banner

        print_clawksis_banner()
    except Exception:
        pass
    print(
        f"{_p}{_b}▼ Estás en un servidor remoto — para verlo en tu navegador, "
        f"corré el túnel en TU COMPUTADORA (no en este servidor):{_x}\n"
        f"  1) Dejá ESTA terminal abierta (acá corre el dashboard).\n"
        f"  2) En tu PC abrí OTRA terminal (PowerShell/Terminal) y pegá esto, "
        f"dejala abierta:\n"
        f"{_p}{_b}        ssh -L {port}:127.0.0.1:{port} {_ssh_user}@{_server_ip}{_x}\n"
        f"  3) Recién ahí, en el navegador, abrí:  {_b}http://127.0.0.1:{port}{_x}\n"
        f"  · Si en cambio corrés esto en tu propia PC (no un servidor), ignorá lo de "
        f"arriba: abrí {_b}http://127.0.0.1:{port}{_x} directamente."
    )


def _on_server_started(
    server,
    *,
    host: str,
    port: int,
    headless: bool,
    isolated: bool,
    open_browser: bool,
    initial_profile: str,
    start_mcp_discovery_after_bind: bool,
    ssh_lock_path: Optional[Path] = None,
) -> None:
    """Post-bind arming on the serving loop right after ``server.startup()``.

    Reap prior corpses, parent-death watchdog, process identity, READY
    announcement, browser open, deferred MCP discovery, loop-noise filter,
    loop heartbeat.
    """

    # Clear corpses from a previous unclean Desktop exit (crash/SIGKILL/update
    # handoff leaves an orphaned backend + its MCP subtree) before stacking a
    # new tree (EMFILE / missing tabs). The watchdog only protects *this*
    # process going forward.
    def _reap_desktop_serves() -> None:
        from clawk_cli.dashboard_procs import _reap_orphaned_desktop_local_serves

        _reap_orphaned_desktop_local_serves()

    def _reap_mcp_helpers() -> None:
        from clawk_cli.process_identity import reap_orphaned_mcp_helpers

        reap_orphaned_mcp_helpers()

    if is_desktop_owned_backend():
        _best_effort("orphan desktop-local serve reap", _reap_desktop_serves)
    # Same sweep for stdio MCP helpers (#61514): positive identity only (spawn
    # ledger + spawner provably dead); anything alive or unprovable is untouched.
    _best_effort("orphan MCP helper reap", _reap_mcp_helpers)

    # No-op for standalone `clawk serve` (no CLAWK_PARENT_PID).
    _start_parent_death_watchdog()
    # SSH-isolated backends are detached from any parent on purpose (#91668); their liveness signal
    # is "does a client still hold a WebSocket" (#101626).
    if getattr(app.state, "ssh_isolated_clients", None) is not None:
        from clawk_cli.web_server_idle_exit import (
            DEFAULT_IDLE_GRACE_S,
            start_idle_watchdog,
        )

        try:
            grace = float(
                (load_config().get("dashboard") or {}).get(
                    "ssh_isolated_idle_grace_s", DEFAULT_IDLE_GRACE_S
                )
            )
        except (TypeError, ValueError):
            grace = DEFAULT_IDLE_GRACE_S
        start_idle_watchdog(server, app.state.ssh_isolated_clients, grace_s=grace)
    if (
        getattr(app.state, "ssh_isolated_clients", None) is not None
        or is_desktop_owned_backend()
    ):
        # The host's updater never restarts this backend (SSH-isolated: only the remote Desktop
        # client holds its token and owner nonce, #91668/#101626; Desktop-owned local serve:
        # the updater defers to the app's ledger-verified restart and the backend otherwise
        # outlives the handoff, #99859), so it retires itself (between turns) when the install
        # moves on. The retirement fence closes admission process-wide before the exit, so a
        # connected Desktop just sees its next request reconnect-respawn the backend on new code.
        from clawk_cli.web_server_skew_exit import start_code_skew_watchdog

        start_code_skew_watchdog(server)
    if (
        getattr(app.state, "ssh_isolated_clients", None) is not None
        and ssh_lock_path
        and _SSH_OWNER_NONCE
    ):
        # A reconnect that cannot prove this pid is its own drops the lock without signalling us
        # and spawns a new nonce (#132034); retire (between turns) once the lock names that spawn.
        from clawk_cli.web_server_owner_exit import start_owner_watchdog

        start_owner_watchdog(server, lock_path=ssh_lock_path, nonce=_SSH_OWNER_NONCE)

    actual_port = _read_bound_port(server, fallback=port)
    app.state.bound_port = actual_port
    # Published by /api/host/identity: an attaching `clawk dashboard` must never be routed to a
    # headless backend (a URL with no UI behind it).
    app.state.serves_spa = not headless

    # Positive process identity in the machine spawn ledger (+ Windows
    # kill-on-close job). Registered AFTER the bind so the entry carries the
    # ACTUAL port — what lets `clawk update` relaunch a manually-started serve
    # on its real endpoint (#63206).
    def _register_identity() -> None:
        from clawk_cli.process_identity import (
            attach_self_to_kill_on_close_job,
            register_self,
        )

        register_self(
            "serve" if headless else "dashboard",
            detail={
                "host": host,
                "port": actual_port,
                "profile": initial_profile or "",
                "isolated": isolated,
            },
        )
        attach_self_to_kill_on_close_job()

    _best_effort("process-identity registration", _register_identity)

    # Host rendezvous (multiplex-only): the host lock + record that let a SECOND `clawk serve`
    # for any profile find this process and attach instead of binding a second port. Published
    # after the bind so the record carries the real port, and beside — not instead of — the
    # spawn-ledger entry above, which Desktop's attach ladder reads.
    _best_effort(
        "host rendezvous publish", lambda: _publish_host_rendezvous(host, actual_port)
    )

    _write_dashboard_ready_file(actual_port)
    # Port-discovery sentinel parsed by the Desktop spawn. Written to fd 1:
    # tui_gateway.server redirects sys.stdout to stderr at import, and the
    # Desktop watches child.stdout (#96282). A headless `serve` announces the
    # neutral token FIRST and the legacy CLAWK_DASHBOARD_READY one after it:
    # a packaged Desktop artifact whose parser predates the neutral token
    # (#60772) still matches the legacy sentinel, while current parsers match
    # either. The legacy `dashboard` backend keeps its own single token.
    if headless:
        _write_machine_sentinel_line(f"CLAWK_BACKEND_READY port={actual_port}")
        _write_machine_sentinel_line(f"CLAWK_DASHBOARD_READY port={actual_port}")
    else:
        _write_machine_sentinel_line(f"CLAWK_DASHBOARD_READY port={actual_port}")
    if headless:
        # Auth-gated JSON-RPC/WS only — announce the bind, not a URL. flush:
        # a piped stdout otherwise surfaces this minutes after the sentinel.
        print(f"  Clawksis backend listening on {host}:{actual_port}", flush=True)
    else:
        from clawk_cli.url_utils import format_url_host

        print(f"  Clawksis Web UI → http://{format_url_host(host)}:{actual_port}")
        print(
            "  (running in the foreground — press Ctrl+C to stop; add `&` or use "
            "nohup/systemd to keep it serving after you log out)"
        )
        if host in _LOOPBACK_HOST_VALUES and (
            os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY")
        ):
            print_dashboard_remote_hint(actual_port)
    _maybe_open_browser(host, actual_port, open_browser, initial_profile)

    if start_mcp_discovery_after_bind:
        # Desktop `serve`: the ~350ms `mcp` SDK import holds the GIL while the
        # renderer does its WS handshake + first hydration reads, so arm it one
        # second later when the shell is painted and idle. An agent build inside
        # that second fires the deferred start itself (wait_for_mcp_discovery).
        try:
            from clawk_cli.mcp_startup import defer_background_mcp_discovery

            defer_background_mcp_discovery(
                logger=_log,
                thread_name="dashboard-mcp-discovery",
                delay=_DESKTOP_MCP_DISCOVERY_DELAY_S,
            )
        except Exception:
            _log.debug("Deferred MCP discovery arm failed", exc_info=True)

    # Collapse the peer-hangup teardown flood (#50005): 50+ identical WinError
    # 10054 tracebacks per Desktop disconnect become one debug line.
    def _install_noise_filter() -> None:
        from tui_gateway.loop_noise import install_loop_noise_filter

        install_loop_noise_filter(asyncio.get_running_loop())

    _best_effort("loop noise filter install", _install_noise_filter)

    # Loop heartbeat watchdog (CF-1): a 2s call_later tick whose drift equals
    # any GIL stall, so a stalled-loop WS drop is diagnosable from the log.
    # call_later (not a task) dies with the loop — nothing to cancel.
    _hb_interval = 2.0
    _hb_stall_threshold = 5.0
    _hb_loop = asyncio.get_running_loop()

    def _loop_heartbeat(expected: float) -> None:
        now = _hb_loop.time()
        drift = now - expected
        if drift > _hb_stall_threshold:
            _log.warning("event loop stalled %.1fs (GIL pressure suspected)", drift)
        _hb_loop.call_later(_hb_interval, _loop_heartbeat, now + _hb_interval)

    _hb_loop.call_later(_hb_interval, _loop_heartbeat, _hb_loop.time() + _hb_interval)


def _windows_serve_loop_factory(config):
    """Loop factory for serve on Windows: always a selector loop.

    uvicorn 0.41's ``asyncio_loop_factory`` returns ProactorEventLoop on
    win32, on which uvicorn's socket stack binds-but-never-accepts (READY
    prints, then WinError 10014 accept failures, exit 1, desktop
    ECONNREFUSED — #120164, regression of #50641). A factory that already
    yields selector loops (older uvicorn, explicit ``--loop``) passes through.
    """
    factory = config.get_loop_factory()
    if factory is None or factory is asyncio.ProactorEventLoop:  # type: ignore[attr-defined]
        return asyncio.SelectorEventLoop
    return factory


def _run_serve(serve, config, host: str, port: int) -> None:
    """Drive ``serve()`` on the loop uvicorn expects.

    POSIX keeps ``asyncio.run`` (already a SelectorEventLoop / uvloop). On
    Windows ``asyncio.run`` defaults to a ProactorEventLoop, on which uvicorn
    binds a socket that never accepts (#50641), so mirror uvicorn's own runner +
    loop factory there (hand-installed selector policy for uvicorn < 0.36).
    Ctrl+C -> clean return; probe-to-bind port race -> sentinel + exit code.
    """
    runner = asyncio.run
    runner_kwargs: dict = {}
    if sys.platform == "win32":
        # Resolved FIRST; the serve call is outside this try so genuine
        # serve-time errors (port in use) propagate instead of double-running.
        try:
            from uvicorn._compat import asyncio_run as runner

            runner_kwargs = {"loop_factory": _windows_serve_loop_factory(config)}
        except Exception:
            runner = asyncio.run
            runner_kwargs = {}
            try:
                asyncio.set_event_loop_policy(
                    asyncio.WindowsSelectorEventLoopPolicy()  # type: ignore[attr-defined]
                )
            except Exception:
                pass

    # ``capture_signals()`` re-raises the captured signal after graceful
    # shutdown; console Ctrl+C lands as KeyboardInterrupt = clean exit.
    # (Re-raised SIGTERM/SIGBREAK keep their terminate disposition.)
    try:
        runner(serve(), **runner_kwargs)
    except KeyboardInterrupt:
        return
    except SystemExit as exc:
        # Probe-to-bind race (#93608): uvicorn's bind_socket() exits 1 — re-check
        # and translate a confirmed conflict into the sentinel + distinct code.
        if exc.code == 1 and _port_bind_conflict(host, port):
            _report_port_in_use(host, port)
            raise SystemExit(PORT_IN_USE_EXIT_CODE) from None
        raise


def start_server(
    host: str = "127.0.0.1",
    port: int = 9119,
    open_browser: bool = True,
    allow_public: bool = False,
    initial_profile: str = "",
    headless: bool = False,
    isolated: bool = False,
    ssh_session_token: Optional[str] = None,
    ssh_owner_nonce: Optional[str] = None,
    start_mcp_discovery_after_bind: bool = False,
    ssh_lock_path: Optional[Path] = None,
):
    """Start the web UI server.

    ``initial_profile`` is appended to the auto-opened URL as ``?profile=<name>``
    (profile alias ``<profile> dashboard``). ``headless`` is the ``serve`` path:
    JSON-RPC/WS backend, no UI build, no SPA mount (``CLAWK_SERVE_HEADLESS``).
    ``isolated`` (``--isolated``) is recorded in the spawn ledger so attach-first
    discovery never adopts this process.
    ``ssh_session_token``/``ssh_owner_nonce`` are process-local Desktop SSH
    bootstrap state, never persisted or exported to children; ``ssh_lock_path`` is the
    Desktop's ``backend.lock.json`` for that ownership slot (supersession watchdog).
    ``start_mcp_discovery_after_bind`` (Desktop ``serve``) defers MCP discovery
    until the ready sentinel is written so its SDK import can't hold the GIL
    against the pre-bind path.
    """
    _apply_ssh_session_token(ssh_session_token or "")
    _apply_ssh_owner_nonce(ssh_owner_nonce)

    # Dashboard-mode starts don't route through main.py's `serve` path, which
    # applies the same RLIMIT_NOFILE floor (policy in resource_limits, #81547).
    from clawk_cli.resource_limits import apply_nofile_soft_limit

    apply_nofile_soft_limit()

    import uvicorn

    _configure_auth_gate(host, allow_public, ssh_session_token, ssh_owner_nonce)

    # host_header_middleware validates Host against this (DNS rebinding,
    # GHSA-ppp5-vxwm-4cf7).
    app.state.bound_host = host
    # The SPA bootstrap reads this so profile-less deep links (/chat?resume=<id>) inherit the
    # launcher's preselected profile instead of silently running in the launch scope (#73085).
    app.state.initial_profile = str(initial_profile or "")

    config, server = _build_uvicorn_server(
        host, port, ssh_isolated=bool(ssh_session_token)
    )

    # Flush-on-kill guard (#94724): chaining SIGTERM/SIGINT handlers persist
    # in-memory transcripts to state.db before shutdown. Installed BEFORE
    # uvicorn's capture_signals() so uvicorn re-raises into them as the
    # "original" handlers — kills outside the serve window are covered too.
    try:
        from tui_gateway.server import install_exit_flush_signal_handlers

        install_exit_flush_signal_handlers()
    except Exception as exc:
        _log.debug("exit-flush signal handlers not installed: %s", exc)

    # #93608: uvicorn's bind_socket() would exit 1 with a bare ERROR line,
    # indistinguishable from "backend broken". Probe first so a conflict
    # surfaces as the BACKEND_PORT_IN_USE sentinel + distinct exit code.
    # ``--port 0`` is skipped by the probe.
    if _port_bind_conflict(host, port):
        _report_port_in_use(host, port)
        raise SystemExit(PORT_IN_USE_EXIT_CODE)

    # LAST boot step, deliberately. One host process serves every profile and this one can be asked
    # for any of them via ``?profile=``, so the decision is made here instead of on the first such
    # request — activation is one-way, and everything the backend had already done by then
    # (idle-reaper flushes, hosted rooms, cron) stayed on single-profile assumptions. It runs after
    # the keepalive / auth gate / uvicorn build because activation FREEZES ``os.environ`` as the
    # launch profile's credentials, and that snapshot is the only source for launch keys with no
    # ``.env`` to rebuild from (systemd ``Environment=``, ``op run``, Compose): anything injected or
    # rotated by a later boot step would otherwise be invisible for the process lifetime. No-op on a
    # single-profile host; `gateway.multiplex_profiles: false` is retired and no longer skips it.
    try:
        from tui_gateway.launch_profile_policy import (
            activate_multi_profile_hosting_eagerly,
        )

        activate_multi_profile_hosting_eagerly()
    except Exception:
        _log.warning("eager multi-profile activation failed", exc_info=True)

    async def _serve():
        # startup split from main_loop so the bound (ephemeral) port is readable.
        if not config.loaded:
            config.load()
        server.lifespan = config.lifespan_class(config)
        with server.capture_signals():
            await server.startup()
            if server.should_exit:
                return

            _on_server_started(
                server,
                host=host,
                port=port,
                headless=headless,
                isolated=isolated,
                open_browser=open_browser,
                initial_profile=initial_profile,
                start_mcp_discovery_after_bind=start_mcp_discovery_after_bind,
                ssh_lock_path=ssh_lock_path,
            )
            if headless:
                from clawk_cli.observability.shared_metrics_startup import (
                    record_process_ready,
                )

                record_process_ready("serve_boot", background=True)

            await server.main_loop()
            if server.started:
                await server.shutdown()

    _run_serve(_serve, config, host, port)
