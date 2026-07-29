# Testing subprocess + tempfile functions

Functions that write CLI output to a temp file and read it back (like `scrape_tool._run_one()`) need 5-6 stdlib mocks working in concert. The key challenge: the temp file path is created by `mkstemp` and consumed by both the command assembly and the `Path.read_text` call — all three must agree on the same path.

## The pattern

```python
import os
import subprocess
import tempfile
from pathlib import Path


def _run_one(base, subcmd, url, ext, css_selector, wait_selector, proxy, timeout_s):
    fd, out_path = tempfile.mkstemp(suffix=ext, prefix="scrape_")
    os.close(fd)
    try:
        cmd = [*base, "extract", subcmd, url, out_path, "--ai-targeted"]
        # ... append flags ...
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        content = Path(out_path).read_text(encoding="utf-8", errors="replace")
        ran_ok = proc.returncode == 0 and bool(content.strip())
        return ran_ok, content, (proc.stderr or "").strip()
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass
```

## Mocking strategy

Mock **every external call** the function makes:

| Stdlib call | Mock | Purpose |
|---|---|---|
| `tempfile.mkstemp(suffix, prefix)` | Returns `(3, "/tmp/fake.md")` | Controls the shared temp path |
| `os.close(fd)` | No-op `lambda fd: None` | Skips actual fd close |
| `subprocess.run(cmd, ...)` | Returns `SimpleNamespace(returncode=0, stderr="")` | Controls exit code + stderr |
| `Path.read_text(...)` | Returns `"# Hello"` | Controls output content |
| `os.unlink(path)` | Appends to a `calls` list for assertions | Verifies cleanup |

### Required import

```python
from types import SimpleNamespace
```

`SimpleNamespace` replaces mock objects for trivial return values (no `from unittest.mock import Mock` needed).

### The mock wiring

```python
import tools.scrape_tool as st


def test_basic_get_command(self, monkeypatch):
    # Track calls to verify command assembly and cleanup
    calls = []

    def _fake_mkstemp(suffix, prefix):
        return (3, "/tmp/fake.md")

    monkeypatch.setattr(st.tempfile, "mkstemp", _fake_mkstemp)
    monkeypatch.setattr(st.os, "close", lambda fd: None)
    monkeypatch.setattr(st.os, "unlink", lambda p: calls.append(f"unlink:{p}"))

    def _fake_run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(st.subprocess, "run", _fake_run)
    monkeypatch.setattr(st.Path, "read_text", lambda *a, **k: "# Hello")

    ran_ok, content, stderr = st._run_one(
        ["scrapling"],
        "get",
        "https://example.com",
        ".md",
        None,
        None,
        None,
        30,
    )
    assert ran_ok is True
    assert content == "# Hello"
    cmd = calls[0]
    assert cmd[:3] == ["scrapling", "extract", "get"]
    assert "--ai-targeted" in cmd
    assert "unlink:/tmp/fake.md" in calls  # cleanup verified
```

### Why monkeypatch attribute resolution matters

`monkeypatch.setattr(st.tempfile, "mkstemp", ...)` works because `import tools.scrape_tool as st` gives us a module reference, and `st.tempfile` is the module's imported reference to stdlib's `tempfile`. Patching `st.tempfile.mkstemp` patches it at the **import site**, not the global `tempfile` module — so only calls from this module are affected. This is critical for avoiding cross-test pollution.

The same applies to `st.os.close`, `st.subprocess.run`, `st.Path.read_text`, `st.os.unlink` — patch each one at `st.<module>.<function>`.

## Key assertions

### Command assembly

```python
cmd = calls[0]
# Basic structure
assert cmd[:3] == ["scrapling", "extract", "get"]  # type: get/fetch/stealthy-fetch
assert "--ai-targeted" in cmd  # mandatory prompt-injection guard (CLI)
assert "--solve-cloudflare" in cmd  # only for stealthy-fetch
assert "--css-selector" in cmd  # when css_selector provided
assert cmd[cmd.index("--css-selector") + 1] == "article"  # value follows flag
assert "--wait-selector" not in cmd  # get mode — no browser
assert "--wait-selector" in cmd  # fetch mode — browser ok
assert "--proxy" in cmd  # when proxy is set
assert cmd[cmd.index("--proxy") + 1] == "http://proxy:8080"
```

### Timeout unit conversion

Scrapling CLI uses **seconds** for `get` mode but **milliseconds** for browser modes:

```python
# get mode: seconds (45 → "45")
idx = cmd.index("--timeout")
assert cmd[idx + 1] == "45"

# fetch/stealthy-fetch: milliseconds (90 * 1000 = 90000)
idx = cmd.index("--timeout")
assert cmd[idx + 1] == "90000"
```

When `timeout_s` is 0 (falsy), the `if timeout_s:` guard skips the flag entirely:

```python
assert "--timeout" not in cmd  # when timeout_s=0
```

### Error handling

| Condition | Mock setup | Assertion |
|---|---|---|
| Subprocess timeout | `subprocess.run` raises `subprocess.TimeoutExpired(cmd=cmd, timeout=30, output="")` | `ran_ok is False`, `content == ""`, `"timed out" in stderr` |
| Subprocess OSError | `subprocess.run` raises `OSError("Permission denied")` | `ran_ok is False`, `content == ""`, `"subprocess error" in stderr` |
| Subprocess ValueError | `subprocess.run` raises `ValueError("Invalid mode")` | `ran_ok is False`, `"subprocess error" in stderr` |
| File read error | `Path.read_text` raises `OSError("No such file")` | `ran_ok is False`, `content == ""` |
| Non-zero exit with content | `returncode=1`, `stderr="something broke"`, content=`"partial content"` | `ran_ok is False`, `content == "partial content"`, `"something broke" in stderr` |

### Cleanup verification

```python
# On success
unlinked = []
monkeypatch.setattr(st.os, "unlink", lambda p: unlinked.append(p))
# ... run _run_one ...
assert "/tmp/scrape_test.md" in unlinked

# On subprocess error (same pattern — finally block always runs)
# ... make subprocess.run raise OSError ...
assert "/tmp/scrape_test.md" in unlinked
```

## `ran_ok` semantics

```python
ran_ok = proc.returncode == 0 and bool(content.strip())
```

Both conditions must be true:
- **Exit code 0** — the CLI tool reported success
- **Non-empty stripped content** — there's actually something to return

A non-zero exit code makes it `False` even if content was written before the error. An empty file with exit code 0 also makes it `False`. This is intentional: the handler's ladder only stops on `ran_ok=True` + `status == "ok"`.

## Real example

See `tests/tools/test_scrape_tool.py` class `TestRunOne` (23 tests, commit `5fc6bd15`) for the complete reference.
