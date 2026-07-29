---
name: media-processing
description: "Video and audio processing with ffmpeg — plus YouTube transcripts, GIF search, audio spectrograms, and music generation tools. Umbrella for all media-related tools."
tags: [media, video, audio, ffmpeg, youtube, gif, spectrogram, music]
---

# Media Processing (Video, Audio, YouTube, GIFs, Spectrograms, Music)

> **Umbrella skill** — covers ffmpeg processing, YouTube transcripts, GIF search, audio spectrograms, and music generation. Each subtopic has a reference file.

## Video Upscaling with ffmpeg

### Quick upscale (640×360 → 1280×720)

```bash
ffmpeg -i input.mp4 \
  -vf "scale=1280:720:flags=lanczos,unsharp=3:3:0.8:3:3:0.4" \
  -c:v libx264 -preset fast -crf 20 \
  -c:a aac -b:a 96k \
  output_mejorado.mp4
```

### High-quality upscale (to 1080p, slower)

```bash
ffmpeg -i input.mp4 \
  -vf "scale=1920:1080:flags=lanczos,unsharp=5:5:1.0:5:5:0.5" \
  -c:v libx264 -preset slow -crf 18 \
  -c:a aac -b:a 128k \
  output_1080p.mp4
```

### Check video info first

```bash
ffprobe -v quiet -print_format json -show_format -show_streams input.mp4
```

### Getting Video Files

- **WeTransfer links**: Use browser to download, files go to `/root/Downloads/`
- **YouTube links**: Use `yt-dlp`, then process with ffmpeg

### Pitfalls
- Long videos (~2min+) at 1080p preset slow may timeout (60s limit). Use `-preset fast` and 720p for faster processing.
- CRF 18-20 is visually lossless for web delivery.
- Create 2-3 variants if multiple download attempts happened — pick the most recent one.

## Subtopic References

| Topic | Reference | What It Covers |
|-------|-----------|----------------|
| **YouTube Transcripts** | `references/youtube-content.md` | Fetch transcripts, format as chapters/summaries/threads/blogs |
| **GIF Search** | `references/gif-search.md` | Search/download GIFs from Tenor API via curl + jq |
| **Audio Spectrograms** | `references/songsee.md` | Visualize audio features: mel, chroma, MFCC via songsee CLI |
| **Music Generation** | `references/heartmula.md` | Open-source Suno-like music generation from lyrics + tags |
| **Quick Slideshow Video** | `references/slideshow-from-scratch.md` | Generate a short video using ONLY built-in tools: `image_generate` for images → edge-tts voiceover → moviepy assembly with PIL text overlays (avoids TextClip font-path pitfalls). No stock footage API needed. |
| **YouTube Shorts Pipeline** | See skill `youtube-shorts-automation` → `references/generator-pattern.md` | Full faceless-channel production: niche research → script → stock footage/Pillow visuals → voiceover → captions → upload via YouTube API. |
