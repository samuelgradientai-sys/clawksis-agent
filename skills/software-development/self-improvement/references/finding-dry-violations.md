# Finding DRY violations across tool + provider boundaries

## The core pattern

In the Clawksis codebase, tools in `tools/` and their web-extract backends in
`plugins/web/<name>/provider.py` often share a common module (e.g.
`tools/scrapegraph_common.py`). When both surfaces need the same utility logic
(e.g. clamping a timeout value), it's tempting to copy-paste — creating a
maintenance hazard.

## Two variants

### Variant A: Tool + its backend provider (tightly coupled)

Both the `scrapegraph` tool handler and its `web_extract` backend need the same
helper. They already share `scrapegraph_common.py` — extraction was
straightforward.

**Real example: `clamp_timeout()` (commit `0d20c552`)**

Both `scrapegraph_tool.py` and `plugins/web/scrapegraphai/provider.py` had
this identical block:

```python
raw_timeout = args.get("timeout")  # or kwargs.get("timeout")
timeout: int | None = None
if raw_timeout is not None:
    try:
        timeout = max(10, min(300, int(raw_timeout)))
    except (ValueError, TypeError):
        timeout = None
```

The fix: extract to a shared function in `scrapegraph_common.py`:

```python
def clamp_timeout(raw_timeout: Any) -> int | None:
    """Clamp a raw timeout value to [10, 300] or return None."""
    if raw_timeout is None:
        return None
    try:
        return max(10, min(300, int(raw_timeout)))
    except (ValueError, TypeError):
        return None
```

Then both files import and call it:
```python
from tools.scrapegraph_common import clamp_timeout

...
timeout = clamp_timeout(raw_timeout)
```

### Variant B: Cross-tool import (loosely coupled)

A completely different tool (different domain, different CLI) duplicates logic
that lives in another tool's shared module. This is subtler: you're not reading
two files that "go together"; you're reading one file and noticing its inline
validation looks like a function you've seen elsewhere.

**Real example: `scrape_tool.py` → `scrapegraph_common.clamp_timeout()` (commit `6c2d0116`)**

`scrape_tool.py` (the Scrapling-backed anti-bot scraper) had inline timeout
validation that only accepted `int` in [10,300]; out-of-range values were
silently rejected:

```python
# Old: inline, silent-reject
user_timeout = args.get("timeout")
if isinstance(user_timeout, int) and 10 <= user_timeout <= 300:
    pass  # valid
else:
    user_timeout = None  # rejected silently
```

Meanwhile `tools/scrapegraph_common.py` already had `clamp_timeout()` — the
same clamp, but better (clamps instead of rejects, handles float and string).

**Fix with graceful fallback:**

```python
try:
    from tools.scrapegraph_common import clamp_timeout
except ImportError:
    # Fallback keeps scrape_tool self-sufficient when scrapegraph_common
    # (and its heavy deps) aren't installed.
    def clamp_timeout(raw_timeout):
        if raw_timeout is None:
            return None
        try:
            return max(10, min(300, int(raw_timeout)))
        except (ValueError, TypeError):
            return None


# Later in the handler:
user_timeout = clamp_timeout(args.get("timeout"))
```

**Key design choice:** The `try/except ImportError` fallback means
`scrape_tool.py` has an *optional* dependency on `scrapegraph_common.py`. If
the module is available (same package, normal install), it reuses the shared
function. If not (unusual — same package), the inline duplicate works. This
keeps `scrape_tool.py` installable without dragging in scrapegraphai's
langchain deps as hard requirements.

**Benefits over the old inline validation:**
- Values <10 are now clamped to 10 (not silently rejected)
- Values >300 are clamped to 300 (not silently rejected)
- Floats like `120.0` and numeric strings like `"150"` are accepted
- Consistent behavior across all scraping tools
- Single source of truth for the [10, 300] range

## How to spot these

1. **Notice a pattern** in a file you're reading (e.g. a `max(10, min(300, ...))`
   clamp, a `try/except` that wraps an env lookup, a URL-normalisation loop).
2. **Search for the same pattern** across related files:
   ```
   search_files(pattern="max\\(10, min\\(300", path="tools/")
   search_files(pattern="max\\(10, min\\(300", path="plugins/")
   ```
3. **Also search unrelated tool files** — the same simple utility often gets
   re-invented independently:
   ```
   search_files(pattern="isinstance.*int.*and 10.*<=.*300", path="tools/")
   ```
4. **Compare** the matched blocks side-by-side — identical logic in two places
   is a strong DRY signal, even if the files don't "belong" together.
5. **Check if a shared module already exists** — `tools/scrapegraph_common.py`,
   `tools/coding_cli_common.py`, etc. If the pattern matches a utility already
   extracted, import with a graceful fallback.

## When to use try/except ImportError (graceful fallback)

Use a fallback when:
- **The shared module has heavy optional deps** (e.g. `scrapegraph_common.py`
  pulls in langchain/scrapegraphai on first call). You don't want to force
  those deps on every consumer.
- **The consumer is in a different domain** (Scrapling scraper importing from
  ScrapeGraphAI common). If the shared module is from the same domain
  (e.g. two ScrapeGraphAI files), a direct import without fallback is fine.

Do NOT use a fallback when:
- Both files are in the same package and the shared module has no heavy deps.
  A direct import is simpler and the import error would be a real bug worth
  catching early.

## Good DRY candidates in Clawksis

| Pattern | Likely shared module | Known instances |
|---|---|---|
| Timeout clamping `max(N, min(M, int(...)))` | `tools/scrapegraph_common.py` | `scrapegraph_tool.py` + `provider.py` ✅ FIXED v1.6; `scrape_tool.py` ✅ FIXED v1.7 |
| URL normalisation (scheme default, dedup) | `tools/scrapegraph_common.py` | Only in `scrapegraph_tool.py` currently |
| Error classification (exception→user-hint) | `tools/scrapegraph_common.py` | `scrapegraph_tool.py` + `provider.py` already shared ✅ |
| Environment/lookup (API key fallback chain) | `tools/scrapegraph_common.py` | Only in `build_llm_config()` currently |

## Pitfalls

- **Don't over‑abstract.** If the "same" code is coincidental (same algorithm
  but different semantics / error behaviour), a shared function adds coupling
  without benefit. Verify the two callers really need identical behaviour.
- **Update both callers in the same change.** Half a refactor is worse than no
  refactor — the survivor block still looks like "the one true way" but isn't.
- **Add tests for the extracted function.** The duplicate blocks probably had
  indirect test coverage through their parent functions. The extracted function
  needs its own direct tests (7 tests added in the `clamp_timeout()` case: None,
  valid, clamp min, clamp max, string, invalid, float).
- **When the consumer is in a different domain, update related tests too.**
  In Variant B, the new `clamp_timeout()` clamps out-of-range values instead of
  rejecting them, so tests like `test_timeout_below_min_uses_default` need to
  become `test_timeout_below_min_clamped` (asserting the clamped boundary, not
  the per-mode default).
- **Consider UX impact of clamp vs reject.** Clamping is almost always better
  for the end user: a timeout of 3s clamped to 10s is usable; a timeout of 3s
  silently ignored (using 45s default) is confusing. Update the test names and
  docstrings to reflect the new semantics so the intent is clear.
