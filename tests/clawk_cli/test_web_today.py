"""The dashboard's "Hoy" page (``/api/analytics/today``): what the agent did on one day, per profile.

Pins the contract the page renders: only the requested calendar day and the requested profile are
counted, files/commands/skills come from the day's tool calls (a failed call is an error, not
work), child sessions fold into their conversation, cron runs come from the execution ledger, and
the AI summary is written once per day and cached until the user asks to regenerate it — with the
page still working when no auxiliary model answers.
"""

import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

DAY = "2026-03-10"


def _ts(day: int, hour: int, minute: int = 0) -> float:
    return datetime(2026, 3, day, hour, minute, tzinfo=UTC).timestamp()


def _call(call_id, name, **args):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _seed(home, sessions):
    """Create ``home/state.db`` through SessionDB, then pin each session's ``started_at``."""
    from clawk_state import SessionDB

    db = SessionDB(db_path=home / "state.db")
    try:
        for s in sessions:
            db.create_session(
                s["id"],
                s.get("source", "cli"),
                cwd=s.get("cwd"),
                parent_session_id=s.get("parent"),
            )
            for m in s["messages"]:
                db.append_message(
                    s["id"],
                    m["role"],
                    m.get("content"),
                    tool_calls=m.get("tool_calls"),
                    tool_call_id=m.get("tool_call_id"),
                    timestamp=m["at"],
                )
    finally:
        db.close()
    conn = sqlite3.connect(home / "state.db")
    with conn:
        for s in sessions:
            conn.execute(
                "UPDATE sessions SET started_at = ?, title = ? WHERE id = ?",
                (s["started_at"], s.get("title"), s["id"]),
            )
    conn.close()


def _chat(sid, day, *, title="Chat", ask="hola", source="cli", **extra):
    return {
        "id": sid,
        "source": source,
        "title": title,
        "started_at": _ts(day, 9),
        "messages": [
            {"role": "user", "content": ask, "at": _ts(day, 9, 1)},
            {
                "role": "assistant",
                "content": f"respuesta a {ask}",
                "at": _ts(day, 9, 2),
            },
        ],
        **extra,
    }


@pytest.fixture
def homes(tmp_path, monkeypatch, _isolate_clawk_home):
    from clawk_cli import profiles
    from clawk_constants import get_clawk_home

    default_home = get_clawk_home()
    profiles_root = default_home / "profiles"
    worker_home = profiles_root / "worker_alpha"
    for home in (default_home, worker_home):
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(profiles, "_get_default_clawk_home", lambda: default_home)
    monkeypatch.setattr(profiles, "_get_profiles_root", lambda: profiles_root)
    return {"default": default_home, "worker_alpha": worker_home}


@pytest.fixture
def client(monkeypatch, homes):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("fastapi/starlette not installed")

    import clawk_state
    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app

    monkeypatch.setattr(clawk_state, "DEFAULT_DB_PATH", homes["default"] / "state.db")
    c = TestClient(app)
    c.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return c


def _get(client, **params):
    resp = client.get(
        "/api/analytics/today", params={"date": DAY, "tz": "UTC", **params}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_only_the_requested_day_and_profile_are_counted(client, homes):
    _seed(
        homes["default"],
        [
            _chat("today-a", 10, title="Arreglar login", ask="arreglá el login"),
            _chat("today-b", 10, title="Armar informe", source="telegram"),
            _chat("yesterday", 9, title="Ayer"),
        ],
    )
    _seed(homes["worker_alpha"], [_chat("worker-today", 10, title="Del worker")])

    data = _get(client)
    assert [c["title"] for c in data["conversations"]] == [
        "Arreglar login",
        "Armar informe",
    ]
    assert data["stats"]["conversations"] == 2
    assert data["stats"]["messages"] == 4
    assert data["conversations"][0]["ask"] == "arreglá el login"
    assert data["conversations"][1]["source"] == "telegram"
    assert data["has_activity"] is True

    worker = _get(client, profile="worker_alpha")
    assert [c["title"] for c in worker["conversations"]] == ["Del worker"]

    quiet = _get(client, date="2026-03-12")
    assert quiet["conversations"] == [] and quiet["has_activity"] is False


def test_a_session_spanning_two_days_counts_only_the_days_messages(client, homes):
    s = _chat("long", 9, title="Larga")
    s["messages"] += [
        {"role": "user", "content": "seguimos", "at": _ts(10, 8)},
        {"role": "assistant", "content": "dale", "at": _ts(10, 8, 1)},
    ]
    child = {
        "id": "long-child",
        "parent": "long",
        "started_at": _ts(10, 8, 2),
        "messages": [
            {"role": "assistant", "content": "subtarea lista", "at": _ts(10, 8, 3)}
        ],
    }
    _seed(homes["default"], [s, child])

    data = _get(client)
    [conv] = data["conversations"]
    assert conv["id"] == "long" and conv["children"] == 1
    assert conv["open_id"] == "long-child"  # resume where the lineage is now
    assert conv["messages"] == 3 and conv["ask"] == "seguimos"
    assert conv["outcome"] == "subtarea lista"


def test_files_commands_and_skills_come_from_the_days_tool_calls(
    client, homes, tmp_path
):
    project = tmp_path / "proyecto"
    (project / ".git").mkdir(parents=True)
    calls = [
        _call("c1", "write_file", path="src/app.py", content="print(1)"),
        _call(
            "c2",
            "patch",
            mode="replace",
            path=str(project / "README.md"),
            old_string="a",
            new_string="b",
        ),
        _call(
            "c3",
            "patch",
            mode="patch",
            patch="*** Begin Patch\n*** Add File: docs/nuevo.md\n+hola\n*** Update File: src/app.py\n@@\n-print(1)\n+print(2)\n*** End Patch",
        ),
        _call("c4", "terminal", command="pytest -q\n  tests/"),
        _call(
            "c5",
            "skill_manage",
            operations=[{"action": "create", "name": "kronos", "content": "---"}],
        ),
        _call("c6", "write_file", path="/etc/protegido", content="x"),
        _call("c7", "terminal", command="python3 graficar.py"),
    ]
    results = {
        "c1": json.dumps({"bytes_written": 8}),
        "c2": json.dumps({"success": True}),
        "c3": json.dumps({"success": True}),
        "c4": json.dumps({"output": "1 passed", "exit_code": 0, "error": None}),
        "c5": json.dumps({"success": True}),
        "c6": json.dumps({"error": "Refusing to write a protected path"}),
        "c7": json.dumps(
            {"output": "", "exit_code": 1, "error": "No module named matplotlib"}
        ),
    }
    messages = [
        {"role": "user", "content": "armá la app", "at": _ts(10, 10)},
        {"role": "assistant", "content": "", "tool_calls": calls, "at": _ts(10, 10, 1)},
    ]
    messages += [
        {"role": "tool", "content": body, "tool_call_id": cid, "at": _ts(10, 10, 2)}
        for cid, body in results.items()
    ]
    _seed(
        homes["default"],
        [
            {
                "id": "dev",
                "title": "App",
                "cwd": str(project),
                "started_at": _ts(10, 10),
                "messages": messages,
            }
        ],
    )

    data = _get(client)
    files = {f["path"]: f for f in data["files"]}
    app_py, readme, doc = (
        str(project / p) for p in ("src/app.py", "README.md", "docs/nuevo.md")
    )
    assert set(files) == {app_py, readme, doc}  # the refused write is not work
    assert files[app_py]["action"] == "created" and files[app_py]["count"] == 2
    assert files[readme]["action"] == "edited"
    assert files[doc]["action"] == "created"
    assert {f["project"] for f in files.values()} == {str(project)}
    assert [(c["command"], c["exit_code"], c["failed"]) for c in data["commands"]] == [
        ("pytest -q tests/", 0, False),
        ("python3 graficar.py", 1, True),  # a command that failed still ran
    ]
    assert [(s["name"], s["action"]) for s in data["skills"]] == [("kronos", "created")]
    assert [(e["tool"], e["message"]) for e in data["errors"]] == [
        ("write_file", "Refusing to write a protected path"),
        ("terminal", "No module named matplotlib"),
    ]
    stats = data["stats"]
    assert (stats["files_created"], stats["files_edited"]) == (2, 1)
    assert (
        stats["tool_calls"],
        stats["commands"],
        stats["skills_created"],
        stats["errors"],
    ) == (7, 2, 1, 2)
    assert data["conversations"][0]["errors"] == 2


def _repo_with_commits(path, commits):
    env = {
        "GIT_AUTHOR_NAME": "agente",
        "GIT_AUTHOR_EMAIL": "a@example.com",
        "GIT_COMMITTER_NAME": "agente",
        "GIT_COMMITTER_EMAIL": "a@example.com",
        "HOME": str(path.parent),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True, env=env, timeout=30)
    for subject, when in commits:
        dated = {**env, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
        subprocess.run(
            ["git", "-C", str(path), "commit", "-q", "--allow-empty", "-m", subject],
            check=True,
            env=dated,
            timeout=30,
        )
    return path


def test_commits_come_from_the_work_trees_the_agent_worked_in(client, homes, tmp_path):
    written = _repo_with_commits(
        tmp_path / "escrito",
        [
            ("viejo", "2026-03-09T12:00:00+00:00"),
            ("arreglo del día", "2026-03-10T12:00:00+00:00"),
        ],
    )
    committed = _repo_with_commits(
        tmp_path / "commiteado", [("feat: landing", "2026-03-10T13:00:00+00:00")]
    )
    just_cwd = _repo_with_commits(
        tmp_path / "solo_cwd", [("ajeno", "2026-03-10T14:00:00+00:00")]
    )
    calls = [
        _call("c1", "write_file", path=str(written / "a.txt"), content="x"),
        _call(
            "c2",
            "terminal",
            command=f"cd {committed} && git add -A && git commit -m 'feat: landing'",
        ),
        _call(
            "c3", "terminal", command="git log --oneline"
        ),  # reading a repo is not working in it
    ]
    ok = json.dumps({"output": "", "exit_code": 0, "error": None})
    messages = [
        {"role": "assistant", "content": "", "tool_calls": calls, "at": _ts(10, 11)}
    ]
    messages += [
        {"role": "tool", "content": ok, "tool_call_id": cid, "at": _ts(10, 11, 1)}
        for cid in ("c1", "c2", "c3")
    ]
    _seed(
        homes["default"],
        [
            {
                "id": "s",
                "cwd": str(just_cwd),
                "started_at": _ts(10, 11),
                "messages": messages,
            }
        ],
    )

    data = _get(client)
    assert [(c["repo_name"], c["subject"]) for c in data["commits"]] == [
        ("escrito", "arreglo del día"),
        ("commiteado", "feat: landing"),
    ]


def test_cron_runs_come_from_the_execution_ledger(client, homes):
    home = homes["default"]
    cron_dir = home / "cron"
    cron_dir.mkdir(exist_ok=True)
    (cron_dir / "jobs.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "j1",
                        "name": "Resumen diario",
                        "created_at": "2026-03-10T07:00:00+00:00",
                        "schedule": {"display": "0 22 * * *"},
                    },
                    {
                        "id": "j2",
                        "name": "Precios",
                        "created_at": "2026-01-01T07:00:00+00:00",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    conn = sqlite3.connect(cron_dir / "executions.db")
    with conn:
        # The columns cron/executions.py declares (the reader only needs these).
        conn.execute(
            "CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL,"
            " source TEXT NOT NULL, process_id TEXT NOT NULL, pid INTEGER NOT NULL,"
            " status TEXT NOT NULL, claimed_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,"
            " error TEXT)"
        )
        conn.executemany(
            "INSERT INTO executions (id, job_id, source, process_id, pid, status, claimed_at,"
            " finished_at, error) VALUES (?, ?, 'scheduler', 'p', 1, ?, ?, ?, ?)",
            [
                (
                    "e1",
                    "j1",
                    "completed",
                    "2026-03-10T08:00:00+00:00",
                    "2026-03-10T08:01:00+00:00",
                    None,
                ),
                (
                    "e2",
                    "j2",
                    "failed",
                    "2026-03-10T09:00:00-03:00",
                    None,
                    "provider down",
                ),
                ("e3", "j2", "completed", "2026-03-09T09:00:00+00:00", None, None),
            ],
        )
    conn.close()

    data = _get(client)
    assert [(r["job_name"], r["status"], r["error"]) for r in data["cron_runs"]] == [
        ("Resumen diario", "ok", None),
        ("Precios", "failed", "provider down"),
    ]
    assert (data["stats"]["cron_ok"], data["stats"]["cron_failed"]) == (1, 1)
    assert [j["name"] for j in data["cron_jobs_created"]] == ["Resumen diario"]
    assert data["has_activity"] is True


def test_the_summary_is_written_once_and_cached_until_regenerated(
    client, homes, monkeypatch
):
    from agent import auxiliary_client

    _seed(homes["default"], [_chat("a", 10, title="Arreglar login")])
    prompts = []

    def fake_call_llm(task=None, messages=None, **kwargs):
        prompts.append((task, messages))
        text = f"Arreglé el login\n- versión {len(prompts)}"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            model="stub-model",
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    body = {"date": DAY, "tz": "UTC", "lang": "es"}

    first = client.post("/api/analytics/today/summary", json=body).json()
    assert first["error"] is None and first["summary"]["text"].endswith("versión 1")
    assert first["summary"]["stale"] is False
    task, messages = prompts[0]
    assert task == "daily_summary" and "Arreglar login" in messages[1]["content"]
    assert "español rioplatense" in messages[0]["content"]

    again = client.post("/api/analytics/today/summary", json=body).json()
    assert again["summary"]["text"].endswith("versión 1") and len(prompts) == 1
    # Page loads read the cache.
    assert _get(client)["summary"]["text"].endswith("versión 1")

    _seed(homes["default"], [_chat("b", 10, title="Otra cosa")])
    assert _get(client)["summary"]["stale"] is True  # the day moved on since

    redone = client.post(
        "/api/analytics/today/summary", json={**body, "regenerate": True}
    ).json()
    assert (
        redone["summary"]["text"].endswith("versión 2")
        and redone["summary"]["stale"] is False
    )
    assert (homes["default"] / "cache" / "today" / f"{DAY}.json").is_file()
    assert not (
        homes["worker_alpha"] / "cache"
    ).exists()  # cached in the profile it describes


def test_no_auxiliary_model_still_leaves_the_page_working(client, homes, monkeypatch):
    from agent import auxiliary_client

    _seed(homes["default"], [_chat("a", 10)])

    def broken(**kwargs):
        raise RuntimeError("no auxiliary provider configured")

    monkeypatch.setattr(auxiliary_client, "call_llm", broken)
    resp = client.post("/api/analytics/today/summary", json={"date": DAY, "tz": "UTC"})
    assert resp.status_code == 200
    assert resp.json() == {"summary": None, "error": "no auxiliary provider configured"}
    data = _get(client)
    assert data["summary"] is None and data["stats"]["conversations"] == 1


def test_the_summary_runs_on_the_profiles_daily_summary_slot(client, homes, monkeypatch):
    """``auxiliary.daily_summary`` in the summarized profile's config.yaml routes the call."""
    from agent import auxiliary_client
    from agent.auxiliary_task_config import _get_auxiliary_task_config

    (homes["worker_alpha"] / "config.yaml").write_text(
        "auxiliary:\n  daily_summary:\n    model: modelo-barato\n", encoding="utf-8"
    )
    for home in homes.values():
        _seed(home, [_chat("a", 10)])
    seen = []

    def fake_call_llm(task=None, **kwargs):
        config = _get_auxiliary_task_config(task)
        seen.append((config.get("model"), config.get("timeout")))
        message = SimpleNamespace(content="Titular\n- algo")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    body = {"date": DAY, "tz": "UTC"}
    client.post("/api/analytics/today/summary?profile=worker_alpha", json=body)
    client.post("/api/analytics/today/summary", json=body)
    assert seen[0][0] == "modelo-barato"
    assert seen[1] == ("", 120)  # the shipped default slot: main model, 120 s


def test_a_quiet_day_never_calls_the_model(client, homes, monkeypatch):
    from agent import auxiliary_client

    monkeypatch.setattr(
        auxiliary_client, "call_llm", lambda **kw: pytest.fail("called the model")
    )
    resp = client.post("/api/analytics/today/summary", json={"date": DAY, "tz": "UTC"})
    assert resp.json() == {"summary": None, "error": None}


def test_a_skill_dashboard_refreshed_that_day_gets_a_card(client, homes):
    import os

    home = homes["default"]
    for name in ("kronos", "dormido"):
        skill = home / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: d\nmetadata:\n  clawk:\n    dashboard:\n"
            f"      title: {name.title()}\n---\n# {name}\n",
            encoding="utf-8",
        )
        snapshot = home / "dashboards" / f"{name}.json"
        snapshot.parent.mkdir(exist_ok=True)
        snapshot.write_text(
            json.dumps(
                {
                    "version": 1,
                    "title": f"{name.title()} Trading",
                    "panels": [
                        {
                            "type": "stats",
                            "items": [
                                {"label": "P&L", "value": 120.5, "tone": "positive"}
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
    os.utime(home / "dashboards" / "kronos.json", (_ts(10, 15),) * 2)
    os.utime(home / "dashboards" / "dormido.json", (_ts(2, 15),) * 2)

    data = _get(client)
    [card] = data["dashboards"]
    assert (card["name"], card["title"], card["at"]) == (
        "kronos",
        "Kronos Trading",
        _ts(10, 15),
    )
    assert card["stats"] == [{"label": "P&L", "value": 120.5, "tone": "positive"}]
    assert data["has_activity"] is True


def test_invalid_date_is_a_400(client):
    resp = client.get("/api/analytics/today", params={"date": "10/03/2026"})
    assert resp.status_code == 400


def test_the_day_is_the_callers_calendar_day():
    from clawk_cli.today_activity import day_window

    ny = day_window("2026-03-08", "America/New_York")  # DST starts: a 23-hour day
    assert ny.end - ny.start == 23 * 3600
    assert ny.start == datetime(2026, 3, 8, 5, 0, tzinfo=UTC).timestamp()
    # An unknown zone falls back to the server's own.
    assert day_window("2026-03-10", "Not/AZone").tz == ""
