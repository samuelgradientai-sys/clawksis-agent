"""Chat-mode cron jobs run as a message in their chat, not as an isolated background agent.

The user's ask: a scheduled instruction should behave exactly like a message they send the agent
(same conversation, memory and tools, the answer lands in that chat). These tests pin that the
scheduler hands such jobs to the live gateway's chat-injection seam with the right chat and text,
records the run, and falls back to the normal isolated run whenever injection is not possible.
"""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from cron import executions, jobs
from cron import scheduler_chat_turn as chat

ORIGIN = {
    "platform": "telegram",
    "chat_id": "5846973344",
    "chat_name": "Samuel",
    "thread_id": None,
    "user_id": "5846973344",
}


@pytest.fixture
def store(tmp_path):
    with jobs.use_cron_store(tmp_path / "cron"):
        yield


class FakeGateway:
    """The gateway runner seam the scheduler drives: its loop, session store and the two
    dispatch coroutines plugins use (keyed session / plain origin)."""

    def __init__(self, loop):
        self._gateway_loop = loop
        self.sessions = []
        self.accept = True
        self.calls = []
        self.session_store = SimpleNamespace(list_sessions=lambda: self.sessions)

    async def _dispatch_plugin_message_injection(self, **kwargs):
        self.calls.append(("session", kwargs))
        return self.accept

    def _plugin_origin_source(self, origin, *, plugin_home, plugin_id):
        return SimpleNamespace(**origin)

    async def _dispatch_plugin_origin_injection(self, **kwargs):
        self.calls.append(("origin", kwargs))
        return self.accept


@pytest.fixture
def gateway(monkeypatch):
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    runner = FakeGateway(loop)
    monkeypatch.setattr(chat, "_gateway_host", lambda: runner)
    yield runner
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    loop.close()


def _session(key="agent:main:telegram:dm:5846973344", chat_id="5846973344"):
    origin = SimpleNamespace(
        platform=SimpleNamespace(value="telegram"), chat_id=chat_id, thread_id=None
    )
    return SimpleNamespace(session_key=key, origin=origin)


def _job(**overrides):
    fields = dict(
        prompt="Escribe a mis leads de LinkedIn desde mi Chrome",
        schedule="every 1h",
        name="LinkedIn: mensajes",
        deliver="telegram:5846973344",
        origin=ORIGIN,
        skills=["linkedin-outreach"],
        run_in_chat=True,
    )
    fields.update(overrides)
    return jobs.create_job(**fields)


def _fire(job):
    execution = executions.create_execution(job["id"], source="test")
    return {**jobs.get_job(job["id"]), "execution_id": execution["id"]}, execution["id"]


def test_mode_follows_the_job_then_the_config():
    assert chat.wants_chat_turn({"run_in_chat": True}, {})
    assert not chat.wants_chat_turn(
        {"run_in_chat": False}, {"cron": {"run_in_chat": True}}
    )
    assert chat.wants_chat_turn({}, {"cron": {"run_in_chat": True}})
    assert not chat.wants_chat_turn({}, {})
    # A script-only job has no instruction for the agent.
    assert not chat.wants_chat_turn({"run_in_chat": True, "no_agent": True}, {})


def test_the_instruction_reads_like_the_users_message(store):
    job = _job()
    text = chat.chat_prompt(job, "Hoy solo 3 mensajes.")
    assert text.startswith("⏰ Tarea programada «LinkedIn: mensajes»:")
    assert "Escribe a mis leads de LinkedIn desde mi Chrome" in text
    assert "Usa la skill: linkedin-outreach." in text
    assert text.endswith("Hoy solo 3 mensajes.")


def test_the_chat_is_the_delivery_target_with_the_senders_identity(store):
    origin = chat.chat_origin(_job())
    assert origin["platform"] == "telegram" and origin["chat_id"] == "5846973344"
    assert origin["user_id"] == "5846973344" and origin["chat_type"] == "dm"
    # Nothing to talk to: local-only jobs keep the isolated run.
    assert chat.chat_origin(_job(deliver="local")) is None


def test_a_due_chat_job_continues_the_chats_own_session_and_is_recorded(store, gateway):
    gateway.sessions = [_session(chat_id="999"), _session()]
    job, execution_id = _fire(_job())
    assert chat.run_in_chat_if_wanted(job, cfg={}) is True

    ((kind, call),) = gateway.calls
    # The existing session, so the turn carries the exact identity of the user's own messages.
    assert kind == "session"
    assert call["session_key"] == "agent:main:telegram:dm:5846973344"
    assert call["plugin_id"] == "cron" and "Escribe a mis leads" in call["content"]
    stored = jobs.get_job(job["id"])
    assert stored["last_status"] == "ok" and stored["last_run_at"]
    assert executions.get_execution(execution_id)["status"] == "completed"


def test_a_chat_with_no_session_yet_is_opened_from_its_origin(store, gateway):
    job, _ = _fire(_job())
    assert chat.run_in_chat_if_wanted(job, cfg={}) is True
    ((kind, call),) = gateway.calls
    assert kind == "origin" and call["source"].chat_id == "5846973344"


@pytest.mark.parametrize("reason", ["no_gateway", "refused", "isolated_job"])
def test_anything_that_cannot_reach_the_chat_runs_isolated(
    store, gateway, monkeypatch, reason
):
    """Regression (28-oct 10:00): the session authority refused the turn after the request was
    accepted, and the job was recorded as done without running. A refusal now runs it isolated."""
    gateway.sessions = [_session()]
    if reason == "no_gateway":
        monkeypatch.setattr(chat, "_gateway_host", lambda: None)
    elif reason == "refused":
        gateway.accept = False
    job, execution_id = _fire(_job(run_in_chat=reason != "isolated_job"))

    assert chat.run_in_chat_if_wanted(job, cfg={}) is False
    assert jobs.get_job(job["id"])["last_run_at"] is None  # left for the isolated run
    assert executions.get_execution(execution_id)["status"] == "claimed"


def test_run_one_job_takes_the_chat_path_before_any_worker(store, gateway, monkeypatch):
    from cron import scheduler

    def no_worker(job):
        raise AssertionError("a chat-mode job must not start an isolated worker")

    monkeypatch.setattr(scheduler, "_launch_external_cron_worker", no_worker)
    gateway.sessions = [_session()]
    job, _ = _fire(_job())
    assert scheduler.run_one_job(job) is True
    assert len(gateway.calls) == 1


def test_new_jobs_store_the_configured_default(store, monkeypatch):
    monkeypatch.setattr(chat, "default_run_in_chat", lambda: True)
    from tools.cronjob_tools import cronjob

    import json

    created = json.loads(
        cronjob(
            action="create",
            prompt="Revisa mis cobros",
            schedule="every 1h",
            deliver="telegram:5846973344",
        )
    )
    assert jobs.get_job(created["job_id"])["run_in_chat"] is True
    json.loads(cronjob(action="update", job_id=created["job_id"], run_in_chat=False))
    assert jobs.get_job(created["job_id"])["run_in_chat"] is False


def test_the_gateway_host_is_the_one_plugins_inject_through(monkeypatch):
    from clawk_cli import plugins

    runner = object()
    monkeypatch.setattr(
        plugins, "_published_gateway_message_injector", (runner, lambda **kw: True)
    )
    assert chat._gateway_host() is runner
    monkeypatch.setattr(plugins, "_published_gateway_message_injector", None)
    assert chat._gateway_host() is None
