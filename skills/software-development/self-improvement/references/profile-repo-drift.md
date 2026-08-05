# Profile ↔ Repo skill drift — detección y sincronización

Workflow probado en la auto-mejora del 14 y 17 jul 2026. Detecta y corrige skills que están más actualizados en el perfil que en el repositorio.

## Detectar deriva (ampliado)

No solo SKILL.md puede tener deriva — los archivos de referencia, templates y scripts también pueden faltar en el repo.

```bash
# 1. Comparar SKILL.md
diff ~/.clawksis/skills/<category>/<name>/SKILL.md /usr/local/lib/clawksis-agent/skills/<category>/<name>/SKILL.md

# 2. Listar archivos en el perfil que NO están en el repo
#    (referencias, templates, scripts que el perfil tiene pero el repo no)
diff <(cd ~/.clawksis/skills/<category>/<name> && find . -type f | sort) \
     <(cd /usr/local/lib/clawksis-agent/skills/<category>/<name> && find . -type f | sort)

# 3. Verificar referencias: si el repo tiene un SKILL.md que menciona
#    `references/algo.md` pero el archivo no existe en el repo, hay que copiarlo.
#    Lo mismo para entradas en la sección References que faltan por completo.
grep -oP '`references/[^`]+`' /usr/local/lib/clawksis-agent/skills/<category>/<name>/SKILL.md \
  | while read -r ref; do
      file=$(echo "$ref" | tr -d '`')
      [ -f "/usr/local/lib/clawksis-agent/skills/<category>/<name>/$file" ] || echo "FALTA: $file"
    done
```

Si hay diferencias, el perfil suele ser la copia autoritativa (recibe `skill_manage` updates).

## Sincronizar perfil → repo

Tres cosas pueden necesitar sincronización:

### 1. SKILL.md

```bash
cp ~/.clawksis/skills/<category>/<name>/SKILL.md /usr/local/lib/clawksis-agent/skills/<category>/<name>/SKILL.md

# Verificar
diff ~/.clawksis/skills/<category>/<name>/SKILL.md /usr/local/lib/clawksis-agent/skills/<category>/<name>/SKILL.md
```

### 2. Archivos de referencia extra (references/, templates/, scripts/)

El perfil puede tener archivos que el repo no tiene. Hay que copiarlos individualmente
porque `diff` solo marca diferencias en archivos existentes, no archivos ausentes.

```bash
# Para cada archivo del perfil que falta en el repo:
cp ~/.clawksis/skills/<category>/<name>/references/<archivo.md> \
   /usr/local/lib/clawksis-agent/skills/<category>/<name>/references/<archivo.md>
```

### 3. Entradas en SKILL.md que referencian archivos nuevos

Si copiaste un archivo de referencia nuevo, verifica que el SKILL.md del repo
tenga la entrada correspondiente en su sección de referencias. Si no está,
agrégala con `patch()`.

```patch
# Ejemplo: agregar una entrada en la lista de referencias
- `references/<existing-file>.md` — descripción existente
+ `references/<existing-file>.md` — descripción existente
+ `references/<new-file>.md` — descripción del nuevo archivo
- `https://github.com/...` — next existing entry
```

### Commit + push

```bash
cd /usr/local/lib/clawksis-agent
git add skills/<category>/<name>/
git commit -m "auto-mejora: sync <skill-name> (SKILL.md + references) perfil → repo"
git push origin main
```

## Ejemplos reales

### 14 jul 2026 — SKILL.md drift

| Skill | Perfil | Repo | Diferencia |
|---|---|---|---|
| `scrapling-official` | v0.4.9 + pitfalls + guardrails + integration notes | v0.4.9 sin pitfalls | +87 líneas (sección "Pitfalls discovered in real usage", Guardrails, Clawksis integration notes) |
| `scrapegraphai` | v1.5 | v1.4 | Versión desactualizada |

El perfil tenía contenido valioso — pitfalls descubiertos en uso real (uso de `.body` vs `.text`, Reddit bloquea todo, Google captcha, etc.) — que nunca se habían subido al repo.

### 17 jul 2026 — Reference file drift

| Activo | Perfil | Repo | Acción |
|---|---|---|---|
| `references/directory-lead-scraping.md` | ✅ existe | ❌ faltaba | Copiado al repo |
| `references/reddit-archives.md` | ✅ existe | ❌ faltaba | Copiado al repo (ya referenciado en SKILL.md pero archivo ausente) |
| SKILL.md → `directory-lead-scraping.md` | ✅ entrada presente | ❌ entrada faltaba | Agregado con `patch()` |

**Lección:** Un archivo referenciado en SKILL.md (como `reddit-archives.md`) puede ser mencionado
en el repo pero el archivo mismo no existir. La verificación con `find` o el bucle `grep` del
paso 3 de detección atrapa estos casos.

### 28 jul 2026 — Self-improvement meta-drift

| Skill | Perfil | Repo | Diferencia |
|---|---|---|---|
| `self-improvement` | v1.7 con efficiency tip + real session example en drift check | v1.7 sin esas secciones | +2 líneas (phrasing más explícito) + párrafo completo de efficiency tip con ejemplo real (`dcd5a590`) |
| `scrapegraphai` | v1.7 en sync | v1.7 en sync | Sin deriva ✅ |
| `scrapling` | v0.4.9 en sync | v0.4.9 en sync | Sin deriva ✅ |

**Lección (meta-drift):** La skill que te dice cómo detectar deriva (`self-improvement`) puede
ella misma tener deriva. Cuando cargas `self-improvement` al inicio de una sesión de
auto-mejora, verifica su SKILL.md contra el repo de inmediato — si la copia del repo está
desactualizada, el propio proceso se ejecuta con instrucciones incompletas. Este es el caso más
importante de drift porque afecta la calidad de todas las auto-mejoras subsiguientes. El drift
check debe incluir todas las skills cargadas en la sesión, incluida la que gobierna el proceso.

### 2 ago 2026 — Drift cosmético: no todo drift es "perfil adelante"

| Skill | Perfil | Repo | Acción |
|---|---|---|---|
| `scrapling` | comillas simples en ejemplos de código | comillas dobles (pasó por `ruff format`) | ❌ NO sincronizar — diff 100% estilo |
| `self-improvement` | v1.8 | v1.5 | ✅ Sincronizado (SKILL.md + `github-secret-scanning.md` + `profile-repo-drift.md` + `input-validation-hardening.md` nuevo) |

**Diagnóstico (antes de sincronizar cualquier archivo con drift):**
1. **Dirección del diff:** `diff <perfil> <repo> | grep -c '^<'` vs `grep -c '^>'`. Si el repo tiene muchas más líneas `>`, probablemente es formateo, no contenido.
2. **Leer el diff real:** ¿solo comillas/espacios/line-wrapping? → skip. ¿Secciones nuevas, párrafos extra, archivos que faltan en el repo? → sync.
3. **Git log del directorio de la skill:** `git log --oneline -- skills/<cat>/<name>/`. Un commit tipo "ruff format sobre las references" / "sanea formato" (ej. `d7e6d899`) indica que el repo es la copia formateada *intencionalmente* — sincronizar perfil → repo la revertiría.

**Lección:** `diff -rq` solo dice "hay diferencias", no "el perfil está adelante". El sesgo natural es asumir que el perfil (que recibe `skill_manage`) es la copia autoritativa — pero cuando el repo pasó por una pasada de formateo deliberada, la dirección se invierte para los archivos afectados. Flujo correcto: verificar dirección + leer el diff + chequear git log, y sincronizar solo los archivos con contenido real adelante.

## Por qué ocurre

`skill_manage(action='edit'/'patch'/'create'/'write_file')` escribe en `~/.clawksis/skills/<cat>/<name>/` (el perfil). El repo en `/usr/local/lib/clawksis-agent/skills/<cat>/<name>/` no se actualiza automáticamente. Si alguien hace `clawk update` o clona fresh, la copia del repo sobreescribe el perfil — y las mejoras se pierden.

## Prevención

Incluir la verificación de deriva como paso obligatorio en Fase 2 de cualquier auto-mejora que cargue skills. La verificación debe cubrir:
1. SKILL.md — diff directo
2. Archivos de referencia — diff recursivo con `find`
3. Integridad de referencias — el SKILL.md no debe mencionar archivos que no existen

Si la deriva existe Y la copia del perfil es más completa, sincronizar es una mejora válida por sí misma.
