"""Tests for the cron-handling rules wiring:

- inline-script auto-materialization (agent pasted script content into the
  path-only ``script`` field),
- the expanded ``_build_job_prompt`` guidance (language / natural tone /
  real-task / [SILENT]),
- ``stop_after_alert`` auto-pause after the first real delivery.
"""

import logging
from unittest.mock import patch

import pytest


# --------------------------------------------------------------------------
# Inline-script auto-materialization
# --------------------------------------------------------------------------
class TestMaterializeInlineScript:
    def test_plain_path_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clawk_constants.get_clawk_home", lambda: tmp_path)
        from tools.cronjob_tools import _materialize_inline_script

        assert _materialize_inline_script("check.py", "job") == "check.py"
        assert _materialize_inline_script("sub/dir/run.sh", "job") == "sub/dir/run.sh"
        # Nothing should have been written for a plain path.
        assert not (tmp_path / "scripts").exists() or not list(
            (tmp_path / "scripts").glob("cron_*")
        )

    def test_shebang_bash_saved_as_sh(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clawk_constants.get_clawk_home", lambda: tmp_path)
        from tools.cronjob_tools import _materialize_inline_script

        content = "#!/usr/bin/env bash\nset -euo pipefail\necho hi\n"
        rel = _materialize_inline_script(content, "Meta WhatsApp active alert")

        assert rel.endswith(".sh")
        assert rel.startswith("cron_meta-whatsapp-active-alert_")
        saved = tmp_path / "scripts" / rel
        assert saved.is_file()
        assert saved.read_text(encoding="utf-8") == content

    def test_inline_python_without_shebang_saved_as_py(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clawk_constants.get_clawk_home", lambda: tmp_path)
        from tools.cronjob_tools import _materialize_inline_script

        content = "import json\nprint(json.dumps({'ok': True}))\n"
        rel = _materialize_inline_script(content, None)

        assert rel.endswith(".py")
        assert (tmp_path / "scripts" / rel).is_file()

    def test_detector(self):
        from tools.cronjob_tools import _looks_like_inline_script

        assert _looks_like_inline_script("#!/bin/bash\necho hi")
        assert _looks_like_inline_script("line one\nline two")
        assert not _looks_like_inline_script("check.py")
        assert not _looks_like_inline_script("   ")


# --------------------------------------------------------------------------
# Expanded cron guidance in _build_job_prompt
# --------------------------------------------------------------------------
class TestCronGuidance:
    def test_language_and_tone_and_task_clauses_present(self):
        from cron.scheduler import _build_job_prompt

        result = _build_job_prompt({"prompt": "Do the thing"})

        # Rule 1 (language), 2 (natural tone), 3 (real task), 4 ([SILENT]).
        assert "LANGUAGE" in result
        assert "Never default to English" in result
        assert "naturally" in result
        assert "REAL TASK" in result
        assert "[SILENT]" in result
        # Existing invariants must survive.
        assert "automatically delivered" in result
        assert "do NOT use send_message" in result
        assert "Do the thing" in result

    def test_user_profile_injected_when_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cron.scheduler._get_clawk_home", lambda: tmp_path)
        (tmp_path / "user.md").write_text(
            "Language: Spanish (LATAM). Name: Samuel.", encoding="utf-8"
        )
        from cron.scheduler import _build_job_prompt

        result = _build_job_prompt({"prompt": "go"})
        assert "USER PROFILE" in result
        assert "Samuel" in result


# --------------------------------------------------------------------------
# stop_after_alert: pause after the first real delivery
# --------------------------------------------------------------------------
class TestStopAfterAlert:
    def _job(self, **extra):
        job = {
            "id": "alert-job",
            "name": "meta-up",
            "deliver": "origin",
            "origin": {"platform": "telegram", "chat_id": "123"},
        }
        job.update(extra)
        return job

    def test_pauses_after_real_delivery_when_flag_set(self):
        with (
            patch(
                "cron.scheduler.get_due_jobs",
                return_value=[self._job(stop_after_alert=True)],
            ),
            patch(
                "cron.scheduler.run_job",
                return_value=(True, "# output", "Meta is back up ✅", None),
            ),
            patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"),
            patch("cron.scheduler._deliver_result", return_value=None),
            patch("cron.scheduler.mark_job_run"),
            patch("cron.jobs.pause_job") as pause_mock,
        ):
            from cron.scheduler import tick

            tick(verbose=False)

        pause_mock.assert_called_once()
        assert pause_mock.call_args.args[0] == "alert-job"

    def test_no_pause_without_flag(self):
        with (
            patch("cron.scheduler.get_due_jobs", return_value=[self._job()]),
            patch(
                "cron.scheduler.run_job",
                return_value=(True, "# output", "Meta is back up ✅", None),
            ),
            patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"),
            patch("cron.scheduler._deliver_result", return_value=None),
            patch("cron.scheduler.mark_job_run"),
            patch("cron.jobs.pause_job") as pause_mock,
        ):
            from cron.scheduler import tick

            tick(verbose=False)

        pause_mock.assert_not_called()

    def test_no_pause_on_silent_even_with_flag(self):
        with (
            patch(
                "cron.scheduler.get_due_jobs",
                return_value=[self._job(stop_after_alert=True)],
            ),
            patch(
                "cron.scheduler.run_job",
                return_value=(True, "# output", "[SILENT]", None),
            ),
            patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"),
            patch("cron.scheduler._deliver_result", return_value=None),
            patch("cron.scheduler.mark_job_run"),
            patch("cron.jobs.pause_job") as pause_mock,
        ):
            from cron.scheduler import tick

            tick(verbose=False)

        pause_mock.assert_not_called()
