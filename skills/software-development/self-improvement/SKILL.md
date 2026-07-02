---
name: self-improvement
description: "Autonomous self-improvement of Clawksis via daily cron jobs — scan skills/tools/MCPs for issues, implement fixes, deploy to main, and run clawk update. USE THIS when setting up or maintaining improvement crons, or when the user says 'mejórate solo', 'auto-mejora', 'improve yourself', 'hazte mejor'. ES: mejora automática del agente, auto-mejora diaria, cron de mejora, optimización autónoma."
version: "1.0"
metadata:
  openclaw:
    emoji: "🔄"
    requires:
      bins:
        - python3
        - git
---

# Self-Improvement — autonomous CI/CD for Clawksis

Run a daily cron job that autonomously improves Clawksis: scans skills/tools/MCPs for issues, implements fixes, deploys to main, and runs `clawk update`. The agent becomes self-healing and self-optimizing.

## Workflow (5 phases)

```
Fase 1: Exploración   → pick one skill/tool/MCP to improve
Fase 2: Diagnóstico    → read code, find issues, check tests
Fase 3: Implementación → coding agent makes the fix
Fase 4: Deploy         → git commit → push → clawk update
Fase 5: Reporte        → summary in Spanish to the user
```

### Fase 1 — Exploración

Scan improvement candidates in this priority order:

1. **Skills** in `~/.clawksis/skills/` or repo's `skills/` — missing docs? wrong commands? outdated?
2. **Tools** in `tools/` — look for:
   - `except Exception` or `except:` without logging
   - `# TODO`, `# FIXME`, `# HACK` comments
   - Hardcoded values that should be configurable
   - Poor error messages (`except: pass`, `return None` silently)
   - Functions >100 lines
   - Missing input validation
   - Schema descriptions too vague to be useful
3. **MCPs** in `plugins/` or `optional-mcps/` — stale install docs? missing capabilities?
4. **Tests** in `tests/` — missing coverage, empty test files, commented-out tests

**Pick ONE candidate per run.** Quality over quantity.

### Fase 2 — Diagnóstico

Before editing:

1. Read the full file with `read_file()`
2. Check its tests: `ls tests/**/test_*<name>*`
3. Check the git log: `git log --oneline -- <file>` — recent changes signal active code
4. Identify the 1-2 specific improvements, not a refactor

**What constitutes a good improvement:**
- ✅ Better error handling (log the error, return a useful message)
- ✅ Better docstrings / schema descriptions (more specific, with examples)
- ✅ Catching a missing edge case (empty input, None, network timeout)
- ✅ Removing a hardcoded value in favor of a config or constant
- ✅ Minor performance fix (unnecessary loop, redundant call)
- ✅ Extra test coverage for the above

**What is NOT:**
- ❌ Full rewrites or architectural changes
- ❌ Adding new features beyond what the tool does
- ❌ Removing functionality
- ❌ Chasing style (ruff, black, prettier) — unless the style causes actual bugs

### Fase 3 — Implementación

You have THREE implementation paths, in preference order:

| Path | When | Caveat |
|---|---|---|
| **`delegate_task()`** (subagent) | **Preferred.** Spawns a coding subagent with a full terminal + file toolset. Isolated context, no risk of corrupting parent state. | Best for 1-3 files with clear instructions. Subagent's summary is self-reported — verify by re-reading changed files and running tests yourself. |
| **`patch()`** (manual find-replace) | Small focused changes (1-5 lines, clear old→new strings). Most reliable, no agent overhead. | Only for changes where the old string is unique and unambiguous. |
| Coding agents (`opencode_run`, `claude_code`, `codex_exec`) | Complex multi-file refactors or logic changes. | `opencode` defaults to a **tiny local model** (qwen2.5-coder:1.5b) if no provider configured. `claude` needs login. `codex` needs OpenAI key. All three require `yolo=False` for safe mode. |

**When using `delegate_task()`:** always follow up with your own `read_file()` verification of the changed files and a fresh `pytest -v` run before moving to Fase 4. Subagents self-report success but can make mistakes.

**Always run tests after editing:**
```bash
cd /usr/local/lib/clawksis-agent && uv run pytest tests/tools/test_<name>.py -v
```

If tests fail, fix until green. If the fix is too complex, revert with `git checkout -- <file>`.

### Fase 4 — Deploy

```bash
cd /usr/local/lib/clawksis-agent
git add -A
git commit -m "auto-mejora: <descripción breve del cambio>"
git push origin main
clawk update
```

**⚠️ Pitfalls:**

- **Push rejected (remote ahead):** If `git push` fails with "Updates were rejected because the remote contains work", the remote has new commits. Fix: `git pull --rebase origin main` then push again. `--rebase` keeps the commit history linear and avoids a merge commit polluting the log.
- **`clawk update` says "Already up to date!":** This is normal when the repo branch is already at the latest commit (e.g. you just pushed). The command checks out the current HEAD and installs it — if HEAD doesn't change, the message is just cosmetic. Verify with `git log --oneline -1` to confirm your commit is HEAD.
- **Clawksis profile matters:** `clawk update` updates the active profile's codebase. If running as a cron, ensure `--profile default` or the correct profile is active.

### Fase 5 — Reporte

Deliver to the user in Spanish:

```
✅ Mejora completada

📝 Archivo: tools/<name>.py
🩹 Cambio: descripción del fix
🧪 Tests: N passed, 0 failed
🔗 Commit: a1b2c3d — "auto-mejora: ..."
🔄 Deploy: clawk update exitoso
```

## Setting up the cron

```json
{
  "action": "create",
  "name": "Auto-mejora: skills & tools",
  "schedule": "0 0 * * *",  // medianoche
  "prompt": "[full prompt with phases 1-5]",
  "enabled_toolsets": ["terminal", "file", "search", "web", "delegation", "coding"],
  "use_soul": true,
  "use_user_md": true,
  "use_memory": false
}
```

### Safety rules (must be in the cron prompt)

1. NEVER modify `~/.clawksis/.env`, `config.yaml`, or any credentials
2. NEVER delete files — only add or modify
3. Always read the file fully before editing
4. Always run tests before commit
5. Maintain backward compatibility
6. If something fails: `git checkout -- <file>` and report
7. **For risky or large changes (≥50 lines):** push to the `Clawksis-VPS_1` branch instead of main. The user reviews before merging. Small, safe fixes (error messages, docstrings, tests) go directly to main.
8. **Never hardcode credentials or API keys** in code — they belong in `~/.clawksis/.env` or the credential pool.

## Finding improvement opportunities

| Signal | What to do |
|---|---|
| `except Exception:` with `str(exc)` in response | Replace with error classifier: detect browser/auth/rate-limit/parse/generic errors and return **user-safe** hints (no internal paths, no raw exception dumps) |
| `# TODO` / `# FIXME` | Address it if the fix is small and safe |
| `return None` silently on error | Log the error before returning |
| Function > 100 lines | Extract a helper with a clear name |
| No docstring | Add one describing args, returns, and errors |
| Vague parameter description | Be specific: `"The page URL. Required."` vs `"URL"` |
| Empty/failing test file | Add a basic test or fix the existing one |
| `time.sleep(N)` without comment | Add a comment explaining why the sleep is needed |

## Real session examples

See `references/cron-setup-example.md` for the complete cron setup from the original session.
See `references/real-session-parallel-fix.md` for the session where the cron autonomously
produced the same fix as the interactive agent — proving the system works.
