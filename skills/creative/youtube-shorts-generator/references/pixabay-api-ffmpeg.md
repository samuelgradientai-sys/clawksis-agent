# Pixabay API Reference

## Endpoints

```
Search videos: GET https://pixabay.com/api/videos/?key=KEY&q=QUERY&per_page=N
Search images: GET https://pixabay.com/api/?key=KEY&q=QUERY&per_page=N
```

## Response format (videos)

```json
{
  "total": 2847,
  "totalHits": 500,
  "hits": [
    {
      "id": 132,
      "pageURL": "https://pixabay.com/videos/id-132/",
      "type": "film",
      "tags": "people, thinking, brain",
      "duration": 15,
      "videos": {
        "large": { "url": "...", "width": 1920, "height": 1080, "size": 8557683 },
        "medium": { "url": "...", "width": 1280, "height": 720, "size": 4604930 },
        "small": { "url": "...", "width": 640, "height": 360, "size": 1311712 },
        "tiny": { "url": "...", "width": 480, "height": 270, "size": 519731 }
      },
      "views": 141918,
      "downloads": 53751,
      "user": "Coverr-Free-Footage"
    }
  ]
}
```

## Keywords que funcionan para psicología/finanzas

| Tema | Keywords (inglés) |
|---|---|
| Psicología | people thinking, brain, psychology experiment, meditation, stress |
| Finanzas | money, business meeting, stock market, graph, office, success |
| Motivación | success, goal, runner, sunrise, mountain, achievement |
| Ciencia | laboratory, microscope, space, technology, research |
| General | people, lifestyle, city, nature, technology, abstract |

## Rate limits
- 100 requests per 60 seconds
- Best to cache search results for 24h
- Download videos immediately (URLs may expire)

## ffmpeg reference: composición vertical con loop

```bash
ffmpeg -y \
  -stream_loop -1 -i footage/stock_0.mp4 \
  -f concat -safe 0 -i scripts/concat.txt \
  -i audio/voiceover.mp3 \
  -filter_complex \
    "[1:v]format=rgba[slides];\
     [0:v]scale=1080:1920:force_original_aspect_ratio=increase,\
            crop=1080:1920[bg];\
     [bg][slides]overlay=0:0[outv]" \
  -map "[outv]" -map "2:a" \
  -c:v libx264 -preset ultrafast -crf 23 \
  -c:a aac -shortest \
  output/short_final.mp4
```
