"""The "Hoy" page's AI-written summary of a day: a compact digest, one auxiliary call, a per-day cache.

The summary runs on the ``daily_summary`` auxiliary slot (``auxiliary.daily_summary`` in
config.yaml; ``auto`` = the main model). It is cached per profile and day under
``<home>/cache/today/<YYYY-MM-DD>.json`` with the activity fingerprint it was written from, so a
page load never pays for it twice and the page can say when the day has moved on since.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from clawk_cli.today_activity import DayWindow

logger = logging.getLogger(__name__)

TASK = "daily_summary"
SUMMARY_MAX_TOKENS = 900
SUMMARY_TIMEOUT_S = 120
_MAX_ITEMS = 14

_PROMPTS = {
    "es": (
        "Sos el asistente que resume la jornada de un agente de IA personal para su dueño. "
        "Con los datos del día (y nada más) escribí en español rioplatense, en primera persona "
        "como el agente: una primera línea de titular (máximo 12 palabras, sin punto final) y "
        "después de 3 a 6 viñetas cortas que empiecen con «- » sobre qué hice, qué desarrollé "
        "(archivos, skills, commits) y qué corrió solo (crons), mencionando fallas si las hubo. "
        "Concreto y sin relleno; no inventes nada que no esté en los datos; sin encabezados."
    ),
    "en": (
        "You summarize a personal AI agent's day for its owner. Using only the day's data, write "
        "in English, first person as the agent: a one-line headline (at most 12 words, no final "
        "period) followed by 3 to 6 short bullets starting with '- ' covering what I did, what I "
        "built (files, skills, commits) and what ran on its own (cron), naming failures if any. "
        "Concrete, no filler, nothing that is not in the data, no headings."
    ),
}


class SummaryUnavailable(RuntimeError):
    """No auxiliary model could write the summary; the message is safe to show."""


def prompt_language(lang: Optional[str]) -> str:
    return "es" if (lang or "").lower().startswith("es") else "en"


# ── cache ────────────────────────────────────────────────────────────────────


def cache_path(home: Path, day: str) -> Path:
    return home / "cache" / "today" / f"{day}.json"


def read_cached(home: Path, day: str) -> Optional[dict]:
    try:
        data = json.loads(cache_path(home, day).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        logger.warning("Hoy: unreadable summary cache for %s", day, exc_info=True)
        return None
    return (
        data if isinstance(data, dict) and isinstance(data.get("text"), str) else None
    )


def write_cached(home: Path, day: str, summary: dict) -> None:
    from clawk_constants import mkdir_under_clawk_home
    from utils import atomic_json_write

    path = cache_path(home, day)
    mkdir_under_clawk_home(path.parent)
    atomic_json_write(path, summary)


def with_staleness(summary: Optional[dict], fingerprint: str) -> Optional[dict]:
    if summary is None:
        return None
    return {**summary, "stale": summary.get("fingerprint") != fingerprint}


# ── digest ───────────────────────────────────────────────────────────────────


def _clock(ts: Optional[float], window: DayWindow) -> str:
    if not ts:
        return "--:--"
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(window.tz) if window.tz else None
    return datetime.fromtimestamp(ts, tz=zone).strftime("%H:%M")


def _conversation_lines(data: dict, window: DayWindow) -> list[str]:
    lines = []
    for c in data["conversations"][-_MAX_ITEMS:]:
        tools = ", ".join(f"{name}×{n}" for name, n in c["top_tools"])
        lines.append(
            f"- {_clock(c['started_at'], window)} [{c['source'] or '?'}] "
            f"{c['title'] or '(sin título)'} | pedido: {c['ask'][:160] or '-'} | "
            f"respuesta: {c['outcome'][:160] or '-'} | herramientas: {tools or '-'}"
            + (f" | errores: {c['errors']}" if c["errors"] else "")
        )
    return lines


def _work_lines(data: dict) -> list[str]:
    lines = [
        f"- archivo {f['action']}: {f['path']}" for f in data["files"][:_MAX_ITEMS]
    ]
    lines += [f"- skill {s['action']}: {s['name']}" for s in data["skills"]]
    lines += [
        f"- commit en {c['repo_name']}: {c['subject'][:120]}"
        for c in data["commits"][:_MAX_ITEMS]
    ]
    lines += [
        f"- cron nuevo: {j['name']} ({j['schedule']})"
        for j in data["cron_jobs_created"]
    ]
    lines += [f"- comando: {c['command'][:120]}" for c in data["commands"][-6:]]
    return lines


def _cron_lines(data: dict, window: DayWindow) -> list[str]:
    return [
        f"- {_clock(r['at'], window)} cron «{r['job_name']}»: {r['status']}"
        + (f" ({r['error'][:140]})" if r.get("error") else "")
        for r in data["cron_runs"][-_MAX_ITEMS:]
    ]


def build_digest(data: dict, window: DayWindow) -> str:
    """The day's facts as compact text for the summary prompt."""
    s = data["stats"]
    sections = [
        f"Fecha: {window.date}",
        f"Totales: {s['conversations']} conversaciones, {s['messages']} mensajes, "
        f"{s['tool_calls']} usos de herramientas, {s['files_created']} archivos nuevos, "
        f"{s['files_edited']} editados, {s['commands']} comandos, cron {s['cron_ok']} ok / "
        f"{s['cron_failed']} fallidos, {s['skills_created']} skills nuevas, "
        f"{s['skills_updated']} actualizadas, {s['errors']} errores de herramientas.",
        "Conversaciones:",
        *(_conversation_lines(data, window) or ["- ninguna"]),
        "Trabajo hecho:",
        *(_work_lines(data) or ["- nada registrado"]),
        "Crons:",
        *(_cron_lines(data, window) or ["- ninguno"]),
    ]
    return "\n".join(sections)


# ── generation ───────────────────────────────────────────────────────────────


def _reply_text(response: Any) -> str:
    try:
        return (response.choices[0].message.content or "").strip()
    except (AttributeError, IndexError, TypeError):
        return ""


def generate(data: dict, window: DayWindow, lang: Optional[str]) -> dict:
    """Write the summary with the auxiliary model; raises SummaryUnavailable when none answers."""
    from agent.auxiliary_client import call_llm

    language = prompt_language(lang)
    route: dict[str, str] = {}
    try:
        response = call_llm(
            task=TASK,
            messages=[
                {"role": "system", "content": _PROMPTS[language]},
                {"role": "user", "content": build_digest(data, window)},
            ],
            max_tokens=SUMMARY_MAX_TOKENS,
            timeout=SUMMARY_TIMEOUT_S,
            reasoning_config={"enabled": False},
            route_info=route,
        )
    except Exception as exc:  # health: allow BLE001 -- any provider failure means "no summary"; the page renders without it
        logger.warning("Hoy: daily summary generation failed: %s", exc, exc_info=True)
        raise SummaryUnavailable(str(exc) or type(exc).__name__) from exc
    text = _reply_text(response)
    if not text:
        raise SummaryUnavailable("the model returned an empty summary")
    return {
        "text": text,
        "lang": language,
        "model": route.get("model") or str(getattr(response, "model", "") or ""),
        "generated_at": time.time(),
        "fingerprint": data["fingerprint"],
    }
