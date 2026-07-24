# Shorts Generator Reference — Architecture & Code Patterns

> Working reference from the session that built `/root/shorts-engine/generator.py`. Copy and adapt.

## Generator Pipeline (5 steps)

```
Topic → 1️⃣ Script (template pool) → 2️⃣ Voiceover (edge-tts) → 3️⃣ Visuals (Pixabay stock or Pillow fallback) → 4️⃣ Compose (moviepy) → 5️⃣ Export (1080×1920 MP4)
```

## Step 1 — Script generation

Use a pool of interchangeable templates. Each template has: hook (strong opener), points (5 concise facts), cta (call to action). Rotate randomly so every video feels fresh.

### 3 proven template formats

| Format | Hook Style | Best For |
|--------|-----------|----------|
| Question hook | "¿Sabías que...?" | General facts, psychology |
| Strong claim | "🚨 [TOPIC]: LA VERDAD QUE NADIE TE CUENTA" | Mystery, controversy |
| Countdown | "🧠 5 DATOS QUE CAMBIARÁN TU FORMA DE VER [TOPIC]" | List content, Top 5 |

### Template structure (JSON)
```python
{
    "hook": "El 90% de las personas hacen esto mal",
    "points": ["Dato 1 con estadística", "Dato 2 con estudio", ...],
    "cta": "Comenta abajo si te pasó. Síguenos para más."
}
```

## Step 2 — Voiceover with edge-tts

```python
import edge_tts

async def generate_voice(text_parts: list, output_path: str, voice: str = "es-CO-GonzaloNeural"):
    full_text = " ".join(text_parts)
    # voice = "es-CO-GonzaloNeural"  # Spanish male, Colombia
    # voice = "es-CO-SalomeNeural"   # Spanish female, Colombia
    communicate = edge_tts.Communicate(full_text, voice, rate="-5%", pitch="+0Hz")
    await communicate.save(output_path)
```

**Key settings:**
- `rate="-5%"` — slightly slower for clarity
- List all voices: `edge-tts --list-voices`
- Spanish voices available: Colombia, Spain, Argentina, Mexico, Chile, etc.

## Step 3 — Visuals

### Option A: Pixabay stock footage (requires API key)

```python
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
url = "https://pixabay.com/api/videos/"
params = {"key": PIXABAY_API_KEY, "q": query, "per_page": 3, "safesearch": "true"}
resp = requests.get(url, params=params, timeout=10)
data = resp.json()
# Returns hits[].videos.medium.url (1280x720) or small.url (640x360)
```

**Get a free key:** Sign up at [pixabay.com](https://pixabay.com) → [API docs](https://pixabay.com/api/docs/) → copy key from your account.

### Option B: Pillow fallback (no API key needed)
### Option B: Pillow fallback (no API key needed)
Generate gradient backgrounds with subtle decorative circles. Results look clean and modern — similar to successful faceless Shorts channels.

### Option C: AI-generated images (image_generate tool)
Use Clawksis's `image_generate` tool to create unique visuals for each video frame. Works well for cinematic/landscape/abstract content where stock footage feels generic.

```python
# Generate images, then crop to 9:16 and use as ImageClip frames
from PIL import Image
import numpy as np

def resize_to_portrait(path, w=1080, h=1920):
    img = Image.open(path).convert("RGB")
    target_ratio = w / h
    orig_w, orig_h = img.size
    orig_ratio = orig_w / orig_h
    if orig_ratio > target_ratio:
        new_w = int(orig_h * target_ratio)
        offset = (orig_w - new_w) // 2
        img = img.crop((offset, 0, offset + new_w, orig_h))
    else:
        new_h = int(orig_w / target_ratio)
        offset = (orig_h - new_h) // 2
        img = img.crop((0, offset, orig_w, offset + new_h))
    return np.array(img.resize((w, h), Image.LANCZOS))

# Use in moviepy:
# from moviepy import ImageClip
# clip = ImageClip(resize_to_portrait("path.jpg")).with_duration(4)
```

**Pros:** Unique visuals every time, no additional API key needed.  
**Cons:** Slower (each image takes ~5-10s to generate), limited to static frames.

```python
from PIL import Image, ImageDraw

c1, c2 = (20, 20, 60), (60, 20, 100)  # purple gradient
img = Image.new("RGB", (1080, 1920))
for y in range(1920):
    ratio = y / 1920
    r = int(c1[0]*(1-ratio) + c2[0]*ratio)
    g = int(c1[1]*(1-ratio) + c2[1]*ratio)
    b = int(c1[2]*(1-ratio) + c2[2]*ratio)
    for x in range(1080):
        img.putpixel((x, y), (r, g, b))
```

Gradient color pairs that work well:
- Purple: `(20,20,60) → (60,20,100)`
- Blue: `(15,25,50) → (30,60,90)`
- Magenta: `(40,15,40) → (80,30,60)`
- Green: `(15,35,25) → (25,60,45)`
- Warm: `(50,30,15) → (80,50,25)`

## Step 4 — Video composition (IMPORTANT: moviepy 2.x API)

### Font handling — CRITICAL PITFALL

moviepy 2.x (released 2024+) uses Pillow internally for TextClip. It requires **font file paths**, not font names.

```python
# ✅ WORKS in moviepy 2.x
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TextClip(text="Hello", font=FONT_BOLD, font_size=44, color='white')

# ❌ FAILS in moviepy 2.x
TextClip(text="Hello", font='DejaVu-Sans-Bold', fontsize=44)  # OSError: cannot open resource
```

### Default font locations (Linux)
- `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`
- `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`

### MoviePy 2.x import changes
```python
# ✅ moviepy 2.x
from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, ImageClip

# ❌ old moviepy 1.x
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip  # deprecated
```

### TextClip parameters (moviepy 2.x)
```python
TextClip(
    text="Hello World",
    font_size=44,           # not fontsize
    color='white',           # str, not (R,G,B) tuple
    font=FONT_BOLD,          # file path, not font name
    stroke_color='black',    # outline
    stroke_width=2,
    text_align='center',
    size=(980, None),        # width constraint, height auto
    method='caption',        # auto-wraps text within size
).with_position(('center', 'center')).with_duration(3.0)
```

## Step 5 — Export settings

```python
final_video.write_videofile(
    output_path,
    fps=30,
    codec='libx264',
    audio_codec='aac',
    bitrate='4000k',     # 4Mbps for 1080p — good quality
    preset='medium',     # 'ultrafast' for quick tests, 'slow' for quality
    threads=2,
    logger=None          # suppress progress bar in scripts
)
```

**Export speed tips:**
- Use `preset='ultrafast'` during development (larger file, faster encode)
- Use `preset='slow'` for final publish (smaller file, better quality)
- 1080×1920 at 4000k takes ~3-5 min for a 45s short
- Reduce to `preset='faster'` for a good middle ground

## Complete pipeline command

```bash
cd /root/shorts-engine && python3 generator.py "tema del short aquí"
```
