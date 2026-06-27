"""ScrapeGraphAI web-extract backend — bundled, auto-loaded.

Local, LLM-powered extraction on our own infrastructure (no paid scraping API).
The heavy ``scrapegraphai`` dependency is lazy-installed on first use, so this
backend reports unavailable until the library is present (the ``scrapegraph``
tool installs it on first call).
"""

from __future__ import annotations

from plugins.web.scrapegraphai.provider import ScrapegraphWebProvider


def register(ctx) -> None:
    """Register the ScrapeGraphAI extract provider with the plugin context."""
    ctx.register_web_search_provider(ScrapegraphWebProvider())
