"""``scrapegraph`` — LLM-powered structured web extraction on our own infra.

Wraps the local ``scrapegraphai`` library so the agent can pull **structured
data** (JSON: tables, prices, listings, contacts, articles) from a web page by
describing what it wants in plain language — no hand-written parsing, no paid
scraping API. It uses the agent's own LLM for the extraction and a local
headless Chromium for JavaScript pages.

How it relates to the other web tools (also encoded in the schema so the model
self-selects):
  * ``scrapegraph``  → structured JSON from a prompt ("get the price + title +
    specs as JSON"). Preferred over Firecrawl/Browserbase when you need DATA,
    not raw text. Costs LLM tokens; runs on our infrastructure.
  * ``web_extract`` / ``scrape`` → raw page content (markdown). Cheaper when you
    just need the text.
  * ``web_search`` → find pages (don't scrape search engines directly).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tools.registry import registry, tool_result
from tools.scrapegraph_common import (
    ScrapegraphUnavailable,
    clamp_timeout,
    classify_scrapegraph_error,
    extract_many,
    extract_structured,
    looks_like_empty_result,
)

logger = logging.getLogger(__name__)

_MAX_RESULT_CHARS = 30000
# Tag appended to a truncated result so the model knows the JSON is INCOMPLETE.
# A bare ``rendered[:limit]`` would otherwise leave a JSON blob that just *ends* —
# it looks finished but a trailing array/object was silently dropped. That's
# misleading for a structured-data tool whose whole point is parseable output.
# Kept short: it counts toward ``_MAX_RESULT_CHARS``.
_TRUNCATION_MARKER = "\n...[TRUNCATED: result exceeds character budget]"
_DEFAULT_PROMPT = (
    "Extract the main, useful content of this page as clean structured data."
)

# Colon-only schemes (no "//") that scrapegraphai can never fetch. Anything
# else — including no scheme at all, or a "host:port" like example.com:8080 —
# is treated as a bare host and gets https:// prepended as before.
_NON_HTTP_SCHEMES = frozenset({
    "mailto",
    "javascript",
    "data",
    "tel",
    "sms",
    "file",
    "about",
    "blob",
    "view-source",
    "chrome",
    "chrome-extension",
    "vscode",
    "ftp",
    "ws",
    "wss",
})


def _is_non_http_scheme(url: str) -> bool:
    """True when ``url`` carries a scheme that isn't http(s).

    ``ftp://x`` / ``git+ssh://y`` (hierarchical schemes) are caught by the
    ``://`` check; ``mailto:`` / ``javascript:`` / ``data:`` etc. (colon-only)
    are caught by the allowlist. A bare host or ``host:port`` (``a.com``,
    ``example.com:8080``) has no recognised scheme and returns False.
    """
    if "://" in url:
        return not url.lower().startswith(("http://", "https://"))
    return url.split(":", 1)[0].lower() in _NON_HTTP_SCHEMES


def _as_bool(value: Any, *, default: bool = True) -> bool:
    """Coerce a raw arg to a bool, falling back to ``default`` for non-bools.

    The schema declares `render_js` as a boolean, but a sloppy call may pass a
    string/int (e.g. "false", "", 0). ``bool("")`` and ``bool(0)`` are ``False``,
    which would silently flip the tool into HEADED browser mode on a headless
    server and crash with "Missing X server or $DISPLAY". Only real booleans are
    meaningful; anything else (str, int, list, None) falls back to ``default``
    (True = headless, the safe mode everywhere). A warning is logged for
    non-None non-bools so the misuse is visible instead of silent.
    """
    if isinstance(value, bool):
        return value
    if value is not None:
        logger.warning(
            "scrapegraph: non-boolean render_js=%r treated as %s (headless)",
            value,
            default,
        )
    return default


def _normalize_urls(args: dict) -> list[str]:
    urls: list[str] = []
    single = args.get("url")
    # The schema declares `url` as a string, but a sloppy call may pass an
    # int/dict/list — that used to crash with AttributeError (`.strip()` on a
    # non-str). Treat non-strings as absent so the handler reports a clean
    # "url required" error instead of blowing up.
    if isinstance(single, str) and single.strip():
        single = single.strip()
        # A URL with a non-http(s) scheme (ftp:, mailto:, javascript:,
        # data:, file:, ...) is not something scrapegraphai can fetch —
        # prepending "https://" would fabricate "https://ftp://..." that
        # fails later with an obscure error. Skip it instead.
        if _is_non_http_scheme(single):
            logger.debug("scrapegraph: skipping non-http(s) URL %r", single)
        else:
            urls.append(single)
    many = args.get("urls")
    if isinstance(many, list):
        for u in many:
            # Only real strings are meaningful URLs. str()-coercing garbage
            # (None, ints, dicts, lists) would fabricate URLs like
            # "https://None" or "https://{'a': 1}" that only fail later with
            # obscure errors — and burn LLM tokens on a doomed extraction.
            # Skip non-strings entirely (schema-violating sloppy calls).
            if isinstance(u, str) and u.strip():
                u = u.strip()
                # A URL with a non-http(s) scheme (ftp:, mailto:, javascript:,
                # data:, file:, ...) is not something scrapegraphai can fetch —
                # prepending "https://" would fabricate "https://ftp://..." that
                # fails later with an obscure error. Skip it instead.
                if _is_non_http_scheme(u):
                    logger.debug("scrapegraph: skipping non-http(s) URL %r", u)
                    continue
                urls.append(u)
    # De-dupe, preserve order, and normalise scheme.
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if not u.lower().startswith(("http://", "https://")):
            u = "https://" + u
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _truncate_rendered(rendered: str, limit: int) -> str:
    """Cut ``rendered`` to ``limit`` chars and append a visible truncation marker.

    A bare ``rendered[:limit]`` signals nothing to the caller — the JSON blob
    just ends mid-value and looks complete. We cut at a boundary that never
    splits a UTF-8 code point (``str`` slicing already guarantees that) and tag
    the tail so the model knows the data is incomplete rather than silently
    dropped. Total length never exceeds ``limit``.
    """
    if limit <= 0:
        return _TRUNCATION_MARKER[:limit] if limit >= 0 else ""
    marker_len = len(_TRUNCATION_MARKER)
    if marker_len >= limit:
        return _TRUNCATION_MARKER[:limit]
    return rendered[: limit - marker_len] + _TRUNCATION_MARKER


def _coerce_schema(raw: Any) -> Any:
    """Accept a JSON-schema dict (or a JSON string of one) for structured output."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(raw, dict):
        return raw
    return None


async def _handle_scrapegraph(args, **kw):
    urls = _normalize_urls(args)
    if not urls:
        return tool_result(ok=False, error="Either `url` or `urls` is required.")

    raw_prompt = args.get("prompt")
    prompt = raw_prompt.strip() if isinstance(raw_prompt, str) else ""
    prompt = prompt or _DEFAULT_PROMPT
    schema = _coerce_schema(args.get("output_schema"))
    render_js = args.get("render_js")
    headless = _as_bool(render_js, default=True)
    raw_timeout = args.get("timeout")
    timeout = clamp_timeout(raw_timeout)

    try:
        if len(urls) == 1:
            data = await extract_structured(
                urls[0], prompt, schema=schema, headless=headless, timeout=timeout
            )
        else:
            data = await extract_many(
                urls, prompt, schema=schema, headless=headless, timeout=timeout
            )
    except ScrapegraphUnavailable as exc:
        return tool_result(ok=False, error=str(exc))
    except TimeoutError:
        return tool_result(
            ok=False,
            urls=urls,
            error=classify_scrapegraph_error(TimeoutError("timed out")),
        )
    except Exception as exc:  # noqa: BLE001 — classify and surface user-friendly error
        logger.warning("scrapegraph extraction failed: %s", exc)
        hint = classify_scrapegraph_error(exc)
        return tool_result(ok=False, urls=urls, error=hint)

    # scrapegraphai "succeeds" with a failure sentinel ("NA", {"content": "NA"},
    # empty dict) when the LLM can't structurally parse the page — it does not
    # raise. Surface that as an actionable error pointing at `scrape` instead of
    # returning ok=True with a fake-success "NA" blob the agent would burn a
    # turn reading (long articles, JS-heavy and anti-bot pages are the usual
    # triggers — see skills/web/scrapegraphai/references/scrapling-fallback.md).
    if looks_like_empty_result(data):
        return tool_result(
            ok=False,
            urls=urls,
            error=(
                "ScrapeGraphAI returned no useful content (it couldn't "
                "structurally parse the page — typical on long articles, "
                "JS-heavy or anti-bot pages). Use the `scrape` tool "
                "(Scrapling) for raw page content instead."
            ),
        )

    try:
        rendered = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        rendered = str(data)
    truncated = len(rendered) > _MAX_RESULT_CHARS
    if truncated:
        rendered = _truncate_rendered(rendered, _MAX_RESULT_CHARS)

    # NB: don't use ``data=`` — tool_result() treats ``data`` as its positional
    # payload arg, which would drop the other fields. Use ``extracted``.
    return tool_result(
        ok=True,
        urls=urls,
        prompt=prompt,
        structured=bool(schema),
        truncated=truncated,
        extracted=rendered,
    )


SCRAPEGRAPH_SCHEMA = {
    "name": "scrapegraph",
    "description": (
        "Extract STRUCTURED data from one or more web pages using ScrapeGraphAI "
        "(runs locally on our own infrastructure + the agent's LLM — no paid "
        "scraping API). Describe what you want in `prompt` and get back JSON. "
        "PREFER this over Firecrawl/Browserbase/web_extract when you need DATA "
        "(tables, prices, product specs, listings, contacts, structured article "
        "fields) rather than raw page text. It renders JavaScript pages with a "
        "local headless browser. For plain page text use `web_extract`/`scrape`; "
        "to find pages use `web_search` (don't scrape search engines)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The page URL to extract from. Either this or `urls` is required.",
            },
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Extract from several pages with the same prompt "
                    "(returns one combined result). Either this or `url` is required."
                ),
            },
            "prompt": {
                "type": "string",
                "description": (
                    "What to extract, in plain language. E.g. 'List every "
                    "product with its name, price and rating as JSON.' Defaults "
                    "to extracting the main content."
                ),
            },
            "output_schema": {
                "type": "object",
                "description": (
                    "Optional JSON Schema describing the exact shape you want "
                    "the result in (keys/types). Forces structured output."
                ),
            },
            "render_js": {
                "type": "boolean",
                "description": (
                    "Render JavaScript with a local headless browser (default "
                    "true). ⚠️ On headless servers NEVER set this to false — "
                    "the headed browser mode requires a display server (X11) "
                    "and will crash. Just omit it (defaults to headless=true)."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "Max seconds for the LLM extraction (default: no timeout, "
                    "min 10, max 300). Increase for large pages with many "
                    "data points; decrease to fail fast on slow models."
                ),
            },
        },
        "required": [],
    },
}


registry.register(
    name="scrapegraph",
    toolset="web",
    schema=SCRAPEGRAPH_SCHEMA,
    handler=_handle_scrapegraph,
    is_async=True,
    emoji="🧩",
    max_result_size_chars=_MAX_RESULT_CHARS + 2000,
)
