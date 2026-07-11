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
    assert {"url", "urls", "prompt", "output_schema", "render_js", "timeout"} <= set(props)
    assert SCRAPEGRAPH_SCHEMA["parameters"]["required"] == ["url"]


def test_coerce_schema():
    from tools.scrapegraph_tool import _coerce_schema

    assert _coerce_schema(None) is None
    assert _coerce_schema("") is None
    assert _coerce_schema({"type": "object"}) == {"type": "object"}
    assert _coerce_schema('{"type": "object"}') == {"type": "object"}
    assert _coerce_schema("not json") is None
    assert _coerce_schema(42) is None


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


def test_build_llm_config_empty_api_key_logs_warning(caplog):
    """When no API key is found anywhere, a warning is logged."""
    import logging

    caplog.set_level(logging.WARNING)
    with patch(
        "agent.auxiliary_client.get_text_auxiliary_client",
        side_effect=ImportError("no aux client"),
    ):
        with patch.dict("os.environ", {}, clear=True):
            cfg = sgc.build_llm_config()
    assert cfg["api_key"] == ""
    assert "no API key" in caplog.text
    assert cfg["model"] == "openai/gpt-4o-mini"


# ── Native tool handler ─────────────────────────────────────────────────────


def test_handler_requires_url():
    from tools.scrapegraph_tool import _handle_scrapegraph

    res = _run_tool(_handle_scrapegraph({}))
    assert res["ok"] is False
    assert "url" in res["error"].lower()


def test_handler_success_single(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    async def _fake_extract(source, prompt, *, schema=None, headless=True, timeout=None):
        return {"title": "Hi", "price": 9.99}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake_extract)
    res = _run_tool(_handle_scrapegraph({"url": "example.com", "prompt": "get price"}))
    assert res["ok"] is True
    assert res["urls"] == ["https://example.com"]  # scheme normalised
    assert "9.99" in res["extracted"]


def test_handler_multi_urls(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    captured = {}

    async def _fake_many(sources, prompt, *, schema=None, headless=True, timeout=None):
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
    # Handler classifies errors — "LLM exploded" maps to generic fallback
    assert "model overload" in res["error"] or "extraction failed" in res["error"]


# ── URL normalisation ───────────────────────────────────────────────────────


def test_normalize_urls_empty():
    from tools.scrapegraph_tool import _normalize_urls

    assert _normalize_urls({}) == []


def test_normalize_urls_scheme_default():
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({"url": "example.com/page"})
    assert out == ["https://example.com/page"]


def test_normalize_urls_https_preserved():
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({"url": "https://site.com"})
    assert out == ["https://site.com"]


def test_normalize_urls_dedup():
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({"url": "https://a.com", "urls": ["https://a.com", "https://b.com"]})
    assert out == ["https://a.com", "https://b.com"]


def test_normalize_urls_order_preserved():
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({"url": "https://z.com", "urls": ["https://a.com", "https://m.com"]})
    assert out == ["https://z.com", "https://a.com", "https://m.com"]


def test_normalize_urls_empty_strings_in_list():
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({"urls": ["https://a.com", "", "  ", "https://b.com"]})
    assert out == ["https://a.com", "https://b.com"]


def test_normalize_urls_mixed_scheme():
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({"url": "http://old.site.com"})
    assert out == ["http://old.site.com"]


# ── Timeout clamping ─────────────────────────────────────────────────────────


def test_timeout_default_when_missing(monkeypatch):
    """No timeout arg → handler passes timeout=None to extractor."""
    from tools.scrapegraph_tool import _handle_scrapegraph

    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["timeout"] = timeout
        return {"ok": True}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert captured["timeout"] is None


def test_timeout_clamps_to_min_10(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["timeout"] = timeout
        return {"ok": True}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    _run_tool(_handle_scrapegraph({"url": "https://x.com", "timeout": 3}))
    assert captured["timeout"] == 10


def test_timeout_clamps_to_max_300(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["timeout"] = timeout
        return {"ok": True}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    _run_tool(_handle_scrapegraph({"url": "https://x.com", "timeout": 999}))
    assert captured["timeout"] == 300


def test_timeout_invalid_value_falls_back_to_none(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["timeout"] = timeout
        return {"ok": True}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    _run_tool(_handle_scrapegraph({"url": "https://x.com", "timeout": "not-a-number"}))
    assert captured["timeout"] is None


def test_timeout_honors_valid_value(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["timeout"] = timeout
        return {"ok": True}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    _run_tool(_handle_scrapegraph({"url": "https://x.com", "timeout": 120}))
    assert captured["timeout"] == 120


# ── Error classification ─────────────────────────────────────────────────────


def _fake_extract_raising(msg):
    """Return a mock extract_structured that raises RuntimeError(msg)."""

    async def _fake(*a, **k):
        raise RuntimeError(msg)

    return _fake


def test_handler_error_x_display(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    monkeypatch.setattr(
        "tools.scrapegraph_tool.extract_structured",
        _fake_extract_raising("Missing X server or $DISPLAY"),
    )
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert "display server" in res["error"] or "render_js=false" in res["error"]


def test_handler_error_unauthorized(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    monkeypatch.setattr(
        "tools.scrapegraph_tool.extract_structured",
        _fake_extract_raising("401 Unauthorized - no api key"),
    )
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert "not authenticated" in res["error"] or "credentials" in res["error"]


def test_handler_error_rate_limit(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    monkeypatch.setattr(
        "tools.scrapegraph_tool.extract_structured",
        _fake_extract_raising("429 Too Many Requests: rate_limit exceeded"),
    )
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert "rate-limited" in res["error"] or "rate limit" in res["error"]


def test_handler_error_invalid_json(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    monkeypatch.setattr(
        "tools.scrapegraph_tool.extract_structured",
        _fake_extract_raising("Invalid json output from LLM"),
    )
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert "malformed" in res["error"] or "specific prompt" in res["error"]


def test_handler_error_generic_fallback(monkeypatch):
    from tools.scrapegraph_tool import _handle_scrapegraph

    monkeypatch.setattr(
        "tools.scrapegraph_tool.extract_structured",
        _fake_extract_raising("Something completely unexpected happened"),
    )
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert "extraction failed" in res["error"] or "network error" in res["error"]


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
