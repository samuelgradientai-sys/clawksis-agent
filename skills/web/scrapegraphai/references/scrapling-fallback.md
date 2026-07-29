# Scrapling fallback: when scrapegraph returns "NA" or "Invalid json output"

## Symptom

`scrapegraph` returns `"NA"`, `"Invalid json output"`, or empty content even though the page is reachable:

```json
{
  "ok": false,
  "error": "ScrapeGraphAI extraction failed: Invalid json output: {{\"content\": \"NA\"}}"
}
```

Or succeeds but returns:

```json
{
  "content": "NA"
}
```

## Root cause

ScrapeGraphAI's LLM-driven extraction **failed to structurally parse the page**. Common triggers:

| Trigger | Why |
|---|---|
| **Long-form articles** (1000+ words) | The LLM can't decide what to extract from the density of text |
| **JS-heavy pages** | The headless Chromium renders the page but structural extraction fails |
| **Pages with complex layouts** (many sections, nav, sidebars, ads) | The LLM gets confused by the noise |
| **Pages behind login/forms** | What's visible isn't the actual content |
| **Anti-bot sites** (Cloudflare, Turnstile) | The page never fully loaded for scrapegraph's browser |

## Fix: fall back to `scrape` (Scrapling)

When scrapegraph fails, switch to the `scrape` tool for **raw content extraction**:

```python
# ❌ scrapegraph fails on this page
# scrapegraph(url="https://example.com/long-article", prompt="...")

# ✅ Fall back to Scrapling for raw markdown
# scrape(url="https://example.com/long-article", mode="auto")
```

### Decision table

| scrapegraph result | Next action |
|---|---|
| `"Invalid json output"` | → `scrape(url, mode="auto")` for raw content |
| `"Content: NA"` | → `scrape(url, mode="auto")` for raw content |
| `"NA"` (structured) | → `scrape(url, mode="auto")` for raw content |
| `Browser closed / Missing X server` | → Don't pass `render_js=false` (see `references/headed-browser-error.md`) |
| `ERR_HTTP2_PROTOCOL_ERROR` | → Try `scrape(url, mode="fetch")` (JS rendering) |
| `net::ERR_NAME_NOT_RESOLVED` | → URL is invalid; double-check the URL |
| `401 / 403` | → Try `scrape(url, mode="stealthy")` for anti-bot |

### Real example from this session

**Goal:** Extract emails from 3PL companies in Colombia listed on a long-form article.

```json
// scrapegraph attempt — FAILED
{
  "url": "https://www.neowork.com/insights/supply-chain-outsourcing-services-companies-in-colombia",
  "prompt": "List all supply chain outsourcing / 3PL companies..."
}
// → "Invalid json output: {{\"content\": \"NA\"}}"
```

```json
// scrape fallback — WORKS
{
  "url": "https://www.neowork.com/insights/supply-chain-outsourcing-services-companies-in-colombia",
  "mode": "auto"
}
// → Full markdown with 14 companies, emails, phones, and addresses
```

**Lesson:** Long-form articles are Scrapling's territory. scrapegraph excels at **small, structured pages** (product pages, tables, specs). For long content, go straight to `scrape`.

## When to keep trying scrapegraph (don't fall back too early)

- **Short pages** (< 500 words) → scrapegraph almost always works
- **Tables and listings** → scrapegraph is the right tool
- **Product specs** → scrapegraph extracts structured JSON cleanly
- **Contact pages** → scrapegraph extracts emails/phones well (as demonstrated in this session with ~10 3PL contact pages)

## Summary

> `scrapegraph` → structured JSON from simple pages, tables, contact info  
> `scrape` (Scrapling) → raw markdown from long articles, anti-bot pages, JS-heavy sites  
> Use `scrapegraph` first for structured data; fall back to `scrape` when it returns `"NA"` or `"Invalid json"`
