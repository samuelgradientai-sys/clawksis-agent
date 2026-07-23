#!/usr/bin/env python3
"""Imprime a stdout la version BASE de un archivo del fork: la version del
upstream en `last_synced_commit` (el punto de partida del sync en curso),
ya rebrandeada hermes->clawksis, para poder calcular el delta propio del fork.

Uso:
  python tools/upstream/mkbase.py <fork_path>  > /tmp/base.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sync import PATH_MAP, STATE_FILE, rebrand, show  # noqa: E402


def unmap_path(p: str) -> str:
    """fork path -> upstream path (inverso de map_path; mas largo primero
    para que 'clawksis-agent' no caiga en el reemplazo de 'clawk')."""
    for old, new in sorted(PATH_MAP, key=lambda t: -len(t[1])):
        p = p.replace(new, old)
    return p


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__)
        return 2
    fork_path = sys.argv[1].replace("\\", "/").lstrip("./")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    # merge_base_commit = base real del ciclo de merges en curso. Ojo:
    # last_synced_commit ya apunta al TARGET después de `sync.py --apply`,
    # usarlo daría base==theirs y un delta-del-fork falso.
    last = state.get("merge_base_commit") or state["last_synced_commit"]
    up_path = unmap_path(fork_path)
    base = show(last, up_path)
    if base is None and up_path != fork_path:
        base = show(last, fork_path)
    if base is None:
        sys.stderr.write(f"[mkbase] {up_path} no existe en {last[:9]}\n")
        return 1
    sys.stdout.buffer.write(rebrand(base, up_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
