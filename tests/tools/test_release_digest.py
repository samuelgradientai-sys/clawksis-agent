"""Tests for tools/upstream/release_digest.py — the upstream-watch issue's
curated architecture checklist."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "release_digest",
    Path(__file__).resolve().parents[2] / "tools" / "upstream" / "release_digest.py",
)
rd = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rd)


SAMPLE = """\
Some intro text.

## ✨ Highlights
- **Big agent thing** — does X ([#123](url))
- **Desktop thing** — does Y

## 🏗️ Core Agent & Architecture
### Agent loop
- loop fix one
- loop fix two

## 🖥️ Hermes Desktop App (NEW)
- desktop only A
- desktop only B

## 简体中文 翻译
- translation stuff
"""


def test_highlights_become_checkboxes():
    out = rd.build_digest(SAMPLE)
    assert "- [ ] **Big agent thing**" in out
    assert "### ✨ Highlights" in out


def test_core_architecture_section_included_with_subsection():
    out = rd.build_digest(SAMPLE)
    assert "### 🏗️ Core Agent & Architecture" in out
    assert "**Agent loop**" in out
    assert "- [ ] loop fix one" in out


def test_desktop_section_flagged_out_of_scope_not_listed():
    out = rd.build_digest(SAMPLE)
    # Desktop section title is noted as out-of-scope...
    assert "Hermes Desktop App (NEW)" in out
    # ...but its items are NOT turned into candidate checkboxes.
    assert "desktop only A" not in out


def test_translation_section_flagged_out():
    out = rd.build_digest(SAMPLE)
    assert "translation stuff" not in out


def test_empty_notes_degrade_gracefully():
    out = rd.build_digest("just a blob with no sections")
    assert "No se detectaron secciones" in out


def test_split_sections_counts_top_level_only():
    secs = rd.split_sections(SAMPLE)
    titles = [t for t, _ in secs]
    assert "✨ Highlights" in titles
    assert "🏗️ Core Agent & Architecture" in titles
    # The "### Agent loop" subsection must NOT be a top-level section.
    assert "Agent loop" not in titles
