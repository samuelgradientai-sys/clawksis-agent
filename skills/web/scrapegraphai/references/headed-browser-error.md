# Headed browser error (Missing X server)

## Symptom

Calling the `scrapegraph` tool with `render_js=false` on a headless Linux server produces:

```
ScrapeGraphAI extraction failed: Failed to scrape after 1 attempts:
BrowserType.launch: Target page, context or browser has been closed
Browser logs:

╔════════════════════════════════════════════════════════════════════════════════╗
║ Looks like you launched a headed browser without having a XServer running.    ║
║ Set either 'headless: true' or use 'xvfb-run <your-playwright-app>' before    ║
║ running Playwright.                                                           ║
║                                                                               ║
║ <3 Playwright Team                                                            ║
╚════════════════════════════════════════════════════════════════════════════════╝
```

## Root cause

The `scrapegraph_tool.py` handler maps `render_js` to the `headless` parameter like this:

```python
headless = True if render_js is None else bool(render_js)
```

| `render_js` passed | `headless` used | Result |
|---|---|---|
| omitted or `true` | `true` | ✅ Headless Chromium |
| `false` | `false` | ❌ Headed — needs X server |

Passing `render_js=false` forces headed mode, which requires a display server. On cloud VMs, containers, and CI runners there is no X server → the browser crashes.

## Fix

Never pass `render_js=false` on a headless server. Omit the parameter or set `render_js=true`. There is no practical difference in output — headless Chromium still renders JavaScript just as well.
