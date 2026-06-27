"""Tests for the ScrapeGraphAI integration (native tool + web_extract backend).

scrapegraphai itself is NOT installed in CI (it's lazy-installed on first use),
so every test mocks the extraction layer. We verify the wiring: registration,
toolset membership, the lazy-deps feature, the LLM-config builder, the tool/
backend handlers (success + unavailable + error paths), and that web_extract
prefers scrapegraph over 3rd-party backends once the library is present.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import tools.scrapegraph_common as sgc
import tools.scrapegraph_tool  # noqa: F401 — registers the tool on import
from plugins.web.scrapegraphai.provider import ScrapegraphWebProvider


def _run(coro):
    return asyncio.run(coro)


def _run_tool(coro):
    """Run a tool handler (returns a JSON string) and parse it to a dict."""
    return json.loads(asyncio.run(coro))


# ── Registration / wiring ───────────────────────────────────────────────────


def test_tool_registered_in_web_toolset():
    from toolsets import TOOLSETS
    from tools.registry import registry

    assert registry.get_definitions(tool_names={"scrapegraph"})
    assert "scrapegraph" in TOOLSETS["web"]["tools"]


def test_lazy_feature_declared():
    from tools.lazy_deps import LAZY_DEPS

    assert LAZY_DEPS.get("scrape.scrapegraph") == ("scrapegraphai",)


def test_schema_shape():
    from tools.scrapegraph_tool import SCRAPEGRAPH_SCHEMA

    assert SCRAPEGRAPH_SCHEMA["name"] == "scrapegraph"
    props = SCRAPEGRAPH_SCHEMA["parameters"]["properties"]
    assert {"url", "urls", "prompt", "output_schema", "render_js"} <= set(props)
    assert SCRAPEGRAPH_SCHEMA["parameters"]["required"] == ["url"]


# ── LLM config builder (uses the agent's own model) ─────────────────────────


def test_build_llm_config_from_auxiliary_client():
    client = SimpleNamespace(api_key="sk-abc", base_url="https://openrouter.ai/api/v1/")
    with patch(
        "agent.auxiliary_client.get_text_auxiliary_client",
        return_value=(client, "anthropic/claude-sonnet-4.6"),
    ):
        cfg = sgc.build_llm_config()
    assert cfg["api_key"] == "sk-abc"
    # already provider-qualified → kept as-is; base_url normalised (no trailing /)
    assert cfg["model"] == "anthropic/claude-sonnet-4.6"
    assert cfg["base_url"] == "https://openrouter.ai/api/v1"


def test_build_llm_config_bare_model_gets_openai_prefix():
    client = SimpleNamespace(api_key="k", base_url=None)
    with patch(
        "agent.auxiliary_client.get_text_auxiliary_client",
        return_value=(client, "gpt-4o-mini"),
    ):
        cfg = sgc.build_llm_config()
    assert cfg["model"] == "openai/gpt-4o-mini"
    assert "base_url" not in cfg


# ── Native tool handler ─────────────────────────────────────────────────────


def test_handler_requires_url():
    from tools.scrapegraph_tool import _handle_scrapegraph

    res = _run_tool(_handle_scrapegraph({}))
    assert res["ok"] is False
    assert "url" in res["error"].lower()


def test_handler_success_single(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    async def _fake_extract(source, prompt, *, schema=None, headless=True):
        return {"title": "Hi", "price": 9.99}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake_extract)
    res = _run_tool(_handle_scrapegraph({"url": "example.com", "prompt": "get price"}))
    assert res["ok"] is True
    assert res["urls"] == ["https://example.com"]  # scheme normalised
    assert "9.99" in res["extracted"]


def test_handler_multi_urls(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    captured = {}

    async def _fake_many(sources, prompt, *, schema=None, headless=True):
        captured["sources"] = list(sources)
        return [{"u": s} for s in sources]

    monkeypatch.setattr("tools.scrapegraph_tool.extract_many", _fake_many)
    res = _run_tool(
        _handle_scrapegraph({
            "url": "https://a.com",
            "urls": ["https://b.com", "a.com"],
        })
    )
    assert res["ok"] is True
    # de-duped, scheme-normalised, order preserved
    assert captured["sources"] == ["https://a.com", "https://b.com"]


def test_handler_unavailable_returns_install_hint(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    async def _boom(*a, **k):
        raise sgc.ScrapegraphUnavailable("not installed: do X")

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _boom)
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert res["ok"] is False
    assert "not installed" in res["error"]


def test_handler_runtime_error(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    async def _boom(*a, **k):
        raise RuntimeError("LLM exploded")

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _boom)
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert res["ok"] is False
    assert "LLM exploded" in res["error"]


# ── web_extract backend ─────────────────────────────────────────────────────


def test_backend_is_extract_only():
    p = ScrapegraphWebProvider()
    assert p.name == "scrapegraph"
    assert p.supports_extract() is True
    assert p.supports_search() is False
    assert p.search("q")["success"] is False


def test_backend_extract_shapes_results(monkeypatch):
    p = ScrapegraphWebProvider()

    async def _fake(source, prompt, *, schema=None, headless=True):
        return {"content": f"# Page {source}"}

    monkeypatch.setattr("tools.scrapegraph_common.extract_structured", _fake)
    out = _run(p.extract(["https://a.com", "https://b.com"]))
    assert [r["url"] for r in out] == ["https://a.com", "https://b.com"]
    assert out[0]["content"] == "# Page https://a.com"
    assert out[0]["metadata"]["sourceURL"] == "https://a.com"


def test_backend_extract_per_url_error(monkeypatch):
    p = ScrapegraphWebProvider()

    async def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr("tools.scrapegraph_common.extract_structured", _boom)
    out = _run(p.extract(["https://a.com"]))
    assert out[0]["error"] == "boom"
    assert out[0]["content"] == ""


def test_stringify_prefers_known_keys():
    from plugins.web.scrapegraphai.provider import _stringify

    assert _stringify({"content": "hello"}) == "hello"
    assert _stringify("raw") == "raw"
    assert "k" in _stringify({"k": "v"})  # falls back to JSON dump


# ── extract-backend prioritisation over 3rd-party ───────────────────────────


def test_web_extract_prefers_scrapegraph_when_installed():
    import tools.web_tools as wt

    with (
        patch.object(wt, "_scrapegraph_importable", return_value=True),
        patch.object(wt, "_load_web_config", return_value={}),
    ):
        assert wt._get_extract_backend() == "scrapegraph"


def test_web_extract_falls_back_when_not_installed():
    import tools.web_tools as wt

    with (
        patch.object(wt, "_scrapegraph_importable", return_value=False),
        patch.object(wt, "_get_backend", return_value="firecrawl"),
        patch.object(wt, "_load_web_config", return_value={}),
    ):
        assert wt._get_extract_backend() == "firecrawl"


def test_explicit_extract_backend_wins_over_scrapegraph():
    import tools.web_tools as wt

    with (
        patch.object(wt, "_scrapegraph_importable", return_value=True),
        patch.object(wt, "_load_web_config", return_value={"extract_backend": "exa"}),
        patch.object(wt, "_is_backend_available", return_value=True),
    ):
        assert wt._get_extract_backend() == "exa"
