"""A chained voice-conversation turn (surface ``voice``) reaches the model with the spoken-reply note.

The dashboard's voice mode transcribes the user in the browser and submits a normal turn with
``surface: "voice"`` + ``voice_turn: true``. The note rides that ONE turn's model input (the
persisted row stays the user's words), exactly like the HUD / GPT-Live notes beside it.
"""

from types import SimpleNamespace

import pytest


async def _authority(tmp_path, monkeypatch, answer):
    from gateway.config import GatewayConfig, Platform
    from gateway.session import SessionSource, SessionStore
    from gateway.session_authority import LiveSession, initialize_session_authority

    monkeypatch.setenv("CLAWK_HOME", str(tmp_path))
    store = SessionStore(tmp_path / "sessions", GatewayConfig())
    runner = SimpleNamespace(
        _session_db=store._db,
        session_store=store,
        _draining=False,
        _handle_message=answer,
        _adapter_for_source=lambda source: None,
    )
    authority = await initialize_session_authority(
        runner, profile_id="p", instance_id="owner"
    )
    store._db.create_session("s", source="telegram")
    authority.sessions["s"] = LiveSession(
        SessionSource(platform=Platform.TELEGRAM, chat_id="c"), "s"
    )
    return authority


async def _submit(connection, rid, **params):
    return await connection.dispatch(
        {
            "id": rid,
            "method": "prompt.submit",
            "params": {"session_id": "s", "submission_id": rid, **params},
        }
    )


@pytest.mark.asyncio
async def test_voice_surface_notes_only_its_own_turn(tmp_path, monkeypatch):
    from gateway.session_controls import AuthorityConnection
    from gateway.session_surface import surface_turn_note, surface_voice_turn
    from clawk_state_runtime import list_session_admissions
    from tools.tts_streaming import SPEECH_INTERRUPTED_NOTE, SPOKEN_REPLY_NOTE

    seen = []

    async def answer(event):
        note = surface_turn_note(SimpleNamespace(valid_tool_names=set()))
        seen.append((event.text, surface_voice_turn(), note))
        return "ok"

    authority = await _authority(tmp_path, monkeypatch, answer)
    connection = AuthorityConnection(authority, object(), {"user_id": "owner"})
    try:
        await connection.dispatch(
            {"id": "open", "method": "session.resume", "params": {"session_id": "s"}}
        )
        turns = (
            ("spoken", {"surface": "voice", "voice_turn": True}),
            ("barged", {"surface": "voice", "voice_turn": True, "interrupted": True}),
            ("typed", {}),
        )
        for rid, extra in turns:
            reply = await _submit(connection, rid, text=f"{rid} words", **extra)
            assert reply["result"]["status"] == "queued", reply
            await authority.sessions["s"].task
        smuggled = await _submit(
            connection, "smuggled", text="x", surface="voice", voice_context="User: x"
        )
        assert smuggled["error"]["message"] == "invalid_params", smuggled
    finally:
        await connection.close()

    rows = {
        row["request_id"]: row["payload"]
        for row in list_session_admissions(
            authority.db, session_id="s", pending_only=False
        )
    }
    assert rows["spoken"]["surface_v1"] == {"surface": "voice", "voice_turn": True}
    assert "surface_v1" not in rows["typed"] and "smuggled" not in rows
    assert seen == [
        ("spoken words", True, SPOKEN_REPLY_NOTE),
        ("barged words", True, f"{SPEECH_INTERRUPTED_NOTE}\n\n{SPOKEN_REPLY_NOTE}"),
        ("typed words", False, ""),
    ], (
        "the note is model input for the spoken turns only; the rows keep the user's words"
    )
