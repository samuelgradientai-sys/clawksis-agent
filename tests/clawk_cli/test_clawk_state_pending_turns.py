"""Tests for the durable pending-turn journal in clawk_state (resilience)."""

import time

import pytest

from clawk_state import SessionDB


@pytest.fixture
def db(tmp_path):
    return SessionDB(tmp_path / "state.db")


def test_record_and_list(db):
    db.record_pending_turn("s1", "hola", history_version=3, started_at=1000.0)
    rows = db.list_pending_turns()
    assert len(rows) == 1
    r = rows[0]
    assert r["session_id"] == "s1"
    assert r["prompt"] == "hola"
    assert r["history_version"] == 3
    assert r["started_at"] == 1000.0
    assert r["status"] == "pending"


def test_record_is_upsert(db):
    db.record_pending_turn("s1", "v1", started_at=1.0)
    db.record_pending_turn("s1", "v2", started_at=2.0)
    rows = db.list_pending_turns()
    assert len(rows) == 1
    assert rows[0]["prompt"] == "v2"


def test_clear(db):
    db.record_pending_turn("s1", "x")
    db.clear_pending_turn("s1")
    assert db.list_pending_turns() == []
    # Clearing a non-existent marker is a no-op.
    db.clear_pending_turn("nope")


def test_list_freshness_window(db):
    now = time.time()
    db.record_pending_turn("fresh", "f", started_at=now - 10)
    db.record_pending_turn("stale", "s", started_at=now - 100_000)
    fresh_ids = [r["session_id"] for r in db.list_pending_turns(max_age_seconds=3600)]
    assert "fresh" in fresh_ids
    assert "stale" not in fresh_ids
    # Without a window, both are returned.
    assert len(db.list_pending_turns()) == 2


def test_list_ordered_newest_first(db):
    db.record_pending_turn("a", "a", started_at=100.0)
    db.record_pending_turn("b", "b", started_at=200.0)
    db.record_pending_turn("c", "c", started_at=150.0)
    order = [r["session_id"] for r in db.list_pending_turns()]
    assert order == ["b", "c", "a"]


def test_table_recreated_on_legacy_db(tmp_path):
    path = tmp_path / "state.db"
    db = SessionDB(path)
    db.record_pending_turn("s1", "x")
    # Simulate a legacy DB that predates the table.
    db._conn.execute("DROP TABLE pending_turns")
    db._conn.commit()
    try:
        db.close()
    except Exception:
        pass
    # Reopening runs CREATE TABLE IF NOT EXISTS -> the table is recreated.
    db2 = SessionDB(path)
    assert db2.list_pending_turns() == []
    db2.record_pending_turn("s2", "y")
    assert len(db2.list_pending_turns()) == 1
