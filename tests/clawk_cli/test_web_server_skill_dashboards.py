"""Skill mini dashboards: a skill that declares ``metadata.clawk.dashboard`` gets a page in the
web UI fed by the snapshot it writes under its profile's home.

Pins the contract the Skills page and the dashboard renderer rely on: declared skills are listed
(even before the first snapshot), the snapshot is served clipped to the version-1 shape, a broken
snapshot is an error message rather than a 500, and each profile only sees its own data.
"""

import json

import pytest

DASHBOARD_SKILL = """---
name: {name}
description: a skill with a dashboard
metadata:
  clawk:
    dashboard:
      title: {title}
      description: What it did
---

# {name}
"""

PLAIN_SKILL = """---
name: plain-skill
description: a skill without a dashboard
---

# plain
"""


def _write(skills_dir, name, text):
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(text, encoding="utf-8")


def _snapshot(home, name, payload):
    target = home / "dashboards"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def homes(tmp_path, monkeypatch, _isolate_clawk_home):
    from clawk_cli import profiles
    from clawk_constants import get_clawk_home

    default_home = get_clawk_home()
    profiles_root = default_home / "profiles"
    worker_home = profiles_root / "worker_alpha"
    for home in (default_home, worker_home):
        (home / "skills").mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text("{}\n", encoding="utf-8")
    _write(
        default_home / "skills",
        "trader",
        DASHBOARD_SKILL.format(name="trader", title="Trader"),
    )
    _write(default_home / "skills", "plain-skill", PLAIN_SKILL)
    _write(
        worker_home / "skills",
        "trader",
        DASHBOARD_SKILL.format(name="trader", title="Worker"),
    )
    monkeypatch.setattr(profiles, "_get_default_clawk_home", lambda: default_home)
    monkeypatch.setattr(profiles, "_get_profiles_root", lambda: profiles_root)
    return {"default": default_home, "worker_alpha": worker_home}


@pytest.fixture
def client(monkeypatch, homes):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")

    import clawk_state
    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app
    from clawk_constants import get_clawk_home

    monkeypatch.setattr(clawk_state, "DEFAULT_DB_PATH", get_clawk_home() / "state.db")
    c = TestClient(app)
    c.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return c


def test_declared_skills_are_listed_before_their_first_snapshot(client):
    listing = client.get("/api/skills/dashboards").json()["dashboards"]
    assert [(d["name"], d["title"], d["modified_at"]) for d in listing] == [
        ("trader", "Trader", "")
    ]

    detail = client.get("/api/skills/dashboards/trader").json()
    assert detail["snapshot"] is None and detail["error"] is None
    assert detail["snapshot_file"].endswith("dashboards/trader.json")

    skills = {s["name"]: s for s in client.get("/api/skills").json()}
    assert skills["trader"]["has_dashboard"] is True
    assert skills["plain-skill"]["has_dashboard"] is False
    assert client.get("/api/skills/dashboards/plain-skill").status_code == 404


def test_snapshot_is_served_clipped_to_the_contract(client, homes):
    _snapshot(
        homes["default"],
        "trader",
        {
            "version": 1,
            "title": "Trader",
            "updated_at": "2026-10-26T14:03:00Z",
            "panels": [
                {
                    "type": "stats",
                    "title": "Today",
                    "items": [{"label": "Orders", "value": 3, "tone": "loud"}],
                },
                {
                    "type": "table",
                    "title": "Bought",
                    "columns": [
                        {"key": "symbol", "label": "Symbol"},
                        {"key": "usd", "format": "money", "align": "right"},
                    ],
                    "rows": [{"symbol": "AAPL", "usd": 50.5, "secret": "dropped"}]
                    * 500,
                },
                {
                    "type": "chart",
                    "series": [
                        {
                            "name": "hit rate",
                            "points": [["2026-10-01", 0.5], ["bad"], [1, "x"]],
                        }
                    ],
                },
                {
                    "type": "iframe",
                    "title": "Not a panel type",
                    "src": "https://example.com",
                },
            ],
        },
    )
    snapshot = client.get("/api/skills/dashboards/trader").json()["snapshot"]
    stats, table, chart, unknown = snapshot["panels"]
    assert stats["items"] == [
        {"label": "Orders", "value": 3, "hint": "", "tone": "neutral"}
    ]
    assert len(table["rows"]) == 200
    assert table["rows"][0] == {"symbol": "AAPL", "usd": 50.5, "_tone": "neutral"}
    assert table["columns"][1] == {
        "key": "usd",
        "label": "usd",
        "align": "right",
        "format": "money",
    }
    assert chart["series"][0]["points"] == [["2026-10-01", 0.5]]
    assert unknown["type"] == "unsupported" and "src" not in unknown

    listed = client.get("/api/skills/dashboards").json()["dashboards"][0]
    assert listed["modified_at"]


@pytest.mark.parametrize(
    "content, message",
    [
        ('{"version": 2, "panels": []}', "unsupported snapshot version"),
        ("{not json", "not valid JSON"),
        ('{"version": 1}', "no 'panels' list"),
    ],
)
def test_a_broken_snapshot_is_reported_not_raised(client, homes, content, message):
    target = homes["default"] / "dashboards"
    target.mkdir(parents=True, exist_ok=True)
    (target / "trader.json").write_text(content, encoding="utf-8")
    detail = client.get("/api/skills/dashboards/trader")
    assert detail.status_code == 200
    assert detail.json()["snapshot"] is None and message in detail.json()["error"]


def test_each_profile_reads_its_own_snapshot(client, homes):
    _snapshot(
        homes["worker_alpha"],
        "trader",
        {"version": 1, "title": "Worker data", "panels": []},
    )

    own = client.get("/api/skills/dashboards/trader").json()
    worker = client.get(
        "/api/skills/dashboards/trader", params={"profile": "worker_alpha"}
    ).json()
    assert own["snapshot"] is None
    assert worker["title"] == "Worker" and worker["snapshot"]["title"] == "Worker data"
