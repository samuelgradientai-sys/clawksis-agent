""" "Mi Chrome" pairing: one extension device token per profile, stored only as a SHA-256 hash.

The dashboard shows the pairing string ONCE (``clawk-mychrome:<base64url JSON>`` carrying the
dashboard URL and the token); the profile home keeps ``my_chrome/pairing.json`` (0600) with the
token's hash. Pairing again replaces the token (the old extension is refused from then on) and
revoking deletes it. The token is 256 bits of randomness, so a plain hash is enough at rest, and it
is compared in constant time. It reaches the server as a WebSocket subprotocol value — never a
query string, which would land in access logs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlsplit

from tools.browser_my_chrome_state import state_dir

PAIRING_PREFIX = "clawk-mychrome:"
SUBPROTOCOL = "clawk-mychrome.v1"
_TOKEN_RE = re.compile(r"^mc1\.[A-Za-z0-9_-]{43}$")
_PAIRING_FILE = "pairing.json"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def pairing_path(home: Path) -> Path:
    return state_dir(home) / _PAIRING_FILE


def dashboard_base(url: str) -> str:
    """``scheme://host[:port][/prefix]`` of an http(s) dashboard URL; ValueError otherwise."""
    parts = urlsplit(str(url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("dashboard URL must be http(s)")
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def pairing_string(base_url: str, token: str) -> str:
    blob = json.dumps({"v": 1, "u": dashboard_base(base_url), "t": token}).encode()
    return PAIRING_PREFIX + _b64url(blob)


def new_pairing(home: Path, base_url: str) -> str:
    """Mint this profile's device token (replacing any previous one) and return the pairing
    string to show the user once."""
    from utils import atomic_json_write

    token = "mc1." + _b64url(secrets.token_bytes(32))
    shown = pairing_string(base_url, token)
    directory = state_dir(home)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_json_write(
        pairing_path(home),
        {"token_sha256": _digest(token), "created_at": time.time()},
        mode=0o600,
    )
    return shown


def revoke_pairing(home: Path) -> bool:
    """Forget this profile's device token; True when there was one."""
    try:
        pairing_path(home).unlink()
    except FileNotFoundError:
        return False
    return True


def pairing_info(home: Path) -> Optional[dict]:
    """``{"created_at"}`` when this profile has a paired device, else None (no secret material)."""
    from utils import read_json_or_empty

    data = read_json_or_empty(pairing_path(home))
    if not isinstance(data.get("token_sha256"), str):
        return None
    return {"created_at": data.get("created_at")}


def token_matches(home: Path, token: str) -> bool:
    from utils import read_json_or_empty

    stored = read_json_or_empty(pairing_path(home)).get("token_sha256")
    if not isinstance(stored, str) or not _TOKEN_RE.match(token or ""):
        return False
    return hmac.compare_digest(stored.encode(), _digest(token).encode())


def offered_token(subprotocols: Iterable[str]) -> Optional[str]:
    """The device token among the WebSocket subprotocols the extension offered, when it also
    offered the Mi Chrome protocol itself."""
    offered = [str(p).strip() for p in subprotocols or ()]
    if SUBPROTOCOL not in offered:
        return None
    return next((p for p in offered if _TOKEN_RE.match(p)), None)


def home_for_token(token: str, homes: Iterable[Path]) -> Optional[Path]:
    """The profile home whose pairing ``token`` belongs to, checking every candidate (so the
    time taken does not say which profiles exist)."""
    match: Optional[Path] = None
    for home in homes:
        if token_matches(home, token) and match is None:
            match = home
    return match
