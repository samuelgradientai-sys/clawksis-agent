---
name: model-fallback
description: "USE THIS when the model runs low on credits/billing, returns a billing/quota error (HTTP 402 / insufficient_quota / 'out of credit'), or the user says 'me quedan pocos créditos', 'cambiá de modelo', 'usá otra API key', 'switch model', 'billing error', 'out of tokens'. It is a deterministic SCRIPT (works even when the model is out of tokens) that audits your providers / API keys / fallback chain and configures automatic failover to another key or model."
argument-hint: 'model-fallback | model-fallback --apply-chain'
allowed-tools: Bash, Read
author: Clawksis (Gradient AI)
license: MIT
user-invocable: true
metadata:
  clawksis:
    emoji: "🔁"
  openclaw:
    emoji: "🔁"
    requires:
      bins:
        - python3
---

# model-fallback — no te quedes sin modelo por billing

El runtime de Clawksis **ya** sabe failover-ear solo (sin LLM): el *credential
pool* rota entre varias API keys del MISMO provider cuando una da 402/429
(billing/rate-limit), y si configurás una **cadena `fallback_providers`** también
cae a OTRO provider/modelo. El problema es que casi nadie lo deja configurado.
Esta skill es un **script determinístico** (anda aunque te hayas quedado sin
tokens — por eso es script, no depende del modelo) que:

1. **Audita**: qué modelo estás usando, qué API keys tenés (por provider, leídas
   de `~/.clawksis/.env`), el estado del pool (activa/agotada/en cooldown) y si
   hay cadena de fallback configurada.
2. **Configura el auto-failover**: escribe `fallback_providers` en
   `~/.clawksis/config.yaml` a partir de las keys que tengas, así el runtime
   cambia solo de provider/modelo cuando el principal tira billing/error.

## Cómo ejecutarla

`SKILL_DIR` = la carpeta de ESTE SKILL.md. El script está en
`SKILL_DIR/scripts/failover.py`.

1. Auditar (solo lectura):

   ```bash
   python3 "$SKILL_DIR/scripts/failover.py"
   ```

   Presentá el resultado en el idioma del usuario, breve: modelo actual, keys
   detectadas por provider, estado del pool, cadena de fallback, y el veredicto
   (✅ auto-failover listo / ⚠️ tenés keys de varios providers pero SIN cadena).

2. Si el veredicto es ⚠️ y el usuario quiere protegerse (o ya hubo un error de
   billing), **ofrecé configurar la cadena** y, con su OK:

   ```bash
   python3 "$SKILL_DIR/scripts/failover.py" --apply-chain
   ```

   Escribe `fallback_providers` en `config.yaml` (con backup). Avisá que hay que
   **reiniciar el gateway/agente** para que tome efecto, y que los modelos de la
   cadena son **editables** (revisá los nombres). `--switch provider[:model]`
   cambia el modelo principal ya, si lo piden.

## Cuándo dispararla

- Error de billing/quota del modelo (402, `insufficient_quota`, "out of credit",
  "out of extra usage").
- El usuario dice que le quedan pocos créditos o pide cambiar de modelo / usar
  otra API key.
- Proactivo: si auditás y NO hay cadena pero sí varias keys, sugerí `--apply-chain`.

> Nota: para resiliencia real sin intervención, conviene tener **2+ API keys del
> mismo provider** (el pool las rota solo ante 402/429) **y/o** la cadena
> `fallback_providers` configurada (cae a otro provider). Esta skill deja ambas
> cosas visibles y configurables. Se puede correr también desde un cron.
