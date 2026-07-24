# Prompt template para el agente del briefing (con audio por script)

Este prompt se usa como `prompt` del cron job. El script `fetch-ai-news.py`
inyecta las noticias via `script:` Y ya genera el audio TTS. El agente solo
formatea el texto y pasa la línea `MEDIA:`.

## Full prompt (actual, 17-Jun-2026)

```text
Recibiste noticias de IA y un audio ya generado. El script puso "🎤 AUDIO: MEDIA:ruta" al final de su output.

Tu tarea:
1. Escribe las noticias como briefing en español, con emojis y estilo natural.
2. Al FINAL de tu respuesta, copia solo la RUTA del audio en una línea aparte, así: MEDIA:/root/.clawksis/audio_cache/briefing_....ogg (sin emojis, sin "AUDIO:", solo la palabra MEDIA: seguida de la ruta exacta).
```

## Cron config (current)

```yaml
model: null                      # uses default (deepseek-v4-flash)
provider: null                   # uses default (deepseek)
script: fetch-ai-news.py
no_agent: false
schedule: "0 13 * * *"
deliver: telegram
toolsets: []                     # all tools available
skills: []
```

## Key changes from v1.0

- **Audio generation moved from agent to script** — script calls `edge-tts --voice es-CO-GonzaloNeural` directly. Agent just passes through the `MEDIA:` path.
- Model reverted from `mistral/mistral-large-2411` (404 on OpenRouter) back to default `deepseek-v4-flash` from deepseek provider
- TTS voice configured as `es-CO-GonzaloNeural` (Colombian Spanish, male)
- MEDIA: line must be on its own line with no emoji prefix for Telegram to parse it

## Important notes

- Do NOT set `model`/`provider` to OpenRouter models — most don't exist and cause 400 errors
- If the cron fails after a model change, edit `~/.clawksis/cron/jobs.json` directly and set `"last_error": null`
- The `enabled_toolsets` must be empty `[]` (not `["web"]`) so the agent can see and pass through the MEDIA: line
