#!/usr/bin/env python3
"""Auto-merge de divergentes en tests/.

Un archivo de test corresponde al codigo que testea: si upstream cambio el
codigo (y nosotros ya adoptamos ese cambio), la version upstream del test es
la que refleja el contrato nuevo. Por eso la accion por defecto para tests es
adoptar `.theirs`.

El unico riesgo real es PERDER tests propios del fork. Por eso el criterio:

  - Se calcula el conjunto de funciones `test_*` (y clases `Test*`) del
    archivo del fork y del `.theirs`.
  - Si el fork NO tiene ninguna que falte en `.theirs`  ->  adoptar `.theirs`
    (seguro: no se pierde cobertura propia).
  - Si el fork tiene tests propios ausentes en `.theirs`  ->  NO se toca; va
    a merge manual (subagente), listado en TESTS_TOAGENT.txt.

Ademas se salta cualquier `.theirs` que reintroduzca acople activo a Nous.

Uso:
  python tools/upstream/automerge_tests.py            # dry-run
  python tools/upstream/automerge_tests.py --apply
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sync import ROOT, match_eol  # noqa: E402
from automerge import NOUS_ACTIVE  # noqa: E402

PENDING = HERE / "pending"


def test_symbols(src: str) -> set[str]:
    """Funciones test_* y clases Test* de nivel superior o dentro de clases."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                out.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            out.add(node.name)
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--list", help="archivo con la lista de tests a procesar")
    args = ap.parse_args()

    if args.list:
        files = [l.strip() for l in Path(args.list).read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        import re
        report = (PENDING / "REPORT.md").read_text(encoding="utf-8")
        files = [p for p in re.findall(r"^- `([^`]+)`", report, re.M) if p.startswith("tests/")]

    adopted, to_agent, skipped = [], [], []
    for fp in files:
        dest = ROOT / fp
        th = PENDING / f"{fp.replace('/', '__')}.theirs"
        if not dest.is_file() or not th.exists():
            skipped.append((fp, "sin archivo/.theirs"))
            continue
        tb = th.read_bytes()
        if not tb.strip():
            skipped.append((fp, "theirs vacio (test borrado por upstream)"))
            continue
        ours = dest.read_bytes()
        try:
            ours_s = ours.decode("utf-8")
            th_s = tb.decode("utf-8")
        except UnicodeDecodeError:
            to_agent.append((fp, "no decodificable"))
            continue
        fork_only = test_symbols(ours_s) - test_symbols(th_s)
        if fork_only:
            to_agent.append((fp, f"tests propios del fork: {sorted(fork_only)[:4]}"))
            continue
        if NOUS_ACTIVE.search(th_s) and not NOUS_ACTIVE.search(ours_s):
            to_agent.append((fp, "theirs reintroduce Nous"))
            continue
        if args.apply:
            dest.write_bytes(match_eol(tb, ours))
        adopted.append(fp)

    mode = "APLICADO" if args.apply else "DRY-RUN"
    print(f"=== automerge_tests [{mode}] sobre {len(files)} tests ===")
    print(f"  adoptados de upstream (sin perder cobertura propia): {len(adopted)}")
    print(f"  a subagente (tienen tests propios del fork / Nous): {len(to_agent)}")
    print(f"  saltados: {len(skipped)}")
    (PENDING / "TESTS_TOAGENT.txt").write_text("\n".join(p for p, _ in to_agent), encoding="utf-8")
    (PENDING / "TESTS_ADOPTED.txt").write_text("\n".join(adopted), encoding="utf-8")
    if not args.apply and to_agent:
        print("\n  ejemplos a subagente:")
        for p, why in to_agent[:15]:
            print(f"    {p}  [{why}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
