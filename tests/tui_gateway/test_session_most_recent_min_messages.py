"""The web chat boots into the most recent session; opening the dashboard's Terminal tab starts
an empty session every time, so without a filter the chat reopened an empty session instead of
the user's last conversation. ``session.most_recent`` takes ``min_messages`` for that."""

from tui_gateway import server


class _DB:
    def list_sessions_rich(self, **kwargs):
        return [
            {"id": "empty-tui", "source": "tui", "started_at": 200, "message_count": 0},
            {
                "id": "real-chat",
                "source": "dashboard",
                "started_at": 100,
                "message_count": 4,
            },
        ]


def _most_recent(monkeypatch, params):
    monkeypatch.setattr(server, "_get_db", lambda: _DB())
    resp = server.handle_request(
        {"id": "1", "method": "session.most_recent", "params": params}
    )
    return resp["result"]["session_id"]


def test_min_messages_skips_empty_sessions(monkeypatch):
    assert _most_recent(monkeypatch, {"min_messages": 1}) == "real-chat"


def test_without_min_messages_the_newest_session_wins(monkeypatch):
    assert _most_recent(monkeypatch, {}) == "empty-tui"
