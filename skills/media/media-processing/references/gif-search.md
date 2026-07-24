# GIF Search (Tenor API)

> Absorbed from `gif-search` skill.

## Setup

```bash
TENOR_API_KEY=your_key_here  # add to ~/.clawksis/.env
```

Get a free API key: https://developers.google.com/tenor/guides/quickstart

## Search

```bash
# Search and get GIF URLs
curl -s "https://tenor.googleapis.com/v2/search?q=thumbs+up&limit=5&key=${TENOR_API_KEY}" | jq -r '.results[].media_formats.gif.url'

# Smaller/preview versions
curl -s "https://tenor.googleapis.com/v2/search?q=nice+work&limit=3&key=${TENOR_API_KEY}" | jq -r '.results[].media_formats.tinygif.url'
```

## Download Top Result

```bash
URL=$(curl -s "https://tenor.googleapis.com/v2/search?q=celebration&limit=1&key=${TENOR_API_KEY}" | jq -r '.results[0].media_formats.gif.url')
curl -sL "$URL" -o celebration.gif
```

## Parameters

`q` (query), `limit` (1-50), `contentfilter` (off/low/medium/high), `media_filter` (gif/tinygif/mp4/tinymp4).
