# ElevenLabs TTS — Known Limitations

## Account Tiers vs API Access

| Plan | API TTS Access | Notes |
|------|---------------|-------|
| **Free** | ❌ **No** | Can authenticate (HTTP 200 on `/v1/voices`) but TTS returns `paid_plan_required` — library/premade voices blocked |
| **Starter** ($5/mo) | ✅ Sí | Unlocks API TTS with library voices |
| **Creator** ($22/mo) | ✅ Sí | Higher character limits |

The Free plan *does* give 10,000 monthly characters but only usable via the **web interface** (elevenlabs.io), not the API.

## Error Codes

| Code | Body | Meaning |
|------|------|---------|
| 401 | `invalid_api_key` | Wrong or malformed key |
| 402 | `payment_required` | Account has no credits at all |
| 402 | `paid_plan_required` | Free plan — API TTS blocked even with credits |
| 404 | `voice_not_found` | Voice ID doesn't exist on this account (deprecated or workspace-specific) |

## Default Voice IDs

These are the Clawksis defaults and known ElevenLabs voices:

- `g5CIjZEefAph4nQFvUzN` — Mateo (default in Clawksis, often deprecated/returns 404)
- `21m00Tcm4TlvDq8ikWAM` — Rachel (universal, English, useful for testing)
- `AZnzlk1XvdvUeBnXmlld` — Domi (Spanish-capable)

## Key Resolution

The `text_to_speech` tool uses `get_env_value("ELEVENLABS_API_KEY")` which:
1. Checks `os.environ` first
2. Falls back to `load_env()` (reads `.env` with mtime-based cache)
3. Ignores `config.yaml` → `tts.elevenlabs.api_key`

Setting `clawk config set tts.elevenlabs.api_key sk-...` stores the key in config.yaml but the TTS tool DOES NOT read it. The key MUST be in `~/.clawksis/.env` as `ELEVENLABS_API_KEY=sk-...`.
