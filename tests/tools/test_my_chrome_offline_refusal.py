"""The agent never swaps the user's Chrome for the server's browser behind their back.

Real incident: the dashboard (which hosts the Mi Chrome relay) was down after a reboot, the 9am
LinkedIn cron silently browsed with the server's browser, and LinkedIn answered "you have been
blocked". With Mi Chrome paired, an offline relay now stops the browser call with a clear reason,
and a cron job can pin its browser (``my_chrome`` / ``server``).
"""

import json

import pytest

from tools import browser_my_chrome_state as state


@pytest.fixture
def mi_chrome(monkeypatch):
    cfg = {"enabled": True, "paired": True, "live": False, "settings": {}}
    monkeypatch.setattr(state, "my_chrome_enabled", lambda: cfg["enabled"])
    monkeypatch.setattr(
        state, "my_chrome_setting", lambda key: cfg["settings"].get(key) is True
    )
    monkeypatch.setattr(
        state,
        "relay_endpoint",
        lambda home: "http://127.0.0.1:9/x" if cfg["live"] else "",
    )
    monkeypatch.setattr(
        "clawk_cli.my_chrome_pairing.pairing_info",
        lambda home: {"created_at": 1} if cfg["paired"] else None,
    )
    monkeypatch.delenv(state.BROWSER_ROUTE_ENV, raising=False)
    return cfg


def test_paired_but_offline_refuses_the_server_browser(mi_chrome):
    assert state.offline_refusal() == state.OFFLINE_MESSAGE
    assert "LinkedIn" in state.OFFLINE_MESSAGE


@pytest.mark.parametrize(
    "change",
    [
        {"live": True},
        {"paired": False},
        {"enabled": False},
        {"settings": {"server_fallback": True}},
    ],
)
def test_nothing_is_refused_when_the_user_did_not_ask_for_their_chrome(
    mi_chrome, change
):
    mi_chrome.update(change)
    assert state.offline_refusal() == ""


def test_a_job_pinned_to_my_chrome_refuses_even_with_the_fallback_on(
    mi_chrome, monkeypatch
):
    mi_chrome.update(paired=False, settings={"server_fallback": True})
    monkeypatch.setenv(state.BROWSER_ROUTE_ENV, "my_chrome")
    assert state.offline_refusal() == state.OFFLINE_MESSAGE
    mi_chrome["live"] = True
    assert state.offline_refusal() == ""


def test_a_job_pinned_to_the_server_never_touches_the_users_chrome(
    mi_chrome, monkeypatch
):
    mi_chrome["live"] = True
    monkeypatch.setenv(state.BROWSER_ROUTE_ENV, "server")
    assert state.my_chrome_cdp_url() == ""
    mi_chrome["live"] = False
    assert state.offline_refusal() == ""


def test_browser_exec_stops_instead_of_launching_the_server_browser(
    mi_chrome, monkeypatch
):
    from tools import browser_use_cli

    monkeypatch.setattr("tools.browser_tool_cdp._get_cdp_override_raw", lambda: "")
    assert browser_use_cli._my_chrome_offline_refusal() == state.OFFLINE_MESSAGE
    # An operator-chosen browser (/browser connect, BROWSER_CDP_URL) is respected.
    monkeypatch.setattr(
        "tools.browser_tool_cdp._get_cdp_override_raw", lambda: "http://10.0.0.5:9222"
    )
    assert browser_use_cli._my_chrome_offline_refusal() == ""


def test_new_browser_sessions_are_refused_too(mi_chrome, monkeypatch):
    from tools import browser_tool_session as session

    monkeypatch.setattr(session._cdp, "_get_cdp_override", lambda: "")
    with pytest.raises(RuntimeError, match="Mi Chrome is paired but not connected"):
        session._create_session_for_key("t1", force_local=False)


def test_cron_jobs_store_a_valid_browser_choice(tmp_path):
    from cron import jobs

    with jobs.use_cron_store(tmp_path / "cron"):
        job = jobs.create_job(
            prompt="Mensajes de LinkedIn", schedule="every 1h", browser="my_chrome"
        )
        assert jobs.get_job(job["id"])["browser"] == "my_chrome"
        jobs.update_job(job["id"], {"browser": "auto"})
        assert jobs.get_job(job["id"])["browser"] is None
        with pytest.raises(ValueError, match="browser must be"):
            jobs.update_job(job["id"], {"browser": "firefox"})


def test_the_worker_pins_the_jobs_browser_for_its_own_process(monkeypatch):
    from cron import scheduler

    monkeypatch.delenv(state.BROWSER_ROUTE_ENV, raising=False)
    scheduler._pin_job_browser_route({"browser": "my_chrome"})
    assert state.BROWSER_ROUTE_ENV not in __import__("os").environ  # not in the gateway

    monkeypatch.setenv("_CLAWK_CRON_EXTERNAL_WORKER", "exec-1")
    scheduler._pin_job_browser_route({"browser": "my_chrome"})
    assert __import__("os").environ[state.BROWSER_ROUTE_ENV] == "my_chrome"
    scheduler._pin_job_browser_route({})
    assert state.BROWSER_ROUTE_ENV not in __import__("os").environ


def test_the_cron_tool_tells_the_agent_to_ask_which_browser():
    from tools.cronjob_tools import CRONJOB_SCHEMA

    text = json.dumps(CRONJOB_SCHEMA)
    assert "ASK the user" in text and "my_chrome" in text
