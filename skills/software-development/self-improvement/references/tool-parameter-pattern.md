# Tool parameter pattern — adding a user-facing option

When adding a new parameter to an existing agent tool, follow this three-layer
pattern so the change is complete, testable, and backward-compatible.

## The three layers

```
SCHEMA (tool registry)  →  defines what the model can pass
    ↓
handler (_handle_X)     →  reads, validates, resolves defaults
    ↓
executor (_run_one)     →  passes the value to the CLI/library
```

### 1. Schema layer (`SCRAPE_SCHEMA` / `WEB_EXTRACT_SCHEMA` etc.)

Add the parameter to the tool's JSON schema with proper type, constraints, and
a description specific enough for the model to know when to use it.

```python
"timeout": {
    "type": "integer",
    "minimum": 10,
    "maximum": 300,
    "description": (
        "Max seconds for each mode attempt (min 10, max 300). "
        "Without this, the tool uses per-mode defaults (45s for "
        "HTTP `get`, 90s for browser modes). Increase for slow "
        "pages or when the scrapling CLI needs more time."
    ),
},
```

Key rules:
- Always include `minimum`/`maximum` for integers when there's a sane range
- The `description` must tell the model WHEN to use this (not just WHAT it is)
- Don't add to `required` unless the tool truly can't work without it

### 2. Handler layer (`_handle_X`)

Read the arg, validate it, and resolve a final value. Invalid values should
fall back to a sensible default, not crash.

```python
# User-provided timeout per-mode override. Clamped to [10, 300].
user_timeout = args.get("timeout")
if isinstance(user_timeout, int) and 10 <= user_timeout <= 300:
    pass  # valid
else:
    user_timeout = None  # use per-mode defaults
```

Pattern:
- `isinstance(value, type) and min <= value <= max` — type + range guard
- Non-integer types (string, float, None) silently fall to default
- Store in a local variable used later in the executor call

### 3. Executor layer (`_run_one` / subprocess builder)

Pass the parameter to the underlying CLI or library, handling any unit
differences between modes.

```python
# Pass the timeout to the scrapling CLI as well. For browser modes
# (fetch / stealthy-fetch), the CLI expects milliseconds; for `get`,
# the CLI expects seconds (both default to 30s/30000ms).
if timeout_s:
    if subcmd == "get":
        cmd += ["--timeout", str(timeout_s)]
    else:
        cmd += ["--timeout", str(timeout_s * 1000)]
```

Key rules:
- Document unit differences inline with a comment
- Only append the CLI flag when the value is non-None/non-zero (don't pass a
  default to the CLI if the user didn't specify one — let the CLI use its own)
- Stringify the value (CLI args are always strings)

## What to test

Add tests for all boundary conditions:

```python
def test_timeout_passed_to_run_one(self, monkeypatch):
    """User-provided timeout should be forwarded to _run_one."""
    captured = {"timeout": None}
    def capturing_run(base, subcmd, url, ext, css, wait, proxy, timeout):
        captured["timeout"] = timeout
        return (True, OK_CONTENT, "")
    monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
    monkeypatch.setattr(st, "_run_one", capturing_run)
    _run_tool(st._handle_scrape({
        "url": "https://example.com",
        "timeout": 120,
    }))
    assert captured["timeout"] == 120

def test_timeout_below_min_uses_default(self, monkeypatch):
    """timeout < min should fall back to per-mode defaults."""
    ...

def test_timeout_above_max_uses_default(self, monkeypatch):
    """timeout > max should fall back to per-mode defaults."""
    ...

def test_timeout_non_int_uses_default(self, monkeypatch):
    """Non-integer type should fall back to defaults."""
    ...

def test_timeout_at_min_boundary(self, monkeypatch):
    """timeout exactly at minimum should be accepted."""
    ...

def test_timeout_at_max_boundary(self, monkeypatch):
    """timeout exactly at maximum should be accepted."""
    ...

def test_timeout_used_across_ladder(self, monkeypatch):
    """When timeout is set, it applies to ALL ladder modes."""
    ...
```

Also update the schema-shape test to include the new parameter:

```python
assert {
    "url",
    "mode",
    "format",
    "css_selector",
    "wait_selector",
    "proxy",
    "timeout",  # ← added
} <= set(props)
```

## Real example

The `scrape` tool (commit `75178b2a`) is the canonical example of this pattern.
The `timeout` parameter was added across all three layers and 7 tests.
