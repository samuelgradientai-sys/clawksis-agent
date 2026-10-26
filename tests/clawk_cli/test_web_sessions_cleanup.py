"""POST /api/sessions/cleanup acts on the NAMED profile's store and never deletes a live chat.

The dashboard's "Limpiar" dialog used to open the launch profile's ``state.db`` whatever the
profile switcher said, so a cleanup previewed while managing one profile deleted another
profile's sessions; and its coarse filters (``source=telegram``) matched the chat a gateway was
answering at that moment.
"""

import time

import pytest
import clawk_yaml as yaml


@pytest.fixture
def homes(monkeypatch, _isolate_clawk_home):
    from clawk_cli import profiles
    from clawk_constants import get_clawk_home

    launch = get_clawk_home()
    beta = launch / "profiles" / "beta"
    for home in (launch, beta):
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text(
            yaml.safe_dump({"model": {"default": "m"}}), encoding="utf-8"
        )
    monkeypatch.setattr(profiles, "_get_default_clawk_home", lambda: launch)
    monkeypatch.setattr(profiles, "_get_profiles_root", lambda: launch / "profiles")
    return {"launch": launch, "beta": beta}


@pytest.fixture
def client(monkeypatch, homes):
    from starlette.testclient import TestClient

    import clawk_state
    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app

    monkeypatch.setattr(clawk_state, "DEFAULT_DB_PATH", homes["launch"] / "state.db")
    test_client = TestClient(app)
    test_client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return test_client


def _seed(home, rows):
    """rows: (session id, source, seconds since last activity, ended)."""
    import sqlite3

    from clawk_state import SessionDB

    db = SessionDB(db_path=home / "state.db")
    try:
        for sid, source, _age, ended in rows:
            db.create_session(sid, source=source)
            db.append_message(sid, role="user", content="hi")
            if ended:
                db.end_session(sid, "user_exit")
    finally:
        db.close()
    conn = sqlite3.connect(home / "state.db")
    try:
        for sid, _source, age, _ended in rows:
            ts = time.time() - age
            conn.execute("UPDATE sessions SET started_at = ? WHERE id = ?", (ts, sid))
            conn.execute(
                "UPDATE messages SET timestamp = ? WHERE session_id = ?", (ts, sid)
            )
        conn.commit()
    finally:
        conn.close()


def _ids(home):
    from clawk_state import SessionDB

    db = SessionDB(db_path=home / "state.db")
    try:
        return {
            row["id"] for row in db.list_sessions_rich(limit=100, include_archived=True)
        }
    finally:
        db.close()


def test_cleanup_previews_and_deletes_only_the_named_profiles_sessions(client, homes):
    _seed(
        homes["launch"],
        [
            ("launch-cli", "cli", 3 * 86400, True),
            ("launch-cli-2", "cli", 4 * 86400, True),
        ],
    )
    _seed(
        homes["beta"],
        [
            ("beta-cli", "cli", 3 * 86400, True),
            ("beta-tg", "telegram", 3 * 86400, True),
        ],
    )

    preview = client.post(
        "/api/sessions/cleanup",
        json={"source": "cli", "profile": "beta", "dry_run": True},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["matched"] == 1

    deleted = client.post(
        "/api/sessions/cleanup",
        json={"source": "cli", "profile": "beta", "dry_run": False},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 1
    assert _ids(homes["beta"]) == {"beta-tg"}
    assert _ids(homes["launch"]) == {"launch-cli", "launch-cli-2"}


def test_cleanup_never_matches_a_session_with_live_activity(client, homes):
    _seed(
        homes["launch"],
        [
            ("live-chat", "telegram", 10, False),
            ("stale-chat", "telegram", 3 * 86400, False),
        ],
    )

    preview = client.post(
        "/api/sessions/cleanup", json={"source": "telegram", "dry_run": True}
    ).json()
    assert (preview["matched"], preview["skipped_active"]) == (1, 1)

    result = client.post(
        "/api/sessions/cleanup", json={"source": "telegram", "dry_run": False}
    )
    assert result.status_code == 200, result.text
    assert _ids(homes["launch"]) == {"live-chat"}
