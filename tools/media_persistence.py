"""
Media Persistence Helper
=========================

Downloads media from provider URLs (FAL, Kling, Pixverse, etc.) and registers
them in the ``media_generations`` table for the gallery feature.

Design:
- Non-blocking with respect to the tool's success: if persistence fails,
  the tool still returns its result normally (we log and swallow).
- Storage layout: ``~/.clawksis/media/YYYY/MM/<uuid>.<ext>``.
- Idempotent: re-registering the same URL is safe (checked by ``original_url``).

Environment flag:
- ``CLAWKSIS_MEDIA_PERSIST_DISABLED=1`` disables persistence entirely.
  Useful for debugging or when the user wants to opt out.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path.home() / ".clawksis" / "media"
STATE_DB = Path.home() / ".clawksis" / "state.db"


def _is_disabled() -> bool:
    """True if persistence is disabled via env var."""
    return os.environ.get("CLAWKSIS_MEDIA_PERSIST_DISABLED", "").strip() in (
        "1",
        "true",
        "True",
    )


def _extract_extension(url: str, fallback: str = "png") -> str:
    """Best-effort extension from URL path."""
    try:
        path = urlparse(url).path
        ext = path.rsplit(".", 1)[-1].lower()
        if ext and len(ext) <= 5 and ext.isalnum():
            return ext
    except Exception:
        pass
    return fallback


def _download_url(url: str, dest: Path, timeout: float = 30.0) -> Optional[int]:
    """Download URL to dest atomically. Returns file size in bytes or None on failure."""
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Clawksis/media-persistence"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        tmp.write_bytes(data)
        tmp.rename(dest)
        return len(data)
    except Exception as e:
        logger.warning("Failed to download %s: %s", url, e)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        return None


def _extract_dimensions(
    file_path: Path, media_type: str
) -> tuple[Optional[int], Optional[int]]:
    """Best-effort dimension extraction. Returns (width, height) or (None, None)."""
    if media_type != "image":
        return (None, None)
    try:
        from PIL import Image  # lazy import — PIL may not be everywhere

        with Image.open(file_path) as img:
            return img.size
    except Exception:
        return (None, None)


def register_media(
    *,
    url: str,
    media_type: str,
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    session_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> Optional[str]:
    """
    Download media from URL and register in media_generations.

    Returns the generated ID on success, None on failure or disabled state.
    NEVER raises — logs and returns None instead. This is by design so that
    tool execution is never impacted by persistence issues.
    """
    if _is_disabled():
        logger.debug("Media persistence disabled via env, skipping")
        return None

    if not url or media_type not in ("image", "video"):
        logger.warning(
            "register_media: invalid args (url=%s, type=%s)", bool(url), media_type
        )
        return None

    try:
        # 1. Idempotencia — si ya existe, no duplicar
        conn = sqlite3.connect(str(STATE_DB))
        cur = conn.cursor()
        cur.execute("SELECT id FROM media_generations WHERE original_url = ?", (url,))
        existing = cur.fetchone()
        if existing:
            conn.close()
            logger.debug("URL already registered: %s", existing[0][:8])
            return existing[0]

        # 2. Download
        media_id = str(uuid.uuid4())
        ext = _extract_extension(
            url, fallback="png" if media_type == "image" else "mp4"
        )
        now = time.time()
        yyyy_mm = time.strftime("%Y/%m", time.localtime(now))
        dest = MEDIA_ROOT / yyyy_mm / f"{media_id}.{ext}"

        file_size = _download_url(url, dest)

        if file_size is None:
            # Registrar como "expired" para que la UI muestre placeholder
            cur.execute(
                """
                INSERT INTO media_generations (
                    id, session_id, message_id, media_type, status,
                    file_path, original_url, file_size_bytes, width, height,
                    prompt, model, provider, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    media_id,
                    session_id,
                    message_id,
                    media_type,
                    "expired",
                    str(dest),
                    url,
                    None,
                    None,
                    None,
                    prompt,
                    model,
                    provider,
                    now,
                ),
            )
            conn.commit()
            conn.close()
            logger.info(
                "Media URL expired/failed, registered as expired: %s", media_id[:8]
            )
            return media_id

        # 3. Dimensions (best effort)
        width, height = _extract_dimensions(dest, media_type)

        # 4. Registrar como ready
        cur.execute(
            """
            INSERT INTO media_generations (
                id, session_id, message_id, media_type, status,
                file_path, original_url, file_size_bytes, width, height,
                prompt, model, provider, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                media_id,
                session_id,
                message_id,
                media_type,
                "ready",
                str(dest),
                url,
                file_size,
                width,
                height,
                prompt,
                model,
                provider,
                now,
            ),
        )
        conn.commit()
        conn.close()

        logger.info(
            "Media registered: id=%s type=%s size=%s bytes",
            media_id[:8],
            media_type,
            file_size,
        )
        return media_id

    except Exception as e:
        logger.exception("register_media failed: %s", e)
        return None
