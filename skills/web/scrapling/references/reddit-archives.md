# Reddit Archive Sources for Scraping

When Reddit directly blocks (403), use these archive/source APIs.

## pullpush.io (recomendado)

Free, no auth needed. Data up to ~May 2025.

### Posts
```
GET https://api.pullpush.io/reddit/search/submission/
  ?subreddit=NAME
  &q=URLENCODED+QUERY
  &sort=score
  &size=20
```
Returns `{"data": [{title, score, num_comments, id, permalink, selftext, created_utc, ...}]}`

### Comments
```
GET https://api.pullpush.io/reddit/search/comment/
  ?link_id=t3_{POST_ID}
  &sort=score
  &size=20
```
Returns same structure with `body` field.

### Limitations
- Rate limit: ~15 req/min before 429
- Data cutoff: ~May 2025 (no Llama 4, DeepSeek V4, Gemma 4 posts)
- Subreddit search only (no multi-reddit)
- No /hot or /top endpoints — only search

### Python pattern
```python
from scrapling.fetchers import Fetcher
import json, urllib.parse

url = f"https://api.pullpush.io/reddit/search/submission/?subreddit={sub}&q={urllib.parse.quote(q)}&sort=score&size=20"
page = Fetcher.get(url, stealthy_headers=True)
data = json.loads(page.body)  # NOT page.text
posts = data['data']
```

## Ollama Library (no Reddit, but useful source)

`ollama.com/library` responds to simple GET with `stealthy_headers=True`. Returns 233 models sorted by popularity with pull counts.

Parse with:
```python
from scrapling.parser import Selector
sel = Selector(page.body)
model_links = sel.css('a[href*="/library/"]')
```

Pull counts are visible as `StaticText "116M"` followed by `StaticText "Pulls"` in the browser snapshot.
