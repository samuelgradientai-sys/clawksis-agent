"""Tests del Cookbook multi-provider (llama.cpp + HF + registry + descargas).

Sin red: la API de HF se testea solo en su parsing puro (quant/multipart/url)
y la descarga end-to-end corre contra un http.server local que sirve un GGUF
falso (con soporte de Range para el resume).
"""

from __future__ import annotations


import http.server
import json
import threading
import time

import pytest


from clawk_cli import cookbook, cookbook_hf, cookbook_llamacpp, cookbook_providers


@pytest.fixture
def gguf_home(tmp_path, monkeypatch):
    """CLAWK_HOME aislado para registry/modelos/binarios."""

    monkeypatch.setattr(cookbook_llamacpp, "_clawk_home", lambda: tmp_path)

    return tmp_path


# ── HF parsing puro ──────────────────────────────────────────────────────────


def test_quant_parsing():

    assert cookbook_hf._quant_of("model-Q4_K_M.gguf") == "Q4_K_M"

    assert cookbook_hf._quant_of("foo.q5_k_m.gguf") == "Q5_K_M"

    assert cookbook_hf._quant_of("bar-IQ2_XXS.gguf") == "IQ2_XXS"

    assert cookbook_hf._quant_of("baz-f16.gguf") == "F16"

    assert cookbook_hf._quant_of("plain.gguf") == ""


def test_multipart_detection():

    assert cookbook_hf._MULTIPART_RE.search("m-00001-of-00003.gguf")

    assert not cookbook_hf._MULTIPART_RE.search("m-Q4_K_M.gguf")


def test_download_url_shape():

    url = cookbook_hf.download_url("Qwen/Qwen2.5-3B-Instruct-GGUF", "a b.gguf")

    assert url.startswith("https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/")

    assert "a%20b.gguf" in url


# ── registry ─────────────────────────────────────────────────────────────────


def _fake_gguf(home, name: str, payload: bytes = b"\0" * 64):

    mdir = cookbook_llamacpp.models_dir()

    mdir.mkdir(parents=True, exist_ok=True)

    path = mdir / name

    path.write_bytes(b"GGUF" + payload)

    return path


def test_registry_discovers_orphans_and_purges(gguf_home):

    _fake_gguf(gguf_home, "orphan-Q4_K_M.gguf")

    models = cookbook_llamacpp.list_models()

    assert [m["id"] for m in models] == ["gguf:orphan-Q4_K_M.gguf"]

    assert models[0]["quant"] == "Q4_K_M"

    # Borrar el archivo a mano → la entrada se purga sola en el próximo list.

    (cookbook_llamacpp.models_dir() / "orphan-Q4_K_M.gguf").unlink()

    assert cookbook_llamacpp.list_models() == []


def test_rename_verify_delete_roundtrip(gguf_home):

    _fake_gguf(gguf_home, "m-Q8_0.gguf")

    (model,) = cookbook_llamacpp.list_models()

    assert cookbook_llamacpp.rename_model(model["id"], "Mi modelo")["ok"]

    assert cookbook_llamacpp.list_models()[0]["name"] == "Mi modelo"

    assert cookbook_llamacpp.verify_model(model["id"])["ok"]

    assert cookbook_llamacpp.delete_model(model["id"])["ok"]

    assert cookbook_llamacpp.list_models() == []

    assert not cookbook_llamacpp.delete_model(model["id"])["ok"]


def test_verify_detects_bad_magic_and_size(gguf_home):

    path = _fake_gguf(gguf_home, "bad.gguf")

    (model,) = cookbook_llamacpp.list_models()

    # Tamaño cambiado tras registrarse → mismatch.

    path.write_bytes(b"GGUF" + b"\0" * 999)

    res = cookbook_llamacpp.verify_model(model["id"])

    assert not res["ok"] and "size mismatch" in res["error"]

    # Magic roto (mismo tamaño que el registrado ahora): re-registrar limpio.

    cookbook_llamacpp.delete_model(model["id"])

    path = _fake_gguf(gguf_home, "bad2.gguf")

    (model,) = cookbook_llamacpp.list_models()

    path.write_bytes(b"XXXX" + b"\0" * 64)

    res = cookbook_llamacpp.verify_model(model["id"])

    assert not res["ok"] and "magic" in res["error"]


# ── validaciones de descarga ─────────────────────────────────────────────────


def test_start_download_rejects_bad_input(gguf_home):

    assert not cookbook_llamacpp.start_download("norepo", "m.gguf")["ok"]

    assert not cookbook_llamacpp.start_download("a/b", "notgguf.bin")["ok"]

    res = cookbook_llamacpp.start_download("a/b", "m-00001-of-00002.gguf")

    assert not res["ok"] and "multi-part" in res["error"]


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    """Sirve un GGUF falso con soporte de Range (para probar el resume)."""

    payload = b"GGUF" + bytes(range(256)) * 64  # ~16KB

    def do_GET(self):  # noqa: N802 — nombre de la stdlib

        rng = self.headers.get("Range")

        if rng and rng.startswith("bytes="):
            start = int(rng.split("=")[1].split("-")[0])

            body = self.payload[start:]

            self.send_response(206)

        else:
            body = self.payload

            self.send_response(200)

        self.send_header("Content-Length", str(len(body)))

        self.end_headers()

        self.wfile.write(body)

    def log_message(self, *args):  # silencio en tests

        pass


@pytest.fixture
def http_gguf_server():

    server = http.server.HTTPServer(("127.0.0.1", 0), _RangeHandler)

    t = threading.Thread(target=server.serve_forever, daemon=True)

    t.start()

    yield f"http://127.0.0.1:{server.server_port}/model.gguf"

    server.shutdown()


def _wait_download(did: str, timeout: float = 15.0) -> dict:

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        p = cookbook_llamacpp.download_progress(did)

        if p["status"] in ("done", "error", "cancelled"):
            return p

        time.sleep(0.05)

    return cookbook_llamacpp.download_progress(did)


def test_download_end_to_end_registers_model(gguf_home, http_gguf_server, monkeypatch):

    monkeypatch.setattr(cookbook_hf, "download_url", lambda repo, f: http_gguf_server)

    res = cookbook_llamacpp.start_download("acme/repo", "model-Q4_K_M.gguf")

    assert res["ok"]

    p = _wait_download(res["download_id"])

    assert p["status"] == "done", p

    assert p["model_id"] == "gguf:model-Q4_K_M.gguf"

    (model,) = [m for m in cookbook_llamacpp.list_models() if m["id"] == p["model_id"]]

    assert model["repo"] == "acme/repo"

    assert model["size_bytes"] == len(_RangeHandler.payload)

    assert cookbook_llamacpp.verify_model(model["id"])["ok"]


def test_download_resumes_from_part_file(gguf_home, http_gguf_server, monkeypatch):

    monkeypatch.setattr(cookbook_hf, "download_url", lambda repo, f: http_gguf_server)

    # Simular una descarga cancelada a la mitad: .part con el primer tramo.

    mdir = cookbook_llamacpp.models_dir()

    mdir.mkdir(parents=True, exist_ok=True)

    half = len(_RangeHandler.payload) // 2

    (mdir / "model-Q4_K_M.gguf.part").write_bytes(_RangeHandler.payload[:half])

    res = cookbook_llamacpp.start_download("acme/repo", "model-Q4_K_M.gguf")

    p = _wait_download(res["download_id"])

    assert p["status"] == "done", p

    final = mdir / "model-Q4_K_M.gguf"

    assert final.read_bytes() == _RangeHandler.payload  # resume sin corromper


# ── providers registry ───────────────────────────────────────────────────────


def test_provider_registry():

    assert cookbook_providers.get_provider("ollama") is not None

    assert cookbook_providers.get_provider("llamacpp") is not None

    assert cookbook_providers.get_provider("LLAMACPP") is not None  # case-insensitive

    assert cookbook_providers.get_provider("nope") is None

    names = [p.name for p in cookbook_providers.all_providers()]

    assert names == ["ollama", "llamacpp"]


def test_all_installed_models_merges_providers(gguf_home, monkeypatch):

    _fake_gguf(gguf_home, "local-Q4_K_M.gguf")

    monkeypatch.setattr(
        cookbook, "ollama_models_detailed", lambda: {"qwen2.5:3b": {"size": 123}}
    )

    models = cookbook_providers.all_installed_models()

    by_provider = {m["provider"] for m in models}

    assert by_provider == {"ollama", "llamacpp"}

    ollama_row = next(m for m in models if m["provider"] == "ollama")

    assert ollama_row["id"] == "ollama:qwen2.5:3b"

    assert ollama_row["size_bytes"] == 123


def test_ollama_provider_tag_roundtrip():

    p = cookbook_providers.OllamaProvider()

    assert p._tag("ollama:qwen2.5:3b") == "qwen2.5:3b"

    assert p._tag("qwen2.5:3b") == "qwen2.5:3b"


def test_pull_progress_shape():

    # Sin pull en curso: shape estable con status vacío.

    p = cookbook.pull_progress("nunca-pulleado:1b")

    assert p["status"] == ""

    assert p["downloaded"] == 0 and p["total"] == 0

    assert p["percent"] is None and p["eta_seconds"] is None


def test_registry_file_is_json(gguf_home):

    _fake_gguf(gguf_home, "x-Q4_K_M.gguf")

    cookbook_llamacpp.list_models()

    data = json.loads((cookbook_llamacpp.models_dir() / "registry.json").read_text())

    assert isinstance(data, list) and data[0]["file"] == "x-Q4_K_M.gguf"


# ── picker de assets del release de llama.cpp ────────────────────────────────


def test_release_asset_picker_real_names(monkeypatch):
    """Nombres REALES del release b9866: Linux/macOS publican .tar.gz (no .zip)
    y hay variantes GPU (vulkan/rocm/cuda) que NO deben elegirse por default."""

    import platform

    names = [
        "cudart-llama-bin-win-cuda-12.4-x64.zip",
        "llama-b9866-bin-macos-arm64.tar.gz",
        "llama-b9866-bin-ubuntu-arm64.tar.gz",
        "llama-b9866-bin-ubuntu-vulkan-x64.tar.gz",
        "llama-b9866-bin-ubuntu-rocm-7.2-x64.tar.gz",
        "llama-b9866-bin-ubuntu-x64.tar.gz",
        "llama-b9866-bin-win-cpu-x64.zip",
        "llama-b9866-bin-win-cuda-12.4-x64.zip",
        "llama-b9866-ui.tar.gz",
    ]

    assets = [{"name": n} for n in names]

    cases = [
        ("Linux", "x86_64", "llama-b9866-bin-ubuntu-x64.tar.gz"),
        ("Windows", "AMD64", "llama-b9866-bin-win-cpu-x64.zip"),
        ("Darwin", "arm64", "llama-b9866-bin-macos-arm64.tar.gz"),
        ("Linux", "aarch64", "llama-b9866-bin-ubuntu-arm64.tar.gz"),
    ]

    for sysname, machine, expected in cases:
        monkeypatch.setattr(platform, "system", lambda s=sysname: s)

        monkeypatch.setattr(platform, "machine", lambda m=machine: m)

        got = cookbook_llamacpp._pick_release_asset(assets)

        assert got and got["name"] == expected, (sysname, machine, got)


def test_hardware_includes_live_system_info():

    hw = cookbook.detect_hardware()

    for key in ("ram_available_gb", "disk_free_gb", "load_1m"):
        assert key in hw
