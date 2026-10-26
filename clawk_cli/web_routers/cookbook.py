"""Cookbook dashboard routes: local models via Ollama and llama.cpp (catalog, search, pulls,
GGUF downloads, installed models, "use as the agent's model").

Backed by :mod:`clawk_cli.cookbook` and :mod:`clawk_cli.cookbook_providers`, shared with the
``clawk cookbook`` CLI. Model files and running servers are machine-level; only "use this model"
writes a profile's ``config.yaml``, so those two routes take ``?profile=`` and write inside
:func:`config_write_scope` — the profile the dashboard switcher selected, not the launch one.
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from clawk_cli.web_routers._common import config_write_scope

router = APIRouter()


def _scoped(profile: Optional[str], fn, *args):
    """Run a config-writing cookbook call inside the profile's config write scope."""
    with config_write_scope(profile):
        return fn(*args)


async def _live(build, key: str) -> dict:
    """Run a live-catalog lookup off the loop. An unreachable source answers ``{key: [],
    "error": ...}`` so the page says "unreachable" instead of "no models match"."""
    from clawk_cli.cookbook_hf import SourceUnreachable

    try:
        return await asyncio.to_thread(build)
    except SourceUnreachable as exc:
        return {key: [], "error": str(exc)}


@router.get("/api/cookbook/hardware")
async def get_cookbook_hardware():
    """Detected hardware (RAM / CPU / GPU + VRAM) for the fit recommender."""
    try:
        from clawk_cli import cookbook

        hw = await asyncio.to_thread(cookbook.detect_hardware)
    except Exception:
        hw = {}
    return {"hardware": hw}


@router.get("/api/cookbook/catalog")
async def get_cookbook_catalog():
    """Curated local-model catalog enriched with a per-model fit verdict.

    Each entry carries ``fit`` ({mode, tier, reason}) for the detected hardware
    and an ``installed`` flag (already pulled into the local Ollama).
    """
    try:
        from clawk_cli import cookbook

        def _build():
            hw = cookbook.detect_hardware()
            installed = cookbook.ollama_models()
            return {
                "hardware": hw,
                "ollama": cookbook.ollama_status(),
                "models": cookbook.catalog_with_fit(hw, installed),
            }

        return await asyncio.to_thread(_build)
    except Exception:
        return {"hardware": {}, "ollama": {}, "models": []}


@router.get("/api/cookbook/search")
async def get_cookbook_search(q: str):
    """Live search of the FULL Ollama library (scraped) for models matching *q*.

    Returns catalog-shaped rows (one per size tag) with fit + installed flags,
    so ANY model in ollama.com/library is findable — not just the curated set.
    An unreachable ollama.com answers ``error`` next to an empty list.
    """
    query = (q or "").strip()
    if not query:
        return {"models": []}
    from clawk_cli import cookbook

    def _build():
        hw = cookbook.detect_hardware()
        installed = cookbook.ollama_models()
        return {
            "models": cookbook.rows_with_fit(
                cookbook.search_ollama_library(query), hw, installed
            )
        }

    return await _live(_build, "models")


@router.get("/api/cookbook/library")
async def get_cookbook_library():
    """The FULL Ollama library (scraped, cached ~30 min) with fit + installed."""
    from clawk_cli import cookbook

    def _build():
        hw = cookbook.detect_hardware()
        installed = cookbook.ollama_models()
        return {
            "hardware": hw,
            "ollama": cookbook.ollama_status(),
            "models": cookbook.rows_with_fit(
                cookbook.full_ollama_library(), hw, installed
            ),
        }

    return await _live(_build, "models")


@router.get("/api/cookbook/ollama")
async def get_cookbook_ollama():
    """Ollama status (installed / running / pulled models)."""
    try:
        from clawk_cli import cookbook

        return await asyncio.to_thread(cookbook.ollama_status)
    except Exception:
        return {"installed": False, "running": False, "models": []}


class CookbookTagBody(BaseModel):
    tag: str


@router.post("/api/cookbook/pull")
async def post_cookbook_pull(body: CookbookTagBody):
    """Start `ollama pull <tag>` in the background. Poll /pull-status for progress."""
    tag = (body.tag or "").strip()
    if not tag:
        raise HTTPException(status_code=400, detail="tag is required")
    from clawk_cli import cookbook

    return await asyncio.to_thread(cookbook.start_pull, tag)


@router.get("/api/cookbook/pull-status")
async def get_cookbook_pull_status(tag: str):
    """Background pull status for a tag: pulling / validating / done / error.

    Incluye el progreso real del streaming pull (bytes, %, velocidad, ETA).
    """
    from clawk_cli import cookbook

    progress = cookbook.pull_progress(tag)
    return {"tag": tag, "status": cookbook.pull_status(tag), **progress}


@router.post("/api/cookbook/pull-cancel")
async def post_cookbook_pull_cancel(body: CookbookTagBody):
    """Cancela un `ollama pull` en curso (los blobs parciales se conservan)."""
    from clawk_cli import cookbook

    return await asyncio.to_thread(cookbook.cancel_pull, (body.tag or "").strip())


@router.post("/api/cookbook/install-ollama")
async def post_cookbook_install_ollama():
    """Install Ollama on the clawk host (background) so the Cookbook works here.

    "We ship Ollama with clawk" — install it on demand on the machine where the
    agent runs. Poll /install-ollama-status. Best-effort (Linux / macOS-brew).
    """
    from clawk_cli import cookbook

    return await asyncio.to_thread(cookbook.start_ollama_install)


@router.get("/api/cookbook/install-ollama-status")
async def get_cookbook_install_ollama_status():
    """Ollama install progress: installing / done / error / "" (unknown)."""
    from clawk_cli import cookbook

    return {"status": cookbook.ollama_install_status()}


@router.post("/api/cookbook/use")
async def post_cookbook_use(body: CookbookTagBody, profile: Optional[str] = None):
    """Set a local Ollama model as *profile*'s active model."""
    tag = (body.tag or "").strip()
    if not tag:
        raise HTTPException(status_code=400, detail="tag is required")
    from clawk_cli import cookbook

    result = await asyncio.to_thread(_scoped, profile, cookbook.use_model, tag)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "failed"))
    return result


# ── Cookbook: provider architecture (Ollama + llama.cpp + futuros) ──────────
#
# Los endpoints de arriba quedan por compatibilidad (Ollama directo). Los de
# abajo hablan con clawk_cli.cookbook_providers — la superficie común que
# permite agregar backends (LM Studio, vLLM, MLX…) sin tocar el frontend.


@router.get("/api/cookbook/providers")
async def get_cookbook_providers():
    """Estado de todos los backends de modelos locales (ollama, llamacpp…)."""
    from clawk_cli import cookbook_providers

    return await asyncio.to_thread(cookbook_providers.providers_status)


class CookbookProviderBody(BaseModel):
    provider: str


@router.post("/api/cookbook/provider-install")
async def post_cookbook_provider_install(body: CookbookProviderBody):
    """Instala un backend en este host, en background. Poll provider-install-status."""
    from clawk_cli import cookbook_providers

    p = cookbook_providers.get_provider(body.provider)
    if p is None:
        raise HTTPException(
            status_code=404, detail=f"unknown provider: {body.provider}"
        )
    return await asyncio.to_thread(p.start_install)


@router.get("/api/cookbook/provider-install-status")
async def get_cookbook_provider_install_status(provider: str):
    from clawk_cli import cookbook_providers

    p = cookbook_providers.get_provider(provider)
    if p is None:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")
    return {"provider": provider, "status": p.install_status()}


@router.get("/api/cookbook/hf-search")
async def get_cookbook_hf_search(q: str):
    """Búsqueda EN VIVO de repos GGUF en Hugging Face (para llama.cpp)."""
    query = (q or "").strip()
    if not query:
        return {"models": []}
    from clawk_cli import cookbook_hf

    return await _live(lambda: {"models": cookbook_hf.search_gguf(query)}, "models")


@router.get("/api/cookbook/hf-files")
async def get_cookbook_hf_files(repo: str):
    """Archivos .gguf de un repo HF con tamaño y cuantización (elegir variante)."""
    r = (repo or "").strip()
    if not r:
        raise HTTPException(status_code=400, detail="repo is required")
    from clawk_cli import cookbook_hf

    return {
        "repo": r,
        **await _live(lambda: {"files": cookbook_hf.repo_gguf_files(r)}, "files"),
    }


class CookbookDownloadBody(BaseModel):
    repo: str
    file: str


@router.post("/api/cookbook/download")
async def post_cookbook_download(body: CookbookDownloadBody):
    """Descarga un GGUF de HF directo a la carpeta de modelos de llama.cpp.

    Devuelve {download_id}; el progreso (bytes, %, velocidad, ETA, cancel) se
    consulta con /download-status. Con un .part previo, RESUME donde quedó.
    """
    from clawk_cli import cookbook_llamacpp

    result = await asyncio.to_thread(
        cookbook_llamacpp.start_download, body.repo, body.file
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "failed"))
    return result


@router.get("/api/cookbook/download-status")
async def get_cookbook_download_status(id: str):
    from clawk_cli import cookbook_llamacpp

    return {"download_id": id, **cookbook_llamacpp.download_progress(id)}


class CookbookDownloadIdBody(BaseModel):
    id: str


@router.post("/api/cookbook/download-cancel")
async def post_cookbook_download_cancel(body: CookbookDownloadIdBody):
    """Cancela una descarga GGUF (el .part queda para reanudar después)."""
    from clawk_cli import cookbook_llamacpp

    return await asyncio.to_thread(cookbook_llamacpp.cancel_download, body.id)


@router.get("/api/cookbook/active")
async def get_cookbook_active():
    """Descargas GGUF y pulls de Ollama EN CURSO (server-side, en background).

    Las descargas corren en threads del server y NO dependen del navegador:
    al volver a la pestaña, la UI llama esto para re-engancharse al progreso
    en vez de dar por muerta la instalación.
    """
    from clawk_cli import cookbook, cookbook_llamacpp

    downloads = await asyncio.to_thread(cookbook_llamacpp.active_downloads)
    pulls = await asyncio.to_thread(cookbook.active_pulls)
    interrupted = await asyncio.to_thread(cookbook_llamacpp.interrupted_downloads)
    return {"downloads": downloads, "pulls": pulls, "interrupted": interrupted}


@router.get("/api/cookbook/installed")
async def get_cookbook_installed():
    """Modelos instalados de TODOS los providers (tamaño, ruta, quant, origen)."""
    from clawk_cli import cookbook_providers

    models = await asyncio.to_thread(cookbook_providers.all_installed_models)
    return {"models": models}


class CookbookModelBody(BaseModel):
    provider: str
    id: str


@router.post("/api/cookbook/model-delete")
async def post_cookbook_model_delete(body: CookbookModelBody):
    from clawk_cli import cookbook_providers

    p = cookbook_providers.get_provider(body.provider)
    if p is None:
        raise HTTPException(
            status_code=404, detail=f"unknown provider: {body.provider}"
        )
    result = await asyncio.to_thread(p.delete_model, body.id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "failed"))
    return result


@router.post("/api/cookbook/model-use")
async def post_cookbook_model_use(
    body: CookbookModelBody, profile: Optional[str] = None
):
    """Deja un modelo instalado (de cualquier provider) como modelo del agente.

    Para llamacpp además arranca el servidor OpenAI-compatible si hace falta.
    Aplica en todo lo que usa el modelo del agente de ``profile``: chat,
    agentes, skills, workflows, crons.
    """
    from clawk_cli import cookbook_providers

    p = cookbook_providers.get_provider(body.provider)
    if p is None:
        raise HTTPException(
            status_code=404, detail=f"unknown provider: {body.provider}"
        )
    result = await asyncio.to_thread(_scoped, profile, p.use_model, body.id)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "failed"))
    return result


class CookbookRenameBody(BaseModel):
    id: str
    name: str


@router.post("/api/cookbook/model-rename")
async def post_cookbook_model_rename(body: CookbookRenameBody):
    """Renombra el display-name de un GGUF registrado (solo llamacpp)."""
    from clawk_cli import cookbook_llamacpp

    result = await asyncio.to_thread(cookbook_llamacpp.rename_model, body.id, body.name)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "failed"))
    return result


class CookbookIdBody(BaseModel):
    id: str


@router.post("/api/cookbook/model-verify")
async def post_cookbook_model_verify(body: CookbookIdBody):
    """Chequeo de integridad de un GGUF (existencia, tamaño, magic bytes)."""
    from clawk_cli import cookbook_llamacpp

    return await asyncio.to_thread(cookbook_llamacpp.verify_model, body.id)


@router.post("/api/cookbook/llamacpp-stop")
async def post_cookbook_llamacpp_stop():
    """Frena el llama-server en curso (libera la RAM del modelo)."""
    from clawk_cli import cookbook_llamacpp

    return await asyncio.to_thread(cookbook_llamacpp.stop_server)
