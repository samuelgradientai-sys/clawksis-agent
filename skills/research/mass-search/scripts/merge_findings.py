#!/usr/bin/env python3
"""Merge findings from a parallel search into one report with numbered, deduplicated sources.

Input: JSON Lines (files or stdin), one finding per line:
  {"question": "...", "claim": "...", "url": "https://...", "title": "...", "key": "optional-id"}
Findings with the same ``key`` (or, without one, the same normalised claim) are one claim; a claim
backed by two or more different sites is marked confirmed, one site is "una sola fuente".
Output: Markdown (default) or ``--json``. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$)")


def normalise_url(url: str) -> str:
    """Same page, same string: lowercase host without www, no fragment, no tracking params."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)]
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower() or "https", host, path, query, ""))


def site_of(url: str) -> str:
    return urlsplit(normalise_url(url)).netloc


def claim_key(finding: dict) -> str:
    key = str(finding.get("key") or "").strip()
    return key or " ".join(str(finding.get("claim", "")).casefold().split())


def read_findings(lines) -> tuple[list[dict], int]:
    """Valid findings (need claim + http(s) url) and how many lines were skipped."""
    findings, skipped = [], 0
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        url = str(item.get("url", "")) if isinstance(item, dict) else ""
        if not item.get("claim") or not url.startswith(("http://", "https://")):
            skipped += 1
            continue
        findings.append(item)
    return findings, skipped


def merge(findings: list[dict]) -> dict:
    """Group findings by question then claim; number sources in first-seen order."""
    sources: OrderedDict[str, dict] = OrderedDict()
    questions: OrderedDict[str, OrderedDict[str, dict]] = OrderedDict()
    for item in findings:
        url = normalise_url(str(item["url"]))
        source = sources.setdefault(
            url, {"n": len(sources) + 1, "url": url, "title": item.get("title") or url}
        )
        claims = questions.setdefault(
            str(item.get("question") or "General"), OrderedDict()
        )
        claim = claims.setdefault(
            claim_key(item),
            {"claim": str(item["claim"]).strip(), "sources": [], "sites": set()},
        )
        if source["n"] not in claim["sources"]:
            claim["sources"].append(source["n"])
            claim["sites"].add(site_of(url))
    return {
        "questions": [
            {
                "question": q,
                "claims": [
                    {
                        "claim": c["claim"],
                        "sources": c["sources"],
                        "confirmed": len(c["sites"]) >= 2,
                    }
                    for c in claims.values()
                ],
            }
            for q, claims in questions.items()
        ],
        "sources": list(sources.values()),
    }


def to_markdown(report: dict, skipped: int = 0) -> str:
    lines = []
    for block in report["questions"]:
        lines += [f"## {block['question']}", ""]
        for c in block["claims"]:
            refs = "".join(f"[{n}]" for n in c["sources"])
            tag = "confirmado" if c["confirmed"] else "una sola fuente"
            lines.append(f"- {c['claim']} {refs} — _{tag}_")
        lines.append("")
    lines += ["## Fuentes", ""]
    lines += [f"{s['n']}. [{s['title']}]({s['url']})" for s in report["sources"]]
    total = sum(len(b["claims"]) for b in report["questions"])
    confirmed = sum(c["confirmed"] for b in report["questions"] for c in b["claims"])
    lines += [
        "",
        f"_{total} afirmaciones, {confirmed} confirmadas por 2+ sitios, {len(report['sources'])} fuentes._",
    ]
    if skipped:
        lines.append(f"_{skipped} líneas ignoradas (sin afirmación o sin URL)._")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "files", nargs="*", type=Path, help="JSONL files (default: stdin)"
    )
    parser.add_argument(
        "--json", action="store_true", help="print the merged report as JSON"
    )
    args = parser.parse_args(argv)
    lines = (
        [ln for f in args.files for ln in f.read_text(encoding="utf-8").splitlines()]
        if args.files
        else sys.stdin
    )
    findings, skipped = read_findings(lines)
    report = merge(findings)
    print(
        json.dumps({**report, "skipped": skipped}, ensure_ascii=False, indent=2)
        if args.json
        else to_markdown(report, skipped)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
