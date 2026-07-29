---
name: youtube-shorts-generator
description: Pipeline completo para generar Shorts de YouTube automáticamente con Clawksis. Script → Voz (edge-tts) → Stock footage (Pixabay) → Edición (ffmpeg + Pillow) → Export MP4. Preparado para YouTube OAuth y cronjobs.
category: creative
---

# YouTube Shorts Generator Pipeline

Pipeline para generar y publicar Shorts de YouTube automáticamente usando Clawksis.

## Stack

| Componente | Herramienta | Por qué |
|---|---|---|
| Script | Clawksis (modelo configurado) | Genera hook + 5 puntos + CTA |
| Voz en off | edge-tts | Gratuito, voces naturales, sin API key |
| Stock footage | Pixabay API (gratis) | Videos reales HD, 100 req/min, sin Cloudflare |
| Textos | Pillow (PIL) | Pre-renderiza frames — MUCHO más rápido que moviepy TextClip |
| Edición | ffmpeg (concat + overlay) | Slideshow + background loop, preset ultrafast |
| Upload | YouTube Data API v3 (OAuth) | Pendiente de configurar |

## Estructura

```
/root/shorts-engine/
├── generator.py         # Pipeline principal
├── config.py            # API keys + settings
├── scripts/concat.txt   # Concat file para ffmpeg (auto-generado)
├── footage/             # Stock videos descargados de Pixabay
├── audio/               # TTS generado por edge-tts
├── output/              # Shorts terminados (.mp4)
└── thumbnails/          # Frames PNG pre-renderizados con Pillow
```

## Uso

```bash
cd /root/shorts-engine && python3 generator.py "tema del short"
```

## Pipeline completo

```
Prompt → generator.py
  ├── 1. Script: hook + 5 datos + CTA (template-based, sin API)
  ├── 2. Voz: edge-tts → audio/voiceover.mp3 (~48s)
  ├── 3. Footage: Pixabay API busca y descarga 6 clips → footage/
  ├── 4. Frames: Pillow genera texto grande sobre fondo oscuro → thumbnails/
  ├── 5. ffmpeg: concat frames + loop background + audio → MP4
  └── 6. Output: short_<tema>_<timestamp>.mp4 (1080x1920, ~48s)
```

## Configuración

### Pixabay API Key (gratis, sin tarjeta)
1. Ir a https://pixabay.com/api/docs/
2. Crear cuenta → recibes API key al instante
3. Configurar en `config.py`: `PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "tu-key-aqui")`

### Voces edge-tts recomendadas
| Voz | Descripción |
|---|---|
| `es-CO-GonzaloNeural` | Español Colombia, masculino (recomendado) |
| `es-MX-JorgeNeural` | Español México, masculino |
| `es-ES-AlvaroNeural` | Español España, masculino |
| `es-CO-SalomeNeural` | Español Colombia, femenino |
| `en-US-GuyNeural` | Inglés US, masculino |

Ajuste de velocidad: `rate="-5%"` (recomendado para speech natural).

## Diseño visual del Short

| Segmento | % Duración | Contenido visual |
|---|---|---|
| Hook | 12% | Texto grande centrado sobre footage real |
| Punto #1-5 | 14% c/u | Número grande + texto explicativo |
| CTA | 18% | Llamado a la acción final |

- **Resolución:** 1080×1920 (9:16 vertical)
- **Fondo:** Stock footage escalado con crop (`force_original_aspect_ratio=increase,crop`)
- **Texto:** Blanco, DejaVu Sans Bold, centrado, sobre fondo oscuro
- **Acento:** Dorado #FFC832
- **Codec:** H.264, preset `ultrafast`, CRF 23
- **Bitrate típico:** ~300 kbps (48s ≈ 2MB)

## Detalles técnicos y pitfalls (importante)

### ffmpeg: convertir landscape → vertical para Shorts
La mayoría del stock footage Pixabay es 16:9 horizontal. Para Shorts verticales:
```bash
-filter_complex "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[bg]"
```

### ffmpeg: loop de background para duración completa
```bash
-stream_loop -1 -i footage/stock_0.mp4   # loop infinito, -shortest lo corta
```

### ffmpeg: concat demuxer para slideshow
Formato correcto del concat.txt:
```
file '/path/to/frame.png'
duration 5.90
file '/path/to/frame2.png'
duration 6.89
```

### Por qué NO usar moviepy TextClip para HD
- `TextClip(method='caption')` renderiza frame por frame → **extremadamente lento** en 1080×1920
- Solución: pre-renderizar con Pillow → usar como ImageClip o directamente en ffmpeg concat
- Un Short de 48s pasa de ~10 min de render a ~15 segundos

### Pixabay API — detalles prácticos
- Endpoint: `https://pixabay.com/api/videos/?key=KEY&q=QUERY&per_page=N`
- Rate limit: 100 requests / 60 seconds
- Videos disponibles en 4 tamaños: large (4K), medium (HD), small, tiny
- El `medium` (1280×720) es el mejor balance calidad/descarga
- Buscar en **inglés** da mejores resultados que español
- Keywords recomendadas: people, thinking, business, success, psychology, brain

## Troubleshooting comunes

| Síntoma | Causa | Solución |
|---|---|---|
| `moov atom not found` | Video no terminó de escribirse | Usar ffmpeg directo, no moviepy |
| Video sale horizontal (1080×608) | Faltó `crop` en filter | Agregar `crop=1080:1920` |
| Audio mismatch: end_time > duration | Segmentos suman más que el audio | Calcular % exactos que sumen 100% (ej: hook 12%, puntos 70%/5, CTA 18%) |
| Sin stock footage | API key vacía o query sin resultados | Verificar key y probar query en inglés |
| ffmpeg: `Option loop not found` | Flag en posición incorrecta | Usar `-stream_loop -1 -i file` no `-loop 1 -i file` |
| HF Inference: 403 "not sufficient permissions" | Token sin permiso inference.serverless.write | Crear token fine-grained con ese permiso explícito |
| Replicate: 402 "Insufficient credit" | No hay billing configurado | Ir a https://replicate.com/account/billing a agregar método de pago |

## Referencias (skill files)
| File | Contenido |
|---|---|
| `SKILL.md` | Este documento — guía principal del pipeline |
| `references/pixabay-api-ffmpeg.md` | API Pixabay, keywords, ffmpeg composición vertical |
| `references/flux-hf-image-generation.md` | FLUX.1 via HuggingFace Inference para imágenes dinámicas |
| `references/sadtalker-avatar.md` | SadTalker avatar parlante via Replicate |

## Próximas mejoras
- [ ] YouTube OAuth + subida automática
- [ ] Varios templates de script (top 10, datos curiosos, historias)
- [ ] Múltiples backgrounds por segmento (cambia el video con cada punto)
- [ ] Música de fondo royalty-free
- [ ] Thumbnail automático
- [ ] Programar cronjob diario con Clawksis
- [ ] Integrar FLUX para imagen única por segmento (vs. mismo fondo todo el video)
- [ ] Integrar SadTalker avatar parlante (foto + audio = presentador virtual)
