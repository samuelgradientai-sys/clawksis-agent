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
"https://42" to the fetcher.

⚠️ **The `urls` LIST branch did keep `str(u)` coercion at first — that was a
mistake, removed in commit `03b2f0c6`.** See the section below; str()-coercing
list items fabricates silent garbage URLs.

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

## Sibling hazard: `bool()` coercion of boolean args (`_as_bool` pattern)

Real example: commit `08bfa16d` — auto-mejora on `tools/scrapegraph_tool.py`.

**Why it's worse than the `.strip()` crash:** `bool()` never raises — it
*silently flips*. `bool("")` and `bool(0)` are `False`; `bool("false")` is
`True`. A sloppy non-bool for a schema-bool param (`render_js`, any flag)
quietly enables the wrong code path instead of failing loudly:

- `headless = True if render_js is None else bool(render_js)` with
  `render_js=""` / `0` / `[]` → `headless=False` → **headed browser mode on a
  headless server** → runtime crash `Missing X server or $DISPLAY` deep in the
  pipeline, with a confusing error that doesn't point at the arg.
- `render_js="false"` → `True` → intent silently ignored.

**The fix — `_as_bool(value, default)` helper (one per file, same style as
`_as_str`):**

```python
def _as_bool(value: Any, *, default: bool = True) -> bool:
    """Coerce a raw arg to a bool, falling back to ``default`` for non-bools."""
    if isinstance(value, bool):
        return value
    if value is not None:
        logger.warning(
            "scrapegraph: non-boolean render_js=%r treated as %s (headless)",
            value,
            default,
        )
    return default
```

Only real booleans pass through; everything else (str, int, list, None) falls
back to the SAFE default (headless=True) and logs a warning so the misuse is
visible instead of silent. Real `False` stays respected — that's the documented
way to request headed mode (and the classifier gives a clean "no display
server" error if it's wrong for the host).

Tests: handler-level loop over `("", 0, "false", [], {})` asserting
`headless is True` + warning text in `caplog`; bool passthrough
(`True`→headless, `False`→headed); missing arg → default. (58 passed in
`tests/tools/test_scrapegraph_tool.py` after the change.)

## Sibling hazard #2: non-string items INSIDE a list arg (`isinstance` filter)

Real example: commit `03b2f0c6` — auto-mejora on `tools/scrapegraph_tool.py`.

**The failure mode is garbage fabrication, not a crash.** Handlers that
str()-coerce list items — `urls.extend(str(u).strip() for u in many if str(u).strip())`
— turn schema-violating items into *plausible-looking nonsense*:

```
{"urls": [42, None, {"a": 1}, ["x"], "b.com"]}
  → ["https://42", "https://None", "https://{'a': 1}", "https://['x']", "https://b.com"]
```

No exception is raised, so nothing fails loudly — the garbage URLs go straight
into the expensive downstream call (LLM-powered extraction) and fail there with
obscure errors, burning LLM tokens on extractions that were doomed from the
start. **Worse than a crash: silent, and it costs money.**

**The fix — `isinstance(u, str)` filter, skip non-strings entirely:**

```python
many = args.get("urls")
if isinstance(many, list):
    for u in many:
        if isinstance(u, str) and u.strip():
            urls.append(u.strip())
```

Same principle as `_as_str()`: never coerce, treat schema-violating values as
absent. Applies to ANY list-typed tool arg (`urls`, `items`, `ids`, ...).

**Scanning heuristic:** look for `str(x)` inside a list comprehension/generator
over a tool arg, or `map(str, ...)`. If the schema says `items: {type: string}`
but the code coerces with `str()` instead of filtering, that's this bug.

Tests added: `test_normalize_urls_skips_non_string_items_in_list`
(`{"urls": [42, None, {"a": 1}, ["x"], "b.com", "  c.com  ", 0]}` →
`["https://b.com", "https://c.com"]`) and
`test_normalize_urls_mixed_valid_and_junk` (valid `url` + junk items in
`urls` → junk dropped, valid kept). 60 passed in
`tests/tools/test_scrapegraph_tool.py` after the change.

## Verification

- `uv run pytest tests/tools/test_scrapegraph_tool.py tests/tools/test_scrape_tool.py -q` → 148 passed
- Related web suite (`test_web_extract_robustness`, `test_web_providers`,
  `test_web_tools_*`) → 103 passed
- `uv run ruff check` + `ruff format --check` clean
