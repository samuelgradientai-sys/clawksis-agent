# Tool test patterns — real patterns from self-improvement sessions

## Patterns for testing async tool handlers (asyncio.to_thread)

Tools that call blocking code via `asyncio.to_thread()` (e.g. `scrape_tool.py`'s `_run_one`) need special care in tests:

### 1. Never use `StopIteration` via iterators inside `asyncio.to_thread`

```python
# ❌ DEADLOCK — StopIteration inside to_thread hangs the event loop
results = iter([("content_a",), ("content_b",)])


def cycling_run(*args):
    return next(results)  # When exhausted → StopIteration → asyncio deadlock


monkeypatch.setattr(st, "_run_one", cycling_run)


# ✅ Use conditional logic instead
def tracking_run(*args):
    calls.append(args[1])  # subcmd is positional arg index 1
    if args[1] == "get":
        return (True, antibot_content, "")
    return (True, ok_content, "")


monkeypatch.setattr(st, "_run_one", tracking_run)
```

**Why:** `StopIteration` raised inside a thread that's scheduled via `asyncio.to_thread` propagates incorrectly — Python's `Future` cannot wrap `StopIteration`. The event loop hangs. Use conditional branching on the subcmd arg instead.

### 2. Content gate: _MIN_USEFUL_CHARS (200)

`_classify()` checks `len(stripped) < _MIN_USEFUL_CHARS` (200) and returns `"empty"` below that. Any mock content fed through `_classify` must be ≥200 chars or it's treated as empty.

```python
# ❌ Too short → classified as "empty", ladder continues
def tracking_run(*a):
    return (True, "# Short", "")


# ✅ Long enough to pass the gate
OK_CONTENT = "# Hello World\n" * 30  # ~420 chars


def tracking_run(*a):
    return (True, OK_CONTENT, "")
```

### 3. `_classify` strips whitespace — padding must be non-whitespace

```python
# ❌ .ljust() pads with spaces → .strip() removes them → content is too short
_small_page("captcha").ljust(200)  # becomes just "captcha" after strip


# ✅ Use 'x' (non-strippable character) for padding
def _small_page(text: str) -> str:
    needed = 750 - len(text)
    return text + "x" * max(needed, 0)
```

### 4. Antibot ≠ ip_block — handler returns ok=True for antibot

The handler ladder:
- **ip_block** → immediately aborts the ladder, returns `ok=False, reason="ip_block"`
- **antibot** → continues the ladder, returns `ok=True, status="antibot"` with the content

Don't assert `ok=False` for antibot content — the handler trusts the caller to decide what to do with antibot content. Only ip_block causes `ok=False`.

### 5. Ladder escalation test pattern

```python
def test_escalates_on_antibot(self, monkeypatch):
    calls = []

    def tracking_run(base, subcmd, *rest):
        calls.append(subcmd)
        if subcmd == "get":
            return (True, _small_page("Checking your browser before accessing"), "")
        return (True, OK_CONTENT, "")

    monkeypatch.setattr(st, "_scrapling_cmd", lambda: ["/fake/scrapling"])
    monkeypatch.setattr(st, "_run_one", tracking_run)
    res = _run_tool(st._handle_scrape({"url": "https://example.com"}))
    assert res["ok"] is True
    assert calls == ["get", "fetch"]
```

## Patterns for testing proxy/binary discovery helpers

For functions that resolve binary paths or proxy settings via env var → config → default chain:

```python
def test_config_fallback(self, monkeypatch):
    monkeypatch.delenv("SCRAPLING_PROXY", raising=False)
    with patch(
        "clawk_cli.config.load_config",
        return_value={"web": {"scrapling_proxy": "http://cfg:3128"}},
    ):
        assert st._resolve_proxy(None) == "http://cfg:3128"
```

Key: patch at the **import site** where the module does its import (e.g. `clawk_cli.config.load_config`), not at the calling module's attribute.

## Test structure template for a tool handler

```python
class TestHandleFoo:
    """Tool handler tests (subprocess mocked)."""

    def test_requires_required_arg(self):
        """Missing required arg should return ok=False."""
        res = _run_tool(module._handle_foo({}))
        assert res["ok"] is False
        assert "required" in res["error"].lower()

    def test_success_path(self, monkeypatch):
        """Happy path returns ok=True with expected data."""
        monkeypatch.setattr(module, "_dependency", lambda: mock_value)
        res = _run_tool(module._handle_foo({"key": "value"}))
        assert res["ok"] is True
        assert "expected_field" in res

    def test_installed_check(self, monkeypatch):
        """Missing dependency returns install hint."""
        monkeypatch.setattr(module, "_dependency_check", lambda: None)
        res = _run_tool(module._handle_foo({"url": "x"}))
        assert res["ok"] is False
        assert "install" in res["error"].lower()

    def test_passes_args_downstream(self, monkeypatch):
        """Verify user-supplied args reach the underlying function."""
        captured = {}

        def capturing_run(*args):
            captured["key"] = args[2]  # positional arg index
            return (True, default_content, "")

        monkeypatch.setattr(module, "_run_one", capturing_run)
        _run_tool(module._handle_foo({"url": "x", "key": "val"}))
        assert captured["key"] == "expected_call_value"
```

## Real reference: scrape_tool.py test suite

See `test_scrape_tool.py` at `tests/tools/test_scrape_tool.py` — 61 tests, 5 classes:
- `TestScraplingCmd` (binary discovery)
- `TestResolveProxy` (proxy chain)
- `TestClassify` (content classification)
- `TestConstants` (mapping checks)
- `TestHandleScrape` (handler logic, 18 tests)

Commit: `ddf95bd5`
