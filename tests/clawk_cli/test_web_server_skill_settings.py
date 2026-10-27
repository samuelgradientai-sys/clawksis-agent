"""Skill settings form: the web UI edits the ``metadata.clawk.config`` values a skill declares.

Pins what the Kronos settings card relies on: fields carry the declaration and the current value,
only declared keys are written (under ``skills.config``), values are checked against their type,
and risky changes (trading on, a real-money account, a higher limit) need an explicit confirm.
"""

import pytest
from utils import fast_safe_load

TRADER_SKILL = """---
name: trader
description: a skill with settings
metadata:
  clawk:
    config:
      - key: trader.trading.enabled
        description: Let the agent place orders
        default: false
        label: {es: "Trading automático"}
        confirm: true
      - key: trader.trading.account
        description: Account for orders
        default: demo
        choices: [demo, real]
        confirm: [real]
      - key: trader.trading.max_order_usd
        description: Max USD per buy
        default: 100
        min: 1
        confirm: true
      - key: trader.goals.watchlist
        description: Symbols to follow
---

# trader
"""


@pytest.fixture
def home(_isolate_clawk_home):
    from clawk_constants import get_clawk_home

    home = get_clawk_home()
    skill = home / "skills" / "trader"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(TRADER_SKILL, encoding="utf-8")
    (home / "config.yaml").write_text(
        "model:\n  default: some-model\nskills:\n  config:\n    trader:\n      trading:\n"
        "        max_order_usd: 200\n",
        encoding="utf-8",
    )
    return home


@pytest.fixture
def client(monkeypatch, home):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")

    import clawk_state
    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app

    monkeypatch.setattr(clawk_state, "DEFAULT_DB_PATH", home / "state.db")
    c = TestClient(app)
    c.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return c


def _stored(home):
    return fast_safe_load((home / "config.yaml").read_text(encoding="utf-8"))


def test_fields_carry_the_declaration_and_the_value_the_skill_sees(client):
    fields = {
        f["key"]: f for f in client.get("/api/skills/settings/trader").json()["fields"]
    }
    enabled = fields["trader.trading.enabled"]
    assert (enabled["type"], enabled["value"], enabled["is_set"]) == (
        "bool",
        False,
        False,
    )
    assert (
        enabled["label"] == {"es": "Trading automático"} and enabled["confirm"] is True
    )
    account = fields["trader.trading.account"]
    assert account["choices"] == ["demo", "real"] and account["confirm"] == ["real"]
    limit = fields["trader.trading.max_order_usd"]
    assert (limit["type"], limit["value"], limit["min"]) == ("integer", 200, 1)
    assert fields["trader.goals.watchlist"]["type"] == "text"
    assert client.get("/api/skills/settings/nope").status_code == 404


def test_safe_changes_save_at_once_and_keep_the_rest_of_the_config(client, home):
    resp = client.put(
        "/api/skills/settings/trader",
        json={
            "values": {
                "trader.trading.max_order_usd": "50",
                "trader.goals.watchlist": "AAPL, BTC",
                "trader.trading.account": "demo",
            }
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["changed"] == [
        "trader.goals.watchlist",
        "trader.trading.max_order_usd",
    ]
    stored = _stored(home)
    assert stored["model"] == {"default": "some-model"}
    trader = stored["skills"]["config"]["trader"]
    # Lowering a limit needs no confirmation; an untouched default is never pinned.
    assert trader["trading"] == {"max_order_usd": 50}
    assert trader["goals"] == {"watchlist": "AAPL, BTC"}


@pytest.mark.parametrize(
    "values",
    [
        {"trader.trading.enabled": True},
        {"trader.trading.account": "real"},
        {"trader.trading.max_order_usd": 500},
    ],
)
def test_risky_changes_wait_for_the_users_confirmation(client, home, values):
    before = (home / "config.yaml").read_text(encoding="utf-8")
    resp = client.put("/api/skills/settings/trader", json={"values": values})
    assert resp.status_code == 409
    assert resp.json()["needs_confirmation"] == list(values)
    assert (home / "config.yaml").read_text(encoding="utf-8") == before

    resp = client.put(
        "/api/skills/settings/trader", json={"values": values, "confirm": True}
    )
    assert resp.status_code == 200 and resp.json()["changed"] == list(values)
    key, value = next(iter(values.items()))
    node = _stored(home)["skills"]["config"]
    for part in key.split("."):
        node = node[part]
    assert node == value


@pytest.mark.parametrize(
    "values",
    [
        {"trader.trading.max_order_usd": 0},
        {"trader.trading.max_order_usd": "lots"},
        {"trader.trading.max_order_usd": 10.5},
        {"trader.trading.account": "margin"},
        {"trader.trading.enabled": "maybe"},
        {"trader.goals.watchlist": "AAPL\nrm -rf"},
        {"model.default": "other"},
    ],
)
def test_values_the_declaration_does_not_accept_are_refused(client, home, values):
    before = (home / "config.yaml").read_text(encoding="utf-8")
    resp = client.put(
        "/api/skills/settings/trader", json={"values": values, "confirm": True}
    )
    assert resp.status_code == 400
    assert (home / "config.yaml").read_text(encoding="utf-8") == before
