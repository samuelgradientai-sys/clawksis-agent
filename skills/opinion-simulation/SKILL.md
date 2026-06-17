---
name: opinion-simulation
description: "USE THIS to forecast PUBLIC REACTION / opinion / sentiment / social dynamics around a topic, message, product, post or document — a synthetic focus group / audience simulation. It drives the MiroFish multi-agent simulation tool. Trigger on ES+EN: 'cómo va a reaccionar la gente a X', 'qué va a opinar/pensar el público', 'simular reacción/opinión/sentimiento', 'focus group sintético', 'probar un mensaje/anuncio antes de publicar', 'simular audiencia', 'forecast public reaction', 'simulate audience/opinion', 'social/opinion simulation', 'sentiment forecast', 'mirofish'."
argument-hint: 'opinion-simulation forecast reaction to <topic / message / product>'
allowed-tools: Bash, Read
author: Clawksis (Gradient AI)
license: MIT
user-invocable: true
metadata:
  clawksis:
    emoji: "🐟"
  openclaw:
    emoji: "🐟"
---

# opinion-simulation — pronosticá la reacción del público (vía MiroFish)

Esto **NO** consulta gente real: corre una **simulación multi-agente** (MiroFish)
que genera cientos de personas-agente a partir de tu material y simula cómo
reaccionarían en redes (Twitter/Reddit), devolviendo un **reporte de análisis**
en Markdown. Es un *focus group sintético* para anticipar reacción / sentimiento
/ dinámica social ante un tema, mensaje, producto, post o documento — ideal
**antes de publicar** algo.

## Paso 0 — disponibilidad y oferta proactiva

La herramienta `mirofish` SOLO está disponible si hay un **server MiroFish
corriendo** (Docker, REST en `:5001`) y habilitado en `clawk tools` → MiroFish.

- **Si la tool `mirofish` ESTÁ disponible** → seguí directo al Flujo y corré la
  simulación.
- **Si NO está disponible** (no aparece la tool, o responde *"No MiroFish server
  responding at …"*) → **NO te limites a decir "no puedo".** Ofrecé la capacidad
  con entusiasmo y explicá cómo activarla. Algo así:

  > "Puedo correr una **simulación de opinión multi-agente** (MiroFish): genera
  > cientos de personas-agente a partir de tu material y pronostica cómo
  > reaccionaría el público a esto, con un reporte. Para activarla necesito un
  > par de cosas (una sola vez):"

  Y listá, con los enlaces:

  1. **Levantar el server MiroFish** (Docker) y apuntar `MIROFISH_BASE_URL` a él
     (habilitarlo en `clawk tools` → MiroFish). Ofrecé guiar el `docker compose`.
  2. **Dos llaves** (van en el `.env` del server MiroFish, no en Clawksis):
     - **`ZEP_API_KEY`** — gratis en **https://app.getzep.com/** (Zep Cloud; el
       free tier mensual alcanza para uso simple). Es el grafo de memoria.
     - **`LLM_API_KEY`** (+ `LLM_BASE_URL` + `LLM_MODEL_NAME`) — cualquier
       proveedor **compatible con OpenAI**: OpenAI (platform.openai.com),
       DeepSeek (platform.deepseek.com), Alibaba DashScope/Qwen, u OpenRouter.
       **Podés reusar una API key de LLM que ya tengas.** (El default de MiroFish
       es DashScope/`qwen-plus`; sirve cualquiera cambiando `LLM_BASE_URL` y
       `LLM_MODEL_NAME`.)

  Cerrá ofreciéndote a guiar el setup paso a paso.

- No intentes "simular a mano" sin el server: este skill es el envoltorio del
  tool `mirofish`.

## Flujo

1. **Definí el requerimiento** (`simulation_requirement`): en lenguaje natural,
   QUÉ querés pronosticar — ej. *"reacción del público latino al lanzamiento de
   este producto"*, *"cómo recibirían este tweet de la marca"*. Cuanto más
   concreto, mejor.
2. **Material fuente** (opcional pero recomendado): pasá **rutas absolutas** de
   documentos (PDF/MD/TXT) en `documents` para sembrar las personas y el
   contexto.
3. **Corré la simulación** — es **larga (minutos)** y async. Llamá la tool:
   `mirofish` con `action="simulate"`, `simulation_requirement`, `documents`,
   y opcional `platform` (`twitter` / `reddit` / `parallel`) y `max_rounds`
   (default 20 — bajalo para ahorrar: es caro en LLM). Avisá al usuario que
   tarda y que vas a esperar.
4. **Si se agota el tiempo** (timeout): la tool devuelve un `simulation_id` y el
   estado. Retomá con `action="status"` (progreso) y `action="report"`
   (genera/trae el reporte) usando ese `simulation_id`. **No relances**
   `simulate`.
5. **Entregá el reporte**: presentá el Markdown al usuario en su idioma,
   resumiendo lo clave (sentimiento general, temas que emergen, riesgos,
   reacciones probables). Ofrecé mandarlo a Telegram/inbox si corresponde.
6. **Interview (opcional)**: para profundizar, `action="interview"` con el
   `simulation_id` + un `prompt` le hace la MISMA pregunta a todas las personas
   simuladas (ej. *"¿comprarías esto? ¿por qué?"*).

## Encuadre honesto

Son personas **sintéticas**, no una encuesta real: presentá los resultados como
un **pronóstico / escenario** (útil para detectar riesgos y reacciones probables
antes de salir a producción), nunca como verdad de mercado.
