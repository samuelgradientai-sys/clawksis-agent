"""Tests for the durable pending-turn journal + crash-resume in tui_gateway."""

import types

import pytest

import tui_gateway.server as srv
from agent.resilience.runtime import install_resilience_runtime, reset_for_tests


class _FakeDB:
    def __init__(self, pending=None):
        self.recorded = []
        self.cleared = []
        self._pending = pending or []

    def record_pending_turn(self, key, prompt, hv, started):
        self.recorded.append((key, prompt, hv, started))

    def clear_pending_turn(self, key):
        self.cleared.append(key)

    def list_pending_turns(self, max_age_seconds=None):
        return list(self._pending)


class _SyncThread:
    """Thread stub that runs the target synchronously on start()."""

    def __init__(self, target=None, daemon=None):
        self._t = target

    def start(self):
        if self._t:
            self._t()


@pytest.fixture(autouse=True)
def _reset():
    reset_for_tests()
    yield
    reset_for_tests()


def _enable(monkeypatch, db):
    install_resilience_runtime(
        {"resilience": {"durable_turns": {"enabled": True, "freshness_seconds": 3600}}},
        force=True,
    )
    monkeypatch.setattr(srv, "_get_db", lambda: db)


def test_journal_written_and_cleared(monkeypatch):
    db = _FakeDB()
    _enable(monkeypatch, db)
    session = {"session_key": "sk1", "history_version": 2}
    srv._start_inflight_turn(session, "hola")
    assert db.recorded == [("sk1", "hola", 2, db.recorded[0][3])]
    srv._clear_inflight_turn(session)
    assert db.cleared == ["sk1"]


def test_journal_noop_when_disabled(monkeypatch):
    db = _FakeDB()
    install_resilience_runtime({"resilience": {}}, force=True)
    monkeypatch.setattr(srv, "_get_db", lambda: db)
    session = {"session_key": "sk1"}
    srv._start_inflight_turn(session, "hola")
    srv._clear_inflight_turn(session)
    assert db.recorded == []
    assert db.cleared == []


def test_resume_dispatches_and_clears(monkeypatch):
    db = _FakeDB(pending=[{"session_id": "sk1", "prompt": "haz X", "started_at": 1.0}])
    _enable(monkeypatch, db)
    monkeypatch.setattr(srv.time, "sleep", lambda s: None)
    monkeypatch.setattr(srv.threading, "Thread", _SyncThread)
    calls = []
    monkeypatch.setattr(
        srv,
        "_run_prompt_submit",
        lambda rid, sid, sess, text: calls.append((sid, text)),
    )
    session = {"session_key": "sk1", "running": False}
    srv._maybe_resume_pending_turn("sid1", session, "sk1")
    assert db.cleared == ["sk1"]  # cleared before re-dispatch
    assert len(calls) == 1
    assert calls[0][0] == "sid1"
    assert "haz X" in calls[0][1]  # original prompt in the resume note


def test_resume_noop_when_running(monkeypatch):
    db = _FakeDB(pending=[{"session_id": "sk1", "prompt": "x", "started_at": 1.0}])
    _enable(monkeypatch, db)
    calls = []
    monkeypatch.setattr(srv, "_run_prompt_submit", lambda *a: calls.append(a))
    session = {"session_key": "sk1", "running": True}
    srv._maybe_resume_pending_turn("sid1", session, "sk1")
    assert calls == []  # already running -> never re-dispatch


def test_resume_noop_when_no_match(monkeypatch):
    db = _FakeDB(pending=[{"session_id": "other", "prompt": "x", "started_at": 1.0}])
    _enable(monkeypatch, db)
    monkeypatch.setattr(srv.time, "sleep", lambda s: None)
    monkeypatch.setattr(srv.threading, "Thread", _SyncThread)
    calls = []
    monkeypatch.setattr(srv, "_run_prompt_submit", lambda *a: calls.append(a))
    session = {"session_key": "sk1", "running": False}
    srv._maybe_resume_pending_turn("sid1", session, "sk1")
    assert calls == []
    assert db.cleared == []  # nothing matched -> nothing cleared


def test_resume_noop_when_disabled(monkeypatch):
    db = _FakeDB(pending=[{"session_id": "sk1", "prompt": "x", "started_at": 1.0}])
    install_resilience_runtime({"resilience": {}}, force=True)
    monkeypatch.setattr(srv, "_get_db", lambda: db)
    calls = []
    monkeypatch.setattr(srv, "_run_prompt_submit", lambda *a: calls.append(a))
    session = {"session_key": "sk1", "running": False}
    srv._maybe_resume_pending_turn("sid1", session, "sk1")
    assert calls == []
    assert db.cleared == []


# `types` kept for parity with other gateway tests that stub namespaces.
_ = types
