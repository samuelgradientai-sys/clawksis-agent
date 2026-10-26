"""Cookbook "use this model" writes the profile the dashboard selected, and a reachable Ollama
daemon is enough to pull a model (Ollama in a container has no binary on our PATH)."""

import http.server
import json
import threading

import pytest
import clawk_yaml as yaml

from clawk_cli import cookbook
from tests.waiting import wait_until


@pytest.fixture
def homes(monkeypatch, _isolate_clawk_home):
    from clawk_cli import profiles
    from clawk_constants import get_clawk_home

    launch = get_clawk_home()
    beta = launch / "profiles" / "beta"
    for home in (launch, beta):
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text(
            yaml.safe_dump(
                {"model": {"default": f"{home.name}-model", "provider": "openrouter"}}
            ),
            encoding="utf-8",
        )
    monkeypatch.setattr(profiles, "_get_default_clawk_home", lambda: launch)
    monkeypatch.setattr(profiles, "_get_profiles_root", lambda: launch / "profiles")
    return {"launch": launch, "beta": beta}


@pytest.fixture
def client(homes):
    from starlette.testclient import TestClient

    from clawk_cli.web_server import _SESSION_HEADER_NAME, _SESSION_TOKEN, app

    test_client = TestClient(app)
    test_client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return test_client


def _model_block(home):
    return yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))["model"]


def test_use_local_model_writes_the_selected_profiles_config(client, homes):
    launch_before = _model_block(homes["launch"])

    response = client.post(
        "/api/cookbook/use", params={"profile": "beta"}, json={"tag": "qwen2.5:7b"}
    )

    assert response.status_code == 200, response.text
    beta_model = _model_block(homes["beta"])
    assert (beta_model["default"], beta_model["provider"]) == ("qwen2.5:7b", "custom")
    assert _model_block(homes["launch"]) == launch_before


class _FakeOllama(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json({"models": []})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/api/pull":
            self._json({"status": "success"})
        else:  # /api/generate — the post-pull validation
            self._json({"response": "OK"})


def test_pull_runs_against_a_reachable_daemon_without_a_local_binary(
    monkeypatch, tmp_path
):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(
            cookbook, "OLLAMA_BASE_URL", f"http://127.0.0.1:{server.server_port}"
        )
        monkeypatch.setenv("PATH", str(tmp_path))  # no `ollama` binary anywhere
        monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")

        started = cookbook.start_pull("tiny:1b")

        assert started["ok"] is True, started
        wait_until(
            lambda: cookbook.pull_status("tiny:1b") not in ("pulling", "validating"),
            what="pull finished",
        )
        assert cookbook.pull_status("tiny:1b") == "done"
    finally:
        server.shutdown()


def test_unreachable_hugging_face_is_reported_and_not_cached_as_no_results(
    client, monkeypatch
):
    from clawk_cli import cookbook_hf

    answers = [None, [{"id": "acme/tiny-GGUF", "downloads": 3, "gguf": {}}]]
    monkeypatch.setattr(
        cookbook_hf, "_get_json", lambda _url, timeout=15.0: answers.pop(0)
    )
    cookbook_hf._cache.clear()

    offline = client.get("/api/cookbook/hf-search", params={"q": "tiny"}).json()
    assert offline["models"] == [] and "huggingface.co" in offline["error"]

    # The failure was not cached as "nothing found": the next search reaches HF again.
    online = client.get("/api/cookbook/hf-search", params={"q": "tiny"}).json()
    assert [m["repo"] for m in online["models"]] == ["acme/tiny-GGUF"]
    assert "error" not in online
