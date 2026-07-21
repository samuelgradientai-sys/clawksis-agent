# Testing logging with env-dependent conditions

When you add a `logger.warning()` that fires only when a certain env var is missing or empty,
test it with pytest's `caplog` fixture + `patch.dict("os.environ", {}, clear=True)`.

## The pattern

```python
def test_warning_logged_when_no_api_key(caplog):
    """When env var X is not set and no fallback exists, a warning is logged."""
    import logging

    caplog.set_level(logging.WARNING)
    with patch("module.path.dependency", side_effect=ImportError("not available")):
        with patch.dict("os.environ", {}, clear=True):  # clear ALL env vars
            result = your_function()
    assert "expected warning text" in caplog.text
    assert result["api_key"] == ""
```

## Why it works

- `caplog` captures all log records at or above the set level (WARNING in this case)
- `patch.dict("os.environ", {}, clear=True)` wipes env vars entirely, forcing every fallback to fail
- You control the scenario: what's absent vs present in the environment

## Variations

**Partial env clear** — keep some vars, clear others:
```python
with patch.dict("os.environ", {"PATH": "/usr/bin"}, clear=True):
    ...
```

**Set a specific value to test the happy path**:
```python
with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
    ...
```

## Real example from scrapegraph

In `tools/scrapegraph_common.py`'s `build_llm_config()`, a warning is emitted when
no API key is found in the auxiliary client *or* in `OPENAI_API_KEY` / `OPENROUTER_API_KEY`.
The test clears all env vars to force the empty-key path:

```python
def test_build_llm_config_empty_api_key_logs_warning(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    with patch(
        "agent.auxiliary_client.get_text_auxiliary_client",
        side_effect=ImportError("no aux client"),
    ):
        with patch.dict("os.environ", {}, clear=True):
            cfg = sgc.build_llm_config()
    assert cfg["api_key"] == ""
    assert "no API key" in caplog.text
```
