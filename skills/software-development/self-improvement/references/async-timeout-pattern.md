# Adding timeout to async blocking extraction functions

Use `asyncio.wait_for` + `asyncio.to_thread` when a blocking library call (e.g. `scrapegraphai`'s `SmartScraperGraph.run()`) runs in a worker thread and needs a configurable deadline.

## Pattern

```python
async def extract_with_timeout(source, prompt, *, timeout=None):
    # ... setup ...
    coro = asyncio.to_thread(_blocking_run, source, prompt)
    if timeout is not None:
        coro = asyncio.wait_for(coro, timeout=timeout)
    return await coro
```

## How it works

- `asyncio.to_thread` runs a blocking function in a separate thread so the event loop stays free.
- `asyncio.wait_for` wraps the awaitable with a deadline. If the deadline passes before the awaitable completes, it raises `TimeoutError` (built-in, same as `asyncio.TimeoutError` on Python 3.11+).
- When `timeout=None`, the `wait_for` wrapper is skipped entirely — no change in behavior for callers that don't want a deadline.

## Caution

- `asyncio.wait_for` **cancels** the outer Task, but the background thread from `asyncio.to_thread` may keep running. The extraction result is simply discarded. This is acceptable — the library call finishes in the background and gets cleaned up.
- Clamp user-supplied timeouts to a sensible range:

```python
raw = args.get("timeout")
timeout = max(10, min(300, int(raw))) if raw is not None else None
```

- Catch `TimeoutError` **before** the generic `except Exception` in the handler to give a specific, actionable error message.

## Real example

See `tools/scrapegraph_common.py` (`extract_structured` and `extract_many`) and `tools/scrapegraph_tool.py` (`_handle_scrapegraph`) for the full implementation. Both were updated in commit `672eb929`.
