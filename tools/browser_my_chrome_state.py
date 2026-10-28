"""Cross-process "Mi Chrome" endpoint, one per profile home.

The dashboard process hosts the extension relay and its loopback CDP endpoint
(``clawk_cli/web_routers/my_chrome.py``); the agents that should drive it run in that process
(dashboard chat) AND in the separate messaging gateway (Telegram). ``/browser connect``'s live
override is process-local, so the endpoint is published here instead: ``<profile home>/my_chrome/
relay.json`` (0600) holds the loopback URL, the dashboard's pid (+ start time, so a crashed
dashboard is never trusted) and an epoch bumped on every publish and clear.

Readers: :func:`my_chrome_cdp_url` is the CDP override (``browser_tool_cdp._get_cdp_override_raw``
consults it right after the live ``/browser connect``), live only while ``browser.my_chrome.enabled``
is on and the extension is connected. :func:`sync_relay_endpoint` runs before a browser session is
reused: when the profile's endpoint changed since this process last looked (the extension connected
or disconnected, the dashboard restarted), the profile's browsers are reaped like ``/browser connect``
does, so the next call lands on the new endpoint, or back on the VPS browser.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STATE_DIRNAME = "my_chrome"
# A cron job's ``browser`` choice, pinned for its own worker process: "my_chrome" (the user's
# Chrome or nothing) or "server" (the VPS browser, never the user's Chrome).
BROWSER_ROUTE_ENV = "CLAWK_BROWSER_ROUTE"
JOB_BROWSER_CHOICES = ("my_chrome", "server")


def _pinned_route() -> str:
    return os.environ.get(BROWSER_ROUTE_ENV, "").strip()


_RELAY_FILE = "relay.json"

_seen: dict[str, str] = {}
_seen_lock = threading.Lock()


def state_dir(home: Path) -> Path:
    return Path(home) / STATE_DIRNAME


def relay_state_path(home: Path) -> Path:
    return state_dir(home) / _RELAY_FILE


def _read(home: Path) -> dict:
    from utils import read_json_or_empty

    return read_json_or_empty(relay_state_path(home))


def _write(home: Path, payload: dict) -> None:
    from utils import atomic_json_write

    directory = state_dir(home)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_json_write(relay_state_path(home), payload, mode=0o600)


def _epoch(data: dict) -> int:
    try:
        return int(data.get("epoch") or 0)
    except (TypeError, ValueError):
        return 0


def publish_relay(home: Path, cdp_url: str, *, browser: str = "") -> int:
    """Record ``cdp_url`` as this profile's live Mi Chrome endpoint; returns the new epoch."""
    from gateway.status import get_process_start_time

    epoch = _epoch(_read(home)) + 1
    pid = os.getpid()
    _write(
        home,
        {
            "epoch": epoch,
            "cdp_url": cdp_url,
            "pid": pid,
            "pid_start": get_process_start_time(pid),
            "connected_at": time.time(),
            "browser": browser,
        },
    )
    return epoch


def clear_relay(home: Path, cdp_url: Optional[str] = None) -> None:
    """Mark the profile disconnected. With ``cdp_url``, only if that endpoint is still the one
    published (a newer extension connection must not be wiped by an older one closing)."""
    data = _read(home)
    if cdp_url is not None and data.get("cdp_url") != cdp_url:
        return
    if not data.get("cdp_url") and relay_state_path(home).exists():
        return
    _write(home, {"epoch": _epoch(data) + 1, "cdp_url": ""})


def _owner_alive(data: dict) -> bool:
    from gateway.status import _pid_exists, get_process_start_time

    pid = data.get("pid")
    if not isinstance(pid, int) or not _pid_exists(pid):
        return False
    recorded = data.get("pid_start")
    return recorded is None or get_process_start_time(pid) == recorded


def relay_endpoint(home: Path) -> str:
    """The published endpoint when its dashboard is still the live publisher, else ""."""
    data = _read(home)
    url = str(data.get("cdp_url") or "")
    return url if url and _owner_alive(data) else ""


def relay_snapshot(home: Path) -> dict:
    """The published record (without trusting it) plus whether its publisher is alive."""
    data = _read(home)
    return {**data, "live": bool(data.get("cdp_url")) and _owner_alive(data)}


def my_chrome_setting(key: str) -> bool:
    """``browser.my_chrome.<key>`` in the current profile's config.yaml, True only when literally
    ``true`` (every Mi Chrome switch defaults off)."""
    from clawk_cli.config import read_raw_config_readonly

    browser = read_raw_config_readonly().get("browser")
    section = browser.get("my_chrome") if isinstance(browser, dict) else None
    return isinstance(section, dict) and section.get(key) is True


def my_chrome_enabled() -> bool:
    """``browser.my_chrome.enabled``: the dashboard accepts the extension and agents use it."""
    return my_chrome_setting("enabled")


def payments_need_confirmation() -> bool:
    """``browser.my_chrome.confirm_payments``: the USER asked to approve every payment first.
    Off (the default), the agent completes the purchases the user asked for on its own."""
    return my_chrome_setting("confirm_payments")


def my_chrome_cdp_url() -> str:
    """This profile's Mi Chrome CDP endpoint while enabled and connected, else "".

    Like the live ``/browser connect`` override, a multiplexed process with no profile bound
    (a bare thread) answers "" instead of the launch profile's endpoint."""
    from agent.secret_scope import is_multiplex_active
    from clawk_constants import get_clawk_home, get_clawk_home_override

    if get_clawk_home_override() is None and is_multiplex_active():
        return ""
    if _pinned_route() == "server" or not my_chrome_enabled():
        return ""
    return relay_endpoint(get_clawk_home())


OFFLINE_MESSAGE = (
    "Mi Chrome is paired but not connected right now (the Clawksis dashboard is not running, or "
    "the extension in the user's Chrome is off), so this browser action was NOT run on the "
    "server's browser instead: that browser has none of the user's sessions and sites like "
    "LinkedIn block it. Stop the browser part of the task and tell the user to open the "
    "dashboard (clawk dashboard) and check that the Clawksis extension shows as connected; "
    "then retry. (To allow the server browser when Mi Chrome is offline, the user sets "
    "browser.my_chrome.server_fallback: true.)"
)


def offline_refusal() -> str:
    """Why a browser call must not fall back to the server's browser right now, else "".

    Mi Chrome enabled + paired but its endpoint not live means the user expects their own Chrome
    (their sessions, their IP); silently using the VPS browser instead gets accounts blocked.
    ``browser.my_chrome.server_fallback: true`` restores the old fallback."""
    from agent.secret_scope import is_multiplex_active
    from clawk_constants import get_clawk_home, get_clawk_home_override

    if get_clawk_home_override() is None and is_multiplex_active():
        return ""
    route = _pinned_route()
    if route == "server":
        return ""
    home = get_clawk_home()
    if route == "my_chrome":  # this job must run on the user's Chrome or not at all
        return "" if my_chrome_enabled() and relay_endpoint(home) else OFFLINE_MESSAGE
    if not my_chrome_enabled() or my_chrome_setting("server_fallback"):
        return ""
    try:
        from clawk_cli.my_chrome_pairing import pairing_info

        paired = pairing_info(home) is not None
    except (OSError, ValueError):
        logger.debug("Mi Chrome pairing unreadable; treated as unpaired", exc_info=True)
        paired = False
    if not paired or relay_endpoint(home):
        return ""
    return OFFLINE_MESSAGE


def sync_relay_endpoint() -> bool:
    """Reap the current profile's browsers if its Mi Chrome endpoint changed since this process
    last looked; True when it did. Cheap when nothing changed (one small file read)."""
    from clawk_constants import clawk_home_key

    key = clawk_home_key()
    current = my_chrome_cdp_url()
    with _seen_lock:
        previous = _seen.get(key, "")
        if previous == current:
            return False
        _seen[key] = current
    from tools.browser_tool_cdp import bump_live_generation
    from tools.browser_tool_lifecycle import cleanup_profile_browsers

    logger.info(
        "Mi Chrome endpoint %s for this profile; refreshing its browsers",
        "connected" if current else "disconnected",
    )
    bump_live_generation(key)
    cleanup_profile_browsers(key)
    return True
