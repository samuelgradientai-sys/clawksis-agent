# Google Maps Scraping Patterns

## Overview

Scraping Google Maps search results for business listings (e.g., opticians, restaurants, etc.) using the `scrape` tool with `stealthy` mode.

## Approach: City-by-City

Google Maps limits results to ~8 per search when **not signed in** (the "limited view"). To get broader coverage, scrape each city separately:

```
https://www.google.com/maps/search/{query}+en+{city},+Colombia/
```

## Mode Selection

| Mode | Works? |
|---|---|
| `stealthy` | ✅ Usually works |

## Pattern

```
scrape(url=..., format="text", mode="stealthy")
```

## Common Issues

- IP blocks after ~6-8 successful city scrapes
- Phone and address columns often swapped in raw output — fix with regex
- Chain stores (Lafam, Opticalia, Santa Lucía, etc.) need filtering
