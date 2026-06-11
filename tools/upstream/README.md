# Sync con upstream (NousResearch/hermes-agent)

Clawksis es un fork rebrandeado de Hermes Agent que **no comparte historia de
git** con upstream (la historia se recreó en el squash inicial). Además el
árbol difiere por tres capas de ruido: el rebrand `hermes → clawksis/clawk`,
line endings (el fork tiene CRLF, upstream LF) y espaciado inconsistente
heredado del squash. Conclusión: `git merge` / `cherry-pick` / `git apply` no
sirven contra upstream.

Este tooling sincroniza **archivo por archivo**: rebrandea la versión de
upstream con el mismo mapping del rebrand original y compara contenido
*normalizado* (sin CRLF, sin líneas en blanco, sin espacios finales), que es
inmune a todo ese ruido.

## Flujo

```bash
# 1. Ver qué hay para traer (no escribe nada)
python tools/upstream/sync.py                      # vs último release de upstream
python tools/upstream/sync.py --target v2026.6.5   # vs un tag específico

# 2. Aplicar en un branch
git switch -c sync/upstream-v2026.6.5
python tools/upstream/sync.py --target v2026.6.5 --apply

# 3. Resolver divergentes (si hay), revisar, commitear
git status && git diff --stat
```

## Qué hace con cada archivo que upstream cambió

| Estado en el fork                                  | Acción |
|----------------------------------------------------|--------|
| Igual al baseline upstream (módulo rebrand/espaciado) | Lo reemplaza por la versión nueva rebrandeada |
| Ya igual al target                                 | Nada |
| Con cambios propios del fork                       | Lo lista como **divergente** y deja material en `pending/` |
| No existe y upstream lo agrega                     | Lo crea rebrandeado |

Los reemplazos limpios además normalizan de paso el espaciado doble del
squash en ese archivo (la versión nueva viene con el formato sano de
upstream).

## Divergentes (`pending/`)

Con `--apply`, cada archivo divergente deja en `tools/upstream/pending/`:

- `<archivo>.patch` — el diff de upstream **ya rebrandeado** (base → target)
- `<archivo>.theirs` — la versión target completa rebrandeada
- `REPORT.md` — la lista con el motivo de cada uno

El merge se hace a mano (o con Claude): aplicar la intención del `.patch`
sobre el archivo del fork, respetando los cambios propios. `pending/` está en
`.gitignore` — no se commitea.

## Ojo al revisar

- **Nous Portal**: upstream puede re-introducir acoplamiento a Nous. Si un
  archivo trae eso, agregalo a `skip_paths` en `sync_state.json` (acepta
  globs, ej. `"nous_portal/*"`) y queda excluido de futuros syncs.
- **Workflows de upstream**: cambios bajo `.github/workflows/` revisarlos con
  cuidado antes de mergear.
- Los PRs del fork van con la cuenta gh `samuelgradientai-sys`.

## Watcher automático

`.github/workflows/upstream-watch.yml` corre diario: si upstream publica un
release más nuevo que `last_synced_tag`, abre un issue en este repo con las
release notes y los comandos de sync. No aplica nada solo.

## Estado

`sync_state.json` registra hasta qué commit/tag de upstream estamos
sincronizados. Lo actualiza `sync.py --apply`; no editarlo a mano salvo para
`skip_paths`.
