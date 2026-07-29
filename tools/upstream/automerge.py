#!/usr/bin/env python3
"""Auto-merge de divergentes cuyo delta propio del fork es SOLO formato/comentarios.

Para cada divergente .py pendiente con .theirs no vacio:
  base = version upstream en merge_base_commit, rebrandeada (via mkbase).
  fork = archivo actual.
  Si ast.dump(base) == ast.dump(fork)  =>  el fork no cambio NADA semantico
  (solo espaciado/comentarios heredados del squash). Entonces es seguro
  reemplazar por .theirs (que ademas sanea el espaciado), preservando el EOL
  del fork. GUARD: si .theirs introduce acople ACTIVO a Nous que el fork no
  tiene, NO se toca y queda para revision manual (subagente).

Los que tienen delta AST real, base irreconstruible, o riesgo Nous, se listan
como "a subagente" y no se tocan.

Uso:
  python tools/upstream/automerge.py            # dry-run: clasifica, no escribe
  python tools/upstream/automerge.py --apply    # escribe los seguros
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sync import ROOT, match_eol  # noqa: E402
from mkbase import unmap_path  # noqa: E402
import json  # noqa: E402
from sync import STATE_FILE, show, rebrand  # noqa: E402

PENDING = HERE / "pending"

# Tokens de acople ACTIVO a Nous Portal/billing. Si aparecen en .theirs y NO en
# el fork actual, el auto-merge se abstiene (va a subagente para stripping).
NOUS_ACTIVE = re.compile(
    r"nous_portal|nous_auth_keepalive|_try_nous|nous_subscription|nous_credits|"
    r"ensure_nous_portal|managed_nous|_nous_api_key|_nous_base_url|_refresh_nous|"
    r"nous_portal_tags|NOUS_EXTRA_BODY|_resolve_nous_runtime"
)


def merge_base() -> str:
    st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return st.get("merge_base_commit") or st["last_synced_commit"]


def ast_norm(src: bytes) -> str | None:
    try:
        return ast.dump(ast.parse(src.decode("utf-8")), include_attributes=False)
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None


def base_rebranded(fork_path: str, base_rev: str) -> bytes | None:
    up = unmap_path(fork_path)
    b = show(base_rev, up)
    if b is None and up != fork_path:
        b = show(base_rev, fork_path)
    if b is None:
        return None
    return rebrand(b, up)


def pending_divergents() -> list[str]:
    report = (PENDING / "REPORT.md").read_text(encoding="utf-8")
    return re.findall(r"^- `([^`]+)`", report, re.M)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only-prefix", default="", help="filtra por prefijo de path")
    args = ap.parse_args()

    base_rev = merge_base()
    applied, to_agent, skipped_nonpy, skipped_gone = [], [], [], []
    nous_guard = []

    for fork_path in pending_divergents():
        if args.only_prefix and not fork_path.startswith(args.only_prefix):
            continue
        if not fork_path.endswith(".py"):
            skipped_nonpy.append(fork_path)
            continue
        safe = fork_path.replace("/", "__")
        theirs_f = PENDING / f"{safe}.theirs"
        dest = ROOT / fork_path
        if not theirs_f.exists():
            to_agent.append((fork_path, "sin .theirs"))
            continue
        theirs = theirs_f.read_bytes()
        if not theirs.strip():
            # upstream lo borro (MOVIDO); lo maneja un subagente
            to_agent.append((fork_path, "theirs vacio (movido/borrado)"))
            continue
        if not dest.is_file():
            skipped_gone.append(fork_path)
            continue
        ours = dest.read_bytes()
        base = base_rebranded(fork_path, base_rev)
        if base is None:
            to_agent.append((fork_path, "base irreconstruible"))
            continue
        a_base, a_ours, a_theirs = ast_norm(base), ast_norm(ours), ast_norm(theirs)
        if a_base is None or a_ours is None:
            to_agent.append((fork_path, "AST no parseable"))
            continue
        if a_ours == a_theirs:
            # el fork ya es semanticamente identico al target: solo normalizar EOL/espaciado
            if a_ours != a_base or ours != match_eol(theirs, ours):
                if args.apply:
                    dest.write_bytes(match_eol(theirs, ours))
                applied.append((fork_path, "fork==target (solo formato)"))
            else:
                applied.append((fork_path, "ya identico"))
            continue
        if a_ours != a_base:
            to_agent.append((fork_path, "delta AST real del fork"))
            continue
        # fork == base semanticamente: el fork no cambio nada; adoptar target.
        if NOUS_ACTIVE.search(
            theirs.decode("utf-8", "replace")
        ) and not NOUS_ACTIVE.search(ours.decode("utf-8", "replace")):
            nous_guard.append(fork_path)
            to_agent.append((fork_path, "theirs introduce Nous -> subagente"))
            continue
        if args.apply:
            dest.write_bytes(match_eol(theirs, ours))
        applied.append((fork_path, "adoptado target (fork sin delta)"))

    mode = "APLICADO" if args.apply else "DRY-RUN"
    print(f"=== automerge [{mode}] ===")
    print(f"  auto-aplicables (.py, delta fork = solo formato): {len(applied)}")
    print(
        f"  a subagente (delta real / movido / base irreconstruible): {len(to_agent)}"
    )
    print(f"  no-.py (a subagente/manual): {len(skipped_nonpy)}")
    print(f"  desaparecidos del arbol: {len(skipped_gone)}")
    print(f"  guard Nous (theirs mete acople): {len(nous_guard)}")
    if not args.apply:
        print("\n--- a subagente (primeros 60) ---")
        for p, why in to_agent[:60]:
            print(f"    {p}  [{why}]")
    # deja la lista de 'a subagente' para el orquestador
    (PENDING / "TO_AGENT.txt").write_text(
        "\n".join(p for p, _ in to_agent), encoding="utf-8"
    )
    (PENDING / "AUTO_APPLIED.txt").write_text(
        "\n".join(p for p, _ in applied), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
