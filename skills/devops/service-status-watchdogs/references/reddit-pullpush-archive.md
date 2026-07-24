# Reddit scraping via pullpush.io archive

Use this technique when Reddit blocks direct scraping (403, bot detection, blanket block on server IP).

## Endpoints

```python
# Search posts
GET https://api.pullpush.io/reddit/search/submission/
  ?subreddit=LocalLLaMA
  &q=search+terms
  &sort=score
  &size=20
  &after=1735689600  # optional unix timestamp filter

# Search comments by post ID
GET https://api.pullpush.io/reddit/search/comment/
  ?link_id=t3_{POST_ID}
  &sort=score
  &size=15
```

Response shape: `{"data": [ ... ]}`, up to ~May 2025.

## Limits

- ~15 requests/min before 429
- Data range: ~2024 to May 2025 (archived, not live)
- Rate-limiting requires spreading queries across subreddits and topics

## Known working subreddits tested

| Subreddit | Best for |
|-----------|----------|
| LocalLLaMA | LLM hardware, model comparisons, inference builds |
| MiniPCs | Mini PC reviews, comparisons, specs |
| homelab | Server builds, Proxmox, power efficiency |
| selfhosted | Self-hosting software, home server setups |
| sffpc | Small form factor builds, compact workstations |
| hardware | General hardware discussions |
| Minisforum | Minisforum-specific support and reviews |

## Scrapling integration

When using this with the `scrapling` library:

```python
from scrapling.fetchers import Fetcher
import json

page = Fetcher.get(url, stealthy_headers=True, timeout=15)
data = json.loads(page.body)  # ⚠️ .body, NOT .text
posts = data.get('data', [])
```

The `.text` property returns a parsed Selector (empty for JSON). Always use `.body` for raw bytes from API responses.

## Rate-limit recovery

When pullpush returns 429:
1. Wait 10-15 seconds
2. Switch to a different subreddit or query
3. Rotate between multiple query patterns
4. If persistent, reduce `size` parameter to 10
