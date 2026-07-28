#!/usr/bin/env python3
"""Merge de 3 vias automatico para divergentes con delta real del fork.

Para cada archivo .py pendiente:
  base   = upstream en merge_base_commit, rebrandeado (mkbase)
  ours   = archivo actual del fork
  theirs = .theirs (target rebrandeado)

Se normaliza el RUIDO de formato en los tres por igual (trailing whitespace +
colapsar lineas en blanco consecutivas), de modo que el espaciado doble
heredado del squash no genere conflictos; solo compiten los cambios reales.
Luego `git merge-file --diff3`. Si NO hay conflicto y el resultado compila y no
introduce acople Nous nuevo, se aplica (con el EOL del fork). Si hay conflicto,
no compila o mete Nous, se deja para subagente.

Uso:
  python tools/upstream/merge3.py --list lista.txt            # dry-run
  python tools/upstream/merge3.py --list lista.txt --apply
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import json  # noqa: E402
from sync import ROOT, STATE_FILE, match_eol, rebrand, show  # noqa: E402
from mkbase import unmap_path  # noqa: E402
from automerge import NOUS_ACTIVE  # noqa: E402

PENDING = HERE / "pending"


def merge_base() -> str:
    st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return st.get("merge_base_commit") or st["last_synced_commit"]


_BLANKS = re.compile(rb"\n[ \t]*(?:\n[ \t]*)+")


def denoise(b: bytes) -> bytes:
    """LF, sin trailing ws por linea, runs de blancos -> 1 blanco."""
    b = b.replace(b"\r\n", b"\n")
    b = b"\n".join(line.rstrip() for line in b.split(b"\n"))
    b = _BLANKS.sub(b"\n\n", b)
    return b


def compiles(b: bytes) -> bool:
    try:
        ast.parse(b.decode("utf-8"))
        return True
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return False


def base_rebranded(fork_path: str, base_rev: str) -> bytes | None:
    up = unmap_path(fork_path)
    b = show(base_rev, up)
    if b is None and up != fork_path:
        b = show(base_rev, fork_path)
    return rebrand(b, up) if b is not None else None


def three_way(base: bytes, ours: bytes, theirs: bytes) -> tuple[bytes | None, int]:
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        (dp / "o").write_bytes(ours)
        (dp / "b").write_bytes(base)
        (dp / "t").write_bytes(theirs)
        res = subprocess.run(
            ["git", "merge-file", "-p", "--diff3",
             str(dp / "o"), str(dp / "b"), str(dp / "t")],
            capture_output=True,
        )
        if res.returncode < 0:
            return None, -1
        return res.stdout, res.returncode


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    base_rev = merge_base()
    files = [l.strip() for l in Path(args.list).read_text(encoding="utf-8").splitlines() if l.strip()]
    merged, conflict, nocompile, nous, skip = [], [], [], [], []

    for fp in files:
        dest = ROOT / fp
        theirs_f = PENDING / f"{fp.replace('/', '__')}.theirs"
        if not dest.is_file() or not theirs_f.exists():
            skip.append(fp); continue
        theirs = theirs_f.read_bytes()
        if not theirs.strip():
            skip.append(fp); continue  # movido, no aplica aca
        base = base_rebranded(fp, base_rev)
        if base is None:
            skip.append(fp); continue
        ours = dest.read_bytes()
        out, rc = three_way(denoise(base), denoise(ours), denoise(theirs))
        if out is None:
            skip.append(fp); continue
        if rc != 0:
            conflict.append(fp); continue
        if not compiles(out):
            nocompile.append(fp); continue
        if NOUS_ACTIVE.search(out.decode("utf-8", "replace")) and not NOUS_ACTIVE.search(
            ours.decode("utf-8", "replace")
        ):
            nous.append(fp); continue
        if args.apply:
            dest.write_bytes(match_eol(out, ours))
        merged.append(fp)

    mode = "APLICADO" if args.apply else "DRY-RUN"
    print(f"=== merge3 [{mode}] sobre {len(files)} archivos ===")
    print(f"  merge limpio + compila: {len(merged)}")
    print(f"  conflicto -> subagente: {len(conflict)}")
    print(f"  merge no compila -> subagente: {len(nocompile)}")
    print(f"  guard Nous -> subagente: {len(nous)}")
    print(f"  saltados (movido/irreconstruible): {len(skip)}")
    (PENDING / "MERGE3_TOAGENT.txt").write_text(
        "\n".join(conflict + nocompile + nous), encoding="utf-8")
    (PENDING / "MERGE3_APPLIED.txt").write_text("\n".join(merged), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
