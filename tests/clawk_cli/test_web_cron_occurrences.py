"""GET /api/cron/occurrences (the Cron page calendar) projects each active job's firing days
across every profile, without blocking the event loop on the jobs.json reads."""

import asyncio
import threading

import pytest

import clawk_cli.web_routers.cron as _rt_cron
import clawk_cli.web_server_cron as _web_server_cron


@pytest.fixture()
def isolated_profiles(tmp_path, monkeypatch):
    from clawk_cli import profiles

    default_home = tmp_path / ".clawksis"
    worker_home = default_home / "profiles" / "worker_alpha"
    for home in (default_home, worker_home):
        (home / "cron").mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text("model: test-model\n", encoding="utf-8")
    monkeypatch.setattr(profiles, "_get_default_clawk_home", lambda: default_home)
    monkeypatch.setattr(
        profiles, "_get_profiles_root", lambda: default_home / "profiles"
    )
    return {"default": default_home, "worker_alpha": worker_home}


def test_calendar_lists_active_jobs_of_every_profile_but_not_paused_ones(
    isolated_profiles,
):
    daily = _web_server_cron._call_cron_for_profile(
        "worker_alpha", "create_job", prompt="brief", schedule="0 9 * * *"
    )
    paused = _web_server_cron._call_cron_for_profile(
        "default", "create_job", prompt="disk", schedule="0 10 * * *"
    )
    _web_server_cron._call_cron_for_profile("default", "pause_job", paused["id"])

    result = _rt_cron._cron_occurrences_sync("2026-11-01", "2026-11-07", "all")

    by_id = {job["id"]: job for job in result["jobs"]}
    assert set(by_id) == {daily["id"]}
    assert sorted(by_id[daily["id"]]["days"]) == [f"2026-11-0{d}" for d in range(1, 8)]


def test_occurrences_read_jobs_off_the_event_loop(isolated_profiles, monkeypatch):
    loop_ran = threading.Event()

    def blocking_list(_profile):
        assert loop_ran.wait(2), "occurrences blocked the event loop"
        return []

    monkeypatch.setattr(_rt_cron, "_occurrence_jobs", blocking_list)

    async def exercise():
        asyncio.get_running_loop().call_soon(loop_ran.set)
        return await _rt_cron.cron_occurrences(
            start="2026-11-01", end="2026-11-30", profile="all"
        )

    assert asyncio.run(exercise())["jobs"] == []
