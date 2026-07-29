# TTS Voice Configuration for Spanish Briefings

## ⚠️ Edge TTS voice was tried and rejected

**User feedback:** "[voz Gonzalo] no se entiende bien, puedes usar una voz de eleven labs?"

Edge TTS voices (even `es-CO-GonzaloNeural`) sound robotic/unclear in Spanish. The user explicitly requested ElevenLabs instead.

## Current recommendation: ElevenLabs

| Setting | Value |
|---------|-------|
| Provider | `elevenlabs` |
| Voice ID (Domi) | `AZnzlk1XvdvUeBnXmlld` — best Spanish voice if account has credits |
| Voice ID (Rachel) | `21m00Tcm4TlvDq8ikWAM` — multilingual fallback |
| Model | `eleven_multilingual_v2` |

### Setup

```bash
clawk config set tts.provider elevenlabs
clawk config set tts.elevenlabs.voice_id AZnzlk1XvdvUeBnXmlld
```

Also set `ELEVENLABS_API_KEY` in `.env` (or embed via base64 in the script — see `references/elevenlabs-integration.md`).

### ⚠️ Known issue: 402 Payment Required

If the ElevenLabs account has no credits, the API returns HTTP 402. Fix: user adds credits at elevenlabs.io > Billing. The free tier provides 10,000 chars/month.

## Edge TTS (fallback, only if ElevenLabs unavailable)

Keep Edge as a fallback in the script. Spanish voices available:

| Voice | Dialect | Gender |
|-------|---------|--------|
| `es-CO-GonzaloNeural` | Colombian 🇨🇴 | Male |
| `es-CO-SalomeNeural` | Colombian 🇨🇴 | Female |
| `es-MX-JorgeNeural` | Mexican 🇲🇽 | Male |
| `es-MX-DaliaNeural` | Mexican 🇲🇽 | Female |
| `es-ES-AlvaroNeural` | Spanish 🇪🇸 | Male |
| `es-ES-ElviraNeural` | Spanish 🇪🇸 | Female |

## Config management

```bash
# Edge (fallback)
clawk config set tts.edge.voice es-CO-GonzaloNeural

# ElevenLabs (preferred)
clawk config set tts.provider elevenlabs
clawk config set tts.elevenlabs.voice_id AZnzlk1XvdvUeBnXmlld
```

- Config file: `~/.clawksis/config.yaml` under `tts.*`
- API key: `ELEVENLABS_API_KEY` in `.env` or base64-embedded in script