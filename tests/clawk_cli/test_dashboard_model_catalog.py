"""Models page catalog contract: what the dashboard needs to show which models a profile can run.

* ``/api/model/options`` rows carry the backend's locality verdict (``is_local`` + ``local_url``)
  so the page splits local from cloud without guessing from slugs.
* A ``provider: custom`` main served by a named ``custom_providers:`` row is ONE current row: the
  canonical "missing credentials" skeleton for ``custom`` used to sit beside it as a second,
  false current row ("Configured provider is not authenticated").
* ``GET /api/model/local-status`` probes every local endpoint the profile routes to.
* ``/api/model/auxiliary`` reports the main model's endpoint like it does for aux pins.
* Hidden usage cards (``dashboard.hidden_models``) are read and written in the requested
  profile, not the dashboard process's.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from starlette.testclient import TestClient

LOCAL_MODELS = ["qwen2.5-coder-7b", "llama-3.1-8b"]


def _write_config(home: Path, cfg: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    # JSON is valid YAML; keeps the fixture free of a yaml dependency.
    (home / "config.yaml").write_text(json.dumps(cfg), encoding="utf-8")


def _closed_port_url() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}/v1"


@pytest.fixture
def local_server():
    """A real OpenAI-compatible server on loopback answering ``/v1/models``."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.rstrip("/") != "/v1/models":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"data": [{"id": m} for m in LOCAL_MODELS]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()
    server.server_close()


@pytest.fixture
def no_ollama(monkeypatch):
    """Keep a developer's real Ollama daemon (or anything on :11434) out of the payload."""
    from clawk_cli import cookbook

    monkeypatch.setattr(cookbook, "ollama_running", lambda: False)
    monkeypatch.setattr(cookbook, "OLLAMA_OPENAI_URL", _closed_port_url())


@pytest.fixture
def clawk_home(tmp_path, monkeypatch):
    home = tmp_path / ".clawksis"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CLAWK_HOME", str(home))
    return home


def _named_endpoint_config(url: str, main_model: str = "llama-3.1-8b") -> dict:
    return {
        "model": {"provider": "custom", "base_url": url, "default": main_model},
        "custom_providers": [
            {
                "name": "vLLM box",
                "base_url": url,
                "model": "qwen2.5-coder-7b",
                "models": {m: {} for m in LOCAL_MODELS},
            }
        ],
    }


@pytest.mark.parametrize("mode", ["include_unconfigured", "explicit_only"])
def test_custom_main_on_named_endpoint_is_a_single_current_row(
    clawk_home, no_ollama, mode
):
    from clawk_cli.inventory import build_models_payload, load_picker_context

    _write_config(clawk_home, _named_endpoint_config("http://127.0.0.1:9/v1"))

    payload = build_models_payload(
        load_picker_context(), probe_custom_providers=False, **{mode: True}
    )

    current = [row for row in payload["providers"] if row.get("is_current")]
    assert [row["slug"] for row in current] == ["custom:vllm-box"]
    assert not [
        r for r in payload["providers"] if r.get("source") == "configured-current"
    ]


def test_lost_credentials_still_keep_the_saved_selection_visible():
    """The skeleton exists for a current provider nothing else represents — keep that."""
    from clawk_cli.inventory import ConfigContext, _append_unconfigured_rows

    ctx = ConfigContext(
        current_provider="openrouter",
        current_model="vendor/model",
        current_base_url="",
        user_providers={},
        custom_providers=[],
    )

    skeletons = [
        r
        for r in _append_unconfigured_rows([], ctx)
        if r["source"] == "configured-current"
    ]
    assert [(r["slug"], r["models"], r["is_current"]) for r in skeletons] == [
        ("openrouter", ["vendor/model"], True)
    ]


def test_rows_carry_the_backends_locality_verdict(clawk_home, no_ollama, local_server):
    from clawk_cli.inventory import build_models_payload, load_picker_context

    cfg = _named_endpoint_config(local_server)
    cfg["custom_providers"].append(
        {
            "name": "Remote proxy",
            "base_url": "https://llm.example.com/v1",
            "model": "big-1",
        }
    )
    _write_config(clawk_home, cfg)

    rows = {
        r["slug"]: r
        for r in build_models_payload(
            load_picker_context(), probe_custom_providers=False
        )["providers"]
    }

    assert rows["custom:vllm-box"]["is_local"] is True
    assert rows["custom:vllm-box"]["local_url"] == local_server
    assert rows["custom:remote-proxy"]["is_local"] is False
    assert "local_url" not in rows["custom:remote-proxy"]


def test_builtin_local_providers_and_pseudo_urls_are_classified_by_endpoint():
    from clawk_cli.model_locality import apply_locality

    rows = [
        {"slug": "ollama", "source": "local"},
        {"slug": "lmstudio", "source": "clawk"},  # registry default 127.0.0.1:1234
        {
            "slug": "copilot-acp",
            "source": "clawk",
        },  # acp://copilot — not an HTTP endpoint
        {"slug": "openrouter", "source": "built-in"},
        {"slug": "llamacpp", "source": "local-runtime"},  # managed server not running
    ]
    apply_locality(rows)

    by_slug = {r["slug"]: r for r in rows}
    assert by_slug["ollama"]["is_local"] and by_slug["ollama"]["local_url"].endswith(
        ":11434/v1"
    )
    assert (
        by_slug["lmstudio"]["is_local"]
        and "127.0.0.1:1234" in by_slug["lmstudio"]["local_url"]
    )
    assert by_slug["copilot-acp"]["is_local"] is False
    assert by_slug["openrouter"]["is_local"] is False
    # Local, but its models start on demand: no endpoint to pin or probe yet.
    assert (
        by_slug["llamacpp"]["is_local"] is True
        and "local_url" not in by_slug["llamacpp"]
    )


@pytest.fixture
def client():
    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app

    c = TestClient(app)
    c.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return c


def test_local_status_probes_every_local_endpoint_the_profile_routes_to(
    clawk_home, no_ollama, local_server, client
):
    down = _closed_port_url()
    cfg = _named_endpoint_config(local_server)
    cfg["auxiliary"] = {
        "vision": {"provider": "custom", "model": "llava", "base_url": down},
        "compression": {"provider": "openrouter", "model": "cloud/model"},
    }
    _write_config(clawk_home, cfg)

    resp = client.get("/api/model/local-status")

    assert resp.status_code == 200, resp.text
    by_url = {e["url"]: e for e in resp.json()["endpoints"]}
    assert by_url[local_server]["reachable"] is True
    assert by_url[local_server]["models"] == LOCAL_MODELS
    assert by_url[down]["reachable"] is False and by_url[down]["models"] is None
    assert not any(
        "openrouter" in url for url in by_url
    )  # cloud endpoints are never probed


def test_auxiliary_listing_reports_the_main_models_endpoint(
    clawk_home, client, local_server
):
    _write_config(clawk_home, _named_endpoint_config(local_server))

    main = client.get("/api/model/auxiliary").json()["main"]

    assert main == {
        "provider": "custom",
        "model": "llama-3.1-8b",
        "base_url": local_server,
        "local_endpoint": True,
    }


@pytest.fixture
def two_profiles(tmp_path, monkeypatch):
    root = tmp_path / "clawk_home"
    named = root / "profiles" / "b"
    for home in (root, named):
        _write_config(
            home, {"model": {"provider": "openrouter", "default": "vendor/m"}}
        )
    monkeypatch.setenv("CLAWK_HOME", str(root))
    from agent import secret_scope
    from tui_gateway import launch_profile_policy as lpp

    monkeypatch.setattr(secret_scope, "_MULTIPLEX_ACTIVE", False)
    monkeypatch.setattr(lpp, "_snapshot", None)
    return root, named


def _hidden_on_disk(home: Path) -> list:
    import clawk_yaml as yaml

    cfg = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8")) or {}
    return (cfg.get("dashboard") or {}).get("hidden_models") or []


def test_hidden_usage_cards_live_in_the_requested_profile(
    two_profiles, client, monkeypatch
):
    from clawk_state import SessionDB
    from clawk_cli.web_routers import analytics

    root, named = two_profiles

    resp = client.post(
        "/api/analytics/models/hide?profile=b",
        json={"model": "gone", "provider": "openrouter"},
    )
    assert resp.status_code == 200, resp.text
    assert _hidden_on_disk(named) == ["openrouter|gone"]
    assert _hidden_on_disk(root) == []
    # The sparse write keeps the profile's own settings.
    assert "vendor/m" in (named / "config.yaml").read_text(encoding="utf-8")

    db = SessionDB(named / "state.db")
    for sid, model in (("s1", "kept"), ("s2", "gone")):
        db.create_session(sid, source="cli", model=model)
        with db._lock:
            db._conn.execute(
                "UPDATE sessions SET billing_provider = 'openrouter', started_at = ?, "
                "input_tokens = 10 WHERE id = ?",
                (time.time(), sid),
            )
            db._conn.commit()
    monkeypatch.setattr(
        analytics, "_open_session_db_for_profile", lambda profile, read_only=True: db
    )
    monkeypatch.setattr(db, "close", lambda: None)

    named_view = analytics._get_models_analytics(days=30, profile="b")
    assert [m["model"] for m in named_view["models"]] == ["kept"]
    assert named_view["hidden_models"] == ["openrouter|gone"]
    # The same sessions seen through the process's own profile hide nothing.
    assert {m["model"] for m in analytics._get_models_analytics(days=30)["models"]} == {
        "kept",
        "gone",
    }

    resp = client.request(
        "DELETE",
        "/api/analytics/models/hide?profile=b",
        json={"model": "gone", "provider": "openrouter"},
    )
    assert resp.status_code == 200, resp.text
    assert _hidden_on_disk(named) == []
