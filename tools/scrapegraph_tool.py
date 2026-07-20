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
)

logger = logging.getLogger(__name__)

_MAX_RESULT_CHARS = 30000
_DEFAULT_PROMPT = (
    "Extract the main, useful content of this page as clean structured data."
)


def _normalize_urls(args: dict) -> list[str]:
    urls: list[str] = []
    single = (args.get("url") or "").strip()
    if single:
        urls.append(single)
    many = args.get("urls")
    if isinstance(many, list):
        urls.extend(str(u).strip() for u in many if str(u).strip())
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
        return tool_result(ok=False, error="`url` (or `urls`) is required.")

    prompt = (args.get("prompt") or "").strip() or _DEFAULT_PROMPT
    schema = _coerce_schema(args.get("output_schema"))
    render_js = args.get("render_js")
    headless = True if render_js is None else bool(render_js)
    raw_timeout = args.get("timeout")
    timeout = clamp_timeout(raw_timeout)

    try:
        if len(urls) == 1:
            data = await extract_structured(
                urls[0], prompt, schema=schema, headless=headless, timeout=timeout
            )
        else:
            data = await extract_many(urls, prompt, schema=schema, headless=headless, timeout=timeout)
    except ScrapegraphUnavailable as exc:
        return tool_result(ok=False, error=str(exc))
    except TimeoutError as exc:
        return tool_result(
            ok=False,
            urls=urls,
            error=(
                "The LLM extraction timed out. This can happen on large pages "
                "or when the model is slow. Increase the `timeout` parameter "
                "(current value: {}s, max 300s) or try a simpler prompt."
            ).format(timeout or "default"),
        )
    except Exception as exc:  # noqa: BLE001 — classify and surface user-friendly error
        logger.warning("scrapegraph extraction failed: %s", exc)
        hint = classify_scrapegraph_error(exc)
        return tool_result(ok=False, urls=urls, error=hint)

    try:
        rendered = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        rendered = str(data)
    truncated = len(rendered) > _MAX_RESULT_CHARS
    if truncated:
        rendered = rendered[:_MAX_RESULT_CHARS]

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
                "description": "The page URL to extract from.",
            },
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional: extract from several pages with the same prompt "
                    "(returns one combined result)."
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
        "required": ["url"],
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
