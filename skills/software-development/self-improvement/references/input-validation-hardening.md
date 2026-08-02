# Input-validation hardening for tool handlers (`_as_str` pattern)

Real example: commit `999faecb` — auto-mejora on the scraping tools
(`tools/scrapegraph_tool.py`, `tools/scrape_tool.py`,
`plugins/web/scrapegraphai/provider.py`).

## The crash signature

Handlers that parse schema-string args with `(args.get("x") or "").strip()`
raise `AttributeError: '<type>' object has no attribute 'strip'` when the
model passes a non-string value (int, dict, list, bool — e.g. a sloppy tool
call). The exception escapes the handler and the registry surfaces it as a
raw "Tool dispatch error" with a traceback instead of a clean tool error.

Found in the wild (all crashed identically):
- `scrapegraph_tool._normalize_urls()` with `{"url": 42}` / `{"url": ["a"]}` / `{"url": {"a": 1}}`
- `scrapegraph_tool._handle_scrapegraph()` with `{"prompt": 42}`
- `scrape_tool._handle_scrape()` with `{"url": 42}`, plus the same fragile
  pattern on `mode`, `format`, `css_selector`, `wait_selector`, `proxy`

## The fix: one helper per file

`scrape_tool.py` (used 6 times → module-level helper):

```python
def _as_str(value: Any) -> str:
    """Return ``value`` stripped if it's a str, else ''."""
    return value.strip() if isinstance(value, str) else ""
```

Usage: `url = _as_str(args.get("url"))`,
`mode = (_as_str(args.get("mode")) or "auto").lower()`, etc. Non-strings
fall back to defaults or produce a clean "required" error — never a crash.

`scrapegraph_tool.py` (2 spots → inline isinstance guards, no helper needed):

```python
single = args.get("url")
if isinstance(single, str) and single.strip():
    urls.append(single.strip())

raw_prompt = args.get("prompt")
prompt = raw_prompt.strip() if isinstance(raw_prompt, str) else ""
prompt = prompt or _DEFAULT_PROMPT
```

## Design decision

Non-string `url` values are treated as **absent** (→ clean "url required"
error), NOT coerced via `str()` — coercing would send nonsense like
"https://42" to the fetcher. The `urls` LIST branch keeps its pre-existing
`str(u)` coercion (documented behavior, covered by tests).

## Tests to add

```python
def test_normalize_urls_non_string_url_does_not_crash():
    assert _normalize_urls({"url": 42}) == []
    assert _normalize_urls({"url": {"a": 1}}) == []
    assert _normalize_urls({"url": ["a.com"]}) == []
    assert _normalize_urls({"url": 42, "urls": ["b.com"]}) == ["https://b.com"]


def test_handler_non_string_prompt_uses_default(monkeypatch):
    # monkeypatch extract_structured to capture prompt; assert the default
    # prompt text is passed; res["ok"] is True


def test_non_string_mode_format_defaults(monkeypatch):
    # url valid, mode=7 → auto; format=["md"] → markdown; res["ok"] is True
```

Plus a small unit class for the helper (`_as_str("  hi  ") == "hi"`,
`_as_str("") == ""`, `_as_str(None) == ""`, `_as_str(42) == ""`,
`_as_str(0) == ""`, `_as_str(["a"]) == ""`, `_as_str({"a": 1}) == ""`).

## Related: result-shape hardening in `_stringify` (web-extract provider)

The same commit hardened `_stringify()` in the scrapegraph provider:
- **List results:** scrapegraphai sometimes wraps extraction output in a
  list — join the items' string forms with `\n\n` instead of returning an
  ugly Python repr (`"[{'content': ...}]"`). Recurse via `_stringify(item)`
  for dict items.
- **Empty dict:** `{}` means "nothing extracted" → return `""` so web_extract
  treats it as missing content instead of leaking a `{}` JSON blob.

## Verification

- `uv run pytest tests/tools/test_scrapegraph_tool.py tests/tools/test_scrape_tool.py -q` → 148 passed
- Related web suite (`test_web_extract_robustness`, `test_web_providers`,
  `test_web_tools_*`) → 103 passed
- `uv run ruff check` + `ruff format --check` clean
