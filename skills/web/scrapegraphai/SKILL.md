---
name: scrapegraphai
description: "Extract structured data from web pages using ScrapeGraphAI + the agent's own LLM — no paid scraping API. Use when you need structured JSON from a page (tables, prices, listings, contacts, specs) described in plain language, and prefer local infra over Firecrawl/Browserbase. ES: extraer datos estructurados de una página web, convertir HTML a JSON, scraping con IA sin API paga."
version: "1.1"
metadata:
  openclaw:
    emoji: "🧩"
    requires:
      bins:
        - python3
---

# ScrapeGraphAI — structured web extraction

Extract **structured data** (JSON) from web pages using the local `scrapegraphai` library driven by the agent's own LLM (text model configured in `auxiliary_client`). Zero paid scraping APIs — runs entirely on your infrastructure.

Two surfaces use this module:

| Surface | File | What it does |
|---|---|---|
| **`scrapegraph` tool** | `tools/scrapegraph_tool.py` | Direct agent tool: structured JSON via a natural-language prompt |
| **`web_extract` backend** | `plugins/web/scrapegraphai/provider.py` | Auto-selected extract backend when library is installed (overrides Firecrawl/Browserbase) |

## How it works

1. The agent sends a plain-language prompt (e.g. "List every product with name, price and rating as JSON")
2. ScrapeGraphAI renders the page (headless Chromium for dynamic JS, simple HTTP for static)
3. The agent's own LLM (via `build_llm_config()`) extracts structured data matching the prompt
4. Returns clean JSON — no need for CSS selectors or parsing code

## When to use this vs `scrape` (Scrapling)

| Tool | Best for | When to switch |
|---|---|---|
| **`scrapegraph`** | **Structured data** — "get me prices + specs as JSON", "extract the table of GPU models with TDP and price", contact info extraction from simple pages | Start here |
| **`scrape` / Scrapling** | **Raw content** — "fetch this page as markdown", anti-bot bypass (Cloudflare), spiders/crawlers | ✅ Falls back when scrapegraph returns `"NA"` or `"Invalid json output"` |

**⚠️ Common trap:** scrapegraph often fails on **long-form articles** (1000+ words), returning `"NA"` content. Don't burn tokens retrying — switch to `scrape` immediately. The LLM can't structurally parse dense text. Don't keep retrying — fall back to `scrape(url, mode="auto")` for raw markdown. See `references/scrapling-fallback.md` for the full decision tree and real examples.

**The library auto-installs on first use** (lazy deps via `tools.lazy_deps`). If lazy install is disabled, run manually:

```bash
pip install scrapegraphai
python -m playwright install chromium  # only needed for JS-heavy pages
```

## Tool parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | string | **required** | The page URL |
| `urls` | array | optional | Multiple URLs (returns combined result) |
| `prompt` | string | "Extract main content" | What to extract in plain language |
| `output_schema` | object | optional | JSON Schema for forcing the output shape |
| `render_js` | boolean | `true` | Render JavaScript with headless browser. ⚠️ On headless servers, NEVER set `false` — crashes (headed mode needs X server). Omit or set `true`. |
| `timeout` | integer | `60` | Max seconds for the LLM extraction (min 10, max 300). Increase for large pages. |

## ❗ Critical: `render_js` and headless mode

The code maps `render_js` to `headless` as follows:

```python
headless = True if render_js is None else bool(render_js)
```

| `render_js` | `headless` | Behaviour |
|---|---|---|
| not provided / `true` | `true` | ✅ Headless Chromium — works everywhere |
| `false` | `false` | ❌ **Headed mode** — requires X server (fails on headless servers) |

**On a headless server (no screen / X server):** NEVER pass `render_js=false`. The error looks like:
```
BrowserType.launch: Target page, context or browser has been closed
Missing X server or $DISPLAY
```

**Fix:** Omit `render_js` or set `render_js=true` (both use headless).

If you genuinely need the page without JS execution, just let it use headless anyway — the difference is the browser window visibility, not JS execution.

📎 See `references/headed-browser-error.md` for the exact error transcript and troubleshooting.

## Known pitfalls

### 1. `langchain-community` ChatOllama compat shim

`scrapegraphai` imports `ChatOllama` from `langchain_community.chat_models`, but `langchain-community` v0.4+ removed it (moved to `langchain_ollama`). The fix lives in `tools/scrapegraph_common.py`:

```python
def _patch_langchain_community() -> None:
    """Re-export ChatOllama into langchain_community.chat_models."""
    try:
        from langchain_ollama import ChatOllama as _ChatOllama_
    except ImportError:
        return
    import langchain_community.chat_models as _lm

    if not hasattr(_lm, "ChatOllama") or _lm.ChatOllama is not _ChatOllama_:
        _lm.ChatOllama = _ChatOllama_
```

This runs automatically every time `ensure_installed()` is called (which is at the start of every extraction). If this fix breaks due to library updates, check whether `langchain_ollama` still exports `ChatOllama` and whether `langchain_community.chat_models` still exists as a module.

### 2. Model routing via `build_llm_config()`

The LLM config is built from the agent's **auxiliary text client** — the same model/key/base_url the agent is already configured with. This means:

- ScrapeGraphAI does NOT need a separate API key
- It uses whatever model you're already paying for (DeepSeek, Grok, Claude, GPT, local Ollama)
- The config sends `"openai/<model>"` format + custom `base_url` via langchain's `ChatOpenAI`
- Falls back to `OPENAI_API_KEY` or `OPENROUTER_API_KEY` env vars if auxiliary client isn't available
- Falls back to `gpt-4o-mini` as model if nothing is configured

### 3. LLM cost

Each extraction costs LLM tokens — the model reads the page HTML and produces structured output. For large pages with many data points, this can be significant. For simple text extraction, prefer `web_extract` or `scrape`.

### 4. Installation is lazy

The library is **not** in the base install. It's a lazy dep registered as `"scrape.scrapegraph"` in `tools/lazy_deps.py`. First call triggers:

```
pip install scrapegraphai + chromium browser (if not cached)
```

This can take 30-60 seconds the first time. Subsequent calls are instant.

### 5. Tests

All tests mock the extraction layer (scrapegraphai itself is not installed in CI). Run them with:

```bash
cd /path/to/clawksis-agent
uv run pytest tests/tools/test_scrapegraph_tool.py -v
```

Tests cover:
- Tool registration + schema shape
- LLM config builder (auxiliary client, env fallback)
- `_coerce_schema` helper — None, dict, valid/invalid JSON strings, non-string types
- `_normalize_urls` — scheme normalisation, dedup, empty input
- Handler success/error/unavailable paths (single + multi-URL)
- Web extract backend (per-URL error isolation, result shaping)
- Backend prioritisation (scrapegraph vs 3rd-party)

### 6. LLM not available / authentication errors

Since commit `cb5a6c7f`, errors are **classified** into 5 categories and surfaced
as clean, actionable messages instead of raw exception dumps:

| Error pattern | What the agent sees |
|---|---|
| No display server / `render_js=false` | "No display server. Omit `render_js` or set it to `true`." |
| HTTP 401 / Unauthorized | "Check auxiliary_text model credentials, or set OPENAI_API_KEY." |
| HTTP 429 / RateLimitError | "Model is rate-limited. Retry later or switch models." |
| Invalid JSON output / parse failure | "Try a more specific prompt or use the `scrape` tool." |
| Any other error | Generic safe message — no paths or exception internals leaked. |

📎 See `references/error-classifier.md` for the full classification table and
test coverage details.

### 7. Narrow `except Exception:` in tool handlers

The tool handler in `scrapegraph_tool.py` and the helpers in `scrapegraph_common.py`
contain several `except Exception:` patterns from earlier iterations. When improving
this code, narrow each catch to the specific exception type the operation can raise:

| Context | Current | Correct |
|---|---|---|
| `_coerce_schema()` — JSON parsing | `except Exception:` | `except (json.JSONDecodeError, TypeError):` |
| JSON serialization in handler | `except Exception:` | `except (TypeError, ValueError):` |
| `build_llm_config()` — auxiliary client | `except Exception` with `# noqa: BLE001` | Acceptable (covers unknown module attributes), but prefer `(ImportError, AttributeError)` |

**Why:** Broad `except Exception:` silently catches `KeyboardInterrupt`, `SystemExit`,
and unexpected bugs that should propagate. Narrowing makes failures visible instead
of silently falling back to `return None` or `str(data)`.

## Verifying it works

```python
from tools.scrapegraph_common import ensure_installed, extract_structured
import asyncio

ensure_installed()  # Triggers the ChatOllama patch

result = asyncio.run(
    extract_structured(
        "https://example.com",
        "Extract the main heading and description",
        headless=True,  # ← MUST be True on headless servers
    )
)
print(result)
```

Or via the tool itself:

```json
{
  "url": "https://example.com",
  "prompt": "Extract the main heading and description text"
}
```

Expected output (with `render_js` omitted or `true`):
```json
{
  "ok": true,
  "extracted": "{\n  \"content\": \"Main heading: Example Domain. ...\"\n}"
}
```

## Files in this module

| File | Purpose |
|---|---|
| `tools/scrapegraph_common.py` | Shared helpers: install, patch, LLM config, graph runners |
| `tools/scrapegraph_tool.py` | Agent tool registration + handler |
| `plugins/web/scrapegraphai/provider.py` | `web_extract` backend |
| `tests/tools/test_scrapegraph_tool.py` | Tests (18 tests, all pass) |
