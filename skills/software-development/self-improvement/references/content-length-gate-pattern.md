# Content-length gate pattern — context-aware empty detection

> Real session: 9 ago 2026, commit `20acf00b` — `scrape` tool v1.10.
> Companion to `empty-result-sentinels.md` (sentinel detection) — this one is
> about **numeric** length gates, not LLM sentinel strings.

## The bug

`tools/scrape_tool.py` classified page content with one flat threshold:

```python
_MIN_USEFUL_CHARS = 200
# ...
if n < _MIN_USEFUL_CHARS:
    return "empty"
```

Applied to **every** code path. But the tool has a `css_selector` parameter
that targets a *specific fragment* — a price, a title, a phone number. A
correct extraction like `"Price: $9.99"` (12 chars) fell under the gate →
classified `"empty"` → the handler ran the whole get→fetch→stealthy ladder
for nothing → reported **"No content returned"** even though the selector
matched. A false negative that cost 2 extra browser launches per call.

## The fix (v1.10)

1. `_classify()` gained injectable thresholds:

   ```python
   def _classify(content, *, min_useful_chars=_MIN_USEFUL_CHARS,
                 block_page_max_chars=_BLOCK_PAGE_MAX_CHARS) -> str:
   ```

2. New constant for selector-targeted extraction:

   ```python
   _MIN_USEFUL_CHARS_WITH_SELECTOR = 1  # any non-blank match is a result
   ```

3. Handler picks the gate per-call:

   ```python
   min_chars = _MIN_USEFUL_CHARS_WITH_SELECTOR if css_selector else _MIN_USEFUL_CHARS
   status = _classify(content, min_useful_chars=min_chars) if content else "empty"
   ```

Backward compatible: default call sites keep the 200-char gate.

## Critical invariant — block detection is NOT gated

The lowered gate must never swallow block/challenge detection. In
`scrape_tool.py` the strong phrases fire **before** the length check:

```python
if any(m in head for m in _IP_BLOCK_STRONG):  # "too many requests", ...
    return "ip_block"
if any(m in head for m in _ANTIBOT_STRONG):  # "just a moment", ...
    return "antibot"
if n < min_useful_chars:
    return "empty"
```

And weak phrases (`access denied`, `403`, `captcha`...) still count as a
block on short pages (`n <= block_page_max_chars`) even with the lowered
gate — so a selector-extracted `"Access denied"` is correctly `ip_block`,
not `ok`. Tests assert both directions:

- `_classify("Price: $9.99", min_useful_chars=1) == "ok"` (short-but-valid)
- `_classify("Too many requests", min_useful_chars=1) == "ip_block"` (strong at any size)
- `_classify("Access denied", min_useful_chars=1) == "ip_block"` (weak on short page)
- `_classify("   ", min_useful_chars=1) == "empty"` (blank is still empty)

## Scan signals (when to apply this pattern)

- One hardcoded length constant shared by all modes of a tool
- `if len(x) < N: return empty` with no per-mode awareness
- A tool with a fragment/selector/field-targeting parameter (`css_selector`,
  `extract=`, `fields=`) where output is *supposed* to be short

## Test coverage added (8 tests, `tests/tools/test_scrape_tool.py`)

- `_classify` unit tests: default gate vs lowered gate, strong/weak block
  phrases at lowered gate, blank still empty
- Handler tests: css_selector + short content → `ok: true` + single ladder
  attempt; css_selector + `"Access denied"` → `ip_block`; css_selector
  matching nothing → still "No content" (empty path preserved)
