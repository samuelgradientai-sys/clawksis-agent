"""``scrape`` — one-call anti-bot web fetch backed by the Scrapling CLI.

The ``scrapling-official`` skill is powerful but makes the agent hand-write
Python each time, which is where it tripped (`.text` vs `.body`, `--impersonate
Chrome` curl_cffi version quirks, parsing). This tool wraps the documented
``scrapling extract`` CLI so the common case — "fetch this anti-bot page and
give me the content" — is a single call that can't get the API wrong.

When to reach for it (also encoded in the schema so the model self-selects):
  * web_fetch / web_extract returned empty, a JS-required/consent page, or 403
  * the site is behind Cloudflare / Turnstile / fingerprint anti-bot
  * a page needs JavaScript to render

When it will NOT help (and the tool says so in its result, instead of letting
the agent brute-force it):
  * 429 / "too many requests" / "unusual traffic" / captcha → that is IP
    reputation, not fingerprint. Scrapling cannot bypass it without a proxy.
    Set ``SCRAPLING_PROXY`` (a residential proxy) or pass ``proxy=``.
  * search engines (Google/DuckDuckGo/Bing) → use the ``web_search`` tool.

The full skill stays for advanced work (spiders, sessions, custom parsing).

Binary discovery: ``SCRAPLING_BIN`` env → ``scrapling`` on PATH →
``python -m scrapling``. Proxy: ``proxy`` arg → ``SCRAPLING_PROXY`` env →
``web.scrapling_proxy`` in config.yaml.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from tools.registry import registry, tool_result

try:
    from tools.scrapegraph_common import clamp_timeout
except ImportError:
    # Fallback when scrapegraph_common is unavailable (unlikely — same package).
    # Inline minimal clamp to keep the scrape tool self-sufficient.
    def clamp_timeout(raw_timeout):  # type: ignore[misc]
        if raw_timeout is None:
            return None
        try:
            return max(10, min(300, int(raw_timeout)))
        except (ValueError, TypeError):
            return None

logger = logging.getLogger(__name__)

_MODE_TO_SUBCMD = {
    "get": "get",
    "fetch": "fetch",
    "stealthy": "stealthy-fetch",
}
# auto escalates cheap → expensive, the same ladder the skill recommends.
_AUTO_LADDER = ["get", "fetch", "stealthy"]
_FORMAT_EXT = {"markdown": ".md", "text": ".txt", "html": ".html"}

# Content shorter than this (after strip) is treated as "empty/blocked".
_MIN_USEFUL_CHARS = 200
_MAX_RESULT_CHARS = 30000
# A genuine block/challenge page is short and template-y. Above this size we
# assume real content even if it happens to mention "captcha"/"forbidden" in the
# body (e.g. a captcha-demo or a security article) — those ambiguous markers
# only count on a short page; the strong phrases below fire at any size.
_BLOCK_PAGE_MAX_CHARS = 1500

# Unambiguous "blocked by IP reputation / rate-limit" — Scrapling can't fix these
# without a proxy. Fire regardless of page size.
_IP_BLOCK_STRONG = (
    "too many requests",
    "unusual traffic",
    "rate limit exceeded",
    "you have been blocked",
    "verify you are human",
    "select all squares containing",
)
# Ambiguous block words — only count as a block on a SHORT page.
_IP_BLOCK_WEAK = (
    "captcha",
    "are you a robot",
    "access denied",
    "forbidden",
    "429",
    "403",
)
# Unambiguous anti-bot / JS interstitials — escalating to a stealthier mode helps.
_ANTIBOT_STRONG = (
    "just a moment",  # Cloudflare interstitial
    "checking your browser before",
    "cf-browser-verification",
    "ddos protection by",
)
_ANTIBOT_WEAK = ("enable javascript", "please enable js")


def _scrapling_cmd() -> Optional[List[str]]:
    """Return the base command to invoke the scrapling CLI, or None if absent."""
    override = os.environ.get("SCRAPLING_BIN")
    if override and (shutil.which(override) or Path(override).exists()):
        return [override]
    found = shutil.which("scrapling")
    if found:
        return [found]
    # Fall back to the module entrypoint if the package is importable.
    try:
        import importlib.util

        if importlib.util.find_spec("scrapling") is not None:
            return [sys.executable, "-m", "scrapling"]
    except (ImportError, OSError):
        logger.debug("scrape: scrapling module import check failed")
    return None


def _resolve_proxy(arg_proxy: Optional[str]) -> Optional[str]:
    if arg_proxy:
        return arg_proxy
    env_proxy = os.environ.get("SCRAPLING_PROXY")
    if env_proxy:
        return env_proxy
    try:
        from clawk_cli.config import load_config

        cfg = load_config() or {}
        web_cfg = cfg.get("web") if isinstance(cfg, dict) else None
        if isinstance(web_cfg, dict):
            p = web_cfg.get("scrapling_proxy")
            if isinstance(p, str) and p.strip():
                return p.strip()
    except (ImportError, OSError, TypeError):
        logger.debug("scrape: config load failed")
    return None


def _classify(content: str) -> str:
    """'ok' | 'antibot' | 'ip_block' | 'empty' for the given page content."""
    stripped = content.strip()
    head = stripped[:2000].lower()
    # Strong phrases are real block/challenge pages at ANY size — check before
    # the empty gate so even a bare "Too many requests" page is flagged.
    if any(m in head for m in _IP_BLOCK_STRONG):
        return "ip_block"
    if any(m in head for m in _ANTIBOT_STRONG):
        return "antibot"
    n = len(stripped)
    if n < _MIN_USEFUL_CHARS:
        return "empty"
    # Ambiguous words only count as a block on a short, template-y page — a long
    # page that merely mentions "captcha"/"forbidden" is real content.
    if n <= _BLOCK_PAGE_MAX_CHARS:
        if any(m in head for m in _IP_BLOCK_WEAK):
            return "ip_block"
        if any(m in head for m in _ANTIBOT_WEAK):
            return "antibot"
    return "ok"


def _run_one(
    base: List[str],
    subcmd: str,
    url: str,
    ext: str,
    css_selector: Optional[str],
    wait_selector: Optional[str],
    proxy: Optional[str],
    timeout_s: int,
) -> Tuple[bool, str, str]:
    """Run one `scrapling extract <subcmd>`; return (ran_ok, content, stderr)."""
    fd, out_path = tempfile.mkstemp(suffix=ext, prefix="scrape_")
    os.close(fd)
    try:
        # --ai-targeted is mandatory per the skill: sanitizes hidden elements
        # (prompt-injection guard) + enables ad-blocking on browser modes.
        cmd = [*base, "extract", subcmd, url, out_path, "--ai-targeted"]
        if css_selector:
            cmd += ["--css-selector", css_selector]
        if proxy:
            cmd += ["--proxy", proxy]
        if wait_selector and subcmd != "get":
            cmd += ["--wait-selector", wait_selector]
        # Pass the timeout to the scrapling CLI as well. For browser modes
        # (fetch / stealthy-fetch), the CLI expects milliseconds; for `get`,
        # the CLI expects seconds (both default to 30s/30000ms).
        if timeout_s:
            if subcmd == "get":
                cmd += ["--timeout", str(timeout_s)]
            else:
                cmd += ["--timeout", str(timeout_s * 1000)]
        # stealthy-fetch can auto-solve Cloudflare interstitials, but the flag
        # defaults off — turn it on since this tool exists to beat anti-bot.
        if subcmd == "stealthy-fetch":
            cmd += ["--solve-cloudflare"]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s
            )
        except subprocess.TimeoutExpired:
            return False, "", f"timed out after {timeout_s}s"
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            logger.warning("scrape: subprocess error for %s (%s)", url, exc)
            return False, "", f"subprocess error: {exc}"
        content = ""
        try:
            content = Path(out_path).read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("scrape: failed to read output %s (%s)", out_path, exc)
            content = ""
        ran_ok = proc.returncode == 0 and bool(content.strip())
        return ran_ok, content, (proc.stderr or "").strip()
    finally:
        try:
            os.unlink(out_path)
        except OSError as exc:
            logger.debug("scrape: cleanup of %s failed (%s)", out_path, exc)


async def _handle_scrape(args, **kw):
    url = (args.get("url") or "").strip()
    if not url:
        return tool_result(ok=False, error="`url` is required.")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    mode = (args.get("mode") or "auto").strip().lower()
    if mode not in ("auto", "get", "fetch", "stealthy"):
        mode = "auto"
    fmt = (args.get("format") or "markdown").strip().lower()
    ext = _FORMAT_EXT.get(fmt, ".md")
    css_selector = (args.get("css_selector") or "").strip() or None
    wait_selector = (args.get("wait_selector") or "").strip() or None
    proxy = _resolve_proxy((args.get("proxy") or "").strip() or None)

    # User-provided timeout per-mode override. Clamped to [10, 300]
    # by the shared clamp_timeout() helper (reused by scrapegraph tools too).
    user_timeout = clamp_timeout(args.get("timeout"))

    base = _scrapling_cmd()
    if base is None:
        return tool_result(
            ok=False,
            error=(
                "Scrapling is not installed. Install it once with: "
                'pip install "scrapling[all]>=0.4.9" && scrapling install '
                "(or open the scrapling-official skill). If it's installed in a "
                "venv not on PATH, set SCRAPLING_BIN to its full path."
            ),
        )

    ladder = _AUTO_LADDER if mode == "auto" else [mode]

    attempts: List[str] = []
    best_content = ""
    best_status = "empty"
    last_stderr = ""
    for m in ladder:
        subcmd = _MODE_TO_SUBCMD[m]
        # Browser modes get a longer budget than the fast HTTP `get`.
        # User-provided timeout overrides the per-mode default.
        timeout_s = (
            user_timeout
            if user_timeout is not None
            else (45 if subcmd == "get" else 90)
        )
        ran_ok, content, stderr = await asyncio.to_thread(
            _run_one,
            base,
            subcmd,
            url,
            ext,
            css_selector,
            wait_selector,
            proxy,
            timeout_s,
        )
        last_stderr = stderr or last_stderr
        status = _classify(content) if content else "empty"
        attempts.append(f"{m}:{status if content else 'failed'}")
        if content and len(content.strip()) > len(best_content.strip()):
            best_content, best_status = content, status
        if ran_ok and status == "ok":
            break
        # IP-block / captcha won't improve with a stealthier browser — stop the
        # ladder and report the real cause instead of burning more attempts.
        if status == "ip_block":
            break

    content = best_content.strip()
    truncated = False
    if len(content) > _MAX_RESULT_CHARS:
        content = content[:_MAX_RESULT_CHARS]
        truncated = True

    if best_status == "ip_block":
        return tool_result(
            ok=False,
            url=url,
            attempts=attempts,
            reason="ip_block",
            error=(
                "Blocked by IP reputation / rate-limit / captcha — NOT a "
                "fingerprint problem, so Scrapling can't bypass it from this "
                "server's IP. Options: (1) for a search query use the web_search "
                "tool, not direct scraping; (2) set a residential proxy via the "
                "SCRAPLING_PROXY env var (or web.scrapling_proxy in config) and "
                "retry; (3) use an official API if the site has one."
            ),
            content=content or None,
        )

    if not content:
        return tool_result(
            ok=False,
            url=url,
            attempts=attempts,
            error=(
                "No content returned"
                + (f" (scrapling: {last_stderr})" if last_stderr else "")
                + ". The page may need a different mode, a proxy, or login."
            ),
        )

    return tool_result(
        ok=True,
        url=url,
        mode_used=attempts[-1] if attempts else mode,
        attempts=attempts,
        status=best_status,
        format=fmt,
        truncated=truncated,
        content=content,
    )


SCRAPE_SCHEMA = {
    "name": "scrape",
    "description": (
        "Fetch a web page with anti-bot bypass (Cloudflare/Turnstile, stealth, "
        "JavaScript rendering) via Scrapling and return its content in ONE call. "
        "Reach for this when web_fetch/web_extract returned empty, a "
        "JS-required/consent page, or HTTP 403, or when the site is behind "
        "Cloudflare/anti-bot. Do NOT use it to get past HTTP 429 / 'too many "
        "requests' / captchas — that is IP reputation, which needs a proxy "
        "(set SCRAPLING_PROXY), not a stealthier browser. Do NOT scrape search "
        "engines (Google/DuckDuckGo/Bing) — use the web_search tool instead. "
        "For spiders, sessions, or custom parsing, use the scrapling-official skill."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The page URL to fetch."},
            "mode": {
                "type": "string",
                "enum": ["auto", "get", "fetch", "stealthy"],
                "description": (
                    "auto (default): try fast HTTP, escalate to headless browser, "
                    "then full stealth as needed. get: fast HTTP only (no JS). "
                    "fetch: headless browser + JS. stealthy: max anti-bot bypass."
                ),
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "text", "html"],
                "description": "Output format (default markdown).",
            },
            "css_selector": {
                "type": "string",
                "description": "Optional CSS selector — return only matching content.",
            },
            "wait_selector": {
                "type": "string",
                "description": "Browser modes only: wait for this CSS selector before extracting.",
            },
            "proxy": {
                "type": "string",
                "description": (
                    "Optional proxy URL (http://user:pass@host:port). Overrides "
                    "the SCRAPLING_PROXY env var / config for this call."
                ),
            },
            "timeout": {
                "type": "integer",
                "minimum": 10,
                "maximum": 300,
                "description": (
                    "Max seconds for each mode attempt (min 10, max 300). "
                    "Without this, the tool uses per-mode defaults (45s for "
                    "HTTP `get`, 90s for browser modes). Increase for slow "
                    "pages or when the scrapling CLI needs more time."
                ),
            },
        },
        "required": ["url"],
    },
}


registry.register(
    name="scrape",
    toolset="web",
    schema=SCRAPE_SCHEMA,
    handler=_handle_scrape,
    is_async=True,
    emoji="🕷️",
    max_result_size_chars=_MAX_RESULT_CHARS + 2000,
)
