# Reddit scraping via pullpush.io archive

## When to use
When Reddit blocks direct scraping (403, bot detection, blanket IP block).

## Key endpoints

```python
# Search posts in a subreddit
GET https://api.pullpush.io/reddit/search/submission/
  ?subreddit=LocalLLaMA
  &q=search+terms
  &sort=score
  &size=20

# Get comments for a post
GET https://api.pullpush.io/reddit/search/comment/
  ?link_id=t3_{POST_ID}
  &sort=score
  &size=15
```

Response: `{"data": [ ... ]}`

## Limits
- ~15 requests/min before 429
- Data range: ~2024 to ~May 2025
- Rate-limited: spread queries across subreddits

## Scrapling integration

```python
from scrapling.fetchers import Fetcher
import json

page = Fetcher.get(url, stealthy_headers=True, timeout=15)
data = json.loads(page.body)  # ⚠️ .body not .text
posts = data.get('data', [])
```

The `.text` property returns a parsed Selector (empty for JSON). Always use `.body` for raw bytes from API responses.

## Tested subreddits

| Subreddit | Use case |
|-----------|----------|
| LocalLLaMA | LLM hardware, model comparisons, inference builds |
| MiniPCs | Mini PC reviews, comparisons, specs |
| homelab | Server builds, Proxmox, power efficiency |
| selfhosted | Self-hosting software, home server setups |
| sffpc | Small form factor builds |
| hardware | General hardware discussions |
| Minisforum | Minisforum support and reviews |

## Recovery from 429
1. Wait 10-15 seconds
2. Switch subreddit or query
3. Reduce `size` to 10
