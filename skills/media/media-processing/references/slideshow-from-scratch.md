# Video Slideshow From Scratch (No Stock Footage)

Create a short video using **AI-generated images + text-to-speech + moviepy assembly**. No stock footage API, no external media — everything comes from the tools you already have.

## Overview

```
image_generate() → 3–5 images   (OpenAI / your image provider)
edge-tts → narration .mp3        (free, natural voices, offline)
Pillow → title/end cards          (avoids moviepy TextClip font-path pitfalls)
moviepy → compose slideshow       (images + transitions + audio sync)
```

## Step-by-step

### 1. Generate images

Use `image_generate()` with consistent prompts for a coherent look:

```python
# First image
image_generate(prompt="...", aspect_ratio="portrait")

# Aspect ratios: portrait=9:16 (1080×1920), landscape=16:9 (1920×1080), square=1:1
```

Generate 3–5 images. Keep the style, lighting, and color palette consistent.

### 2. Generate voiceover

Use `edge-tts` for free, natural-sounding narration:

```bash
edge-tts \
  --voice es-CO-SalomeNeural \
  --text "Tu texto aquí..." \
  --rate="-5%" \
  --write-media /tmp/narration.mp3
```

**Spanish voices**: `es-CO-SalomeNeural` (Colombia), `es-MX-DaliaNeural` (Mexico), `es-ES-AlvaroNeural` (Spain)

Check duration with `ffprobe` to time your slides:
```bash
ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /tmp/narration.mp3
```

### 3. Assembly script (PIL + moviepy — no TextClip bugs)

Use **Pillow (PIL)** for title/end cards — this avoids moviepy 2.x TextClip's font-path requirement:

```python
from moviepy import *
from PIL import Image, ImageDraw, ImageFont
import numpy as np

W, H = 1080, 1920
font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def resize_image(path):
    """Crop to 9:16 center, resize to (W, H)."""
    img = Image.open(path).convert("RGB")
    target_ratio = W / H
    ow, oh = img.size
    if ow / oh > target_ratio:
        nw = int(oh * target_ratio)
        offset = (ow - nw) // 2
        img = img.crop((offset, 0, offset + nw, oh))
    else:
        nh = int(ow / target_ratio)
        offset = (oh - nh) // 2
        img = img.crop((0, offset, ow, offset + nh))
    return np.array(img.resize((W, H), Image.LANCZOS))

def create_title_card(text, subtitle="", bg=(10, 10, 30)):
    """Create a text overlay with PIL instead of moviepy TextClip."""
    img = Image.new("RGB", (W, H), color=bg)
    draw = ImageDraw.Draw(img)
    font_lg = ImageFont.truetype(font_path, 72)
    font_sm = ImageFont.truetype(font_path, 36)
    bbox = draw.textbbox((0, 0), text, font=font_lg)
    draw.text(((W - (bbox[2]-bbox[0])) // 2, H // 2 - 80),
              text, font=font_lg, fill=(255, 215, 0))
    if subtitle:
        bbox = draw.textbbox((0, 0), subtitle, font=font_sm)
        draw.text(((W - (bbox[2]-bbox[0])) // 2, H // 2 + 40),
                  subtitle, font=font_sm, fill=(200, 200, 200))
    return np.array(img)
```

### 4. Compose clips

```python
# Load images
img1 = ImageClip(resize_image("/path/to/img1.png")).with_duration(4)
img2 = ImageClip(resize_image("/path/to/img2.png")).with_duration(4)

# Create title + end cards
title = ImageClip(create_title_card("TITLE", "Subtitle")).with_duration(3)
closing = ImageClip(create_title_card("Gracias ✨", bg=(10, 10, 30))).with_duration(3)

# Add fade transitions
title = title.with_effects([vfx.FadeIn(0.5), vfx.FadeOut(0.5)])
img1 = img1.with_effects([vfx.FadeIn(0.5), vfx.FadeOut(0.5)])
# ... same for each clip

# Concatenate
final = concatenate_videoclips([title, img1, img2, closing], method="chain")
```

### 5. Add audio

```python
audio = AudioFileClip("/tmp/narration.mp3")
# Loop audio if shorter than video
if audio.duration < final.duration:
    audio = audio.with_effects([afx.AudioLoop(duration=final.duration)])
else:
    final = final.with_duration(audio.duration)

final = final.with_audio(audio)
```

### 6. Export

```python
final.write_videofile(
    "/tmp/output.mp4",
    codec="libx264",
    audio_codec="aac",
    fps=24,
    preset="ultrafast",   # use 'slow' for final, 'ultrafast' for dev
    bitrate="3000k"
)
```

## Pitfalls

- **moviepy TextClip fonts**: MoviePy 2.x uses Pillow internally for TextClip but requires absolute font file paths (not font names). The `create_title_card` helper above sidesteps this entirely by using PIL directly.
- **Export speed**: `preset='ultrafast'` runs ~5× faster but produces larger files. Use for iteration, then switch to `preset='medium'` for final export.
- **Audio shorter than video**: Either loop the audio (`.with_effects([afx.AudioLoop(duration=final.duration)])`) or trim the video to match audio length.
- **Available fonts**: Check with `ls /usr/share/fonts/truetype/` or `fc-list`. DejaVu Sans Bold at `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf` is always present.
