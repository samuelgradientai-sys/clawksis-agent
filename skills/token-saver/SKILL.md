---
name: token-saver
description: "USE THIS to optimize / reduce token usage. Audits the installed skills, finds the ones that are NOT being used but still cost context tokens every turn, estimates how much each costs, and recommends which to DISABLE (and can disable them). Trigger on ES+EN: 'optimizar tokens', 'reducir tokens', 'ahorrar tokens', 'gastar menos tokens', 'estoy gastando muchos tokens', 'qué skills desactivar', 'skills que no uso', 'limpiar/aligerar el contexto', 'optimize tokens', 'reduce token usage', 'token audit', 'unused skills', 'context bloat'."
argument-hint: 'token-saver | token-saver --days 45'
allowed-tools: Bash, Read
author: Clawksis (Gradient AI)
license: MIT
user-invocable: true
metadata:
  clawksis:
    emoji: "🪙"
  openclaw:
    emoji: "🪙"
    requires:
      bins:
        - python3
---

# token-saver — recortá los tokens que gastan las skills que no usás

Cada skill instalada agrega su descripción al catálogo que el agente ve en CADA
turno (y su contenido completo cuando se invoca). Las skills que no usás siguen
costando tokens. Esta skill audita el uso real y recomienda cuáles **desactivar**
para liberar ese contexto, sin borrar nada (desactivar es reversible).

## Cómo ejecutarla

1. `SKILL_DIR` = la carpeta donde está ESTE SKILL.md (tu harness te dice la ruta
   al leerlo). El script vive en `SKILL_DIR/scripts/audit.py`.
2. Corré la auditoría (solo lectura):

   ```bash
   python3 "$SKILL_DIR/scripts/audit.py" --days 30
   ```

   Resuelve solo el home de Clawksis (`CLAWK_HOME` o `~/.clawksis`), lee
   `skills/.usage.json` y `config.yaml`. No escribe nada.

3. **Presentá el reporte en el idioma del usuario**, natural y breve: cuántas
   skills hay, el costo estimado en tokens, y la lista de candidatas a desactivar
   (sin uso o frías) con su ahorro estimado. Las marcadas `(¿nueva?)` son las que
   nunca se usaron — puede que sean recién instaladas; avisá eso y no las
   desactives sin confirmar.

## Desactivar (siempre con confirmación del usuario)

Si el usuario quiere desactivar las recomendadas, corré:

```bash
python3 "$SKILL_DIR/scripts/audit.py" --apply skill1,skill2,skill3
```

Esto las agrega a `skills.disabled` en `~/.clawksis/config.yaml` (hace backup
antes). Avisá que hay que **reiniciar el gateway/agente** para que tome efecto, y
que **reactivar** es solo sacarlas de esa lista (o `config.yaml`).

Reglas:
- NUNCA recomiendes ni desactives skills protegidas (`plan`) ni a `token-saver`.
- Confirmá con el usuario antes de `--apply`. Mostrá primero el reporte.
- Si el usuario tiene un `config.yaml` muy comentado y no quiere que se reformatee,
  ofrecé el snippet YAML del reporte para que lo pegue a mano en vez de `--apply`.

## Opciones

- `--days N` — umbral de inactividad para marcar una skill como "fría" (def. 30).
- `--json` — salida estructurada (para procesar vos mismo).
- `--apply a,b,c` — desactiva esas skills (con backup del config).
