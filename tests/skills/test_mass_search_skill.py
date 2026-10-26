"""mass-search's merge helper: one claim per key/text, numbered deduplicated sources, and "confirmed"
only when two different sites back a claim (mirrors of one page don't count)."""

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "skills/research/mass-search/scripts/merge_findings.py"
)
spec = importlib.util.spec_from_file_location("merge_findings", SCRIPT)
merge_findings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge_findings)


def _lines(*items):
    return [json.dumps(i) for i in items]


def test_same_page_variants_are_one_source():
    a = merge_findings.normalise_url("https://www.Example.com/a/?utm_source=x&id=3#top")
    b = merge_findings.normalise_url("https://example.com/a?id=3")
    assert a == b


def test_claims_merge_by_key_and_need_two_sites_to_be_confirmed():
    findings, skipped = merge_findings.read_findings(
        _lines(
            {
                "question": "Ingresos",
                "claim": "NVDA facturó 35 mil M",
                "url": "https://reuters.com/x",
                "key": "rev",
            },
            {
                "question": "Ingresos",
                "claim": "Ingresos de 35.000 M",
                "url": "https://bloomberg.com/y",
                "key": "rev",
            },
            {
                "question": "Ingresos",
                "claim": "Margen 75%",
                "url": "https://reuters.com/x?utm_medium=s",
            },
            {
                "question": "Ingresos",
                "claim": "Margen 75%",
                "url": "https://www.reuters.com/x",
            },
        )
        + [
            "not json",
            json.dumps({"claim": "sin url"}),
            json.dumps({"claim": "x", "url": "ftp://a"}),
        ]
    )
    assert skipped == 3
    report = merge_findings.merge(findings)
    claims = report["questions"][0]["claims"]
    assert [(c["claim"], c["sources"], c["confirmed"]) for c in claims] == [
        ("NVDA facturó 35 mil M", [1, 2], True),
        ("Margen 75%", [1], False),
    ]
    assert [s["url"] for s in report["sources"]] == [
        "https://reuters.com/x",
        "https://bloomberg.com/y",
    ]


def test_markdown_report_cites_every_claim(tmp_path):
    path = tmp_path / "findings.jsonl"
    path.write_text(
        "\n".join(
            _lines(
                {
                    "question": "Precio",
                    "claim": "Cuesta 999 USD",
                    "url": "https://apple.com/p",
                    "title": "Apple",
                },
                {
                    "question": "Precio",
                    "claim": "Cuesta 999 USD",
                    "url": "https://gsmarena.com/p",
                },
            )
        ),
        encoding="utf-8",
    )
    out = io.StringIO()
    with redirect_stdout(out):
        assert merge_findings.main([str(path)]) == 0
    text = out.getvalue()
    assert "- Cuesta 999 USD [1][2] — _confirmado_" in text
    assert "1. [Apple](https://apple.com/p)" in text
    assert "1 afirmaciones, 1 confirmadas por 2+ sitios, 2 fuentes" in text
