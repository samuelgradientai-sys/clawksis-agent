"""Chat-mode cron jobs: the scheduled instruction lands in the user's own chat as if they had sent it.

A normal agent job runs in a fresh, isolated ``AIAgent`` (no conversation, no long-term memory, no
``messaging``/``clarify`` tools) and only its final answer is delivered. A job with ``run_in_chat``
(or every agent job when ``cron.run_in_chat: true``) instead hands its prompt to the live gateway,
which runs it as a normal turn of the target chat's session: same conversation, memory, tools and
skills as a message the user typed, and the agent answers right there, where the user can follow up.

Only the gateway process can do this (the turn runs on its adapters). Whenever the injection is not
possible — no live gateway in this process, the target is not a messaging chat, or the gateway
refuses the route — the job falls back to the isolated run, so a scheduled task is never skipped.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("cron.scheduler")

PLUGIN_ID = "cron"
_NOT_CHATS = {"local", "bot-chat", "api_server", "webhook", "cron"}


def wants_chat_turn(job: dict, cfg: Optional[dict] = None) -> bool:
    """True when this agent job should run inside its chat instead of an isolated session.

    The job's own ``run_in_chat`` wins; unset, ``cron.run_in_chat`` in config.yaml decides.
    Script-only (``no_agent``) jobs never do: they have no prompt for the agent.
    """
    if job.get("no_agent"):
        return False
    if job.get("browser") == "server":
        # A turn in the chat drives the user's Chrome when it is connected; a job that must stay
        # on the server's browser runs as its own background task instead.
        return False
    explicit = job.get("run_in_chat")
    if isinstance(explicit, bool):
        return explicit
    cron_cfg = (cfg or {}).get("cron") or {}
    return cron_cfg.get("run_in_chat") is True


def default_run_in_chat() -> Optional[bool]:
    """``True`` when config.yaml's ``cron.run_in_chat`` makes chat mode the default for new jobs.

    New jobs store it explicitly, so the dashboard shows what the job will really do."""
    try:
        from clawk_cli.config import load_config

        cron_cfg = (load_config() or {}).get("cron") or {}
    except (OSError, ValueError):
        logger.debug(
            "cron.run_in_chat unreadable; new jobs keep the default", exc_info=True
        )
        return None
    return True if cron_cfg.get("run_in_chat") is True else None


def chat_origin(job: dict) -> Optional[dict[str, Any]]:
    """The chat the turn runs in: the job's first delivery target, when it is a messaging chat.

    The stored ``origin`` (the chat the job was created from) supplies the sender identity when it
    is the same chat, so the gateway authorizes the turn exactly as it would the user's own message.
    """
    from cron.scheduler_delivery import _resolve_delivery_targets

    try:
        targets = _resolve_delivery_targets(job)
    except Exception:
        logger.debug(
            "Job '%s': no delivery target for a chat turn", job.get("id"), exc_info=True
        )
        return None
    if not targets:
        return None
    target = targets[0]
    platform = str(target.get("platform") or "").strip().lower()
    chat_id = str(target.get("chat_id") or "").strip()
    if not platform or not chat_id or platform in _NOT_CHATS:
        return None
    origin: dict[str, Any] = {
        "platform": platform,
        "chat_id": chat_id,
        "thread_id": target.get("thread_id"),
    }
    stored = job.get("origin") if isinstance(job.get("origin"), dict) else {}
    if (
        str(stored.get("platform") or "").lower() == platform
        and str(stored.get("chat_id") or "") == chat_id
    ):
        for key in ("chat_type", "chat_name", "user_id", "user_name", "scope_id"):
            if stored.get(key) not in (None, ""):
                origin[key] = stored[key]
    origin.setdefault("chat_type", "dm")
    if origin["chat_type"] == "dm":
        origin.setdefault("user_id", chat_id)
    return origin


def chat_prompt(job: dict, extra_prompt: Optional[str] = None) -> str:
    """What the user would have typed: the task's name and instruction, plus its skills and notes."""
    name = str(job.get("name") or job.get("id") or "").strip()
    lines = [f"⏰ Tarea programada «{name}»:" if name else "⏰ Tarea programada:"]
    prompt = str(job.get("prompt") or "").strip()
    if prompt:
        lines.append(prompt)
    skills = [str(s).strip() for s in (job.get("skills") or []) if str(s).strip()]
    if not skills and str(job.get("skill") or "").strip():
        skills = [str(job["skill"]).strip()]
    if skills:
        lines.append("Usa la skill: " + ", ".join(skills) + ".")
    if extra_prompt and str(extra_prompt).strip():
        lines.append(str(extra_prompt).strip())
    return "\n\n".join(lines)


def _gateway_host():
    """The live gateway runner in this process (the host plugins inject through), or None."""
    from clawk_cli import plugins

    with plugins._published_gateway_host_lock:
        host = plugins._published_gateway_message_injector
    return host[0] if host else None


def _session_key_for_chat(owner, origin: dict[str, Any]) -> Optional[str]:
    """The existing gateway session of this chat, so the turn continues it with the exact sender
    identity of the user's own messages (the session authority refuses a look-alike source)."""
    want = (origin["platform"], str(origin["chat_id"]), origin.get("thread_id") or None)
    for entry in owner.session_store.list_sessions():
        source = getattr(entry, "origin", None)
        if source is None:
            continue
        platform = getattr(source.platform, "value", source.platform)
        have = (str(platform), str(source.chat_id), source.thread_id or None)
        if have == want:
            return entry.session_key
    return None


DISPATCH_WAIT_SECONDS = 60


def _wait_on_gateway(owner, coro) -> bool:
    """Run a gateway dispatch coroutine on its loop and wait for the real answer.

    Waiting matters: the gateway can still refuse the turn after accepting the request (its
    session authority checks the route), and a refused task must run isolated, not be recorded
    as done. A dispatch still busy after the wait already started its turn."""
    future = asyncio.run_coroutine_threadsafe(coro, owner._gateway_loop)
    try:
        return bool(future.result(timeout=DISPATCH_WAIT_SECONDS))
    except concurrent.futures.TimeoutError:
        logger.warning(
            "Chat dispatch still running after %ss; leaving it to finish",
            DISPATCH_WAIT_SECONDS,
        )
        return True
    except Exception:
        logger.warning("Chat dispatch failed; the job runs isolated", exc_info=True)
        return False


def inject_chat_turn(job: dict, extra_prompt: Optional[str] = None) -> bool:
    """Run the job as a turn of its chat on the live gateway; False when that did not happen."""
    origin = chat_origin(job)
    owner = _gateway_host()
    if origin is None or owner is None or getattr(owner, "_gateway_loop", None) is None:
        return False
    from clawk_constants import get_clawk_home

    home = Path(get_clawk_home())
    content = chat_prompt(job, extra_prompt)
    session_key = _session_key_for_chat(owner, origin)
    if session_key:
        coro = owner._dispatch_plugin_message_injection(
            session_key=session_key,
            content=content,
            plugin_id=PLUGIN_ID,
            plugin_home=home,
        )
    else:
        source = owner._plugin_origin_source(
            origin, plugin_home=home, plugin_id=PLUGIN_ID
        )
        if source is None:
            return False
        coro = owner._dispatch_plugin_origin_injection(
            source=source, content=content, plugin_id=PLUGIN_ID
        )
    return _wait_on_gateway(owner, coro)


def run_in_chat_if_wanted(
    job: dict, *, cfg: Optional[dict] = None, extra_prompt: Optional[str] = None
) -> bool:
    """Run a chat-mode job by injecting it into its chat and record the run; True when handled.

    False (nothing recorded) leaves the caller to run the job the isolated way.
    """
    from cron.executions import finish_execution, mark_execution_running
    from cron.jobs import mark_job_run, save_job_output

    if cfg is None:
        from cron import scheduler as _sched

        try:
            cfg = _sched.load_config() or {}
        except (OSError, ValueError):
            logger.debug(
                "config unreadable; chat mode follows the job only", exc_info=True
            )
            cfg = {}
    if not wants_chat_turn(job, cfg):
        return False
    if extra_prompt is None and job.get("manual_run_at"):
        extra_prompt = job.get("manual_run_prompt") or None
    if not inject_chat_turn(job, extra_prompt):
        logger.info(
            "Job '%s': could not run inside its chat; running it as an isolated task instead",
            job.get("id"),
        )
        return False

    job_id = job["id"]
    execution_id = str(job.get("execution_id") or "")
    note = (
        "Sent to the chat as a message from you; the agent runs it in that conversation "
        "and answers there."
    )
    claim = job.get("fire_claim")
    owner = str(claim.get("by") or "") if isinstance(claim, dict) else ""
    try:
        save_job_output(
            job_id,
            f"# {job.get('name') or job_id}\n\n{note}\n\n{chat_prompt(job, extra_prompt)}\n",
        )
    except Exception:
        logger.debug("Job '%s': chat-mode output note not saved", job_id, exc_info=True)
    try:
        mark_job_run(
            job_id,
            True,
            **({"expected_fire_owner": owner} if owner else {}),
            **({"execution_id": execution_id} if execution_id else {}),
        )
    finally:
        if execution_id:
            mark_execution_running(execution_id)
            finish_execution(execution_id, success=True, delivery_outcome="delivered")
    logger.info("Job '%s': handed to its chat as a message", job_id)
    return True
