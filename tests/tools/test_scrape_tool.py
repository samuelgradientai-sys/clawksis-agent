"""Tests for ``scrape_tool.py`` — the Scrapling-backed anti-bot fetch tool.

Coverage:
  _scrapling_cmd() — binary discovery (override env, PATH, python -m, none)
  _resolve_proxy() — priority chain: arg > env > config > None
  _classify() — all content-classification patterns (ip_block, antibot,
                empty, ok) at both short and long page sizes
  _MODE_TO_SUBCMD and _FORMAT_EXT mappings
  Tool registration — name, toolset, schema shape
  _handle_scrape() — URL requirement, scheme normalisation, ladder
                     escalation, ip_block early-abort, empty-content
                     reporting, success, proxy resolution integration

All subprocess calls are mocked — no real ``scrapling`` binary required.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

import tools.scrape_tool as st


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _run_tool(coro):
    """Run a tool handler (returns JSON string) and parse to dict."""
    return json.loads(asyncio.run(coro))


# ═══════════════════════════════════════════════════════════════════════
# _scrapling_cmd — binary discovery
# ═══════════════════════════════════════════════════════════════════════


class TestScraplingCmd:
    """Verify the binary discovery ladder: env → PATH → python -m → None."""

    def test_uses_env_override(self, monkeypatch):
        monkeypatch.setenv("SCRAPLING_BIN", "/custom/scrapling")
        monkeypatch.setattr(st.shutil, "which", lambda x: x if "custom" in x else None)
        assert st._scrapling_cmd() == ["/custom/scrapling"]

    def test_env_override_skipped_when_not_found(self, monkeypatch):
        monkeypatch.setenv("SCRAPLING_BIN", "/nonexistent/scrapling")
        monkeypatch.setattr(st.shutil, "which", lambda x: None)
        assert st._scrapling_cmd() is None

    def test_finds_on_path(self, monkeypatch):
        monkeypatch.delenv("SCRAPLING_BIN", raising=False)
        monkeypatch.setattr(st.shutil, "which", lambda x: "/usr/bin/scrapling")
        assert st._scrapling_cmd() == ["/usr/bin/scrapling"]

    def test_fallback_python_minus_m(self, monkeypatch):
        monkeypatch.delenv("SCRAPLING_BIN", raising=False)
        monkeypatch.setattr(st.shutil, "which", lambda x: None)
        monkeypatch.setattr(
            "importlib.util.find_spec",
            lambda name: True if name == "scrapling" else None,
        )
        assert st._scrapling_cmd()[-2:] == ["-m", "scrapling"]

    def test_returns_none_when_not_found(self, monkeypatch):
        monkeypatch.delenv("SCRAPLING_BIN", raising=False)
        monkeypatch.setattr(st.shutil, "which", lambda x: None)
        monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
        assert st._scrapling_cmd() is None


# ═══════════════════════════════════════════════════════════════════════
# _resolve_proxy — priority chain
# ═══════════════════════════════════════════════════════════════════════


class TestResolveProxy:
    """Verify arg > env > config.yaml > None priority."""

    def test_arg_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("SCRAPLING_PROXY", "http://env:8080")
        assert st._resolve_proxy("http://arg:3128") == "http://arg:3128"

    def test_env_wins_over_config(self, monkeypatch):
        monkeypatch.setenv("SCRAPLING_PROXY", "http://env:8080")
        with patch(
            "clawk_cli.config.load_config",
            return_value={"web": {"scrapling_proxy": "http://cfg:3128"}},
        ):
            assert st._resolve_proxy(None) == "http://env:8080"

    def test_config_fallback(self, monkeypatch):
        monkeypatch.delenv("SCRAPLING_PROXY", raising=False)
        with patch(
            "clawk_cli.config.load_config",
            return_value={"web": {"scrapling_proxy": "http://cfg:3128"}},
        ):
            assert st._resolve_proxy(None) == "http://cfg:3128"

    def test_returns_none_when_no_source(self, monkeypatch):
        monkeypatch.delenv("SCRAPLING_PROXY", raising=False)
        with patch(
            "clawk_cli.config.load_config",
            return_value={},
        ):
            assert st._resolve_proxy(None) is None

    def test_empty_arg_treated_as_none(self, monkeypatch):
        monkeypatch.delenv("SCRAPLING_PROXY", raising=False)
        with patch(
            "clawk_cli.config.load_config",
            return_value={},
        ):
            assert st._resolve_proxy("") is None


# ═══════════════════════════════════════════════════════════════════════
# _classify — content classification
# ═══════════════════════════════════════════════════════════════════════
#
# KEY INSIGHT: `_classify` calls `.strip()` then checks `len(stripped)`.
# Any padding used in test helpers must be non-whitespace so it survives
# `.strip()`. We use 'x' for padding.

MIN_FOR_CLASSIFY = st._MIN_USEFUL_CHARS + 1  # 201 — just past empty gate
SHORT_FOR_WEAK = st._BLOCK_PAGE_MAX_CHARS // 2  # 750 — well under threshold
LONG_FOR_WEAK = st._BLOCK_PAGE_MAX_CHARS + 500  # 2000 — safely above


def _small_page(text: str) -> str:
    """Page content between MIN_USEFUL_CHARS and BLOCK_PAGE_MAX_CHARS."""
    needed = SHORT_FOR_WEAK - len(text)
    return text + "x" * max(needed, 0)


def _large_page(text: str) -> str:
    """Page content longer than BLOCK_PAGE_MAX_CHARS."""
    needed = LONG_FOR_WEAK - len(text)
    return text + "x" * max(needed, 0)


def _min_page(text: str) -> str:
    """Page content just above MIN_USEFUL_CHARS threshold."""
    needed = MIN_FOR_CLASSIFY - len(text)
    return text + "x" * max(needed, 0)


class TestClassify:
    """Verify the five output states: ip_block / antibot / empty / ok."""

    # ── IP block (strong — matches at ANY length) ───────────────────

    @pytest.mark.parametrize(
        "phrase",
        [
            "too many requests",
            "unusual traffic",
            "rate limit exceeded",
            "you have been blocked",
            "verify you are human",
            "select all squares containing",
        ],
    )
    def test_ip_block_strong_short(self, phrase):
        assert st._classify(_small_page(phrase)) == "ip_block"

    def test_ip_block_strong_long(self):
        assert st._classify(_large_page("Too Many Requests")) == "ip_block"

    # ── IP block (weak — only on SHORT pages) ───────────────────────

    @pytest.mark.parametrize(
        "phrase",
        [
            "captcha",
            "are you a robot",
            "access denied",
            "forbidden",
            "429",
            "403",
        ],
    )
    def test_ip_block_weak_short(self, phrase):
        assert st._classify(_small_page(phrase)) == "ip_block"

    def test_ip_block_weak_long_is_not_block(self):
        """A long page with 'captcha'/'forbidden' in body = real content."""
        assert (
            st._classify(
                _large_page("In this article we discuss captcha solving techniques")
            )
            == "ok"
        )

    # ── Anti-bot (strong — matches at ANY length) ───────────────────

    @pytest.mark.parametrize(
        "phrase",
        [
            "just a moment",
            "checking your browser before",
            "cf-browser-verification",
            "ddos protection by",
        ],
    )
    def test_antibot_strong(self, phrase):
        assert st._classify(_small_page(phrase)) == "antibot"

    def test_antibot_strong_long(self):
        assert (
            st._classify(_large_page("Checking your browser before accessing"))
            == "antibot"
        )

    # ── Anti-bot (weak — only on SHORT pages) ───────────────────────

    @pytest.mark.parametrize("phrase", ["enable javascript", "please enable js"])
    def test_antibot_weak_short(self, phrase):
        assert st._classify(_small_page(phrase)) == "antibot"

    def test_antibot_weak_long_is_not_antibot(self):
        assert (
            st._classify(
                _large_page("Please enable JS to view comments on this article")
            )
            == "ok"
        )

    # ── Empty ───────────────────────────────────────────────────────

    @pytest.mark.parametrize("text", ["", "   ", "a", "A" * 50])
    def test_empty_content(self, text):
        assert st._classify(text) == "empty"

    # ── OK ──────────────────────────────────────────────────────────

    def test_normal_content(self):
        assert (
            st._classify("This is a real article with lots of content. " * 20) == "ok"
        )


# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════


class TestConstants:
    """Verify mode-to-subcmd and format-extension mappings."""

    def test_mode_to_subcmd(self):
        assert st._MODE_TO_SUBCMD == {
            "get": "get",
            "fetch": "fetch",
            "stealthy": "stealthy-fetch",
        }

    def test_format_ext(self):
        assert st._FORMAT_EXT == {
            "markdown": ".md",
            "text": ".txt",
            "html": ".html",
        }

    def test_auto_ladder(self):
        assert st._AUTO_LADDER == ["get", "fetch", "stealthy"]


# ═══════════════════════════════════════════════════════════════════════
# Tool registration
# ═══════════════════════════════════════════════════════════════════════


class TestRegistration:
    """Verify the tool is registered correctly in the 'web' toolset."""

    def test_registered_in_web_toolset(self):
        from toolsets import TOOLSETS
        from tools.registry import registry

        defs = registry.get_definitions(tool_names={"scrape"})
        assert defs, "scrape tool not found in registry"
        assert "scrape" in TOOLSETS["web"]["tools"]

    def test_schema_shape(self):
        from tools.scrape_tool import SCRAPE_SCHEMA

        assert SCRAPE_SCHEMA["name"] == "scrape"
        props = SCRAPE_SCHEMA["parameters"]["properties"]
        assert {
            "url",
            "mode",
            "format",
            "css_selector",
            "wait_selector",
            "proxy",
        } <= set(props)
        assert SCRAPE_SCHEMA["parameters"]["required"] == ["url"]


# ═══════════════════════════════════════════════════════════════════════
# _handle_scrape — tool handler
# ═══════════════════════════════════════════════════════════════════════
#
# The handler calls _run_one (which invokes subprocess). All such calls
# are mocked below. Content returned by mocks must be ≥ 200 chars to
# survive _classify()'s empty-content gate, unless we're explicitly
# testing the empty path.

OK_CONTENT = "# Hello World\n" * 30  # ~420 chars — passes empty gate


class TestHandleScrape:
    """Test the tool handler logic (subprocess mocked)."""

    def test_requires_url(self):
        res = _run_tool(st._handle_scrape({}))
        assert res["ok"] is False
        assert "url" in res["error"].lower()

    def test_scheme_normalisation(self, monkeypatch):
        """A bare domain gets https:// prepended."""
        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", lambda *a, **k: (True, OK_CONTENT, ""))

        res = _run_tool(st._handle_scrape({"url": "example.com"}))
        assert res["ok"] is True
        assert res["url"] == "https://example.com"

    def test_missing_scrapling_reported(self, monkeypatch):
        monkeypatch.setattr(st, "_scrapling_cmd", lambda: None)
        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is False
        assert "Scrapling is not installed" in res["error"]

    def test_ladder_stops_on_ok(self, monkeypatch):
        """When the first mode succeeds, don't try the rest."""
        calls = []

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            return (True, OK_CONTENT, "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is True
        assert calls == ["get"]

    def test_ladder_escalates_on_antibot(self, monkeypatch):
        """When get returns antibot, escalate to fetch then stealthy."""
        calls = []

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            if subcmd == "get":
                return (True, _small_page("Checking your browser before accessing"), "")
            # fetch and stealthy both return ok content
            return (True, OK_CONTENT, "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is True
        assert calls == ["get", "fetch"]

    def test_ladder_escalates_all_the_way(self, monkeypatch):
        """When fetch also returns antibot, go all the way to stealthy."""
        calls = []

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            if subcmd in ("get", "fetch"):
                return (True, _small_page("Checking your browser before accessing"), "")
            return (True, OK_CONTENT, "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is True
        assert calls == ["get", "fetch", "stealthy-fetch"]

    def test_stealthy_antibot_content_is_returned(self, monkeypatch):
        """When all modes return antibot, content is still returned (ok=True)
        with status='antibot'. Only ip_block causes ok=False."""
        calls = []

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            return (True, _small_page("Checking your browser before accessing"), "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        # Antibot content is still returned — the handler trusts the caller
        assert res["ok"] is True
        assert res["status"] == "antibot"
        assert calls == ["get", "fetch", "stealthy-fetch"]

    def test_ladder_aborts_on_ip_block(self, monkeypatch):
        """ip_block status stops the ladder — Scrapling can't fix IP bans."""
        calls = []

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            return (True, _small_page("Too Many Requests"), "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is False
        assert res["reason"] == "ip_block"
        assert "proxy" in res["error"].lower()
        assert len(calls) == 1

    def test_empty_content_ladder_runs_all_modes(self, monkeypatch):
        """When content is empty/too-short, all ladder modes are tried."""
        calls = []

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            return (False, "", "empty page")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is False
        assert "No content" in res["error"]
        assert calls == ["get", "fetch", "stealthy-fetch"]

    def test_proxy_passed_to_run_one(self, monkeypatch):
        captured = {"proxy": None}

        def capturing_run(base, subcmd, url, ext, css, wait, proxy, timeout):
            captured["proxy"] = proxy
            return (True, OK_CONTENT, "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", capturing_run)

        res = _run_tool(
            st._handle_scrape({
                "url": "https://example.com",
                "proxy": "http://user:pass@proxy:8080",
            })
        )
        assert res["ok"] is True
        assert captured["proxy"] == "http://user:pass@proxy:8080"

    def test_mode_auto_default(self, monkeypatch):
        calls = []

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            return (True, OK_CONTENT, "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert calls == ["get"]

    def test_explicit_fetch_mode(self, monkeypatch):
        calls = []

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            return (True, OK_CONTENT, "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        _run_tool(st._handle_scrape({"url": "https://example.com", "mode": "fetch"}))
        assert calls == ["fetch"]

    def test_invalid_mode_falls_back_to_auto(self, monkeypatch):
        calls = []

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            return (True, OK_CONTENT, "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        _run_tool(st._handle_scrape({"url": "https://example.com", "mode": "nope"}))
        assert calls == ["get"]

    def test_truncation_above_max_chars(self, monkeypatch):
        big_content = "# Big\n" + ("x" * st._MAX_RESULT_CHARS)

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", lambda *a, **k: (True, big_content, ""))

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is True
        assert res["truncated"] is True
        assert len(res["content"]) <= st._MAX_RESULT_CHARS

    def test_best_content_wins_across_ladder(self, monkeypatch):
        """When get returns short antibot and fetch returns longer ok,
        the fetch content should be used."""
        calls = []

        OK_BIG = "# Real Content\n" * 200  # ~3600 chars — much longer than antibot

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            if subcmd == "get":
                return (True, _small_page("Just a moment checking browser..."), "")
            return (True, OK_BIG, "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is True
        assert "Real Content" in res["content"]

    def test_stderr_included_in_empty_error(self, monkeypatch):
        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(
            st, "_run_one", lambda *a, **k: (False, "", "command not found")
        )

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is False
        assert "command not found" in res["error"]

    def test_format_extensions_mapped(self, monkeypatch):
        """HTML format should produce .html output file extension."""
        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        captured = {}

        def capturing_run(base, subcmd, url, ext, *rest):
            captured["ext"] = ext
            return (True, OK_CONTENT, "")

        monkeypatch.setattr(st, "_run_one", capturing_run)

        _run_tool(
            st._handle_scrape({
                "url": "https://example.com",
                "format": "html",
            })
        )
        assert captured["ext"] == ".html"

    def test_timeout_on_run_one_handled(self, monkeypatch):
        """A timeout from _run_one should produce an empty/failed result."""
        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(
            st, "_run_one", lambda *a, **k: (False, "", "timed out after 45s")
        )

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is False
        assert "timed" in res["error"]

    def test_subprocess_oserror_handled(self, monkeypatch):
        """An OSError from subprocess.run should be caught by _run_one."""
        import subprocess

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])

        def _raising_run(*a, **k):
            raise OSError("Permission denied")

        monkeypatch.setattr(subprocess, "run", _raising_run)

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert res["ok"] is False
        assert "subprocess error" in res["error"] or "Permission" in res["error"]

    def test_attempts_tracked_in_result(self, monkeypatch):
        """Result includes attempts list showing each mode+status tried."""
        calls = []

        def tracking_run(base, subcmd, *rest):
            calls.append(subcmd)
            if subcmd == "get":
                return (True, _small_page("Checking your browser before accessing"), "")
            return (True, OK_CONTENT, "")

        monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
        monkeypatch.setattr(st, "_run_one", tracking_run)

        res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
        assert "attempts" in res
        assert len(res["attempts"]) == 2
        assert "get" in res["attempts"][0]
        assert "fetch" in res["attempts"][1]
