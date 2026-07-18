---
name: self-improvement
description: "Autonomous self-improvement of Clawksis via daily cron jobs — scan skills/tools/MCPs for issues, implement fixes, deploy to main, and run clawk update. USE THIS when setting up or maintaining improvement crons, or when the user says 'mejórate solo', 'auto-mejora', 'improve yourself', 'hazte mejor'. ES: mejora automática del agente, auto-mejora diaria, cron de mejora, optimización autónoma."
version: "1.5"
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
4. **Profile-repo drift check** — for any skill loaded this session (via `skill_view()` or user invocation), compare its profile copy at `~/.clawksis/skills/<category>/<name>/SKILL.md` against the repo copy at `skills/<category>/<name>/SKILL.md`. If the profile is ahead (newer content, more sections, real-world pitfalls), syncing the docs IS a valid standalone improvement — do it now instead of searching for other candidates. Use `diff` to confirm.
5. Identify the 1-2 specific improvements, not a refactor

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

Choose the right tool for the job. Smaller is faster; save subagents for when you actually need them.

| Path | Best for | Caveat |
|---|---|---|
| **`patch()`** (find-replace) | **Single small edits** — adding a log line, fixing an error message, updating a docstring. Fastest — call it directly and verify. | old_string must be unique/unambiguous in the file. For multi-line content, verify the patched region immediately — fuzzy matching can leave duplicate lines. |
| **`write_file()`** (overwrite) | **Creating or replacing files** — new test files, new reference docs, **SKILL.md updates** (since skill docs are replaced wholesale). | Overwrites entirely — use only when you know the full content. Perfect for documentation updates where you're supplying the complete new version. |
| **`patch()` + `write_file()` combo** | When you need both code edits and new files (e.g. modify `scrapegraph_common.py` + add a test to `test_scrapegraph_tool.py`). No subagent overhead. | Works for 2-3 files with small, well-understood changes. |
| **`delegate_task()`** (subagent) | **Multi-file logic changes** (refactors, new functionality across 3+ files). Isolated context, no risk of corrupting parent state. | Subagent's summary is self-reported — verify changed files and run tests yourself. |
| Coding agents (`opencode_run`, `claude_code`, `codex_exec`) | Complex multi-file refactors or logic changes that need interactive iteration. | `opencode` defaults to a **tiny local model** (qwen2.5-coder:1.5b) if no provider configured. `claude` needs login. `codex` needs OpenAI key. All three require `yolo=False` for safe mode. |

**Key insight:** most self-improvement tasks (adding error handling, logging, tests, or updating documentation) are 1-2 file changes that fit `patch()` + `write_file()` in a single turn. Reserve subagents for when you honestly can't express the change as a find-replace or a full file overwrite.

**Checkpoint — after editing, verify the skill is self-consistent:**

If you modified a skill's implementation files (e.g. `scrapegraph_common.py`), check whether its `SKILL.md` in **both** locations needs updating:

1. `~/.clawksis/skills/<category>/<name>/SKILL.md` — the profile's copy (updated by `skill_manage`)
2. `skills/<category>/<name>/SKILL.md` in the repo — the repo's copy, if it exists

These two copies can diverge: the profile copy gets `skill_manage` updates, but the repo copy stays stale until manually synced. A future `clawk update` or fresh clone would overwrite the profile with the stale repo copy. **Always check and sync both.** The workflow: update via `skill_manage` (hits the profile), then read the profile's updated SKILL.md and write it to the repo path, then commit the repo change.

Keeping code and docs in sync is the whole point.

**Checkpoint — loaded skills:**
If any skill was loaded this session (via `skill_view()` or user invocation), compare its installed version against what was loaded. If the loaded context is newer or more detailed, update the installed `SKILL.md`. Skills that were consulted should leave the session at least as accurate as they entered.

**Always run tests after editing:**
```bash
cd /usr/local/lib/clawksis-agent && uv run pytest tests/tools/test_<name>.py -v
```

If tests fail, fix until green. If the fix is too complex, revert with `git checkout -- <file>`.

If you added logging or a new code path, also add a test for it. Proven pattern:
```python
def test_new_warning_is_logged(caplog):
    """Verify the warning fires when expected."""
    import logging
    caplog.set_level(logging.WARNING)
    with patch("module.path.dependency", side_effect=SomeError("...")):
        with patch.dict("os.environ", {}, clear=True):  # clear env vars to hit fallback
            result = your_function()
    assert "expected warning text" in caplog.text
    assert result["some_key"] == expected_value
```
Use `caplog` (built-in pytest fixture) + `patch.dict("os.environ", {}, clear=True)` to test logging when env-dependent conditions trigger warnings.

### Fase 4 — Deploy

```bash
cd /usr/local/lib/clawksis-agent
git add -A
git commit -m "auto-mejora: <descripción breve del cambio>"
git push origin main
# clawk update is NOT run here — it's hardline-blocked from the agent
# (restarts the gateway = self-termination). A push to main is sufficient;
# changes are picked up on the next gateway restart (scheduled or manual).
```

**⚠️ Pitfalls:**

- **Push rejected (remote ahead):** If `git push` fails with "Updates were rejected because the remote contains work", the remote has new commits. Fix: `git pull --rebase origin main` then push again. `--rebase` keeps the commit history linear and avoids a merge commit polluting the log.
- **`clawk update` is hardline-blocked from the agent:** The agent CANNOT run `clawk update` because it restarts the gateway (self-termination). The command is on the unconditional blocklist. Instead, just `git push origin main` — the changes are picked up on the next gateway restart (scheduled or manual). A push to main is sufficient deployment.
- **`clawk update` says "Already up to date!":** This is normal when the repo branch is already at the latest commit (e.g. you just pushed). The command checks out the current HEAD and installs it — if HEAD doesn't change, the message is just cosmetic. Verify with `git log --oneline -1` to confirm your commit is HEAD.
- **Clawksis profile matters:** `clawk update` updates the active profile's codebase. If running as a cron, ensure `--profile default` or the correct profile is active.
- **`patch()` with multi-line content can leave duplicates:** When the old_string spans multiple lines (especially around comments with inconsistent line wrapping), `patch()`'s fuzzy matcher may match partially and insert your new_string while leaving some of the old lines behind. You end up with a duplicate. **Always verify the patched region immediately after the call**, and be ready to apply a second cleanup `patch()` to remove any leftover lines. Read the affected lines back with `read_file()` before moving on — don't rely on the success message alone.
- **Profile skill vs repo skill drift:** When you modify a skill's SKILL.md via `skill_manage`, it updates `~/.clawksis/skills/<category>/<name>/SKILL.md` (the profile copy). But the repo may also have a copy at `skills/<category>/<name>/SKILL.md`. If the repo copy is stale, `clawk update` on another machine or a fresh clone would restore the stale version. **Check both paths after updating a skill and sync by writing the profile's updated content to the repo path, then committing.**

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
   ```bash
   git fetch origin Clawksis-VPS_1
   git checkout -b Clawksis-VPS_1 origin/Clawksis-VPS_1
   # ... make changes, commit ...
   git push origin Clawksis-VPS_1
   ```
   See the `github-pr-workflow` skill for more on branch conventions.
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
| Empty/failing test file | Add a basic test or fix the existing one. See `references/tool-test-patterns.md` for proven patterns for async tool handlers. |
| `time.sleep(N)` without comment | Add a comment explaining why the sleep is needed |
| **Skill docs vs code mismatch** | Compare a loaded skill's parameter table / examples / error table against the actual tool code. A parameter documented in `SKILL.md` but missing from the tool's schema or handler is a concrete, self-contained fix — implement it. See the v1.2→v1.3 `scrapegraphai` update for a real example. |
| **Profile skill vs repo skill drift** | Loaded skill's profile copy is ahead of the repo copy (run `diff ~/.clawksis/skills/<cat>/<name>/SKILL.md skills/<cat>/<name>/SKILL.md`). Sync profile → repo and commit. This is a low-risk, high-value improvement: prevents stale docs from being restored on next `clawk update`. |

## Real session examples

See `references/cron-setup-example.md` for the complete cron setup from the original session.
See `references/real-session-parallel-fix.md` for the session where the cron autonomously
produced the same fix as the interactive agent — proving the system works.
See `references/caplog-env-test-pattern.md` for the proven test pattern for logging with
env-dependent conditions, extracted from this session's work.
See `references/async-timeout-pattern.md` for the `asyncio.wait_for` + `asyncio.to_thread`
pattern used to add configurable timeouts to blocking extraction calls (real example: the
v1.3 `scrapegraph` tool update).
See `references/subprocess-error-handling.md` for the `subprocess.SubprocessError` / `OSError`
handling pattern added to `scrape_tool._run_one()` (real example: the v1.5 auto-mejora update).
See `references/tool-parameter-pattern.md` for the three-layer pattern (schema → handler →
executor) used to add the `timeout` parameter to the `scrape` tool (real example: commit
`75178b2a`).
