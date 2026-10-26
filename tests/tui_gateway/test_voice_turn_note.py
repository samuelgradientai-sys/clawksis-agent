"""The TUI gateway (dashboard ``/api/ws``) path of a chained voice turn: ``surface: "voice"``.

The note is computed per turn from the session's ``client_surface`` and prepended to the MODEL
INPUT by ``prompt_turn`` (``_prepend_note``), so the system prompt and the persisted row stay
byte-identical; a later typed submit clears it.
"""

import threading
import types

import pytest

from tools.tts_streaming import SPOKEN_REPLY_NOTE
from tui_gateway import server


@pytest.fixture
def busy_session():
    session = {
        "agent": types.SimpleNamespace(valid_tool_names=set()),
        "session_key": "session-key",
        "history": [],
        "history_lock": threading.Lock(),
        "history_version": 0,
        "running": True,
        "transport": None,
        "attached_images": [],
    }
    server._sessions["sid"] = session
    yield session
    server._sessions.pop("sid", None)


def _submit(rid, **params):
    server._methods["prompt.submit"](
        rid, {"session_id": "sid", "queued": True, **params}
    )


def test_voice_surface_turn_carries_the_spoken_reply_note(busy_session):
    _submit("r1", text="qué hora es", surface="voice", voice_turn=True)

    assert busy_session["client_surface"] == "voice"
    assert busy_session["voice_turn"] is True
    assert server._hud_surface_note(busy_session) == SPOKEN_REPLY_NOTE
    assert server._prepend_note("qué hora es", SPOKEN_REPLY_NOTE) == (
        f"{SPOKEN_REPLY_NOTE}\n\nqué hora es"
    )


def test_the_chat_title_comes_from_the_words_not_the_note(monkeypatch):
    """The model input carries the note; the session title must not ("[Note: this message…")."""
    monkeypatch.setattr(server, "_emit", lambda *_a, **_k: None)
    monkeypatch.setattr(server, "_load_interim_assistant_messages", lambda: False)
    seen = {}

    def run_conversation(message, title_user_message=None, **_kwargs):
        seen.update(message=message, title=title_user_message)
        return {"final_response": "Son las diez."}

    agent = types.SimpleNamespace(run_conversation=run_conversation)
    session = {
        "pending_title": None,
        "session_key": "k",
        "history_lock": threading.Lock(),
        "agent": agent,
    }
    st = server._TurnRun(
        agent=agent,
        one_turn_restore=None,
        terminal_callback=None,
        receipt_committed=True,
    )
    noted = server._prepend_note("qué hora es", SPOKEN_REPLY_NOTE)

    server._invoke_agent("sid", session, st, "qué hora es", noted, None, [], None, None)

    assert seen == {"message": noted, "title": "qué hora es"}


def test_typed_submit_after_a_voice_turn_drops_the_note(busy_session):
    _submit("r1", text="hola", surface="voice", voice_turn=True)
    _submit("r2", text="y ahora escribo")

    assert busy_session["client_surface"] == ""
    assert busy_session["voice_turn"] is False
    assert server._hud_surface_note(busy_session) == ""
