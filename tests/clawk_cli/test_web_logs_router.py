"""The Logs page reads the SELECTED profile's logs, the root home's update logs, every log
``clawk logs`` knows, and can download a whole file."""

import pytest
import clawk_yaml as yaml


@pytest.fixture
def homes(monkeypatch, _isolate_clawk_home):
    from clawk_cli import profiles
    from clawk_constants import get_clawk_home

    launch = get_clawk_home()
    beta = launch / "profiles" / "beta"
    for home in (launch, beta):
        (home / "logs").mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text(
            yaml.safe_dump({"model": {"default": "m"}}), encoding="utf-8"
        )
        (home / "logs" / "agent.log").write_text(
            f"2026-10-26 10:00:00,000 INFO agent.loop: agent log of {home.name}\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(profiles, "_get_default_clawk_home", lambda: launch)
    monkeypatch.setattr(profiles, "_get_profiles_root", lambda: launch / "profiles")
    return {"launch": launch, "beta": beta}


@pytest.fixture
def client(homes):
    from starlette.testclient import TestClient

    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app

    test_client = TestClient(app)
    test_client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return test_client


def test_update_log_is_read_from_the_root_home_under_a_named_profile(client, homes):
    # `clawk update` mirrors its output into the ROOT home's logs whatever profile is active.
    (homes["launch"] / "logs" / "update.log").write_text(
        "=== clawk update started ===\n", encoding="utf-8"
    )

    response = client.get("/api/logs", params={"file": "update", "profile": "beta"})

    assert response.status_code == 200, response.text
    assert response.json()["lines"] == ["=== clawk update started ===\n"]


def test_inventory_and_download_follow_the_selected_profile(client, homes):
    (homes["beta"] / "logs" / "mcp-stderr.log").write_text(
        "[mcp foo] started\n", encoding="utf-8"
    )

    inventory = client.get("/api/logs/files", params={"profile": "beta"})
    assert inventory.status_code == 200, inventory.text
    files = {f["name"]: f for f in inventory.json()["files"]}
    assert files["mcp"]["exists"] is True
    assert files["gui"]["exists"] is False
    assert "gui" in inventory.json()["components"]

    download = client.get(
        "/api/logs/download", params={"file": "agent", "profile": "beta"}
    )
    assert download.status_code == 200, download.text
    assert "agent log of beta" in download.text
    assert "attachment" in download.headers["content-disposition"]

    assert (
        client.get(
            "/api/logs/download", params={"file": "gui", "profile": "beta"}
        ).status_code
        == 404
    )
