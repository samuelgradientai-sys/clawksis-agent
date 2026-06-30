#!/usr/bin/env python3
"""Curated checklist of Hermes release highlights for the upstream-watch issue.

Reads a Hermes release-notes markdown body (stdin or --file) and emits a
markdown checklist of the architecture / capability updates most relevant to
Clawksis, so the upstream-watch issue is actionable ("tick what to bring")
instead of a raw notes dump.

Deterministic (no LLM, no API key): it leans on upstream's own section
structure (## headings) and a keyword allow/deny list. For deep Clawksis-fit
analysis, run the differential audit instead — this is a fast triage radar.
"""

import argparse
import re
import sys

# Section titles (matched case-insensitively, by substring) whose items are
# integration candidates for Clawksis.
CORE_KEYWORDS = (
    "highlight",
    "core agent",
    "architecture",
    "agent loop",
    "agent",
    "multi-agent",
    "kanban",
    "skill",
    "memory",
    "session",
    "mcp",
    "provider",
    "model",
    "tool",
    "reasoning",
    "performance",
    "perf",
    "security",
    "gateway",
    "automation",
    "cron",
    "delegat",
    "context",
    "dashboard",
    "channel",
    "api",
)

# Section titles likely OUT of scope for Clawksis (SaaS — no desktop app, no
# bundled translations). Their items are NOT listed; only the title is noted.
OUT_KEYWORDS = ("desktop", "i18n", "translation", "中文", "chinese", "简体", "electron")


def split_sections(md):
    """Return [(title, [body_lines]), ...] for each top-level ``## `` heading."""
    sections = []
    title, body = None, []
    for line in md.splitlines():
        if line.startswith("## ") and not line.startswith("###"):
            if title is not None:
                sections.append((title, body))
            title, body = line[3:].strip(), []
        elif title is not None:
            body.append(line)
    if title is not None:
        sections.append((title, body))
    return sections


def _has(title, keywords):
    t = title.lower()
    return any(k in t for k in keywords)


def to_checklist(lines):
    """Turn top-level bullets into ``- [ ]`` checkboxes; keep subsections/nesting."""
    out = []
    for raw in lines:
        s = raw.rstrip()
        if not s.strip():
            continue
        if s.startswith("### "):
            out.append(f"\n**{s[4:].strip()}**")
            continue
        m = re.match(r"^(\s*)[-*]\s+(.*)$", s)
        if m and not m.group(1):  # top-level bullet
            out.append(f"- [ ] {m.group(2)}")
        elif m:  # nested bullet — preserve as sub-item
            out.append(s)
    return out


def build_digest(md):
    sections = split_sections(md)
    core, out_titles = [], []
    for title, body in sections:
        if _has(title, OUT_KEYWORDS):
            out_titles.append(title)
        elif _has(title, CORE_KEYWORDS):
            items = to_checklist(body)
            if items:
                core.append((title, items))

    lines = [
        "## 🏗️ Cambios de arquitectura / capacidades — candidatos para Clawksis",
        "",
        "> Tildá lo que valga traer. Curado de las release notes (no es un análisis "
        "de fit profundo — para eso, correr la auditoría diferencial). Recordá: "
        "Clawksis NO subsidia inferencia (BYOK), no usa Nous, y es SaaS web "
        "(la app desktop y las traducciones quedan fuera de scope).",
        "",
    ]
    if not core:
        lines.append(
            "_No se detectaron secciones de arquitectura en las notas — "
            "ver notas completas abajo._"
        )
    for title, items in core:
        lines.append(f"### {title}")
        lines.extend(items)
        lines.append("")
    if out_titles:
        lines.append("### ⏸️ Probablemente fuera de scope (SaaS / no aplica)")
        for t in out_titles:
            lines.append(f"- {t}")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", help="release notes markdown file (default: stdin)")
    args = ap.parse_args()
    md = (
        open(args.file, encoding="utf-8").read()
        if args.file
        else sys.stdin.buffer.read().decode("utf-8", errors="replace")
    )
    # Force UTF-8 output (the digest has emoji headings); the default locale
    # encoding can be cp1252 on Windows. CI runners are UTF-8 already.
    sys.stdout.buffer.write(build_digest(md).encode("utf-8"))


if __name__ == "__main__":
    main()
