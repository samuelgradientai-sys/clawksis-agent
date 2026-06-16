#!/usr/bin/env python3
"""token-saver: audit installed skills and flag unused ones that bloat context.

Original Clawksis skill (MIT, Gradient AI) — no third-party code. Scans the
skills directory, cross-references per-skill usage (skills/.usage.json), estimates
the token cost each skill adds, and recommends which unused/cold skills to disable
via config.yaml `skills.disabled`. Read-only by default; `--apply` edits the
disabled list (with a timestamped backup of config.yaml).

  audit.py                  human report (default 30-day staleness)
  audit.py --days 45        change the staleness threshold
  audit.py --json           machine-readable output
  audit.py --apply a,b,c    add skills a,b,c to skills.disabled (backs up config)
  audit.py --skills-dir DIR --config FILE   explicit overrides (testing)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Never recommend disabling these: load-bearing built-ins + this auditor itself.
NEVER_DISABLE = {"plan", "token-saver"}


def default_skills_dir() -> Path:
    """Resolve the skills directory.

    Prefers CLAWK_HOME/skills (set by the runtime); otherwise derives it from this
    script's own location — it lives at ``<home>/skills/token-saver/scripts/audit.py``,
    so ``parents[2]`` is the skills directory it belongs to.
    """
    env = os.environ.get("CLAWK_HOME")
    if env:
        return Path(env).expanduser() / "skills"
    return Path(__file__).resolve().parents[2]


def parse_frontmatter_name(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    for line in text[3:end].splitlines():
        s = line.strip()
        if s.startswith("name:"):
            return s.split(":", 1)[1].strip().strip('"').strip("'") or None
    return None


def est_tokens(n_chars: int) -> int:
    return max(1, round(n_chars / 4))  # rough chars-per-token heuristic


def iter_skills(skills_dir: Path):
    if not skills_dir.is_dir():
        return
    for md in sorted(skills_dir.rglob("SKILL.md")):
        rel = md.relative_to(skills_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue  # skip .archive, etc.
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        name = parse_frontmatter_name(text) or md.parent.name
        yield name, md, text


def load_usage(skills_dir: Path) -> dict:
    try:
        return json.loads((skills_dir / ".usage.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def activity(rec: dict) -> int:
    return sum(int(rec.get(k) or 0) for k in ("use_count", "view_count", "patch_count"))


def last_activity(rec: dict):
    best = None
    for k in ("last_used_at", "last_viewed_at", "last_patched_at"):
        v = rec.get(k)
        if not v:
            continue
        try:
            dt = datetime.fromisoformat(str(v))
        except (TypeError, ValueError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if best is None or dt > best:
            best = dt
    return best


def _load_yaml(path: Path):
    import yaml  # PyYAML ships with the agent runtime

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_disabled(config_path: Path) -> set:
    try:
        cfg = _load_yaml(config_path)
    except Exception:
        return set()
    skills_cfg = (cfg.get("skills") or {}) if isinstance(cfg, dict) else {}
    out: set = set()
    d = skills_cfg.get("disabled")
    if isinstance(d, list):
        out |= {str(x).strip() for x in d if str(x).strip()}
    pd = skills_cfg.get("platform_disabled")
    if isinstance(pd, dict):
        for v in pd.values():
            if isinstance(v, list):
                out |= {str(x).strip() for x in v if str(x).strip()}
    return out


def apply_disable(config_path: Path, names: list[str]) -> list[str]:
    import yaml

    cfg = {}
    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8")
        cfg = yaml.safe_load(raw) or {}
        if not isinstance(cfg, dict):
            raise SystemExit("config.yaml is not a YAML mapping; refusing to edit.")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        config_path.with_name(config_path.name + f".bak-{ts}").write_text(raw, encoding="utf-8")
    skills_cfg = cfg.setdefault("skills", {})
    if not isinstance(skills_cfg, dict):
        raise SystemExit("config 'skills' is not a mapping; refusing to edit.")
    disabled = skills_cfg.setdefault("disabled", [])
    if not isinstance(disabled, list):
        raise SystemExit("config 'skills.disabled' is not a list; refusing to edit.")
    added = []
    for n in names:
        n = n.strip()
        if n and n not in disabled and n not in NEVER_DISABLE:
            disabled.append(n)
            added.append(n)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return added


def main() -> int:
    # Print UTF-8 regardless of the host console encoding (Windows cp1252 would
    # otherwise crash on the emoji / accents). No-op on already-UTF-8 stdouts.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Audit skills and flag unused ones.")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply", default="")
    ap.add_argument("--skills-dir", default="")
    ap.add_argument("--config", default="")
    args = ap.parse_args()

    skills_dir = Path(args.skills_dir).expanduser() if args.skills_dir else default_skills_dir()
    config_path = Path(args.config).expanduser() if args.config else skills_dir.parent / "config.yaml"

    if args.apply:
        try:
            added = apply_disable(config_path, args.apply.split(","))
        except SystemExit as exc:
            print(str(exc))
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"apply failed: {exc}")
            return 1
        print(f"Desactivadas (agregadas a skills.disabled): {', '.join(added) or '(ninguna nueva)'}")
        print(f"Config: {config_path}  · backup guardado al lado.")
        print("Reiniciá el gateway/agente para que tome efecto. Reactivar = sacarlas de esa lista.")
        return 0

    usage = load_usage(skills_dir)
    disabled = load_disabled(config_path)
    now = datetime.now(timezone.utc)

    rows = []
    for name, _md, text in iter_skills(skills_dir):
        rec = usage.get(name) or {}
        act = activity(rec)
        la = last_activity(rec)
        days_idle = (now - la).days if la else None
        if name in disabled:
            status = "disabled"
        elif name in NEVER_DISABLE:
            status = "protected"
        elif act == 0:
            status = "never"
        elif days_idle is not None and days_idle >= args.days:
            status = "stale"
        else:
            status = "active"
        rows.append({
            "name": name,
            "tokens": est_tokens(len(text)),
            "activity": act,
            "last_used": la.date().isoformat() if la else None,
            "days_idle": days_idle,
            "status": status,
        })

    rows.sort(key=lambda r: -r["tokens"])
    candidates = [r for r in rows if r["status"] in ("never", "stale")]
    total_tokens = sum(r["tokens"] for r in rows)
    save_tokens = sum(r["tokens"] for r in candidates)

    if args.json:
        print(json.dumps({
            "skills_dir": str(skills_dir),
            "total_skills": len(rows),
            "total_tokens_est": total_tokens,
            "savings_est": save_tokens,
            "candidates": candidates,
            "skills": rows,
        }, indent=2))
        return 0

    print("🪙 token-saver — auditoría de skills")
    print(f"Carpeta: {skills_dir}")
    print(f"Skills instaladas: {len(rows)}  ·  costo estimado en contexto: ~{total_tokens:,} tokens")
    already = [r for r in rows if r["status"] == "disabled"]
    if already:
        print(f"Ya desactivadas: {len(already)} ({', '.join(r['name'] for r in already)})")
    print()

    if not candidates:
        print(f"✅ Ninguna skill lleva ≥ {args.days} días sin usarse. Nada que recortar.")
        return 0

    print(f"Candidatas a desactivar (sin uso ≥ {args.days} días o nunca usadas) — ahorro ~{save_tokens:,} tokens:")
    print()
    print(f"  {'skill':<26} {'~tokens':>8}  {'último uso':<12} estado")
    for r in candidates:
        lu = r["last_used"] or "nunca"
        tag = " (¿nueva?)" if r["status"] == "never" else ""
        print(f"  {r['name']:<26} {r['tokens']:>8,}  {lu:<12} {r['status']}{tag}")

    names = ",".join(r["name"] for r in candidates)
    print()
    print("Para desactivarlas (libera ese contexto en cada turno):")
    print(f'  python3 "{Path(__file__)}" --apply {names}')
    print("…o a mano en ~/.clawksis/config.yaml:")
    print("  skills:")
    print("    disabled: [" + ", ".join(r["name"] for r in candidates) + "]")
    print("Luego reiniciá el gateway/agente. Las marcadas (¿nueva?) podrían ser recién instaladas — confirmá antes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
