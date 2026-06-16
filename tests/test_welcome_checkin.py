"""Tests for the install-time welcome check-in cron seeding (cron.jobs)."""

from datetime import datetime

import pytest

import cron.jobs as J
from cron.jobs import (
    WELCOME_CHECKIN_NAME,
    load_jobs,
    seed_welcome_checkin_job,
    upgrade_welcome_checkin_delivery,
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


# ---------------------------------------------------------------------------
# upgrade_welcome_checkin_delivery — retargets a pending local welcome job
# when a channel gets connected after install.
# ---------------------------------------------------------------------------


def test_upgrade_retargets_pending_local_job():
    seed_welcome_checkin_job(deliver="local")

    assert upgrade_welcome_checkin_delivery("telegram") is True
    assert load_jobs()[0]["deliver"] == "telegram"


def test_upgrade_never_downgrades_targeted_job():
    seed_welcome_checkin_job(deliver="telegram")

    assert upgrade_welcome_checkin_delivery("local") is False
    assert upgrade_welcome_checkin_delivery(None) is False
    assert load_jobs()[0]["deliver"] == "telegram"


def test_upgrade_skips_job_that_already_ran():
    seed_welcome_checkin_job(deliver="local")

    jobs = load_jobs()
    jobs[0]["last_run_at"] = clawk_now().isoformat()
    J.save_jobs(jobs)

    assert upgrade_welcome_checkin_delivery("telegram") is False
    assert load_jobs()[0]["deliver"] == "local"


def test_upgrade_never_creates_a_job():
    assert upgrade_welcome_checkin_delivery("telegram") is False
    assert load_jobs() == []


def test_reseeding_with_channel_upgrades_existing_local_job():
    """Setup re-run after connecting Telegram: still no duplicate, but the
    pending local job now targets the channel."""

    seed_welcome_checkin_job(deliver="local")

    assert seed_welcome_checkin_job(deliver="telegram") is None
    assert len(load_jobs()) == 1
    assert load_jobs()[0]["deliver"] == "telegram"


# ---------------------------------------------------------------------------
# _resolve_welcome_deliver_target (clawk_cli.setup) — picks the channel the
# operator configured during setup.
# ---------------------------------------------------------------------------


def _resolve_with_env(monkeypatch, env: dict) -> str:
    import clawk_cli.setup as S

    monkeypatch.setattr(S, "get_env_value", lambda key: env.get(key, ""))

    return S._resolve_welcome_deliver_target()


def test_resolver_picks_configured_channel_without_home(monkeypatch):
    """Telegram set up (bot token) but home channel deferred to /set-home —
    the welcome check-in must still target telegram, not fall back to local."""

    target = _resolve_with_env(monkeypatch, {"TELEGRAM_BOT_TOKEN": "123:abc"})

    assert target == "telegram"


def test_resolver_prefers_channel_with_home_set(monkeypatch):
    """A channel whose home is already set (guaranteed delivery) wins over one
    with only credentials."""

    target = _resolve_with_env(
        monkeypatch,
        {"TELEGRAM_BOT_TOKEN": "123:abc", "DISCORD_HOME_CHANNEL": "987"},
    )

    assert target == "discord"


def test_resolver_picks_one_of_two_configured_channels(monkeypatch):
    target = _resolve_with_env(
        monkeypatch,
        {
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "TELEGRAM_HOME_CHANNEL": "555",
            "DISCORD_BOT_TOKEN": "tok",
            "DISCORD_HOME_CHANNEL": "987",
        },
    )

    assert target == "telegram"


def test_resolver_falls_back_to_local_when_nothing_configured(monkeypatch):
    assert _resolve_with_env(monkeypatch, {}) == "local"


def test_resolver_ignores_whatsapp_explicitly_disabled(monkeypatch):
    assert _resolve_with_env(monkeypatch, {"WHATSAPP_ENABLED": "false"}) == "local"
