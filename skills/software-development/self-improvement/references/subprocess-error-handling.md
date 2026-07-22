# Subprocess error-handling pattern

When wrapping a CLI tool via `subprocess.run()`, it's common to only catch `subprocess.TimeoutExpired`. But the subprocess can also fail with `OSError` (permission denied, binary missing between check-and-call) or `ValueError` (invalid command arguments), and bare `subprocess.SubprocessError` for other process-level failures. If any of these propagate unhandled, the tool handler crashes with a generic error instead of a useful message.

## The pattern

```python
try:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
except subprocess.TimeoutExpired:
    return False, "", f"timed out after {timeout_s}s"
except (OSError, ValueError, subprocess.SubprocessError) as exc:
    logger.warning("tool: subprocess error for %s (%s)", url, exc)
    return False, "", f"subprocess error: {exc}"
```

## Key points

- **`subprocess.TimeoutExpired`** is a subclass of `subprocess.SubprocessError`, so it must be caught *before* the broader tuple — otherwise it would match the generic handler and lose the specific timeout message.
- **`OSError`** covers `PermissionError`, `FileNotFoundError` (if the binary disappears between discovery and execution), and other OS-level faults.
- **`ValueError`** catches things like invalid command arguments (`cmd` is a list with `None` entries, null bytes in arguments, etc.).
- **`subprocess.SubprocessError`** is the base class for all subprocess-specific errors (`CalledProcessError`, etc.) except when `check=False` (the default), `CalledProcessError` is not raised, but other `SubprocessError` subclasses may still be.
- **Always log the warning** so debugging is possible without leaking internal paths in user-facing errors.
- **Return a clean failure tuple** so the caller can decide how to present the error.

## Real example

This pattern was applied in `scrape_tool.py`'s `_run_one()` function (commit `505a6c4e`), where previously only `subprocess.TimeoutExpired` was caught. The fix added the `(OSError, ValueError, subprocess.SubprocessError)` catch with a `logger.warning()` call.
