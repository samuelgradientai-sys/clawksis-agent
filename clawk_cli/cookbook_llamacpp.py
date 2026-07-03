"""llama.cpp backend for the Cookbook — descarga, registro y serving de GGUF.

Segundo backend del Cookbook junto a Ollama (NO lo reemplaza). Piezas:

  * **Binario**: detecta ``llama-server`` en PATH o en
    ``~/.clawksis/llamacpp/bin/``; si falta, lo instala bajando el release
    precompilado de GitHub (ggml-org/llama.cpp) para esta plataforma.
  * **Modelos**: los .gguf viven en ``~/.clawksis/models/gguf/`` con un
    ``registry.json`` al lado (id, repo HF, archivo, quant, tamaño, nombre).
    Nada que mover a mano: Install descarga directo a esa carpeta.
  * **Descargas**: manager en background con progreso real (bytes, %,
    velocidad, ETA), cancelación y **resume** — si quedó un ``.part``, la
    próxima descarga continúa con un header Range en vez de re-bajar todo.
  * **Servidor**: arranca/frena ``llama-server`` (OpenAI-compatible en
    ``127.0.0.1:8085/v1`` con ``--jinja`` para tool-calling) y "Use" apunta
    el modelo del agente ahí — mismo mecanismo custom-provider que Ollama.

Todo best-effort: nunca levanta al caller; los errores quedan en el estado
consultable (``download_progress`` / ``install_status`` / ``server_status``).
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from clawk_cli import cookbook_hf

LLAMACPP_PORT = int(os.environ.get("CLAWK_LLAMACPP_PORT", "8085"))

LLAMACPP_BASE_URL = f"http://127.0.0.1:{LLAMACPP_PORT}"

LLAMACPP_OPENAI_URL = f"{LLAMACPP_BASE_URL}/v1"

_GITHUB_RELEASES = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"

_CHUNK = 256 * 1024  # 256 KiB por read — progreso fluido sin castigar IO.


def _clawk_home() -> Path:
    try:
        from clawk_constants import get_clawk_home

        return Path(get_clawk_home())

    except Exception:
        return Path(os.environ.get("CLAWK_HOME", str(Path.home() / ".clawksis")))


def bin_dir() -> Path:
    return _clawk_home() / "llamacpp" / "bin"


def models_dir() -> Path:
    return _clawk_home() / "models" / "gguf"


def _registry_path() -> Path:
    return models_dir() / "registry.json"


# ── binario: detección + instalación ─────────────────────────────────────────


def server_binary() -> Optional[str]:
    """Ruta del ``llama-server`` utilizable, o None si no hay ninguno."""

    exe = "llama-server.exe" if os.name == "nt" else "llama-server"

    local = bin_dir() / exe

    if local.is_file():
        return str(local)

    return shutil.which("llama-server")


def llamacpp_installed() -> bool:
    return server_binary() is not None


_install_status = ""

_install_lock = threading.Lock()


def install_status() -> str:
    with _install_lock:
        return _install_status


def _pick_release_asset(assets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Elige el .zip del release que corresponde a esta plataforma (CPU build)."""

    sysname = platform.system()

    machine = platform.machine().lower()

    arm = machine in {"arm64", "aarch64"}

    if sysname == "Linux":
        tokens = ["ubuntu", "arm64" if arm else "x64"]

    elif sysname == "Darwin":
        tokens = ["macos", "arm64" if arm else "x64"]

    elif sysname == "Windows":
        tokens = ["win", "cpu", "arm64" if arm else "x64"]

    else:
        return None

    def score(name: str) -> int:
        n = name.lower()

        return sum(1 for t in tokens if t in n)

    zips = [
        a
        for a in assets
        if str(a.get("name", "")).endswith(".zip")
        and "cudart" not in str(a.get("name", "")).lower()
    ]

    if not zips:
        return None

    best = max(zips, key=lambda a: score(str(a.get("name", ""))))

    return best if score(str(best.get("name", ""))) >= len(tokens) - 0 else None


def _do_install() -> None:
    global _install_status

    try:
        data = json.loads(
            urllib.request
            .urlopen(
                urllib.request.Request(
                    _GITHUB_RELEASES, headers={"User-Agent": "clawksis-cookbook"}
                ),
                timeout=30,
            )
            .read()
            .decode()
        )

        asset = _pick_release_asset(data.get("assets") or [])

        if not asset:
            with _install_lock:
                _install_status = (
                    "error: no prebuilt llama.cpp release for this platform — "
                    "install it manually (brew install llama.cpp / "
                    "github.com/ggml-org/llama.cpp/releases) and Refresh."
                )

            return

        url = str(asset.get("browser_download_url") or "")

        dest = bin_dir()

        dest.mkdir(parents=True, exist_ok=True)

        tmp_zip = dest / "_llamacpp_release.zip"

        with (
            urllib.request.urlopen(
                urllib.request.Request(
                    url, headers={"User-Agent": "clawksis-cookbook"}
                ),
                timeout=60,
            ) as resp,
            open(tmp_zip, "wb") as out,
        ):
            shutil.copyfileobj(resp, out, length=_CHUNK)

        # Extraer plano: el zip trae build/bin/… — nos quedamos con los
        # binarios/librerías en bin_dir sin la jerarquía del zip.

        with zipfile.ZipFile(tmp_zip) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue

                name = Path(info.filename).name

                if not name:
                    continue

                with zf.open(info) as src, open(dest / name, "wb") as out:
                    shutil.copyfileobj(src, out)

        tmp_zip.unlink(missing_ok=True)

        if os.name != "nt":
            for f in dest.iterdir():
                if f.name.startswith("llama-"):
                    f.chmod(f.stat().st_mode | 0o755)

        with _install_lock:
            _install_status = (
                "done"
                if llamacpp_installed()
                else "error: extracted but no llama-server binary found"
            )

    except Exception as exc:  # noqa: BLE001 — estado consultable, nunca raise
        with _install_lock:
            _install_status = f"error: {str(exc)[:200]}"


def start_install() -> Dict[str, Any]:
    """Instala llama.cpp (release CPU precompilado) en background."""

    global _install_status

    if llamacpp_installed():
        return {"ok": True, "status": "done"}

    with _install_lock:
        if _install_status == "installing":
            return {"ok": True, "status": "installing"}

        _install_status = "installing"

    threading.Thread(target=_do_install, name="llamacpp-install", daemon=True).start()

    return {"ok": True, "status": "installing"}


# ── registry de modelos instalados ───────────────────────────────────────────

_registry_lock = threading.Lock()


def _load_registry() -> List[Dict[str, Any]]:
    try:
        data = json.loads(_registry_path().read_text(encoding="utf-8"))

        return data if isinstance(data, list) else []

    except Exception:
        return []


def _save_registry(entries: List[Dict[str, Any]]) -> None:
    models_dir().mkdir(parents=True, exist_ok=True)

    tmp = _registry_path().with_suffix(".json.tmp")

    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    tmp.replace(_registry_path())


def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def list_models() -> List[Dict[str, Any]]:
    """Modelos GGUF registrados + huérfanos encontrados en la carpeta.

    Un .gguf copiado a mano a la carpeta también aparece (se auto-registra
    liviano), así "gestioná las rutas automáticamente" vale en ambos sentidos.
    """

    with _registry_lock:
        entries = _load_registry()

        known = {e.get("file") for e in entries}

        changed = False

        mdir = models_dir()

        if mdir.is_dir():
            for f in sorted(mdir.glob("*.gguf")):
                if f.name in known:
                    continue

                entries.append({
                    "id": f"gguf:{f.name}",
                    "name": f.stem,
                    "file": f.name,
                    "repo": "",
                    "quant": cookbook_hf._quant_of(f.name),
                    "size_bytes": f.stat().st_size,
                    "added_at": int(f.stat().st_mtime),
                })

                changed = True

        # Purgar entradas cuyo archivo ya no existe.

        alive = [e for e in entries if (mdir / str(e.get("file", ""))).is_file()]

        if changed or len(alive) != len(entries):
            _save_registry(alive)

        for e in alive:
            e["path"] = str(mdir / str(e.get("file", "")))

        return alive


def delete_model(model_id: str) -> Dict[str, Any]:
    with _registry_lock:
        entries = _load_registry()

        keep, removed = [], None

        for e in entries:
            if e.get("id") == model_id:
                removed = e

            else:
                keep.append(e)

        if removed is None:
            return {"ok": False, "error": "model not found"}

        path = models_dir() / str(removed.get("file", ""))

        try:
            path.unlink(missing_ok=True)

        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"could not delete file: {exc}"}

        _save_registry(keep)

    # Si el server estaba sirviendo justo este modelo, frenarlo.

    if _server.get("model_file") == removed.get("file"):
        stop_server()

    return {"ok": True}


def rename_model(model_id: str, new_name: str) -> Dict[str, Any]:
    new_name = (new_name or "").strip()

    if not new_name:
        return {"ok": False, "error": "name is required"}

    with _registry_lock:
        entries = _load_registry()

        for e in entries:
            if e.get("id") == model_id:
                e["name"] = new_name

                _save_registry(entries)

                return {"ok": True}

    return {"ok": False, "error": "model not found"}


def verify_model(model_id: str) -> Dict[str, Any]:
    """Integridad básica: existe, tamaño esperado y magic bytes GGUF."""

    for e in list_models():
        if e.get("id") != model_id:
            continue

        path = Path(str(e.get("path", "")))

        if not path.is_file():
            return {"ok": False, "error": "file missing"}

        expected = int(e.get("size_bytes") or 0)

        actual = path.stat().st_size

        if expected and actual != expected:
            return {
                "ok": False,
                "error": f"size mismatch: expected {expected} bytes, found {actual}",
            }

        try:
            with open(path, "rb") as fh:
                magic = fh.read(4)

        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"unreadable: {exc}"}

        if magic != b"GGUF":
            return {"ok": False, "error": "not a GGUF file (bad magic bytes)"}

        return {"ok": True, "size_bytes": actual}

    return {"ok": False, "error": "model not found"}


# ── descargas con progreso / cancel / resume ─────────────────────────────────

_downloads: Dict[str, Dict[str, Any]] = {}

_downloads_lock = threading.Lock()


def download_progress(download_id: str) -> Dict[str, Any]:
    with _downloads_lock:
        d = _downloads.get(download_id)

        if not d:
            return {"status": ""}

        return {
            "status": d["status"],
            "repo": d["repo"],
            "file": d["file"],
            "downloaded": d["downloaded"],
            "total": d["total"],
            "percent": (
                round(d["downloaded"] * 100.0 / d["total"], 1) if d["total"] else None
            ),
            "speed_bps": d["speed_bps"],
            "eta_seconds": (
                int((d["total"] - d["downloaded"]) / d["speed_bps"])
                if d["total"] and d["speed_bps"] > 0
                else None
            ),
            "error": d.get("error", ""),
            "model_id": d.get("model_id", ""),
        }


def active_downloads() -> List[Dict[str, Any]]:
    with _downloads_lock:
        ids = list(_downloads.keys())

    out = []

    for did in ids:
        p = download_progress(did)

        p["download_id"] = did

        out.append(p)

    return out


def cancel_download(download_id: str) -> Dict[str, Any]:
    with _downloads_lock:
        d = _downloads.get(download_id)

        if not d:
            return {"ok": False, "error": "unknown download"}

        d["cancel"].set()

    return {"ok": True}


def _register_downloaded(repo: str, filename: str, size_bytes: int) -> str:
    """Alta en el registry apenas termina la descarga → usable sin reiniciar."""

    model_id = f"gguf:{filename}"

    display = re.sub(r"\.gguf$", "", filename, flags=re.IGNORECASE)

    with _registry_lock:
        entries = [e for e in _load_registry() if e.get("id") != model_id]

        entries.append({
            "id": model_id,
            "name": display,
            "file": filename,
            "repo": repo,
            "quant": cookbook_hf._quant_of(filename),
            "size_bytes": size_bytes,
            "added_at": int(time.time()),
        })

        _save_registry(entries)

    return model_id


def _do_download(download_id: str) -> None:
    with _downloads_lock:
        d = _downloads[download_id]

    repo, filename = d["repo"], d["file"]

    dest = models_dir() / _sanitize_filename(filename)

    part = dest.with_name(dest.name + ".part")

    try:
        models_dir().mkdir(parents=True, exist_ok=True)

        url = cookbook_hf.download_url(repo, filename)

        resume_from = part.stat().st_size if part.exists() else 0

        headers = {"User-Agent": "clawksis-cookbook"}

        if resume_from:
            headers["Range"] = f"bytes={resume_from}-"

        req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, timeout=60) as resp:
            # 206 = el server honró el Range (resume); 200 = arranca de cero.

            if resume_from and resp.status != 206:
                resume_from = 0

            length = resp.headers.get("Content-Length")

            total = (int(length) + resume_from) if length else 0

            with _downloads_lock:
                d["total"] = total

                d["downloaded"] = resume_from

            mode = "ab" if resume_from else "wb"

            window_t = time.monotonic()

            window_bytes = 0

            with open(part, mode) as out:
                while True:
                    if d["cancel"].is_set():
                        with _downloads_lock:
                            d["status"] = "cancelled"

                        return  # el .part queda: la próxima descarga resume

                    chunk = resp.read(_CHUNK)

                    if not chunk:
                        break

                    out.write(chunk)

                    window_bytes += len(chunk)

                    now = time.monotonic()

                    with _downloads_lock:
                        d["downloaded"] += len(chunk)

                        if now - window_t >= 1.0:
                            d["speed_bps"] = int(window_bytes / (now - window_t))

                            window_t, window_bytes = now, 0

        with _downloads_lock:
            d["status"] = "verifying"

        actual = part.stat().st_size

        if d["total"] and actual != d["total"]:
            raise RuntimeError(f"incomplete download: {actual} of {d['total']} bytes")

        with open(part, "rb") as fh:
            if fh.read(4) != b"GGUF":
                part.unlink(missing_ok=True)  # basura: no sirve para resume

                raise RuntimeError("downloaded file is not GGUF (bad magic bytes)")

        with _downloads_lock:
            d["status"] = "registering"

        part.replace(dest)

        model_id = _register_downloaded(repo, dest.name, actual)

        with _downloads_lock:
            d["status"] = "done"

            d["model_id"] = model_id

    except Exception as exc:  # noqa: BLE001
        with _downloads_lock:
            d["status"] = "error"

            d["error"] = str(exc)[:300]


def start_download(repo: str, filename: str) -> Dict[str, Any]:
    """Baja ``repo/filename`` de HF a la carpeta de modelos, en background.

    Devuelve {ok, download_id}; el progreso se consulta con
    ``download_progress(download_id)``. Idempotente: si ese archivo ya se está
    bajando, devuelve el download en curso.
    """

    repo = (repo or "").strip().strip("/")

    filename = (filename or "").strip()

    if not repo or "/" not in repo or not filename.lower().endswith(".gguf"):
        return {"ok": False, "error": "repo and a .gguf filename are required"}

    if cookbook_hf._MULTIPART_RE.search(filename):
        return {
            "ok": False,
            "error": "multi-part GGUF files aren't supported yet — pick a single-file quant",
        }

    with _downloads_lock:
        for did, d in _downloads.items():
            if (
                d["repo"] == repo
                and d["file"] == filename
                and d["status"] in ("preparing", "downloading")
            ):
                return {"ok": True, "download_id": did, "status": d["status"]}

        did = uuid.uuid4().hex[:12]

        _downloads[did] = {
            "repo": repo,
            "file": filename,
            "status": "downloading",
            "downloaded": 0,
            "total": 0,
            "speed_bps": 0,
            "cancel": threading.Event(),
        }

    threading.Thread(
        target=_do_download, args=(did,), name=f"gguf-dl-{did}", daemon=True
    ).start()

    return {"ok": True, "download_id": did, "status": "downloading"}


# ── servidor llama-server ────────────────────────────────────────────────────

_server: Dict[str, Any] = {"proc": None, "model_file": "", "started_at": 0.0}

_server_lock = threading.Lock()


def server_running() -> bool:
    try:
        with urllib.request.urlopen(f"{LLAMACPP_BASE_URL}/health", timeout=2) as resp:
            return 200 <= resp.status < 300

    except Exception:
        return False


def server_status() -> Dict[str, Any]:
    proc = _server.get("proc")

    alive = proc is not None and proc.poll() is None

    return {
        "running": alive and server_running(),
        "model_file": _server.get("model_file", "") if alive else "",
        "base_url": LLAMACPP_OPENAI_URL,
        "port": LLAMACPP_PORT,
    }


def stop_server() -> Dict[str, Any]:
    with _server_lock:
        proc = _server.get("proc")

        _server.update({"proc": None, "model_file": ""})

    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()

            try:
                proc.wait(timeout=8)

            except subprocess.TimeoutExpired:
                proc.kill()

        except Exception:
            pass

    return {"ok": True}


def start_server(
    model_file: str, ctx: int = 8192, wait_seconds: float = 90.0
) -> Dict[str, Any]:
    """Arranca (o reusa) llama-server sirviendo *model_file*.

    ``--jinja`` habilita el chat-template nativo → tool-calling OpenAI-style.
    El primer arranque carga el modelo a memoria, por eso la espera generosa.
    """

    binary = server_binary()

    if not binary:
        return {
            "ok": False,
            "error": "llama.cpp isn't installed",
            "needs_install": True,
        }

    path = models_dir() / model_file

    if not path.is_file():
        return {"ok": False, "error": f"model file not found: {model_file}"}

    with _server_lock:
        proc = _server.get("proc")

        if (
            proc is not None
            and proc.poll() is None
            and _server.get("model_file") == model_file
        ):
            if server_running():
                return {"ok": True, "base_url": LLAMACPP_OPENAI_URL, "reused": True}

    stop_server()

    try:
        proc = subprocess.Popen(
            [
                binary,
                "-m",
                str(path),
                "--host",
                "127.0.0.1",
                "--port",
                str(LLAMACPP_PORT),
                "-c",
                str(int(ctx)),
                "--jinja",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
        )

    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"failed to spawn llama-server: {exc}"}

    with _server_lock:
        _server.update({
            "proc": proc,
            "model_file": model_file,
            "started_at": time.time(),
        })

    deadline = time.monotonic() + wait_seconds

    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return {
                "ok": False,
                "error": "llama-server exited during startup (model too big for RAM?)",
            }

        if server_running():
            return {"ok": True, "base_url": LLAMACPP_OPENAI_URL}

        time.sleep(0.6)

    return {"ok": False, "error": "llama-server didn't become healthy in time"}


def use_model(model_id: str) -> Dict[str, Any]:
    """Sirve el GGUF con llama-server y lo deja como modelo del agente.

    Mismo mecanismo custom-provider que Ollama (base_url OpenAI-compatible),
    así que aplica a chat, agentes, skills, workflows — todo lo que use el
    modelo del agente.
    """

    entry = next((e for e in list_models() if e.get("id") == model_id), None)

    if entry is None:
        return {"ok": False, "error": "model not found"}

    started = start_server(str(entry["file"]))

    if not started.get("ok"):
        return started

    try:
        from clawk_cli.config import load_config, save_config

        config = load_config()

        model_cfg = config.get("model")

        if not isinstance(model_cfg, dict):
            model_cfg = {}

        model_cfg.update({
            "provider": "custom",
            "default": str(entry["name"]),
            "base_url": LLAMACPP_OPENAI_URL,
            "api_key": "llamacpp",  # llama-server lo ignora; no-vacío evita prompts
        })

        config["model"] = model_cfg

        save_config(config)

    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"failed to set model: {exc}"}

    return {
        "ok": True,
        "provider": "custom",
        "model": str(entry["name"]),
        "base_url": LLAMACPP_OPENAI_URL,
    }


def status() -> Dict[str, Any]:
    return {
        "installed": llamacpp_installed(),
        "install_status": install_status(),
        "server": server_status(),
        "models_dir": str(models_dir()),
        "models": list_models(),
        "base_url": LLAMACPP_OPENAI_URL,
    }
