"""A5 (Hermes→Clawksis quick wins): skill-index hygiene + curator cost gate."""

import os
from pathlib import Path

from agent import skill_utils as su
from agent import curator as cur


def _make_skill_tree(base: Path) -> None:
    (base / "myskill").mkdir()
    (base / "myskill" / "SKILL.md").write_text("x", encoding="utf-8")
    # A whole old package preserved under references/ (e.g. after consolidation).
    (base / "myskill" / "references" / "old").mkdir(parents=True)
    (base / "myskill" / "references" / "old" / "SKILL.md").write_text(
        "y", encoding="utf-8"
    )
    # A category literally named "scripts" containing a real skill.
    (base / "scripts" / "foo").mkdir(parents=True)
    (base / "scripts" / "foo" / "SKILL.md").write_text("z", encoding="utf-8")


class TestSkillSupportDirs:
    def test_iter_excludes_support_package(self, tmp_path):
        _make_skill_tree(tmp_path)
        found = {
            str(p.relative_to(tmp_path)).replace(os.sep, "/")
            for p in su.iter_skill_index_files(tmp_path, "SKILL.md")
        }
        assert "myskill/SKILL.md" in found
        assert "myskill/references/old/SKILL.md" not in found
        # "scripts" as a category is NOT a support dir (no SKILL.md at its parent).
        assert "scripts/foo/SKILL.md" in found

    def test_is_skill_support_path(self, tmp_path):
        _make_skill_tree(tmp_path)
        assert su.is_skill_support_path(
            tmp_path / "myskill" / "references" / "old" / "SKILL.md"
        )
        assert not su.is_skill_support_path(tmp_path / "scripts" / "foo" / "SKILL.md")

    def test_is_excluded_includes_support(self, tmp_path):
        _make_skill_tree(tmp_path)
        assert su.is_excluded_skill_path(
            tmp_path / "myskill" / "references" / "old" / "SKILL.md"
        )


class TestCuratorConsolidateGate:
    def test_get_consolidate_default_off(self, monkeypatch):
        monkeypatch.setattr(cur, "_load_config", lambda: {})
        assert cur.get_consolidate() is False

    def test_get_consolidate_config_on(self, monkeypatch):
        monkeypatch.setattr(cur, "_load_config", lambda: {"consolidate": True})
        assert cur.get_consolidate() is True

    def _mock_free_parts(self, monkeypatch):
        monkeypatch.setattr(
            cur,
            "apply_automatic_transitions",
            lambda now=None: {
                "checked": 1,
                "marked_stale": 0,
                "archived": 0,
                "reactivated": 0,
            },
        )
        monkeypatch.setattr(cur, "load_state", lambda: {})
        monkeypatch.setattr(cur, "save_state", lambda s: None)
        import agent.curator_backup as cb

        monkeypatch.setattr(cb, "snapshot_skills", lambda reason=None: None)

    def test_review_skips_llm_when_consolidate_off(self, monkeypatch):
        self._mock_free_parts(monkeypatch)
        monkeypatch.setattr(cur, "get_consolidate", lambda: False)

        spawned = []

        class _Thread:
            def __init__(self, *a, **k):
                pass

            def start(self):
                spawned.append("started")

        monkeypatch.setattr(cur.threading, "Thread", _Thread)
        result = cur.run_curator_review(synchronous=False)
        assert result.get("consolidation") == "skipped"
        assert spawned == []  # the aux-model review thread was NOT spawned

    def test_review_runs_llm_when_consolidate_on(self, monkeypatch):
        self._mock_free_parts(monkeypatch)
        monkeypatch.setattr(cur, "get_consolidate", lambda: True)

        spawned = []

        class _Thread:
            def __init__(self, *a, **k):
                pass  # don't actually run the LLM pass target

            def start(self):
                spawned.append("started")

        monkeypatch.setattr(cur.threading, "Thread", _Thread)
        result = cur.run_curator_review(synchronous=False)
        assert "consolidation" not in result  # gate passed through
        assert spawned == ["started"]
