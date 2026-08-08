# Error Classifier — scrapegraph tool

The `scrapegraph_tool.py` handler converts raw exceptions into 9 categorized,
user-actionable error messages (shared with the `web_extract` backend via
`tools.scrapegraph_common.classify_scrapegraph_error()`). Never leaks internal
paths or exception text.

## Classification rules

Order matters — more specific checks (auth, quota, rate-limit, timeout type)
run before broader keyword families (HTTP status, network).

| # | Category | Detected by | User message |
|---|---|---|---|
| 1 | **Browser/headless** | `"missing x server"`, `"headed browser"`, `"browsertype.launch"`, `"x display"`, `"xserver"` | "No display server. Happens when `render_js=false` on a headless server." |
| 2 | **Auth** | `"401"`, `"authenticationerror"`, `"unauthorized"`, `"no api key"` | "Check auxiliary_text model credentials, or set OPENAI_API_KEY / OPENROUTER_API_KEY." |
| 3 | **Quota / billing** (v1.9) | `"insufficient_quota"`, `"billing_not_active"`, `"insufficient credits"`, `"out of credits"`, `"credit balance"`, `"payment required"`, `"402"`, `"quota"`, `"billing"`, `"max monthly spend"` | "The LLM model used by ScrapeGraphAI has run out of credits or its billing is inactive. Check the provider balance or switch models — retrying won't help." |
| 4 | **Rate limit** | `"429"`, `"ratelimiterror"`, `"rate_limit"`, `"too many requests"` | "Retry later or configure a different model with higher rate limits." |
| 5 | **HTTP status** | `"403"`, `"404"`, `"500"`, `"502"`, `"503"`, `"http error"`, `"status code"`, `"bad gateway"`, `"forbidden"`, `"page not found"`, `"service unavailable"` | "The page returned an HTTP error (e.g. 403/404/5xx). Verify the URL, or use the `scrape` tool (Scrapling) which bypasses anti-bot protections." |
| 6 | **Timeout** | `isinstance(exc, TimeoutError)` or `"graph execution timed out"` | "The LLM extraction timed out. Increase the `timeout` parameter (max 300s) or try a simpler prompt." |
| 7 | **Network / DNS / TLS** | `"getaddrinfo"`, `"connection refused"`, `"connection reset"`, `"max retries exceeded"`, `"ssl"`, `"certificate verify failed"`, `"timed out"`, ... | "Network error reaching the page — DNS, connection, TLS, or a network-level timeout. Verify the URL, check connectivity, or use the `scrape` tool (Scrapling)." |
| 8 | **Parse error** | `"invalid json output"`, `"output_parsing_failure"`, `"parsing"` | "Try a more specific prompt with fewer fields, or use `scrape` tool (Scrapling)." |
| 9 | **Generic fallback** | Everything else | "Could be a network error, model overload, or page issue." |

Notes:
- **Quota before rate-limit (v1.9):** quota errors often carry a `429` status
  code too (e.g. OpenAI `insufficient_quota`); the quota family runs first so
  they are not misread as a plain rate limit.
- **Timeout type before network keywords:** a real `TimeoutError` from our own
  `asyncio.wait_for` is never misread as a network timeout.

## Code location

`tools/scrapegraph_common.py`, function `classify_scrapegraph_error()`.
Both the native `scrapegraph` tool handler and the `web_extract` backend
(`plugins/web/scrapegraphai/provider.py`) surface these hints.

## Test

`tests/tools/test_scrapegraph_tool.py` — `test_classify_*` covers every branch:
`test_classify_x_display`, `test_classify_auth`, `test_classify_quota_billing`
(v1.9, incl. quota-over-429 precedence), `test_classify_rate_limit`,
`test_classify_http_status`, `test_classify_timeout_error` (incl. the
graph-execution-timeout message), network/DNS/TLS, `test_classify_invalid_json`
and `test_classify_generic`.
