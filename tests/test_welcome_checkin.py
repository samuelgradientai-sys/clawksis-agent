"""Tests for the install-time welcome check-in cron seeding (cron.jobs)."""

from datetime import datetime

import pytest

import cron.jobs as J
from cron.jobs import (
    WELCOME_CHECKIN_NAME,
    load_jobs,
    seed_welcome_checkin_job,
)
from clawk_time import now as clawk_now


@pytest.fixture(autouse=True)
def _isolate_cron_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")


def test_seeds_one_welcome_job_with_chosen_channel():
    job = seed_welcome_checkin_job(deliver="telegram")

    assert job is not None
    assert job["name"] == WELCOME_CHECKIN_NAME
    assert job["deliver"] == "telegram"
    assert job["schedule"]["kind"] == "once"
    assert job["repeat"]["times"] == 1
    assert job["next_run_at"]

    jobs = load_jobs()
    assert len(jobs) == 1
    assert jobs[0]["name"] == WELCOME_CHECKIN_NAME


def test_seeding_is_idempotent():
    first = seed_welcome_checkin_job(deliver="telegram")
    second = seed_welcome_checkin_job(deliver="telegram")

    assert first is not None
    assert second is None  # re-running setup must never duplicate it
    assert len(load_jobs()) == 1


def test_schedule_is_tomorrow_within_business_hours():
    job = seed_welcome_checkin_job(deliver="discord")

    run_at = datetime.fromisoformat(job["next_run_at"])
    assert run_at.date() > clawk_now().date()
    assert 9 <= run_at.hour <= 18


def test_deliver_defaults_to_local_when_no_channel():
    job = seed_welcome_checkin_job(deliver=None)

    assert job["deliver"] == "local"
