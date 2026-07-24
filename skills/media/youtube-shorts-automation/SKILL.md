---
name: youtube-shorts-automation
description: "Automated YouTube Shorts production pipeline: niche research → AI script → local video assembly (ffmpeg + moviepy + Pillow) → YouTube API upload → Clawksis cron scheduling. Build and operate your own faceless channels."
tags: [youtube, shorts, automation, faceless, video, ffmpeg, moviepy, cron, youtube-api, content-creation]
---

# YouTube Shorts Automation Pipeline

> **Class-level skill** — produce and auto-publish YouTube Shorts using Clawksis as the orchestrator. All tools run locally (ffmpeg, moviepy, Pillow) or via open APIs (OpenRouter, YouTube Data API v3). No SaaS subscriptions needed.

## 🧭 Workflow Overview

```
Niche Research → Script Generation → Visuals → Voiceover → Video Assembly → Upload → Cron Schedule
```

## 🎯 Niche Selection Framework

### Selection criteria (in order of importance)
1. **RPM × retention** — not just raw RPM. A $0.40 RPM niche with 78% retention beats a $0.45 RPM niche with 40% retention
2. **Ease of automation** — can the script/visuals be generated programmatically?
3. **Content pipeline depth** — how many videos before running out of ideas?
4. **Time to monetize** — YPP gate: 1,000 subs + 10M Shorts views in 90 days

### Top-rated faceless Shorts niches (2026 data)

| Niche | RPM (Shorts) | Retention | Time to Monetize | Production Effort |
|-------|:---:|:---:|:---:|:---:|
| Psychology / Human behavior | $7-14 | 68-78% | 2-4 months | Low |
| "What if" scenarios | $6-11 | 62-73% | 2-3 months | Very Low |
| AI news / tool reviews | $10-22 | 60-70% | 3-5 months | Medium |
| Dark history / mysteries | $8-12 | 70-82% | 3-6 months | Medium-High |
| Science facts | $5-12 | 60-70% | 3-6 months | Low |
| Finance / investing | $9-21 | 65-75% | 4-8 months | High (accuracy needed) |

### Niches to AVOID for faceless
- Generic motivation quotes (28-42% retention, 9-12mo to monetize, saturated)
- Generic life hacks (dead niche post-2018)
- Celebrity gossip (copyright strikes)
- Pets/animals (RPM too low: $0.02-0.06)

### Niche validation checklist
- [ ] Search YouTube — do top 10 results show channels with low subs but high views? (strong demand signal)
- [ ] Can you write 30 scripts without repeating?
- [ ] Does it support 50-60s storytelling format?
- [ ] Is there a clear hook in the first 3 seconds?

See `references/niche-research.md` for the full data from our scraping session.

## 🔧 Tech Stack

| Stage | Tool | Notes |
|-------|------|-------|
| Script generation | OpenRouter (any model) | Clawksis generates the hook → body → CTA structure |
| Text-to-speech | **edge-tts** (primary) or ElevenLabs | edge-tts: free, natural voices, works offline, supports Spanish (Colombia, Spain, Mexico, Argentina, Chile). Use `rate="-5%"` for slightly slower, clearer delivery. |
| Stock footage | **Pixabay API** (free) | Sign up at pixabay.com → 100 req/min, 4 video quality tiers. Set key as `PIXABAY_API_KEY` env var. |
| Visual fallback (no API key) | **Pillow gradients** | Clean gradient backgrounds + decorative circles. Looks professional, no AI-slop. Works immediately. |
| Video assembly | **moviepy 2.x** + ffmpeg | ⚠️ moviepy 2.x changed TextClip API — uses Pillow internally, requires **font file paths** (not font names). Import from `moviepy` not `moviepy.editor`. |
| Captions burned-in | ffmpeg drawtext or moviepy | Shorts with captions retain 18-30% longer |
| YouTube upload | YouTube Data API v3 (OAuth 2.0) | Resumable upload protocol, ~6 uploads/day with default quota |
| Scheduling | Clawksis cronjob | Cronjob with prompt to generate + upload on schedule |

### Pipeline optimization (user preference)
- **Do NOT build a SaaS** — own the channels, operate them via cron
- **Prioritize local tools** over paid APIs when possible
- **Batch production** over real-time generation
- **Use fallback visuals when no stock footage API key is available** — Pillow-generated gradients look clean and professional (see reference file)
- **Prefer edge-tts for voiceover** — free, natural voices, works offline, supports Spanish (Colombia, Spain, Mexico, Argentina, Chile)
- **Always test with `preset='ultrafast'`** during development, switch to `preset='slow'` for final publish

## 📝 Short Script Structure (55-60 seconds)

```
0-3s:        Pattern interrupt hook ("La gente que hace X en realidad...")
3-15s:       Surprising claim / counterintuitive fact
15-40s:      Explanation with visual metaphor
40-55s:      Practical takeaway / "lo que esto significa para ti"
55-60s:      Subtle CTA or cliffhanger to next video
```

### Psychology niche example hooks
- "Nunca debes hacer esto en una discusión según psicólogos"
- "La gente exitosa tiene este hábito en común y no lo sabes"
- "El 90% de las personas fallan en esto por una razón psicológica"

### "What if" niche example hooks
- "¿Qué pasaría si la Tierra dejara de girar?"
- "¿Qué pasaría si los humanos vivieran 200 años?"
- "¿Qué pasaría si Internet se apagara por un año?"

## 📤 YouTube Upload Setup

### One-time setup
1. Go to Google Cloud Console → create project → enable YouTube Data API v3
2. Create OAuth 2.0 credentials (Desktop app type)
3. Download `client_secrets.json`
4. Run first upload manually to authorize → generates credentials file with refresh token
5. Store refresh token → subsequent uploads are fully automated

### Quota budget
- Default: 10,000 units/day
- Upload: 1,600 units each
- Max: ~6 uploads/day (request increase for more)
- Use resumable upload protocol for reliability

### Tools for automation
- `tokland/youtube-upload` — CLI tool, works well with cron
- Custom Python script using google-api-python-client

## ⏰ Cron Scheduling Pattern

```yaml
# Example cron job structure
prompt: >
  Generate one 55-second Shorts video on [niche topic]:
  1. Script: 60s hook+body+CTA
  2. Voice: generate with TTS
  3. Visuals: create title cards with Pillow
  4. Video: assemble with moviepy (9:16, 1080×1920)
  5. Upload: via YouTube API to channel
  6. Return the YouTube URL
schedule: "0 8 * * *"  # daily at 8am
```

## 🐛 Pitfalls

- **Quota exhaustion**: YouTube API only allows ~6 uploads/day. Request quota increase or batch uploads strategically
- **OAuth token expiry**: Refresh tokens expire if unused >6 months. Schedule a monthly "keepalive" cron that does a lightweight API call
- **Copyright music**: NEVER use copyrighted background music in automated pipelines. Use royalty-free or AI-generated
- **Content recycling**: YouTube flags reused content. Ensure each script is unique
- **Monetization delay**: YPP approval takes 1-2 months after hitting thresholds. Don't expect ad revenue in month 1
- **Niche hopping**: The algorithm rewards consistency. Commit to one niche for minimum 30 videos
- **Long-form companion**: Shorts RPM is low. The real money is Shorts → long-form funnel. Always link to a long-form video in description
- **MoviePy 2.x TextClip requires font file paths**: `font='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'` works; `font='DejaVu-Sans-Bold'` raises OSError. Pillow is the backend — font names are NOT resolved automatically.
- **Export speed vs quality**: 1080×1920 at `bitrate='4000k'` with `preset='medium'` takes 3-5 min for a 45s video. Use `preset='ultrafast'` during dev, `preset='slow'` for final publish.

## 📚 Reference Files

| File | Contents |
|------|----------|
| `references/niche-research.md` | Full RPM tables, retention data, niche rankings, verified channel examples, sources from 2026 scraping |
| `references/youtube-api-setup.md` | Google Cloud Console setup, OAuth 2.0 flow, quota management, common error fixes, video format specs |
| `references/generator-pattern.md` | Complete pipeline code patterns: edge-tts voiceover, Pixabay API, Pillow fallback visuals, moviepy 2.x composition (font paths, TextClip API), export settings. Working reference built during session. |
