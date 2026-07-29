# Cron Job Patterns — Gradient Cloud Ecosystem

## Script + Agent Pattern (recommended for quality crons)

Cuando un modelo no soporta tool calling o no llama herramientas (`tool_turns=0`),
usar este patrón:

```
Cron:
  script: fetch-data.py     # Recolecta datos (gratis, sin LLM)
  prompt: "Los datos están arriba. Formatéalos..."
  model: deepseek-v4-flash   # Solo formatea, no necesita tools
  no_agent: false            # El agente procesa el output del script
  toolsets: ["web"]          # Opcional, por si necesita buscar
```

- El script se ejecuta PRIMERO, su stdout se inyecta en el prompt del agente
- El agente SOLO formatea datos existentes — no necesita web_search
- Costo: ~$0.0015 por ejecución (solo tokens de salida)

## No-Agent Pattern (for zero-cost crons)

```
Cron:
  script: report.sh          # Genera el mensaje completo
  no_agent: true             # El stdout del script ES el mensaje
  prompt: ""                 # Se ignora
```

- Sin LLM, sin costo
- Output directo del script a Telegram
- Bueno para: reportes de billing, health checks, monitoreo

## Model Limitations Discovered

| Model | Provider | Tool Calling | Notas |
|-------|----------|-------------|-------|
| deepseek-v4-flash | deepseek | ❌ tool_turns=0 | No llama herramientas. Usar solo para formatear |
| deepseek-v4-flash | openrouter | ✅ tool_turns=1+ | Funciona si hay créditos en OpenRouter |
| x-ai/grok-4.3 | openrouter | ✅ | Funciona pero OpenRouter sin créditos (402 error) |

## Cost Estimates

| Config | Por ejecución | Por mes (30 días) |
|--------|--------------|-------------------|
| Script + Agent (deepseek-v4-flash) | ~$0.0015 | ~$0.045 |
| No-Agent script | $0 | $0 |
| Agent con web_search | ~$0.003-0.005 | ~$0.09-0.15 |

## Skills loading in crons

- Cargar skills pesadas como `last30days` (~36k tokens) en un cron duplica el
  costo de contexto. Evaluar si el beneficio supera el costo.
- Preferir el patrón Script+Agent sobre skills pesadas para tareas de recolección.
