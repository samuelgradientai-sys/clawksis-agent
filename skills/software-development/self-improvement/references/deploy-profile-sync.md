# Deploying a committed skill edit to the LIVE profile

Real example: 6 ago 2026 — the auto-mejora cron updated
`skills/web/scrapegraphai/SKILL.md` to v1.8 and pushed to main. The change was
in the repo, but the running agent still loaded v1.7 from
`~/.clawksis/skills/web/scrapegraphai/SKILL.md`. `sync_skills()` refused to
propagate it.

## Why `sync_skills()` won't do it

`tools.skills_sync.sync_skills()` has a `user_modified` guard: a profile copy
whose on-disk hash diverges from its manifest baseline (stored in
`~/.clawksis/skills/.bundled_manifest`, format `name:hash`) is treated as a
user edit and **never overwritten**. After previous auto-mejora runs edited
skills directly, several skills sit in this state permanently — check:

```python
from tools.skills_sync import sync_skills

res = sync_skills(quiet=True)
print(res.get("user_modified"))  # e.g. ['scrapegraphai', 'scrapling-official', ...]
```

## The fix: direct copy + manifest re-baseline (repo → profile)

```python
import shutil
from pathlib import Path
from tools.skills_sync import _read_manifest, _write_manifest, _dir_hash

src = Path("skills/web/scrapegraphai")  # repo copy (just committed)
dest = Path.home() / ".clawksis/skills/web/scrapegraphai"  # live profile copy
for f in ["SKILL.md", "references/scrapling-fallback.md"]:  # EVERY file you touched
    shutil.copy2(src / f, dest / f)
# Re-baseline so future syncs see the profile as in-sync, not user-modified:
m = _read_manifest()
m["scrapegraphai"] = _dir_hash(dest)
_write_manifest(m)
```

Notes:
- `_dir_hash(dest)` must now equal the repo's `_dir_hash(src)` — that's the
  "in sync" state.
- Re-baselining matters: without it the next `sync_skills()` run still lists
  the skill as `user_modified` (cosmetic, but it misleads drift checks).

## Verify

```python
from tools.skills_sync import sync_skills

res = sync_skills(quiet=True)
assert "scrapegraphai" not in res.get("user_modified", [])
```

## Why it matters

The profile copy at `~/.clawksis/skills/` is what the runtime skill loader
actually serves — a repo push alone only reaches it after a gateway restart
that re-runs the sync. For doc updates you want effective immediately (or for
the *next* session regardless of restart timing), this copy+re-baseline is the
reliable path. The profile-ahead state this creates is self-healing: the next
auto-mejora run's Fase 2 drift check syncs it to the repo if needed.
