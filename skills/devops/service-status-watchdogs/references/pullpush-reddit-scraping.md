# Reddit scraping via pullpush.io

## When to use

Reddit blocks direct HTTP/browser access from this server (403, rate-limited, captcha). The pullpush.io archive is a public, free alternative for historical Reddit data (2024 to ~May 2025).

## Endpoints

```python
# Search submissions in a subreddit
GET https://api.pullpush.io/reddit/search/submission/?subreddit={name}&q={query}&sort=score&size={n}

# Search comments on a post
GET https://api.pullpush.io/reddit/search/comment/?link_id=t3_{post_id}&sort=score&size={n}
```

## Important: response body access

Scrapling's `Fetcher.get()` returns a `Selector` object. The raw response is in `.body` (bytes), NOT `.text` (which is the parsed DOM text, often empty for JSON responses).

```python
from scrapling.fetchers import Fetcher
import json

page = Fetcher.get(url, stealthy_headers=True, timeout=15)
data = json.loads(page.body)  # ✅ correct
posts = data['data']          # pullpush returns {data: [...]}
```

## Rate limits

- ~15 requests per minute before 429 errors
- Each query returns max 100 results (use `size` param)
- Data indexed up to ~May 2025 only — recent posts (Llama 4, DeepSeek V4, etc.) won't appear

## Workflow

1. Build query with relevant subreddit and search terms
2. Fetch via scrapling `Fetcher.get(url, stealthy_headers=True, timeout=15)`
3. Parse with `json.loads(page.body)`
4. For comments, get `link_id` as `t3_{post.id}` and query the comment endpoint
5. Sort results by `score` to get top-voted content

## Reddit URLs from permalinks

Pullpush returns `permalink` field (e.g. `/r/subreddit/comments/abc123/title/`). Prepend `https://www.reddit.com` to get the live URL.

```python
reddit_url = f"https://www.reddit.com{p['permalink']}" if p.get('permalink') else ''
```

## Models that are too recent for pullpush

- Llama 4 (Meta)
- DeepSeek V4
- Gemma 4 (Google)
- Mythos 70B
- Framework Desktop

For these, use the Ollama website scrape or direct knowledge.
