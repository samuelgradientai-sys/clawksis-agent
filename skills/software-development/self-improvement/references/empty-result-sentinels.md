# Failure-sentinel detection + non-http(s) URL scheme filter + quota classifier

Three hardening patterns from the `scrapegraph` updates: v1.8 (commit `9e150b5e`,
6 ago 2026) and v1.9 (commit `399589a2` — recursive detection, expanded
sentinels, quota/billing classifier family). All are "silent failure" fixes: no
exception, no crash — just garbage that the agent wastes a turn reading or that
fails later with obscure errors.

## Pattern A — LLM-driven extractors "succeed" with a failure sentinel

### Symptom (doc-code drift)

The `scrapegraphai` SKILL.md and its `references/scrapling-fallback.md` already
documented: *"scrapegraph often fails on long-form articles, returning `"NA"`
content — fall back to `scrape` immediately."* But the tool handler returned
those results as **`ok: true` with `extracted: '"NA"'`** — a fake success. The
agent burned a full turn interpreting garbage before ever reaching the
documented fallback. **The docs described the desired behaviour; the code
didn't enforce it.**

### The fix — shared conservative sentinel check (recursive since v1.9)

`tools/scrapegraph_common.looks_like_empty_result(data)`:

```python
_EMPTY_RESULT_SENTINELS = frozenset({
    "",
    "na",
    "n/a",
    "n.a.",
    "none",
    "null",
    "nan",
    "{}",
    # v1.9: common LLM "couldn't extract anything" phrasings
    "no content",
    "no data",
    "no result",
    "no results",
    "no text",
    "nothing",
    "not found",
    "empty",
    "nil",
    "undefined",
})


def looks_like_empty_result(data):
    if data is None:
        return True
    if isinstance(data, str):
        return data.strip().lower() in _EMPTY_RESULT_SENTINELS
    if isinstance(data, dict):
        values = [v for v in data.values() if v is not None]
        if not values:
            return True
        # v1.9: recurse — a dict is empty when every value is empty
        return all(looks_like_empty_result(v) for v in values)
    if isinstance(data, (list, tuple)):
        return all(looks_like_empty_result(item) for item in data)
    return False
```

**The conservative rule is the whole point** (don't discard real data):
- `{"content": "NA"}` → empty (every value is a sentinel)
- `{"content": {"answer": "NA"}}` → **empty since v1.9** (nested dict recursion;
  previously slipped through as "real content" garbage)
- `{"data": [{"content": "N/A"}]}` → empty (nested list-of-dicts)
- `{"data": []}` → empty; `{"data": [{}]}` → empty
- `{"title": "NA", "body": "real text"}` → **kept** (partial extraction)
- `{"price": 9.99}` → kept; `{"content": {"price": 9.99}}` → kept (any real
  value at ANY depth keeps the result)
- `["NA", "real"]` → kept

Both surfaces call it: the `scrapegraph` tool handler returns `ok: false` +
"Use the `scrape` tool (Scrapling) for raw page content instead", and the
`web_extract` backend returns empty content + the same hint as a per-URL error.

### When to apply

Any tool wrapping an LLM-driven extractor where a "no useful content" answer
is a plausible *success* payload. Check for handlers that `json.dumps`/render
results unconditionally without a content sanity check. When the extractor can
return nested shapes, make the check recursive like v1.9 — a flat
"every non-None string value is a sentinel" check misses
`{"content": {"answer": "NA"}}`.

## Pattern B — URL normalization mangles non-http(s) schemes

### Symptom

`_normalize_urls()` prepended `https://` to *any* bare string, so `ftp://x`,
`mailto:a@b`, `javascript:void(0)`, `data:text/html;...`, `file:///etc/passwd`
became `https://ftp://x`-style garbage that only failed later with obscure
errors (and burned LLM tokens on a doomed extraction).

### Three approaches, two traps

| Approach | Result |
|---|---|
| `"://" in url` scheme check | ❌ misses colon-only schemes: `mailto:a@b`, `javascript:void(0)`, `data:...` have no `//` |
| Regex `^([a-zA-Z][a-zA-Z0-9+.-]*):` | ❌ misreads **host:port** — `example.com:8080` parses as scheme `"example.com"` per RFC 3986 |
| Hybrid (the working one) | ✅ `://` present → reject unless http(s); no `://` → reject only a known colon-only-scheme allowlist |

```python
_NON_HTTP_SCHEMES = frozenset({
    "mailto",
    "javascript",
    "data",
    "tel",
    "sms",
    "file",
    "about",
    "blob",
    "view-source",
    "chrome",
    "chrome-extension",
    "vscode",
    "ftp",
    "ws",
    "wss",
})


def _is_non_http_scheme(url: str) -> bool:
    if "://" in url:
        return not url.lower().startswith(("http://", "https://"))
    return url.split(":", 1)[0].lower() in _NON_HTTP_SCHEMES
```

`example.com:8080/path` keeps the `https://` prefix treatment; `git+ssh://x`
is caught by the `://` branch. Applied to BOTH the single `url` and the `urls`
list paths, with a `logger.debug` on skip. Uppercase schemes are handled via
`.lower()`.

## Pattern C — quota/billing errors misread as rate limits (v1.9)

### Symptom

OpenAI-compatible endpoints answer exhausted credits with
`Error code: 429 - {'error': {'code': 'insufficient_quota'}}` — the message
contains BOTH `429` and quota keywords. A classifier that checks the
rate-limit family (`"429"`, `"ratelimiterror"`, ...) first tells the user
"retry later", which is wrong: retrying an exhausted account never helps.

### The fix — dedicated family BEFORE rate-limit

`classify_scrapegraph_error()` gained family #3 (after auth, before
rate-limit): keywords `insufficient_quota`, `billing_not_active`,
`insufficient credits`, `out of credits`, `credit balance`, `payment
required`, `402`, `quota`, `billing`, `max monthly spend` → hint: "out of
credits / billing inactive — check provider balance or switch models;
retrying will not help." Order matters: quota errors often carry `429`, so
the quota check MUST precede the `429`/rate-limit family. The classifier went
from 8 to 9 categories (docstring and SKILL.md table updated accordingly).

## Tests added (10 → 13, v1.9)

- `looks_like_empty_result`: sentinel strings (incl. the 10 new v1.9
  phrasings), real text kept, dict shapes, partial kept, list shapes,
  non-strings (`42`, `9.99`, `True`) kept, **nested shapes** (dict-of-dicts,
  list-of-dicts in a dict, `{"data": []}`, `{"data": [{}]}`, deep mixed,
  any-real-value-at-any-depth kept)
- `classify_scrapegraph_error`: `test_classify_quota_billing` asserts
  quota-over-429 precedence (`"rate-limited" not in hint` when the message
  carries both `429` and `insufficient_quota`)
- handler: bare `"NA"` → `ok: false` + scrape hint; `{"content": "NA"}` →
  `ok: false`; partial `{"title": "NA", "body": "..."}` → `ok: true`;
  multi-source path flags empty too
- backend: `{"content": "NA"}` → empty content + "scrape" hint
- `_normalize_urls`: ftp/mailto/javascript/data/file skipped, uppercase
  `FTP://` skipped, `host:port` and `git+ssh://` handled correctly

Result: 82 passed in `tests/tools/test_scrapegraph_tool.py` (79 → 82, +3
v1.9 tests), 255 passed across the related web test files
(`test_web_tools_config.py`, `test_web_tools_truncate.py`, `test_scrape_tool.py`,
`test_scrapegraph_tool.py`, `test_web_extract_robustness.py`).
