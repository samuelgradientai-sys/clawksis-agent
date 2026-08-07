# Failure-sentinel detection + non-http(s) URL scheme filter

Two hardening patterns from the v1.8 `scrapegraph` update (commit `9e150b5e`,
6 ago 2026). Both are "silent failure" fixes: no exception, no crash — just
garbage that the agent wastes a turn reading or that fails later with obscure
errors.

## Pattern A — LLM-driven extractors "succeed" with a failure sentinel

### Symptom (doc-code drift)

The `scrapegraphai` SKILL.md and its `references/scrapling-fallback.md` already
documented: *"scrapegraph often fails on long-form articles, returning `"NA"`
content — fall back to `scrape` immediately."* But the tool handler returned
those results as **`ok: true` with `extracted: '"NA"'`** — a fake success. The
agent burned a full turn interpreting garbage before ever reaching the
documented fallback. **The docs described the desired behaviour; the code
didn't enforce it.**

### The fix — shared conservative sentinel check

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
        return all(
            isinstance(v, str) and v.strip().lower() in _EMPTY_RESULT_SENTINELS
            for v in values
        )
    if isinstance(data, (list, tuple)):
        return all(looks_like_empty_result(item) for item in data)
    return False
```

**The conservative rule is the whole point** (don't discard real data):
- `{"content": "NA"}` → empty (every value is a sentinel)
- `{"title": "NA", "body": "real text"}` → **kept** (partial extraction)
- `{"price": 9.99}` → kept (non-string values break the all-sentinel check)
- `["NA", "real"]` → kept

Both surfaces call it: the `scrapegraph` tool handler returns `ok: false` +
"Use the `scrape` tool (Scrapling) for raw page content instead", and the
`web_extract` backend returns empty content + the same hint as a per-URL error.

### When to apply

Any tool wrapping an LLM-driven extractor where a "no useful content" answer
is a plausible *success* payload. Check for handlers that `json.dumps`/render
results unconditionally without a content sanity check.

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

## Tests added (10)

- `looks_like_empty_result`: sentinel strings, real text kept, dict shapes,
  partial kept, list shapes, non-strings (`42`, `9.99`, `True`) kept
- handler: bare `"NA"` → `ok: false` + scrape hint; `{"content": "NA"}` →
  `ok: false`; partial `{"title": "NA", "body": "..."}` → `ok: true`;
  multi-source path flags empty too
- backend: `{"content": "NA"}` → empty content + "scrape" hint
- `_normalize_urls`: ftp/mailto/javascript/data/file skipped, uppercase
  `FTP://` skipped, `host:port` and `git+ssh://` handled correctly

Result: 79 passed in `tests/tools/test_scrapegraph_tool.py` (+10), plus 77 in
the related `tests/plugins/web/test_web_search_provider_plugins.py` +
`tests/test_toolsets.py`.
