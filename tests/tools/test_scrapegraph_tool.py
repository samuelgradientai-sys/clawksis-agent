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
    assert {"url", "urls", "prompt", "output_schema", "render_js", "timeout"} <= set(
        props
    )
    assert SCRAPEGRAPH_SCHEMA["parameters"]["required"] == []


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

    async def _fake_extract(
        source, prompt, *, schema=None, headless=True, timeout=None
    ):
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

    out = _normalize_urls({
        "url": "https://a.com",
        "urls": ["https://a.com", "https://b.com"],
    })
    assert out == ["https://a.com", "https://b.com"]


def test_normalize_urls_order_preserved():
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({
        "url": "https://z.com",
        "urls": ["https://a.com", "https://m.com"],
    })
    assert out == ["https://z.com", "https://a.com", "https://m.com"]


def test_normalize_urls_empty_strings_in_list():
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({"urls": ["https://a.com", "", "  ", "https://b.com"]})
    assert out == ["https://a.com", "https://b.com"]


def test_normalize_urls_mixed_scheme():
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({"url": "http://old.site.com"})
    assert out == ["http://old.site.com"]


def test_normalize_urls_skips_non_http_schemes():
    """ftp:/mailto:/javascript:/data:/file: URLs are not fetchable by
    scrapegraphai — they used to be mangled into "https://ftp://..." garbage
    that only failed later with obscure errors. They must be skipped."""
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({
        "url": "ftp://files.example.com/x.zip",
        "urls": [
            "mailto:boss@example.com",
            "javascript:void(0)",
            "data:text/html;base64,PGI+",
            "file:///etc/passwd",
            "https://good.example.com",
        ],
    })
    assert out == ["https://good.example.com"]

    # Uppercase scheme is still recognised as non-http(s) and skipped.
    assert _normalize_urls({"url": "FTP://x.com"}) == []

    # host:port is NOT a scheme — it must keep the https:// treatment.
    out = _normalize_urls({"urls": ["example.com:8080/path", "git+ssh://x@y/z"]})
    assert out == ["https://example.com:8080/path"]


def test_normalize_urls_non_string_url_does_not_crash():
    """Schema-violating non-string `url` values (int/dict/list) used to raise
    AttributeError; they must be treated as absent, not crash the handler."""
    from tools.scrapegraph_tool import _normalize_urls

    assert _normalize_urls({"url": 42}) == []
    assert _normalize_urls({"url": {"a": 1}}) == []
    assert _normalize_urls({"url": ["a.com"]}) == []
    assert _normalize_urls({"url": 42, "urls": ["b.com"]}) == ["https://b.com"]


def test_normalize_urls_none_url():
    from tools.scrapegraph_tool import _normalize_urls

    assert _normalize_urls({"url": None}) == []
    assert _normalize_urls({"url": None, "urls": ["https://a.com"]}) == [
        "https://a.com"
    ]


def test_normalize_urls_skips_non_string_items_in_list():
    """Non-string items inside `urls` (None/int/dict/list — schema-violating
    sloppy calls) used to be str()-coerced into garbage URLs like
    "https://None" or "https://{'a': 1}" that only failed later with obscure
    errors. They must be skipped, keeping only real string URLs."""
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({
        "urls": [42, None, {"a": 1}, ["x"], "b.com", "  c.com  ", 0],
    })
    assert out == ["https://b.com", "https://c.com"]


def test_normalize_urls_mixed_valid_and_junk():
    """Valid `url` + `urls` with junk items: junk dropped, valid kept, no crash."""
    from tools.scrapegraph_tool import _normalize_urls

    out = _normalize_urls({
        "url": "https://a.com",
        "urls": [None, "", "https://b.com", {"bad": 1}],
    })
    assert out == ["https://a.com", "https://b.com"]


def test_handler_non_string_prompt_uses_default(monkeypatch):
    """A non-string `prompt` must fall back to the default, not crash."""
    from tools.scrapegraph_tool import _handle_scrapegraph

    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["prompt"] = prompt
        return {"ok": True}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com", "prompt": 42}))
    assert res["ok"] is True
    assert "main, useful content" in captured["prompt"]


# ── render_js / headless hardening ──────────────────────────────────────────


def test_handler_non_bool_render_js_stays_headless(monkeypatch, caplog):
    """A sloppy non-bool `render_js` ("" / 0 / "false") must NOT flip the tool
    into headed mode — bool("") and bool(0) are False, which would crash on
    headless servers with "Missing X server or $DISPLAY". Non-bools fall back
    to headless=True and log a warning so the misuse is visible."""
    import logging

    from tools.scrapegraph_tool import _handle_scrapegraph

    caplog.set_level(logging.WARNING)
    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["headless"] = headless
        return {"ok": True}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    for bad in ("", 0, "false", [], {}):
        res = _run_tool(_handle_scrapegraph({"url": "https://x.com", "render_js": bad}))
        assert res["ok"] is True, f"render_js={bad!r} must not crash"
        assert captured["headless"] is True, f"render_js={bad!r} must stay headless"
    assert "non-boolean render_js" in caplog.text


def test_handler_bool_render_js_respected(monkeypatch):
    """Real booleans pass through: True → headless, False → headed (respected)."""
    from tools.scrapegraph_tool import _handle_scrapegraph

    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["headless"] = headless
        return {"ok": True}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    _run_tool(_handle_scrapegraph({"url": "https://x.com", "render_js": True}))
    assert captured["headless"] is True
    _run_tool(_handle_scrapegraph({"url": "https://x.com", "render_js": False}))
    assert captured["headless"] is False


def test_handler_render_js_missing_defaults_headless(monkeypatch):
    """No `render_js` arg → headless=True (the documented default)."""
    from tools.scrapegraph_tool import _handle_scrapegraph

    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["headless"] = headless
        return {"ok": True}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert captured["headless"] is True


# ── clamp_timeout helper ─────────────────────────────────────────────────────


def test_clamp_timeout_none():
    assert sgc.clamp_timeout(None) is None


def test_clamp_timeout_valid():
    assert sgc.clamp_timeout(120) == 120
    assert sgc.clamp_timeout(10) == 10
    assert sgc.clamp_timeout(300) == 300


def test_clamp_timeout_clamps_min():
    assert sgc.clamp_timeout(3) == 10
    assert sgc.clamp_timeout(0) == 10
    assert sgc.clamp_timeout(-5) == 10


def test_clamp_timeout_clamps_max():
    assert sgc.clamp_timeout(999) == 300
    assert sgc.clamp_timeout(500) == 300


def test_clamp_timeout_string():
    assert sgc.clamp_timeout("120") == 120
    assert sgc.clamp_timeout("3") == 10
    assert sgc.clamp_timeout("999") == 300


def test_clamp_timeout_invalid():
    assert sgc.clamp_timeout("not-a-number") is None
    assert sgc.clamp_timeout([]) is None
    assert sgc.clamp_timeout({}) is None


def test_clamp_timeout_bool_treated_as_absent():
    """bool is an int subclass — without the guard, `timeout=False` (0) would
    clamp to the 10s minimum and silently ENABLE an extraction timeout the
    caller meant to disable; `timeout=True` (1) would too. Bools carry no
    timeout value: treat them as absent (same sloppy-call defence as _as_bool).
    """
    assert sgc.clamp_timeout(True) is None
    assert sgc.clamp_timeout(False) is None


def test_clamp_timeout_float():
    """Float is truncated to int via int()."""
    assert sgc.clamp_timeout(45.7) == 45
    assert sgc.clamp_timeout(12.1) == 12
    assert sgc.clamp_timeout(9.9) == 10  # clamped up


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


# ── Shared error classifier ─────────────────────────────────────────────────


def test_classify_x_display():
    hint = sgc.classify_scrapegraph_error(RuntimeError("Missing X server"))
    assert "display server" in hint


def test_classify_auth():
    hint = sgc.classify_scrapegraph_error(RuntimeError("401 Unauthorized"))
    assert "not authenticated" in hint


def test_classify_rate_limit():
    hint = sgc.classify_scrapegraph_error(RuntimeError("429 RateLimitError"))
    assert "rate-limited" in hint


def test_classify_quota_billing():
    """Quota/billing errors get their own hint (v1.9) — retrying won't help."""
    hint = sgc.classify_scrapegraph_error(
        RuntimeError("Error code: 429 - {'error': {'code': 'insufficient_quota'}}")
    )
    assert "out of credits" in hint
    assert "retrying" in hint
    assert "rate-limited" not in hint  # NOT misread as a plain rate limit
    assert sgc.classify_scrapegraph_error(
        RuntimeError("billing_not_active for the project")
    ).startswith("The LLM model used by ScrapeGraphAI")
    assert "balance" in sgc.classify_scrapegraph_error(
        RuntimeError("Insufficient Credits on OpenRouter")
    )
    assert "balance" in sgc.classify_scrapegraph_error(
        RuntimeError("402 Payment Required")
    )


def test_classify_invalid_json():
    hint = sgc.classify_scrapegraph_error(RuntimeError("Invalid json output from LLM"))
    assert "malformed" in hint


def test_classify_generic():
    hint = sgc.classify_scrapegraph_error(RuntimeError("Something weird"))
    assert "extraction failed" in hint


def test_classify_timeout_error():
    """TimeoutError (asyncio.TimeoutError) is classified specifically now."""
    hint = sgc.classify_scrapegraph_error(TimeoutError("timed out"))
    assert "timed out" in hint
    assert "Increase" in hint
    assert "timeout" in hint.lower()
    assert "simpler" in hint


def test_classify_http_status():
    """HTTP status errors (404/5xx) are page-level, classified specifically."""
    hint = sgc.classify_scrapegraph_error(RuntimeError("HTTP 404 Not Found"))
    assert "http error" in hint.lower()
    hint = sgc.classify_scrapegraph_error(RuntimeError("503 Service Unavailable"))
    assert "http error" in hint.lower()


def test_classify_http_forbidden_is_not_network():
    """A Cloudflare-style 403 is a page-level HTTP error, not a network one."""
    hint = sgc.classify_scrapegraph_error(
        RuntimeError("403 Forbidden - Access denied by Cloudflare")
    )
    assert "http error" in hint.lower()
    assert "network error" not in hint.lower()


def test_classify_network_dns():
    """DNS failures (getaddrinfo / name resolution) get the network hint."""
    hint = sgc.classify_scrapegraph_error(
        RuntimeError("getaddrinfo failed: Name or service not known")
    )
    assert "network error" in hint.lower()
    assert "dns" in hint.lower()


def test_classify_network_connection():
    hint = sgc.classify_scrapegraph_error(ConnectionError("Connection refused"))
    assert "network error" in hint.lower()


def test_classify_network_timeout_message():
    """A string-based network timeout (NOT a TimeoutError instance) maps to
    the network category, not the LLM-extraction-timeout hint."""
    hint = sgc.classify_scrapegraph_error(
        RuntimeError("Read timed out after 30 seconds")
    )
    assert "network error" in hint.lower()
    assert "simpler prompt" not in hint


def test_classify_real_timeout_beats_network_keywords():
    """A real TimeoutError still maps to the LLM-extraction hint even though
    its message contains 'timed out' (a network keyword)."""
    hint = sgc.classify_scrapegraph_error(TimeoutError("timed out"))
    assert "Increase" in hint
    assert "network error" not in hint.lower()


def test_classify_graph_execution_timeout_message():
    """scrapegraphai's own 'graph execution timed out' message maps to the
    LLM-extraction timeout hint, not the network category."""
    hint = sgc.classify_scrapegraph_error(
        RuntimeError("The graph execution timed out after 60 seconds")
    )
    assert "Increase" in hint


# ── Empty-result ("NA") detection ───────────────────────────────────────────


def test_looks_like_empty_result_string_sentinels():
    """scrapegraphai "succeeds" with NA/N-A/None sentinels when it fails to
    structurally parse a page — those must be flagged as empty."""
    for bad in (
        "NA",
        "na",
        "N/A",
        "n/a",
        "n.a.",
        "None",
        "null",
        "nan",
        "{}",
        "  NA  ",
        # v1.9: common LLM "couldn't extract anything" phrasings
        "no content",
        "No Data",
        "no result",
        "no results",
        "no text",
        "NOTHING",
        "not found",
        "EMPTY",
        "nil",
        "undefined",
        # v1.10: placeholder family — dash/dot/ellipsis and "not available"
        # phrasings LLMs emit when they could not find the field.
        "-",
        "–",
        "—",
        ".",
        "..",
        "...",
        "…",
        "  —  ",
        "not available",
        "No Info",
        "no information",
        "NO VALUE",
    ):
        assert sgc.looks_like_empty_result(bad) is True, f"{bad!r} must be empty"
    assert sgc.looks_like_empty_result("") is True
    assert sgc.looks_like_empty_result(None) is True


def test_looks_like_empty_result_punctuated_sentinels():
    """v1.12: LLMs punctuate their failure sentinels — 'N/A.', 'none.',
    'not available.', '...' — so a trailing full stop must not turn an empty
    sentinel into 'real content'. The lone '.' family stays a sentinel too."""
    for bad in (
        "N/A.",
        "n/a.",
        "none.",
        "null.",
        "nan.",
        "No Data.",
        "no content.",
        "no result.",
        "not found.",
        "nothing.",
        "empty.",
        "nil.",
        "undefined.",
        "-.",
        "not available.",
        "no info.",
        "no information.",
        "no value.",
    ):
        assert sgc.looks_like_empty_result(bad) is True, f"{bad!r} must be empty"
    # Dotted sentinels survive the trailing-'.' trim.
    for bad in (".", "..", "...", "…"):
        assert sgc.looks_like_empty_result(bad) is True, f"{bad!r} must be empty"
    # Real content with a period is still kept — never discarded.
    for good in ("Real content.", "N/A and here's the note", "price is 9.99."):
        assert sgc.looks_like_empty_result(good) is False, f"{good!r} must be kept"
    assert sgc.looks_like_empty_result({"price": "N/A."}) is True
    assert sgc.looks_like_empty_result({"price": "N/A.", "title": "Real"}) is False


def test_looks_like_empty_result_placeholders_partial_kept():
    """A placeholder marks a field as missing, but only ALL-placeholder results
    are empty — a result mixing a dash with a real value is kept (v1.10)."""
    # Whole results made of placeholders → empty.
    assert sgc.looks_like_empty_result({"price": "-"}) is True
    assert sgc.looks_like_empty_result({"answer": "…"}) is True
    assert sgc.looks_like_empty_result([{"name": "-"}, {"name": "—"}]) is True
    assert sgc.looks_like_empty_result({"data": {"price": "."}}) is True
    assert sgc.looks_like_empty_result({"status": "not available"}) is True
    # Any real value anywhere keeps the result.
    assert sgc.looks_like_empty_result({"price": "-", "title": "Real"}) is False
    assert sgc.looks_like_empty_result({"name": "—", "count": 3}) is False
    assert (
        sgc.looks_like_empty_result({"data": [{"price": "-"}, {"price": 9.99}]})
        is False
    )
    # Real single-char values that are NOT placeholders stay real data.
    assert sgc.looks_like_empty_result("a") is False
    assert sgc.looks_like_empty_result("?") is False


def test_looks_like_empty_result_real_content_kept():
    """Real text is never mistaken for a failure sentinel."""
    for good in ("The page loads fine", "NA means North America", "a", "NaN handling"):
        assert sgc.looks_like_empty_result(good) is False, f"{good!r} must be kept"
    assert sgc.looks_like_empty_result(42) is False
    assert sgc.looks_like_empty_result(9.99) is False
    assert sgc.looks_like_empty_result(True) is False


def test_looks_like_empty_result_dict_shapes():
    """Dict is empty when every value is a sentinel; partial extractions are
    kept so real data is never discarded."""
    assert sgc.looks_like_empty_result({}) is True
    assert sgc.looks_like_empty_result({"content": "NA"}) is True
    assert sgc.looks_like_empty_result({"content": ""}) is True
    assert sgc.looks_like_empty_result({"title": "NA", "body": "NA"}) is True
    assert sgc.looks_like_empty_result({"content": None}) is True
    # Partial results (any real value) are kept.
    assert sgc.looks_like_empty_result({"title": "NA", "body": "real text"}) is False
    assert sgc.looks_like_empty_result({"price": 9.99}) is False
    assert sgc.looks_like_empty_result({"content": "real content"}) is False


def test_looks_like_empty_result_list_shapes():
    assert sgc.looks_like_empty_result([]) is True
    assert sgc.looks_like_empty_result(["NA"]) is True
    assert sgc.looks_like_empty_result([{"content": "N/A"}]) is True
    assert sgc.looks_like_empty_result(["NA", "real"]) is False
    assert sgc.looks_like_empty_result([{"content": "real"}]) is False


def test_looks_like_empty_result_nested_shapes():
    """Nested dict/list values are checked recursively (v1.9): an all-sentinel
    nested result is empty, a nested result with any real value is kept."""
    # Nested dict of dicts — previously kept as "real content" garbage.
    assert sgc.looks_like_empty_result({"content": {"answer": "NA"}}) is True
    assert sgc.looks_like_empty_result({"data": {"result": "N/A"}}) is True
    # Nested list-of-dicts inside a dict.
    assert sgc.looks_like_empty_result({"data": [{"content": "N/A"}]}) is True
    assert sgc.looks_like_empty_result({"data": []}) is True
    assert sgc.looks_like_empty_result({"data": [{}]}) is True
    # Deeply nested mixed shapes.
    assert (
        sgc.looks_like_empty_result({
            "content": [{"answer": "none"}, {"answer": "null"}]
        })
        is True
    )
    # Any real value at ANY depth keeps the result.
    assert sgc.looks_like_empty_result({"content": {"answer": "real"}}) is False
    assert sgc.looks_like_empty_result({"data": [{"content": "real"}]}) is False
    assert (
        sgc.looks_like_empty_result({"data": [{"content": "NA"}, {"content": "real"}]})
        is False
    )
    assert sgc.looks_like_empty_result({"content": {"price": 9.99}}) is False


def test_handler_empty_result_string_returns_scrape_hint(monkeypatch):
    """A bare "NA" result used to come back as ok=True with extracted='"NA"'.
    It must now be an actionable error pointing at the `scrape` tool."""
    from tools.scrapegraph_tool import _handle_scrapegraph

    async def _fake(*a, **k):
        return "NA"

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert res["ok"] is False
    assert "`scrape` tool" in res["error"] or "Scrapling" in res["error"]


def test_handler_empty_dict_result_returns_scrape_hint(monkeypatch):
    """The documented failure shape {"content": "NA"} must not be a success."""
    from tools.scrapegraph_tool import _handle_scrapegraph

    async def _fake(*a, **k):
        return {"content": "NA"}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert res["ok"] is False
    assert "no useful content" in res["error"]


def test_handler_partial_result_stays_success(monkeypatch):
    """A partial extraction (some real data) must still be returned as ok=True."""
    from tools.scrapegraph_tool import _handle_scrapegraph

    async def _fake(*a, **k):
        return {"title": "NA", "body": "real content here"}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake)
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert res["ok"] is True
    assert "real content here" in res["extracted"]


def test_handler_multi_empty_result_returns_scrape_hint(monkeypatch):
    """Multi-source path flags empty results too."""
    from tools.scrapegraph_tool import _handle_scrapegraph

    async def _fake(*a, **k):
        return [{"content": "NA"}]

    monkeypatch.setattr("tools.scrapegraph_tool.extract_many", _fake)
    res = _run_tool(_handle_scrapegraph({"urls": ["https://a.com", "https://b.com"]}))
    assert res["ok"] is False
    assert "`scrape` tool" in res["error"] or "Scrapling" in res["error"]


# ── Lazy install must not block the event loop ──────────────────────────────


def test_extract_structured_install_runs_in_worker_thread(monkeypatch):
    """The lazy install (ensure_installed) must run through asyncio.to_thread
    so the first-use 30-60s pip install never freezes the event loop."""
    import tools.scrapegraph_common as sgc

    install_fn = lambda: None  # noqa: E731 — stands in for ensure_installed
    run_fn = lambda *a, **k: {"ok": True}  # noqa: E731 — stands in for _run_smart
    calls: list[object] = []
    real_to_thread = asyncio.to_thread

    async def _spy_to_thread(fn, *a, **k):
        calls.append(fn)
        return await real_to_thread(fn, *a, **k)

    monkeypatch.setattr(asyncio, "to_thread", _spy_to_thread)
    monkeypatch.setattr(sgc, "ensure_installed", install_fn)
    monkeypatch.setattr(sgc, "_run_smart", run_fn)
    monkeypatch.setattr(sgc, "graph_config", lambda **k: {"llm": {}, "headless": True})

    res = _run(sgc.extract_structured("https://x.com", "test prompt"))
    assert res == {"ok": True}
    # install ran FIRST, inside a worker thread (asyncio.to_thread), never
    # synchronously on the event loop.
    assert calls[0] is install_fn
    assert run_fn in calls


def test_extract_many_install_runs_in_worker_thread(monkeypatch):
    """Same guarantee for the multi-source path."""
    import tools.scrapegraph_common as sgc

    install_fn = lambda: None  # noqa: E731
    run_fn = lambda *a, **k: [{"ok": True}]  # noqa: E731
    calls: list[object] = []
    real_to_thread = asyncio.to_thread

    async def _spy_to_thread(fn, *a, **k):
        calls.append(fn)
        return await real_to_thread(fn, *a, **k)

    monkeypatch.setattr(asyncio, "to_thread", _spy_to_thread)
    monkeypatch.setattr(sgc, "ensure_installed", install_fn)
    monkeypatch.setattr(sgc, "_run_multi", run_fn)
    monkeypatch.setattr(sgc, "graph_config", lambda **k: {"llm": {}, "headless": True})

    res = _run(sgc.extract_many(["https://a.com", "https://b.com"], "p"))
    assert res == [{"ok": True}]
    assert calls[0] is install_fn
    assert run_fn in calls


# ── web_extract backend ─────────────────────────────────────────────────────


def test_backend_is_extract_only():
    p = ScrapegraphWebProvider()
    assert p.name == "scrapegraph"
    assert p.supports_extract() is True
    assert p.supports_search() is False
    assert p.search("q")["success"] is False


def test_backend_extract_shapes_results(monkeypatch):
    p = ScrapegraphWebProvider()

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        return {"content": f"# Page {source}"}

    monkeypatch.setattr("tools.scrapegraph_common.extract_structured", _fake)
    out = _run(p.extract(["https://a.com", "https://b.com"]))
    assert [r["url"] for r in out] == ["https://a.com", "https://b.com"]
    assert out[0]["content"] == "# Page https://a.com"
    assert out[0]["metadata"]["sourceURL"] == "https://a.com"


def test_backend_extract_per_url_error(monkeypatch):
    """Provider errors are classified (not raw str(exc))."""
    p = ScrapegraphWebProvider()

    async def _boom(*a, **k):
        raise RuntimeError("Missing X server or $DISPLAY")

    monkeypatch.setattr("tools.scrapegraph_common.extract_structured", _boom)
    out = _run(p.extract(["https://a.com"]))
    assert "display server" in out[0]["error"]
    assert "boom" not in out[0]["error"]
    assert out[0]["content"] == ""


def test_backend_extract_timeout_passthrough(monkeypatch):
    """Provider passes timeout from kwargs to extract_structured."""
    p = ScrapegraphWebProvider()
    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["timeout"] = timeout
        return {"content": "ok"}

    monkeypatch.setattr("tools.scrapegraph_common.extract_structured", _fake)
    _run(p.extract(["https://a.com"], timeout=120))
    assert captured["timeout"] == 120


def test_backend_extract_timeout_clamps(monkeypatch):
    """Timeout is clamped to [10, 300] before reaching extract_structured."""
    p = ScrapegraphWebProvider()
    captured = {}

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        captured["timeout"] = timeout
        return {"content": "ok"}

    monkeypatch.setattr("tools.scrapegraph_common.extract_structured", _fake)
    _run(p.extract(["https://a.com"], timeout=999))
    assert captured["timeout"] == 300


def test_backend_extract_empty_result_hint(monkeypatch):
    """A "NA" sentinel result must yield an actionable hint, not "NA" content."""
    p = ScrapegraphWebProvider()

    async def _fake(source, prompt, *, schema=None, headless=True, timeout=None):
        return {"content": "NA"}

    monkeypatch.setattr("tools.scrapegraph_common.extract_structured", _fake)
    out = _run(p.extract(["https://a.com"]))
    assert out[0]["content"] == ""
    assert "scrape" in out[0]["error"].lower()
    assert "NA" not in out[0]["content"]


def test_stringify_prefers_known_keys():
    from plugins.web.scrapegraphai.provider import _stringify

    assert _stringify({"content": "hello"}) == "hello"
    assert _stringify("raw") == "raw"
    assert "k" in _stringify({"k": "v"})  # falls back to JSON dump


def test_stringify_handles_list_results():
    """scrapegraphai sometimes wraps results in a list — join their string
    forms instead of dumping an ugly Python repr."""
    from plugins.web.scrapegraphai.provider import _stringify

    assert _stringify([{"content": "first"}, {"content": "second"}]) == (
        "first\n\nsecond"
    )
    assert _stringify(["raw", "text"]) == "raw\n\ntext"
    assert _stringify([{}, []]) == ""
    assert "k" in _stringify([{"k": "v"}])  # per-item JSON dump fallback
    assert _stringify(None) == ""


def test_stringify_extra_keys_and_nested_values():
    """v1.9: data/response/output/body keys are honoured, and dict/list values
    under a known key are stringified recursively instead of JSON-dumped."""
    from plugins.web.scrapegraphai.provider import _stringify

    assert _stringify({"data": "payload"}) == "payload"
    assert _stringify({"response": "resp"}) == "resp"
    assert _stringify({"output": "out"}) == "out"
    assert _stringify({"body": "body text"}) == "body text"
    # Nested dict under a known key.
    assert _stringify({"data": {"content": "nested"}}) == "nested"
    assert _stringify({"data": {"answer": "deep answer"}}) == "deep answer"
    # Nested list under a known key.
    assert _stringify({"data": [{"content": "first"}, {"content": "second"}]}) == (
        "first\n\nsecond"
    )
    # Empty nested value under a known key → falls through to JSON dump.
    assert "k" in _stringify({"data": {}, "k": "v"})


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


# ── Result truncation ───────────────────────────────────────────────────────


def test_handler_truncation_marks_oversized_result(monkeypatch):
    """An oversized JSON result is cut AND tagged so the model knows it's incomplete
    (a bare cut otherwise looks like a finished blob whose tail silently vanished)."""
    from tools.scrapegraph_tool import (
        _MAX_RESULT_CHARS,
        _TRUNCATION_MARKER,
        _handle_scrapegraph,
    )

    async def _fake_extract(
        source, prompt, *, schema=None, headless=True, timeout=None
    ):
        # Render to well over the budget (with indent=2 the dump is large).
        return {"content": "x" * (_MAX_RESULT_CHARS + 500)}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake_extract)
    res = _run_tool(_handle_scrapegraph({"url": "https://x.com"}))
    assert res["ok"] is True
    assert res["truncated"] is True
    # The visible marker is present so the cut is not silent.
    assert _TRUNCATION_MARKER in res["extracted"]
    # Total output never exceeds the budget.
    assert len(res["extracted"]) <= _MAX_RESULT_CHARS
    # The tail carries the marker (not a dangling value mid-way).
    assert res["extracted"].endswith(_TRUNCATION_MARKER)


def test_handler_short_result_not_truncated(monkeypatch):
    """Results within budget stay untouched — no marker, no flag."""
    from tools.scrapegraph_tool import _handle_scrapegraph

    async def _fake_extract(
        source, prompt, *, schema=None, headless=True, timeout=None
    ):
        return {"title": "Hi", "price": 9.99}

    monkeypatch.setattr("tools.scrapegraph_tool.extract_structured", _fake_extract)
    res = _run_tool(_handle_scrapegraph({"url": "example.com"}))
    assert res["ok"] is True
    assert res["truncated"] is False
    assert "TRUNCATED" not in res["extracted"]
    assert '"title"' in res["extracted"]


def test_truncate_rendered_respects_budget_and_marker():
    """Unit-level: the helper keeps total length <= limit, keeps payload bytes and appends the marker."""
    from tools.scrapegraph_tool import _TRUNCATION_MARKER, _truncate_rendered

    big = "a" * 200
    marker_len = len(_TRUNCATION_MARKER)

    # Budget > marker: payload is cut, marker fits fully, total <= limit.
    limit = 60
    limited = _truncate_rendered(big, limit=limit)
    assert len(limited) == limit
    assert limited.startswith("a" * (limit - marker_len))
    assert limited.endswith(_TRUNCATION_MARKER)

    # Budget == marker length: only the marker fits, no payload.
    assert _truncate_rendered(big, limit=marker_len) == _TRUNCATION_MARKER

    # Budget < marker length: truncate the marker itself.
    assert _truncate_rendered(big, limit=5) == _TRUNCATION_MARKER[:5]

    # Zero/below-zero budgets don't blow up.
    assert _truncate_rendered(big, limit=0) == ""
    assert _truncate_rendered(big, limit=-1) == ""
