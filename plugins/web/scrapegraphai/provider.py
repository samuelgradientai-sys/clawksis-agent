"""ScrapeGraphAI web-extract backend — local, LLM-powered, own infrastructure.

Lets ``web_extract`` (and the auto-selected extract backend) run on the local
``scrapegraphai`` library + the agent's own LLM instead of a paid third-party
API (Firecrawl/Browserbase). Extract-only: for search use a search backend
(ddgs/searxng/brave-free) and for structured data prefer the ``scrapegraph``
tool directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "Extract the full readable main content of this page as a single clean "
    "Markdown string. Preserve headings, lists and tables. Omit nav, ads, "
    "cookie banners and boilerplate."
)


def _stringify(data: Any) -> str:
    """Coerce a scrapegraphai result into a content string."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        # Common shapes: {"content": "..."} / {"markdown": "..."} / {"text": "..."}
        for key in ("content", "markdown", "text", "result", "answer"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val
        try:
            return json.dumps(data, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):
            return str(data)
    return str(data)


class ScrapegraphWebProvider(WebSearchProvider):
    """Extract-only web backend backed by the local scrapegraphai library."""

    @property
    def name(self) -> str:
        return "scrapegraph"

    @property
    def display_name(self) -> str:
        return "ScrapeGraphAI (local)"

    def is_available(self) -> bool:
        # Available once the library is importable. The `scrapegraph` tool
        # lazy-installs it on first use; after that this backend can be
        # auto-selected for web_extract too.
        try:
            from tools.scrapegraph_common import is_available

            return is_available()
        except ImportError:
            return False

    def supports_search(self) -> bool:
        return False

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        return {
            "success": False,
            "error": (
                "scrapegraph is an extraction backend, not a search engine — "
                "use a search backend (ddgs/searxng/brave-free)."
            ),
        }

    async def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        from tools.scrapegraph_common import ScrapegraphUnavailable, extract_structured

        try:
            from tools.interrupt import is_interrupted
        except ImportError:  # interrupt module optional

            def is_interrupted() -> bool:
                return False

        results: List[Dict[str, Any]] = []
        for url in urls:
            if is_interrupted():
                results.append({"url": url, "title": "", "error": "Interrupted"})
                continue
            try:
                data = await extract_structured(url, _EXTRACT_PROMPT, headless=True)
                content = _stringify(data)
                results.append({
                    "url": url,
                    "title": "",
                    "content": content,
                    "raw_content": content,
                    "metadata": {"sourceURL": url},
                })
            except ScrapegraphUnavailable as exc:
                results.append({
                    "url": url,
                    "title": "",
                    "content": "",
                    "error": str(exc),
                })
            except Exception as exc:  # noqa: BLE001 — per-URL failure, don't abort batch
                logger.warning("scrapegraph extract failed for %s: %s", url, exc)
                results.append({
                    "url": url,
                    "title": "",
                    "content": "",
                    "error": str(exc),
                })
        return results
