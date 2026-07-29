# YouTube Transcripts

> Absorbed from `youtube-content` skill.

## Setup

```bash
uv pip install youtube-transcript-api
```

## Usage

```bash
# Fetch transcript (JSON with metadata)
uv run python3 scripts/fetch_transcript.py "https://youtube.com/watch?v=VIDEO_ID"

# Plain text
uv run python3 scripts/fetch_transcript.py "URL" --text-only

# With timestamps
uv run python3 scripts/fetch_transcript.py "URL" --timestamps

# Specific language with fallback
uv run python3 scripts/fetch_transcript.py "URL" --language tr,en
```

## Output Formats

| Format | Description |
|--------|-------------|
| Chapters | Group by topic shifts, timestamped |
| Summary | 5-10 sentence overview |
| Chapter summaries | Chapters + paragraph each |
| Thread | Twitter/X thread format |
| Blog post | Full article with sections |
| Quotes | Notable quotes with timestamps |

## Workflow

1. Fetch transcript with `--text-only --timestamps`
2. Validate non-empty, correct language
3. If >50K chars, chunk into ~40K segments with overlap
4. Transform to requested format
