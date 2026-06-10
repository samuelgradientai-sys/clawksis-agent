"""``mirofish`` — drive a MiroFish multi-agent social-simulation server.

Unlike the coding-CLI tools, MiroFish (https://github.com/666ghj/MiroFish) is
NOT a prompt-in / code-out CLI. It is a Flask service (default
``http://localhost:5001``) that runs an OASIS-based "swarm" simulation: you give
it source documents + a natural-language *simulation requirement*, and it builds
a knowledge graph, generates hundreds of agent personas, runs them on simulated
Twitter/Reddit for N rounds, and produces a Markdown analysis report. It is an
inherently long-running, multi-stage async job.

This tool wraps the MiroFish ``/api/{graph,simulation,report}`` REST API:

* ``action="simulate"`` (default) runs the whole pipeline end-to-end —
  ontology → graph build → prepare personas → run → report — blocking up to
  ``timeout`` seconds and returning the final report. If it doesn't finish in
  time it returns the ``simulation_id`` and latest status so you can resume with
  ``action="status"`` / ``action="report"``.
* ``action="status"`` returns run progress for a ``simulation_id``.
* ``action="report"`` generates (if needed) and fetches the Markdown report.
* ``action="interview"`` broadcasts a question to every simulated agent.

The toolset is off by default and only appears when a MiroFish server answers
``/health`` at the configured base URL (env ``MIROFISH_BASE_URL`` or the
localhost default). Stand up the MiroFish Docker stack first, then enable it in
``clawk tools`` → MiroFish.

NOTE: the MiroFish server itself needs its own ``LLM_API_KEY`` and
``ZEP_API_KEY`` configured — those live on the MiroFish side, not here. Field
names below track MiroFish's current API blueprints; the tool surfaces raw
server responses so any drift is easy to spot.
"""

from __future__ import annotations

import os
import time
import urllib.request

from tools.registry import registry, tool_result

DEFAULT_BASE_URL = "http://localhost:5001"
# A full simulation can take many minutes; bounded so a stuck run still returns.
DEFAULT_TIMEOUT = 900
MAX_TIMEOUT = 3600
_POLL_INTERVAL = 5


def _base_url(args) -> str:
    raw = (args.get("base_url") or os.environ.get("MIROFISH_BASE_URL") or "").strip()
    return (raw or DEFAULT_BASE_URL).rstrip("/")


def _server_alive(base_url: str, timeout: float = 1.5) -> bool:
    """Cheap liveness probe for ``check_fn`` (stdlib only — no requests dep)."""
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _check_mirofish_available() -> bool:
    base = (os.environ.get("MIROFISH_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    return _server_alive(base)


def _eff_timeout(args) -> int:
    try:
        val = int(args.get("timeout")) if args.get("timeout") else DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        val = DEFAULT_TIMEOUT
    return max(30, min(val, MAX_TIMEOUT))


# ── pipeline stages ──────────────────────────────────────────────────────────


def _run_simulate(rq, base, args, deadline):
    """Drive the full ontology → build → prepare → run → report pipeline."""
    requirement = (args.get("simulation_requirement") or "").strip()
    if not requirement:
        return tool_result(
            ok=False,
            cli="mirofish",
            error="`simulation_requirement` is required for action='simulate'.",
        )

    project_name = (args.get("project_name") or "clawksis-sim").strip()
    documents = args.get("documents") or []
    if isinstance(documents, str):
        documents = [documents]

    # Stage 1 — ontology from uploaded docs + the requirement.
    open_files = []
    try:
        files = []
        for path in documents:
            if not os.path.isfile(path):
                return tool_result(
                    ok=False, cli="mirofish", error=f"document not found: {path}"
                )
            fh = open(path, "rb")
            open_files.append(fh)
            files.append(("files", (os.path.basename(path), fh)))
        status, body = rq(
            "POST",
            f"{base}/api/graph/ontology/generate",
            files=files or None,
            data={"simulation_requirement": requirement, "project_name": project_name},
        )
    finally:
        for fh in open_files:
            try:
                fh.close()
            except Exception:
                pass
    if not (200 <= status < 300):
        return _stage_error("ontology/generate", status, body)
    project_id = _pick(body, "project_id", "projectId", "id")
    if not project_id:
        return _stage_error("ontology/generate (no project_id)", status, body)

    # Stage 2 — build the graph (async task).
    status, body = rq(
        "POST",
        f"{base}/api/graph/build",
        json={"project_id": project_id, "force": False},
    )
    if not (200 <= status < 300):
        return _stage_error("graph/build", status, body)
    task_id = _pick(body, "task_id", "taskId")
    graph_id = _pick(body, "graph_id", "graphId")
    if task_id and not graph_id:
        ok, body = _poll(
            rq,
            "GET",
            f"{base}/api/graph/task/{task_id}",
            deadline=deadline,
            done=lambda b: (
                _pick(b, "status") in {"done", "completed", "success", "finished"}
            ),
        )
        if not ok:
            return _timeout_result(
                "graph build", {"project_id": project_id, "task_id": task_id}
            )
        graph_id = _pick(body, "graph_id", "graphId", "id") or graph_id

    # Stage 3 — create + prepare the simulation.
    status, body = rq(
        "POST",
        f"{base}/api/simulation/create",
        json={
            "project_id": project_id,
            "graph_id": graph_id,
            "enable_twitter": True,
            "enable_reddit": False,
        },
    )
    if not (200 <= status < 300):
        return _stage_error("simulation/create", status, body)
    sim_id = _pick(body, "simulation_id", "simulationId", "id")
    if not sim_id:
        return _stage_error("simulation/create (no simulation_id)", status, body)

    status, body = rq(
        "POST",
        f"{base}/api/simulation/prepare",
        json={"simulation_id": sim_id, "use_llm_for_profiles": True},
    )
    if 200 <= status < 300:
        prep_task = _pick(body, "task_id", "taskId")
        if prep_task:
            _poll(
                rq,
                "POST",
                f"{base}/api/simulation/prepare/status",
                json={"simulation_id": sim_id, "task_id": prep_task},
                deadline=deadline,
                done=lambda b: (
                    _pick(b, "status") in {"done", "completed", "ready", "prepared"}
                ),
            )

    # Stage 4 — run.
    max_rounds = args.get("max_rounds") or 20
    platform = (args.get("platform") or "twitter").strip()
    status, body = rq(
        "POST",
        f"{base}/api/simulation/start",
        json={"simulation_id": sim_id, "platform": platform, "max_rounds": max_rounds},
    )
    if not (200 <= status < 300):
        return _stage_error(
            "simulation/start", status, body, extra={"simulation_id": sim_id}
        )

    ran, _ = _poll(
        rq,
        "GET",
        f"{base}/api/simulation/{sim_id}/run-status",
        deadline=deadline,
        done=lambda b: (
            _pick(b, "status", "runner_status")
            in {"done", "completed", "finished", "stopped"}
        ),
    )
    if not ran:
        return _timeout_result("simulation run", {"simulation_id": sim_id})

    # Stage 5 — report.
    return _fetch_report(rq, base, sim_id, deadline, generate=True)


def _fetch_report(rq, base, sim_id, deadline, *, generate):
    if generate:
        status, body = rq(
            "POST", f"{base}/api/report/generate", json={"simulation_id": sim_id}
        )
        if 200 <= status < 300:
            rtask = _pick(body, "task_id", "taskId")
            if rtask:
                _poll(
                    rq,
                    "POST",
                    f"{base}/api/report/generate/status",
                    json={"simulation_id": sim_id, "task_id": rtask},
                    deadline=deadline,
                    done=lambda b: _pick(b, "status") in {"done", "completed", "ready"},
                )
    status, body = rq("GET", f"{base}/api/report/by-simulation/{sim_id}")
    if not (200 <= status < 300):
        return _stage_error(
            "report fetch", status, body, extra={"simulation_id": sim_id}
        )
    report_md = _pick(body, "content", "markdown", "report") or ""
    return tool_result(
        ok=True,
        cli="mirofish",
        simulation_id=sim_id,
        report=report_md if isinstance(report_md, str) else body,
        raw=None if isinstance(report_md, str) and report_md else body,
    )


def _run_status(rq, base, args):
    sim_id = (args.get("simulation_id") or "").strip()
    if not sim_id:
        return tool_result(
            ok=False, cli="mirofish", error="`simulation_id` is required."
        )
    status, body = rq("GET", f"{base}/api/simulation/{sim_id}/run-status")
    return tool_result(
        ok=200 <= status < 300,
        cli="mirofish",
        simulation_id=sim_id,
        status_code=status,
        status=body,
    )


def _run_interview(rq, base, args, deadline):
    sim_id = (args.get("simulation_id") or "").strip()
    prompt = (args.get("prompt") or "").strip()
    if not sim_id or not prompt:
        return tool_result(
            ok=False,
            cli="mirofish",
            error="`simulation_id` and `prompt` are required for action='interview'.",
        )
    status, body = rq(
        "POST",
        f"{base}/api/simulation/interview/all",
        json={"simulation_id": sim_id, "prompt": prompt},
    )
    return tool_result(
        ok=200 <= status < 300,
        cli="mirofish",
        simulation_id=sim_id,
        status_code=status,
        result=body,
    )


# ── small helpers ────────────────────────────────────────────────────────────


def _pick(body, *keys):
    if not isinstance(body, dict):
        return None
    # MiroFish sometimes wraps payloads in a "data" envelope.
    for container in (
        body,
        body.get("data") if isinstance(body.get("data"), dict) else {},
    ):
        for k in keys:
            if isinstance(container, dict) and container.get(k) not in (None, ""):
                return container[k]
    return None


def _poll(rq, method, url, *, deadline, done, json=None):
    """Poll *url* until ``done(body)`` or the deadline. Returns (ok, last_body)."""
    last = None
    while time.time() < deadline:
        status, body = rq(method, url, json=json)
        last = body
        if 200 <= status < 300 and done(body):
            return True, body
        if isinstance(body, dict) and _pick(body, "status") in {"error", "failed"}:
            return False, body
        time.sleep(_POLL_INTERVAL)
    return False, last


def _stage_error(stage, status, body, *, extra=None):
    payload = {
        "ok": False,
        "cli": "mirofish",
        "stage": stage,
        "status_code": status,
        "response": body,
    }
    if extra:
        payload.update(extra)
    return tool_result(payload)


def _timeout_result(stage, extra):
    payload = {
        "ok": False,
        "cli": "mirofish",
        "timed_out": True,
        "stage": stage,
        "note": "Stage exceeded the time budget; the job may still be running. "
        "Resume with action='status' or action='report'.",
    }
    payload.update(extra)
    return tool_result(payload)


def _make_requester():
    """Return a `rq(method, url, json=, data=, files=)` -> (status, body) closure.

    Lazily binds ``requests`` so the rest of the module imports even when the
    dependency is absent.
    """
    try:
        import requests
    except ImportError:
        return None

    def rq(method, url, *, json=None, data=None, files=None):
        try:
            resp = requests.request(
                method, url, json=json, data=data, files=files, timeout=60
            )
        except Exception as exc:  # network error — surface, don't crash
            return 0, {"error": f"{type(exc).__name__}: {exc}"}
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text

    return rq


MIROFISH_SCHEMA = {
    "name": "mirofish",
    "description": (
        "Run a MiroFish multi-agent social/opinion simulation and get a Markdown "
        "analysis report. MiroFish spawns hundreds of AI persona-agents from your "
        "source material and simulates how they react on social platforms — use it "
        "to forecast public reaction / sentiment / social dynamics around a topic, "
        "message, product, or document. This is a long-running async job (minutes), "
        "not an instant answer. Requires a running MiroFish server."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["simulate", "status", "report", "interview"],
                "description": (
                    "'simulate' (default) runs the full pipeline and returns the "
                    "report. 'status' checks a running simulation_id. 'report' "
                    "fetches/generates a finished report. 'interview' asks every "
                    "agent a question."
                ),
                "default": "simulate",
            },
            "simulation_requirement": {
                "type": "string",
                "description": (
                    "Natural-language description of what to simulate / study "
                    "(required for action='simulate')."
                ),
            },
            "documents": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Absolute paths to source documents (PDF/MD/TXT) to seed the "
                    "simulation. Optional but recommended."
                ),
            },
            "project_name": {
                "type": "string",
                "description": "Label for the simulation project. Default 'clawksis-sim'.",
            },
            "platform": {
                "type": "string",
                "enum": ["twitter", "reddit", "parallel"],
                "description": "Which simulated platform(s) to run. Default 'twitter'.",
                "default": "twitter",
            },
            "max_rounds": {
                "type": "integer",
                "description": "Number of simulation rounds (default 20; keep low — LLM-cost-heavy).",
                "minimum": 1,
            },
            "simulation_id": {
                "type": "string",
                "description": "Existing simulation id (for action='status'/'report'/'interview').",
            },
            "prompt": {
                "type": "string",
                "description": "Question to broadcast to agents (action='interview').",
            },
            "base_url": {
                "type": "string",
                "description": (
                    "MiroFish server base URL. Defaults to $MIROFISH_BASE_URL or "
                    "http://localhost:5001."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Overall budget in seconds (default 900, max 3600).",
                "minimum": 30,
            },
        },
        "required": [],
    },
}


def _handle_mirofish(args, **kw):
    base = _base_url(args)
    rq = _make_requester()
    if rq is None:
        return tool_result(
            ok=False,
            cli="mirofish",
            error="The MiroFish tool needs the `requests` package in the clawksis environment.",
        )
    if not _server_alive(base, timeout=3):
        return tool_result(
            ok=False,
            cli="mirofish",
            error=f"No MiroFish server responding at {base} (/health). Start the MiroFish stack first.",
        )

    deadline = time.time() + _eff_timeout(args)
    action = (args.get("action") or "simulate").strip()
    if action == "status":
        return _run_status(rq, base, args)
    if action == "report":
        sim_id = (args.get("simulation_id") or "").strip()
        if not sim_id:
            return tool_result(
                ok=False, cli="mirofish", error="`simulation_id` is required."
            )
        return _fetch_report(rq, base, sim_id, deadline, generate=True)
    if action == "interview":
        return _run_interview(rq, base, args, deadline)
    return _run_simulate(rq, base, args, deadline)


registry.register(
    name="mirofish",
    toolset="mirofish",
    schema=MIROFISH_SCHEMA,
    handler=_handle_mirofish,
    check_fn=_check_mirofish_available,
    emoji="🐟",
    max_result_size_chars=120_000,
)
