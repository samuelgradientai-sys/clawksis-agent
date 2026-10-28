"""Chat-mode cron jobs run as a message in their chat, not as an isolated background agent.

The user's ask: a scheduled instruction should behave exactly like a message they send the agent
(same conversation, memory and tools, the answer lands in that chat). These tests pin that the
scheduler hands such jobs to the live gateway's chat-injection seam with the right chat and text,
records the run, and falls back to the normal isolated run whenever injection is not possible.
"""

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


@pytest.fixture
def injector(monkeypatch):
    calls = []

    def inject(**kwargs):
        calls.append(kwargs)
        return inject.accept

    inject.accept = True
    monkeypatch.setattr(chat, "_gateway_injector", lambda: inject)
    inject.calls = calls
    return inject


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


def test_a_due_chat_job_is_sent_to_its_chat_and_recorded(store, injector):
    job, execution_id = _fire(_job())
    assert chat.run_in_chat_if_wanted(job, cfg={}) is True

    (call,) = injector.calls
    assert call["plugin_id"] == "cron"
    assert call["origin"]["chat_id"] == "5846973344"
    assert "Escribe a mis leads" in call["content"]
    stored = jobs.get_job(job["id"])
    assert stored["last_status"] == "ok" and stored["last_run_at"]
    assert executions.get_execution(execution_id)["status"] == "completed"


@pytest.mark.parametrize("reason", ["no_gateway", "refused", "isolated_job"])
def test_anything_that_cannot_reach_the_chat_runs_isolated(
    store, injector, monkeypatch, reason
):
    if reason == "no_gateway":
        monkeypatch.setattr(chat, "_gateway_injector", lambda: None)
    elif reason == "refused":
        injector.accept = False
    job, execution_id = _fire(_job(run_in_chat=reason != "isolated_job"))

    assert chat.run_in_chat_if_wanted(job, cfg={}) is False
    assert jobs.get_job(job["id"])["last_run_at"] is None  # left for the isolated run
    assert executions.get_execution(execution_id)["status"] == "claimed"


def test_run_one_job_takes_the_chat_path_before_any_worker(
    store, injector, monkeypatch
):
    from cron import scheduler

    def no_worker(job):
        raise AssertionError("a chat-mode job must not start an isolated worker")

    monkeypatch.setattr(scheduler, "_launch_external_cron_worker", no_worker)
    job, _ = _fire(_job())
    assert scheduler.run_one_job(job) is True
    assert len(injector.calls) == 1


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


def test_the_injector_is_the_gateway_one_plugins_use(monkeypatch):
    from clawk_cli import plugins

    def inject(**kwargs):
        return True

    monkeypatch.setattr(
        plugins, "_published_gateway_message_injector", (object(), inject)
    )
    assert chat._gateway_injector() is inject
    monkeypatch.setattr(plugins, "_published_gateway_message_injector", None)
    assert chat._gateway_injector() is None
