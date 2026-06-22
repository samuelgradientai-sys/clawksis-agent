#!/usr/bin/env python3
"""Sync curado de cambios desde upstream (NousResearch/hermes-agent).

El fork NO comparte historia de git con upstream (la historia se recreo en el
squash inicial del 2026-06-04) y el arbol difiere por el rebrand
hermes->clawksis, por line endings (CRLF vs LF) y por espaciado inconsistente
heredado del squash. Por eso este sync no usa merge/cherry-pick/patch:
trabaja ARCHIVO POR ARCHIVO comparando contenido normalizado.

Para cada archivo que upstream cambio entre `last_synced_commit` y el target:

  estado del archivo en el fork                         accion
  ----------------------------------------------------  ----------------------
  igual al baseline upstream (modulo rebrand/espaciado)  reemplazar por la
                                                         version target
                                                         rebrandeada
  ya igual al target                                     nada
  divergente (cambios propios del fork)                  va a pending/ para
                                                         merge manual
  inexistente en el fork y upstream lo agrega            crear rebrandeado

Uso:
  python tools/upstream/sync.py                        # dry-run vs ultimo release
  python tools/upstream/sync.py --target v2026.6.5     # dry-run vs tag
  python tools/upstream/sync.py --target v2026.6.5 --apply

Despues de un --apply: revisar `git status`, resolver lo que quedo en
tools/upstream/pending/ (si hay), correr smoke tests, commitear. El estado
queda registrado en tools/upstream/sync_state.json.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE_FILE = HERE / "sync_state.json"
PENDING_DIR = HERE / "pending"

UPSTREAM_URL = "https://github.com/NousResearch/hermes-agent.git"

# Renombres de paths del rebrand original (upstream -> fork): reemplazos
# ordenados sobre el path completo (el rebrand real renombro tambien archivos
# de docs/tests, ej. use-mcp-with-hermes.md -> use-mcp-with-clawk.md).
PATH_MAP = [
    ("hermes_cli", "clawk_cli"),
    ("hermes_bootstrap", "clawk_bootstrap"),
    ("hermes_constants", "clawk_constants"),
    ("hermes_logging", "clawk_logging"),
    ("hermes_state", "clawk_state"),
    ("hermes_time", "clawk_time"),
    ("hermes-agent", "clawksis-agent"),
    ("hermes-web", "clawksis-web"),
    ("hermes-acp", "clawk-acp"),
    ("hermes-dashboard", "clawksis-dashboard"),
    ("hermes", "clawk"),
    ("Hermes", "Clawksis"),
]

# Reemplazos de contenido en el MISMO orden que tools/rebrand.sh del monorepo
# (mas especifico primero). El orden importa: reproduce el transform historico
# tal cual se aplico al fork, incluidas sus redundancias.
CONTENT_MAP = [
    ("NousResearch/hermes-agent", "samuelgradientai-sys/clawksis-agent"),
    ("hermes_cli", "clawk_cli"),
    ("hermes_bootstrap", "clawk_bootstrap"),
    ("hermes_constants", "clawk_constants"),
    ("hermes_logging", "clawk_logging"),
    ("hermes_state", "clawk_state"),
    ("hermes_time", "clawk_time"),
    ("hermes-agent", "clawksis-agent"),
    ("hermes-web", "clawksis-web"),
    ("hermes-acp", "clawk-acp"),
    ("hermes-dashboard", "clawksis-dashboard"),
    ("HERMES_HOME", "CLAWK_HOME"),
    ("HERMES_INSTALL_DIR", "CLAWK_INSTALL_DIR"),
    ("HERMES_TUI_DIR", "CLAWK_TUI_DIR"),
    ("HERMES_WEB_DIST", "CLAWK_WEB_DIST"),
    ("HERMES_UID", "CLAWK_UID"),
    ("HERMES_GID", "CLAWK_GID"),
    ("HERMES_GIT_BASH_PATH", "CLAWK_GIT_BASH_PATH"),
    ("/opt/hermes", "/opt/clawksis"),
    ("~/.hermes", "~/.clawksis"),
    ("LocalAppData\\hermes", "LocalAppData\\clawksis"),
    ("LocalAppData/hermes", "LocalAppData/clawksis"),
    ("container_name: hermes", "container_name: clawksis"),
    ("--hermes-home", "--clawk-home"),
    ("HermesHome", "ClawkHome"),
    ("Hermes Agent", "Clawksis"),
    ("Hermes-Agent", "Clawksis"),
    ("<title>Hermes</title>", "<title>Clawksis</title>"),
    ('"Hermes"', '"Clawksis"'),
    ("'Hermes'", "'Clawksis'"),
    ("hermes setup", "clawk setup"),
    ("hermes chat", "clawk chat"),
    ("hermes gateway", "clawk gateway"),
    ("hermes update", "clawk update"),
    ("hermes config", "clawk config"),
    ("hermes dashboard", "clawk dashboard"),
    ("hermes model", "clawk model"),
    ("hermes doctor", "clawk doctor"),
    ("$ hermes", "$ clawk"),
    ('"hermes"', '"clawk"'),
    ('hermes = "hermes_cli.main:main"', 'clawk = "clawk_cli.main:main"'),
    ('hermes = "clawk_cli.main:main"', 'clawk = "clawk_cli.main:main"'),
    ('hermes-agent = "run_agent:main"', 'clawk-agent = "run_agent:main"'),
    ('hermes-acp = "acp_adapter.entry:main"', 'clawk-acp = "acp_adapter.entry:main"'),
    # Fallbacks blanket: el rebrand historico del fork reemplazo tambien las
    # menciones a secas (verificado contra el arbol real: class ClawksisACPAgent,
    # CLAWK_ALLOW_PRIVATE_URLS, docs "run Clawksis", etc.).
    ("HERMES_", "CLAWK_"),
    ("HERMES", "CLAWKSIS"),
    ("Hermes", "Clawksis"),
    ("hermes", "clawk"),
]

# IDs de modelo de Nous (Hermes-3 / Hermes-4 y sus variantes, incluidos los
# slugs de OpenRouter ``nousresearch/hermes-*``). El blanket hermes->clawk de
# arriba los corrompe a ``clawk-3``/``clawk-4``, que NO existen en ningun
# proveedor y fallan en runtime. Se preservan haciendo stash/unstash alrededor
# del CONTENT_MAP (ver ``rebrand``). "Hermes" como producto/agente SI se
# rebrandea; solo los nombres de modelo Herme quedan intactos.
_MODEL_ID_RE = re.compile(r"(?:nousresearch/)?[Hh]ermes[ _-]?[34][\w.\-]*")

# Solo estos tipos de archivo se rebrandean en contenido (igual que rebrand.sh).
REBRAND_EXTS = {
    ".py",
    ".toml",
    ".json",
    ".md",
    ".sh",
    ".ps1",
    ".yml",
    ".yaml",
    ".html",
    ".tsx",
    ".ts",
    ".js",
    ".txt",
    ".cfg",
    ".ini",
    ".rst",
}
REBRAND_BASENAMES = {"Dockerfile", "dockerfile"}


def git(*args: str, check: bool = True) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} fallo:\n{res.stderr.strip()}")
    return res.stdout


def git_bytes(*args: str) -> bytes | None:
    res = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    return res.stdout if res.returncode == 0 else None


def show(rev: str, path: str) -> bytes | None:
    return git_bytes("show", f"{rev}:{path}")


def map_path(p: str) -> str:
    for old, new in PATH_MAP:
        p = p.replace(old, new)
    return p


def rebrand(content: bytes, path: str) -> bytes:
    name = path.rsplit("/", 1)[-1]
    ext = ("." + name.rsplit(".", 1)[-1]).lower() if "." in name else ""
    if ext not in REBRAND_EXTS and name not in REBRAND_BASENAMES:
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    # Stash IDs de modelo Hermes detras de placeholders inertes (NUL-delimitados,
    # imposibles en fuente) para que el blanket hermes->clawk no los corrompa.
    stash: dict[str, str] = {}

    def _stash(m: "re.Match[str]") -> str:
        key = f"\x00MODELID{len(stash)}\x00"
        stash[key] = m.group(0)
        return key

    text = _MODEL_ID_RE.sub(_stash, text)
    for old, new in CONTENT_MAP:
        text = text.replace(old, new)
    for key, orig in stash.items():
        text = text.replace(key, orig)
    return text.encode("utf-8")


_WS = re.compile(rb"\s+")


def norm(content: bytes | None) -> bytes:
    """Forma canonica para comparar igualdad: SIN ningun whitespace.

    El squash inicial del fork dejo CRLF, espaciado doble y un reformateo
    estilo black (wrapping/alineacion/trailing commas distintos); todo eso es
    ruido sin semantica para detectar si el fork cambio de verdad un archivo.
    Solo se usa para clasificar — el contenido que se escribe nunca pasa por
    aca."""
    if content is None:
        return b""
    out = _WS.sub(b"", content)
    for a, b in ((b",)", b")"), (b",]", b"]"), (b",}", b"}")):
        out = out.replace(a, b)
    return out


def match_eol(new: bytes, like: bytes | None) -> bytes:
    """Preserva el line ending que ya usa el archivo del fork (evita diffs
    fantasma por CRLF)."""
    if like and b"\r\n" in like and b"\r\n" not in new:
        return new.replace(b"\n", b"\r\n")
    return new


def ensure_upstream() -> None:
    res = subprocess.run(
        ["git", "remote", "get-url", "upstream"], cwd=ROOT, capture_output=True
    )
    if res.returncode != 0:
        git("remote", "add", "upstream", UPSTREAM_URL)
        print(f"[sync] remote upstream agregado: {UPSTREAM_URL}")


def rev_exists(rev: str) -> bool:
    res = subprocess.run(
        ["git", "cat-file", "-e", f"{rev}^{{commit}}"], cwd=ROOT, capture_output=True
    )
    return res.returncode == 0


def fetch_rev(rev: str) -> None:
    if rev_exists(rev):
        return
    print(f"[sync] trayendo {rev} de upstream...")
    for refspec in (
        ["fetch", "--depth", "1", "upstream", "tag", rev],
        ["fetch", "upstream", rev],
    ):
        res = subprocess.run(["git", *refspec], cwd=ROOT, capture_output=True)
        if res.returncode == 0 and rev_exists(rev):
            return
    raise RuntimeError(f"No pude traer '{rev}' de upstream.")


def ensure_history(state: dict) -> None:
    last = state["last_synced_commit"]
    if rev_exists(last):
        return
    since = state.get("last_synced_date", "").split("T")[0]
    print(f"[sync] historial local no tiene {last[:9]}; fetch de upstream main...")
    args = ["fetch", "upstream", "main"]
    if since:
        args.insert(1, f"--shallow-since={since}")
    subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if not rev_exists(last):
        raise RuntimeError(
            f"El commit base {last[:9]} sigue sin estar disponible. "
            f"Corre: git fetch upstream main"
        )


def latest_release_tag() -> str:
    res = subprocess.run(
        [
            "gh",
            "api",
            "repos/NousResearch/hermes-agent/releases/latest",
            "--jq",
            ".tag_name",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    # Fallback sin gh: tags por ls-remote, orden calver
    out = git("ls-remote", "--tags", "upstream")
    tags = re.findall(r"refs/tags/(v[\d.]+)$", out, flags=re.MULTILINE)
    if not tags:
        raise RuntimeError("No encontre tags en upstream (¿gh y red ok?).")
    return max(tags, key=lambda t: [int(x) for x in re.findall(r"\d+", t)])


def parse_changes(last: str, target: str) -> list[tuple[str, str]]:
    """Devuelve [(status, upstream_path)]; renames se descomponen en D + A."""
    raw = git("diff", "--name-status", "-z", "-M", last, target)
    toks = raw.split("\0")
    changes: list[tuple[str, str]] = []
    i = 0
    while i < len(toks):
        status = toks[i].strip()
        if not status:
            i += 1
            continue
        if status[0] in ("R", "C"):
            old, new = toks[i + 1], toks[i + 2]
            if status[0] == "R":
                changes.append(("D", old))
            changes.append(("A", new))
            i += 3
        else:
            changes.append((status[0], toks[i + 1]))
            i += 2
    return changes


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # consolas Windows cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--target", help="tag o commit de upstream (default: ultimo release)"
    )
    ap.add_argument(
        "--apply", action="store_true", help="escribir cambios (default: dry-run)"
    )
    args = ap.parse_args()

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    skip_patterns = state.get("skip_paths", [])
    ensure_upstream()
    ensure_history(state)

    target = args.target or latest_release_tag()
    fetch_rev(target)
    target_sha = git("rev-parse", "--verify", f"{target}^{{commit}}").strip()
    last = state["last_synced_commit"]
    if target_sha == last:
        print(f"[sync] ya estas sincronizado con {target} ({last[:9]}).")
        return 0

    print(f"[sync] upstream {last[:9]} -> {target} ({target_sha[:9]})")
    changes = parse_changes(last, target_sha)
    print(f"[sync] {len(changes)} cambios de archivo en upstream\n")

    replaced, added, deleted, already, skipped, diverged = [], [], [], [], [], []

    for status, up_path in changes:
        if any(fnmatch.fnmatch(up_path, pat) for pat in skip_patterns):
            skipped.append(up_path)
            continue
        fork_path = map_path(up_path)
        dest = ROOT / fork_path
        ours = dest.read_bytes() if dest.is_file() else None
        base = show(last, up_path)
        targ = show(target_sha, up_path)
        base_r = rebrand(base, up_path) if base is not None else None
        targ_r = rebrand(targ, up_path) if targ is not None else None

        if targ_r is None:  # upstream lo borro
            if ours is None:
                already.append(fork_path)
            elif norm(ours) == norm(base_r):
                deleted.append(fork_path)
                if args.apply:
                    dest.unlink()
            else:
                diverged.append((
                    fork_path,
                    up_path,
                    "upstream lo borra, fork lo modifico",
                ))
        elif ours is None:
            if base_r is None or status == "A":
                added.append(fork_path)
                if args.apply:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(targ_r)
            else:
                diverged.append((
                    fork_path,
                    up_path,
                    "upstream lo modifica, fork lo elimino",
                ))
        elif norm(ours) == norm(targ_r):
            already.append(fork_path)
        elif norm(ours) == norm(base_r):
            replaced.append(fork_path)
            if args.apply:
                dest.write_bytes(match_eol(targ_r, ours))
        else:
            diverged.append((fork_path, up_path, "cambios propios del fork"))

    def listing(title: str, items: list[str]) -> None:
        if items:
            print(f"  {title} ({len(items)}):")
            for it in items:
                print(f"    {it}")
            print()

    mode = "APLICADO" if args.apply else "DRY-RUN (nada escrito; usa --apply)"
    print(f"=== Resultado [{mode}] ===\n")
    listing("Actualizados desde upstream", replaced)
    listing("Nuevos", added)
    listing("Borrados", deleted)
    listing("Saltados por skip_paths", skipped)
    if already:
        print(f"  Sin cambios reales (ya al dia / solo espaciado): {len(already)}\n")
    if diverged:
        print(f"  DIVERGENTES — requieren merge manual ({len(diverged)}):")
        for fork_path, up_path, why in diverged:
            print(f"    {fork_path}  [{why}]")
        print()

    if args.apply and diverged:
        import difflib

        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        report = [
            "# Merges pendientes de upstream\n",
            f"Sync {last[:9]} -> {target} ({target_sha[:9]})\n",
        ]
        for fork_path, up_path, why in diverged:
            safe = fork_path.replace("/", "__")
            base = show(last, up_path)
            targ = show(target_sha, up_path)
            base_r = rebrand(base, up_path) if base is not None else b""
            targ_r = rebrand(targ, up_path) if targ is not None else b""
            (PENDING_DIR / f"{safe}.theirs").write_bytes(targ_r)
            diff = difflib.unified_diff(
                base_r.decode("utf-8", "replace").splitlines(keepends=True),
                targ_r.decode("utf-8", "replace").splitlines(keepends=True),
                fromfile=f"a/{fork_path}",
                tofile=f"b/{fork_path}",
            )
            (PENDING_DIR / f"{safe}.patch").write_text("".join(diff), encoding="utf-8")
            report.append(f"- `{fork_path}` — {why}\n")
        (PENDING_DIR / "REPORT.md").write_text("".join(report), encoding="utf-8")
        print(
            f"  Material para los merges manuales en {PENDING_DIR.relative_to(ROOT)}/"
        )
        print(
            "  (aplicar cada .patch a mano sobre el archivo del fork y borrar pending/)\n"
        )

    if args.apply:
        state["last_synced_commit"] = target_sha
        if re.fullmatch(r"v[\d.]+", target):
            state["last_synced_tag"] = target
        state["last_synced_date"] = git("log", "-1", "--format=%cI", target_sha).strip()
        STATE_FILE.write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print("[sync] sync_state.json actualizado. Proximos pasos:")
        print("  1. Resolver pending/ si hay divergentes")
        print("  2. Revisar:  git status && git diff --stat")
        print("  3. Smoke test del CLI y commitear")

    return 0


if __name__ == "__main__":
    sys.exit(main())
