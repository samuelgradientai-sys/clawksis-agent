"""Shared helpers for the ScrapeGraphAI integration.

Two surfaces consume this module: the native ``scrapegraph`` tool
(``tools/scrapegraph_tool.py``) and the ``scrapegraph`` web-extract backend
(``plugins/web/scrapegraphai/``). Both run the **local** ``scrapegraphai``
library — NOT the paid ScrapeGraphAI cloud API — driven by the agent's own
LLM (the auxiliary text model it's already configured with). For JavaScript
pages, scrapegraphai's headless Chromium loader runs locally; no third-party
scraping service is involved. This is deliberate: keep scraping on our own
infrastructure and minimise dependence on Firecrawl/Browserbase/Apify et al.

Heavy deps (the langchain stack) are lazy-installed on first use via
``tools.lazy_deps`` so they never bloat the base install.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lazy-deps feature key (registered in tools/lazy_deps.py LAZY_DEPS).
LAZY_FEATURE = "scrape.scrapegraph"

_INSTALL_HINT = (
    "ScrapeGraphAI is not installed. It auto-installs on first use, but if that "
    "is disabled run once: pip install scrapegraphai && python -m playwright "
    "install chromium (the Chromium download is only needed for JavaScript "
    "pages)."
)


class ScrapegraphUnavailable(RuntimeError):
    """scrapegraphai could not be imported/installed in this environment."""


def is_available() -> bool:
    """True if the ``scrapegraphai`` package is importable right now."""
    import importlib.util

    return importlib.util.find_spec("scrapegraphai") is not None


def _patch_langchain_community() -> None:
    """Re-export ``ChatOllama`` into ``langchain_community.chat_models``.

    ``scrapegraphai`` imports ``ChatOllama`` from the old location
    ``langchain_community.chat_models``, but ``langchain-community`` v0.4+
    removed it (the model lives in ``langchain_ollama`` now). This shim
    patches the old namespace so scrapegraphai can find it regardless of
    the installed langchain-community version.
    """
    try:
        from langchain_ollama import ChatOllama as _ChatOllama_
    except ImportError:
        return  # langchain-ollama not installed either — nothing to patch

    import langchain_community.chat_models as _lm

    if not hasattr(_lm, "ChatOllama") or _lm.ChatOllama is not _ChatOllama_:
        _lm.ChatOllama = _ChatOllama_


def ensure_installed(*, prompt: bool = False) -> None:
    """Make ``scrapegraphai`` importable, lazy-installing it if needed.

    Raises :class:`ScrapegraphUnavailable` if it's missing and cannot be
    installed (lazy installs disabled, offline, or install failed).
    """
    if is_available():
        _patch_langchain_community()
        return
    try:
        from tools.lazy_deps import FeatureUnavailable, ensure
    except ImportError as exc:
        raise ScrapegraphUnavailable(_INSTALL_HINT) from exc
    try:
        ensure(LAZY_FEATURE, prompt=prompt)
    except FeatureUnavailable as exc:
        raise ScrapegraphUnavailable(f"{_INSTALL_HINT} ({exc})") from exc
    if not is_available():
        raise ScrapegraphUnavailable(_INSTALL_HINT)
    _patch_langchain_community()


def build_llm_config(*, temperature: float = 0.0) -> dict[str, Any]:
    """Build scrapegraphai's ``llm`` config from the agent's own model.

    Reuses the auxiliary text client (same model / key / base_url the agent is
    already configured with) so no extra API key is required — scraping runs on
    the model the user already pays for (or a local Ollama). scrapegraphai routes
    ``"openai/<model>"`` + a custom ``base_url`` through langchain's ChatOpenAI,
    which targets any OpenAI-compatible endpoint (OpenRouter / Nous / local).

    If no API key can be found from any source, a warning is logged to help
    debug authentication failures early rather than failing with a cryptic
    error from the LLM provider.
    """
    api_key = ""
    base_url: Optional[str] = None
    model: Optional[str] = None
    try:
        from agent.auxiliary_client import get_text_auxiliary_client

        client, model = get_text_auxiliary_client()
        api_key = getattr(client, "api_key", "") or ""
        raw_base = getattr(client, "base_url", None)
        base_url = str(raw_base).rstrip("/") if raw_base else None
    except (ImportError, AttributeError) as exc:
        logger.debug("scrapegraph: auxiliary client unavailable (%s)", exc)

    if not api_key:
        import os

        api_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get(
            "OPENROUTER_API_KEY", ""
        )
    if not model:
        model = "gpt-4o-mini"

    if not api_key:
        logger.warning(
            "scrapegraph: no API key configured for LLM extraction — "
            "set OPENAI_API_KEY/OPENROUTER_API_KEY or configure "
            "auxiliary_text model credentials"
        )

    model_slug = str(model) if "/" in str(model) else f"openai/{model}"
    llm: dict[str, Any] = {
        "api_key": api_key,
        "model": model_slug,
        "temperature": temperature,
    }
    if base_url:
        llm["base_url"] = base_url
    return llm


def graph_config(
    *, headless: bool = True, overrides: Optional[dict] = None
) -> dict[str, Any]:
    """Assemble a scrapegraphai graph config (llm + loader options)."""
    cfg: dict[str, Any] = {
        "llm": build_llm_config(),
        "verbose": False,
        "headless": headless,
    }
    if overrides:
        cfg.update(overrides)
    return cfg


def _run_smart(source: Any, prompt: str, schema: Any, config: dict) -> Any:
    """Run a single-source SmartScraperGraph (blocking)."""
    from scrapegraphai.graphs import SmartScraperGraph

    kwargs: dict[str, Any] = {"prompt": prompt, "source": source, "config": config}
    if schema is not None:
        kwargs["schema"] = schema
    return SmartScraperGraph(**kwargs).run()


def _run_multi(sources: Any, prompt: str, schema: Any, config: dict) -> Any:
    """Run a multi-source SmartScraperMultiGraph (blocking)."""
    from scrapegraphai.graphs import SmartScraperMultiGraph

    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "source": list(sources),
        "config": config,
    }
    if schema is not None:
        kwargs["schema"] = schema
    return SmartScraperMultiGraph(**kwargs).run()


def clamp_timeout(raw_timeout: Any) -> int | None:
    """Clamp a raw timeout value to the valid range [10, 300] or return None.

    Accepts int, float, or string. Returns ``None`` when the input is None
    or cannot be coerced to int. This centralises the clamping logic so both
    the native tool handler and the web-extract backend stay in sync.

    ``bool`` values (a subclass of ``int``) are treated as absent: without
    this guard ``int(False)`` == 0 would clamp to the 10s minimum and
    silently *enable* an extraction timeout a sloppy ``timeout=False`` call
    meant to disable. Same philosophy as ``_as_bool`` in the tool handler —
    a type that carries no meaningful value falls back to the default.
    """
    if raw_timeout is None:
        return None
    if isinstance(raw_timeout, bool):
        return None
    try:
        return max(10, min(300, int(raw_timeout)))
    except (ValueError, TypeError) as exc:
        logger.debug(
            "clamp_timeout: uncoercible timeout %r ignored, returning None: %s",
            raw_timeout,
            exc,
        )
        return None


# Values scrapegraphai's LLM-driven extraction returns when it FAILED to
# structurally parse a page. It rarely raises — it answers with a sentinel
# like ``"NA"`` / ``"N/A"`` or ``{"content": "NA"}`` instead, which callers
# must recognise or the agent burns a turn reading garbage.
_EMPTY_RESULT_SENTINELS = frozenset({
    "",
    "na",
    "n/a",
    "n.a.",
    "none",
    "null",
    "nan",
    "{}",
    # Common LLM "I couldn't extract anything" phrasings (v1.9).
    "no content",
    "no data",
    "no result",
    "no results",
    "no text",
    "nothing",
    "not found",
    "empty",
    "nil",
    "undefined",
    # v1.10: placeholder family — LLMs answer with a dash/dot/ellipsis or a
    # "not available" phrasing when they could not find the field at all
    # (common in table/listing extractions: {"price": "-"}). A whole result
    # made of these carries no usable content; partial extractions that mix
    # them with real values are still kept (see looks_like_empty_result).
    "-",
    "–",
    "—",
    ".",
    "..",
    "...",
    "…",
    "not available",
    "no info",
    "no information",
    "no value",
})


def looks_like_empty_result(data: Any) -> bool:
    """True when a scrapegraphai result carries no usable content.

    ScrapeGraphAI's extraction frequently *succeeds* with a failure sentinel
    (``"NA"``, ``"N/A"``, ``{"content": "NA"}``, empty dict) instead of
    raising. Callers use this to surface an actionable "use the `scrape` tool"
    error instead of handing the agent a fake-success ``"NA"`` blob.

    Deliberately conservative to avoid discarding real partial extractions:
    a dict/list only counts as empty when **every** contained value is empty,
    checked recursively (v1.9) so nested shapes like
    ``{"content": {"answer": "NA"}}`` or ``{"data": [{"content": "N/A"}]}``
    are caught too. ``{"title": "NA", "body": "real text"}`` or
    ``{"price": 9.99}`` → kept.
    """
    if data is None:
        return True
    if isinstance(data, str):
        # LLMs punctuate their failure sentinels: "N/A.", "none.", "not
        # available." all carry zero info yet differ from the exact sentinel
        # tokens by a trailing full stop only. Try the exact (trimmed) token
        # first — that keeps the "." family (v1.10) and "n.a." intact — then
        # the trailing-dot-stripped form, so punctuated sentinels are caught
        # without ever discarding real content (no genuine answer is a bare
        # sentinel + ".").
        normalized = data.strip().lower()
        return (
            normalized in _EMPTY_RESULT_SENTINELS
            or normalized.rstrip(".") in _EMPTY_RESULT_SENTINELS
        )
    if isinstance(data, dict):
        values = [v for v in data.values() if v is not None]
        if not values:
            return True
        # Recurse into every value: a dict is empty when each value is empty
        # (sentinel string, empty nested dict/list, or an empty sub-result).
        return all(looks_like_empty_result(v) for v in values)
    if isinstance(data, (list, tuple)):
        return all(looks_like_empty_result(item) for item in data)
    return False


def classify_scrapegraph_error(exc: Exception) -> str:
    """Return a user-friendly error hint based on the exception type/message.

    Classifies extraction errors into 9 categories (X server, auth, quota,
    rate-limit, HTTP status, timeout, network, parsing, generic) so callers
    can surface actionable messages instead of raw exception dumps. Both the
    native tool handler and the web-extract backend use this for consistent
    user-facing errors.

    The classification is based on type checking (isinstance) for built-in
    exception types and keyword matching of the lowercased exception string
    for everything else — no internal paths or sensitive details are leaked.
    Order matters: more specific checks (auth, quota, rate-limit, timeout
    type) run before broader keyword families (HTTP status, network) so a
    429 from exhausted credits is not misread as a plain rate limit, and a
    real ``TimeoutError`` from our own ``asyncio.wait_for`` is never misread
    as a network timeout.
    """
    exc_msg = str(exc).lower()

    # 1) Browser/headless — no X server or headed mode on headless server
    if any(
        kw in exc_msg
        for kw in (
            "missing x server",
            "headed browser",
            "browsertype.launch",
            "x display",
            "xserver",
        )
    ):
        return (
            "ScrapeGraphAI attempted to launch a headed browser but there "
            "is no display server. Happens when `render_js=false` on a "
            "headless server. Omit `render_js` or set it to `true`."
        )
    # 2) Auth / credential errors
    # Covers HTTP 401 (retries won't help), generic unauthorized markers, and
    # the provider-specific invalid-API-key messages (OpenAI "Incorrect API
    # key provided", OpenRouter "expensive API key", Anthropic "invalid
    # x-api-key", etc.) with their OpenAI 401-style payload bodies like
    # `"Invalid API key provided: sk-..."`. All of these mean the configured
    # credential is wrong or missing — retrying is pointless.
    if any(
        kw in exc_msg
        for kw in (
            "401",
            "authenticationerror",
            "unauthorized",
            "no api key",
            "invalid api key",
            "incorrect api key",
            "expensive api key",
            "api key does not provide",
            "invalid x-api-key",
            "api key provided",
        )
    ):
        return (
            "The LLM model used by ScrapeGraphAI is not authenticated. "
            "Check auxiliary_text model credentials, or set "
            "OPENAI_API_KEY / OPENROUTER_API_KEY in the environment."
        )
    # 3) Quota / billing — model credits exhausted or billing inactive
    # (OpenAI "insufficient_quota" / 402, Anthropic "billing_not_active",
    # OpenRouter "Insufficient Credits", ...). MUST run before the rate-limit
    # family: quota errors often carry a "429" status code too, but retrying
    # will not help — the fix is checking billing or switching models.
    if any(
        kw in exc_msg
        for kw in (
            "insufficient_quota",
            "billing_not_active",
            "insufficient credits",
            "out of credits",
            "credit balance",
            "payment required",
            "402",
            "quota",
            "billing",
            "max monthly spend",
        )
    ):
        return (
            "The LLM model used by ScrapeGraphAI has run out of credits or "
            "its billing is inactive (quota/billing error). Check the "
            "provider balance or switch to a different model — retrying "
            "will not help."
        )
    # 4) Rate limit
    if any(
        kw in exc_msg
        for kw in ("429", "ratelimiterror", "rate_limit", "too many requests")
    ):
        return (
            "The model is rate-limited. Retry later or configure a "
            "different model with higher rate limits."
        )
    # 5) HTTP status errors — page-level: wrong URL, removed page, or the
    # site blocking automated access (checked before network so e.g. a
    # Cloudflare 403 is not misread as a connectivity problem).
    if any(
        kw in exc_msg
        for kw in (
            "403",
            "404",
            "500",
            "502",
            "503",
            "http error",
            "status code",
            "bad gateway",
            "forbidden",
            "page not found",
            "service unavailable",
        )
    ):
        return (
            "The page returned an HTTP error (e.g. 403/404/5xx) — the URL "
            "may be wrong or the page removed, or the site is blocking "
            "automated access. Verify the URL, or use the `scrape` tool "
            "(Scrapling) which bypasses anti-bot protections."
        )
    # 6) TimeoutError — LLM extraction took too long (asyncio.wait_for);
    # also catches scrapegraphai's own graph-execution timeout message.
    if isinstance(exc, TimeoutError) or "graph execution timed out" in exc_msg:
        return (
            "The LLM extraction timed out. This can happen on large pages "
            "or when the model is slow. Increase the `timeout` parameter "
            "(max 300s) or try a simpler prompt."
        )
    # 7) Network / DNS / TLS — unreachable page, connection reset, SSL
    # failures, network-level timeouts (NOT our own wait_for TimeoutError,
    # which is caught by the isinstance check above).
    if any(
        kw in exc_msg
        for kw in (
            "getaddrinfo",
            "name or service not known",
            "nodename nor servname",
            "temporary failure in name resolution",
            "connection refused",
            "connection reset",
            "connection aborted",
            "connection closed",
            "failed to establish",
            "max retries exceeded",
            "network unreachable",
            "dns resolution",
            "ssl",
            "certificate verify failed",
            "tls",
            "read timed out",
            "connect timed out",
            "timed out",
            "timeout occurred",
        )
    ):
        return (
            "Network error reaching the page — DNS, connection, TLS, or a "
            "network-level timeout. The site may be down or blocking "
            "automated access. Verify the URL, check connectivity, or use "
            "the `scrape` tool (Scrapling) for anti-bot pages."
        )
    # 8) Output parsing (LLM returned bad JSON)
    if any(
        kw in exc_msg
        for kw in ("invalid json output", "output_parsing_failure", "parsing")
    ):
        return (
            "The LLM returned malformed output. Try a more specific "
            "prompt with fewer fields, or use the `scrape` tool "
            "(Scrapling) for raw page content instead."
        )
    # 9) Generic fallback — safe, no internal details leaked
    return (
        "ScrapeGraphAI extraction failed. Could be a network error, "
        "model overload, or page issue. Try: using `scrape` "
        "(Scrapling) for raw content, a different URL, "
        "or a more specific prompt."
    )


async def extract_structured(
    source: Any,
    prompt: str,
    *,
    schema: Any = None,
    headless: bool = True,
    overrides: Optional[dict] = None,
    timeout: Optional[int] = None,
) -> Any:
    """Extract from ONE source (URL or rendered HTML string) per ``prompt``.

    ``schema`` (a pydantic model or JSON-schema dict) yields structured output.
    Runs the blocking graph in a worker thread so the event loop is never stalled.

    The lazy install (``ensure_installed``) also runs in a worker thread — on
    first use it can pip-install scrapegraphai for 30-60s, and doing that
    synchronously in the coroutine would freeze the whole event loop.

    When ``timeout`` is set (seconds), the extraction is cancelled if it takes
    longer — useful for slow pages or overloaded models. Pass a value between
    10 and 300.
    """
    # Lazy install (pip) can take 30-60s on first use — run it in a worker
    # thread so it never stalls the event loop (and can't delay other tasks).
    await asyncio.to_thread(ensure_installed)
    cfg = graph_config(headless=headless, overrides=overrides)
    coro = asyncio.to_thread(_run_smart, source, prompt, schema, cfg)
    if timeout is not None:
        coro = asyncio.wait_for(coro, timeout=timeout)
    return await coro


async def extract_many(
    sources: Any,
    prompt: str,
    *,
    schema: Any = None,
    headless: bool = True,
    overrides: Optional[dict] = None,
    timeout: Optional[int] = None,
) -> Any:
    """Extract from MULTIPLE sources with one prompt (SmartScraperMultiGraph)."""
    # Same as extract_structured: lazy install runs in a worker thread so the
    # first-use pip install never blocks the event loop.
    await asyncio.to_thread(ensure_installed)
    cfg = graph_config(headless=headless, overrides=overrides)
    coro = asyncio.to_thread(_run_multi, sources, prompt, schema, cfg)
    if timeout is not None:
        coro = asyncio.wait_for(coro, timeout=timeout)
    return await coro
