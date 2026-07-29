# Error Classifier — scrapegraph tool

The `scrapegraph_tool.py` handler converts raw exceptions into 6 categorized,
user-actionable error messages. Never leaks internal paths or exception text.

## Classification rules

| # | Category | Detected by | User message |
|---|---|---|---|
| 1 | **Browser/headless** | `"missing x server"`, `"headed browser"`, `"browsertype.launch"`, `"x display"`, `"xserver"` | "No display server. Happens when `render_js=false` on a headless server." |
| 2 | **Auth** | `"401"`, `"authenticationerror"`, `"unauthorized"`, `"no api key"` | "Check auxiliary_text model credentials, or set OPENAI_API_KEY / OPENROUTER_API_KEY." |
| 3 | **Rate limit** | `"429"`, `"ratelimiterror"`, `"rate_limit"`, `"too many requests"` | "Retry later or configure a different model with higher rate limits." |
| 4 | **Timeout** | `isinstance(exc, TimeoutError)` | "The LLM extraction timed out. Increase the `timeout` parameter (max 300s) or try a simpler prompt." |
| 5 | **Parse error** | `"invalid json output"`, `"output_parsing_failure"`, `"parsing"` | "Try a more specific prompt with fewer fields, or use `scrape` tool (Scrapling)." |
| 6 | **Generic fallback** | Everything else | "Could be a network error, model overload, or page issue." |

## Code location

`tools/scrapegraph_common.py`, function `classify_scrapegraph_error()`.

## Test

`tests/tools/test_scrapegraph_tool.py::test_classify_timeout_error` now asserts
the specific timeout message instead of falling through to the generic fallback.
