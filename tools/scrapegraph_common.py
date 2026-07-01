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
    except Exception as exc:  # lazy_deps itself unavailable
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
    except Exception as exc:  # noqa: BLE001 — fall back to env below
        logger.debug("scrapegraph: auxiliary client unavailable (%s)", exc)

    if not api_key:
        import os

        api_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get(
            "OPENROUTER_API_KEY", ""
        )
    if not model:
        model = "gpt-4o-mini"

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


async def extract_structured(
    source: Any,
    prompt: str,
    *,
    schema: Any = None,
    headless: bool = True,
    overrides: Optional[dict] = None,
) -> Any:
    """Extract from ONE source (URL or rendered HTML string) per ``prompt``.

    ``schema`` (a pydantic model or JSON-schema dict) yields structured output.
    Runs the blocking graph in a worker thread so the event loop is never stalled.
    """
    ensure_installed()
    cfg = graph_config(headless=headless, overrides=overrides)
    return await asyncio.to_thread(_run_smart, source, prompt, schema, cfg)


async def extract_many(
    sources: Any,
    prompt: str,
    *,
    schema: Any = None,
    headless: bool = True,
    overrides: Optional[dict] = None,
) -> Any:
    """Extract from MULTIPLE sources with one prompt (SmartScraperMultiGraph)."""
    ensure_installed()
    cfg = graph_config(headless=headless, overrides=overrides)
    return await asyncio.to_thread(_run_multi, sources, prompt, schema, cfg)
