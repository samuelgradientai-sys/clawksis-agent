"""Local-vs-cloud classification for model picker rows and the local endpoint reachability probe.

A row is *local* when the endpoint serving it is loopback / LAN / Tailscale
(``agent.model_metadata.is_local_endpoint``): user-defined rows by their ``api_url``, the
built-in local providers (Ollama, LM Studio, the managed llama.cpp runtime) by their default
endpoint. ``apply_locality`` stamps every inventory row with ``is_local`` (+ ``local_url``), so
GUI pickers split local from cloud on the backend's verdict instead of guessing from slugs.

``probe_local_endpoints`` answers ``GET /api/model/local-status``: every local endpoint the
profile's config points at (main model, ``custom_providers:`` / ``providers:``, auxiliary pins,
the built-in local defaults) is asked for its model list with a short timeout, so the dashboard
can say "running · 3 models" or "not reachable" next to a local model — the picker payload itself
never probes saved endpoints on a normal open.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_HTTP_SCHEMES = ("http://", "https://")
_LOCAL_ROW_SOURCES = frozenset({"local", "local-runtime"})
_PROBE_TIMEOUT_S = 2.5


def norm_url(url: Any) -> str:
    return str(url or "").strip().rstrip("/").lower()


def is_http_local(url: Any) -> bool:
    """``is_local_endpoint`` restricted to HTTP(S): pseudo-URLs such as ``acp://copilot`` or
    ``cloudcode-pa://google`` carry an unqualified "host" that the endpoint check calls local."""
    from agent.model_metadata import is_local_endpoint

    text = str(url or "").strip()
    return text.lower().startswith(_HTTP_SCHEMES) and is_local_endpoint(text)


def _managed_llamacpp_endpoint() -> dict | None:
    try:
        from clawk_cli.local_runtime.endpoint import _state_endpoint

        return _state_endpoint()
    except (
        Exception
    ):  # an unreadable runtime state file means "not running", never a failed catalog
        logger.debug("managed llama.cpp state unreadable", exc_info=True)
        return None


def builtin_local_url(slug: str) -> str:
    """Default endpoint of a built-in local provider; ``""`` for every other slug (or when the
    managed llama.cpp server is not running — its models start on demand)."""
    from clawk_cli.providers import LLAMACPP_ALIASES

    key = str(slug or "").strip().lower()
    if key == "ollama":
        from clawk_cli.cookbook import OLLAMA_OPENAI_URL

        return OLLAMA_OPENAI_URL
    if key in LLAMACPP_ALIASES:
        managed = _managed_llamacpp_endpoint()
        return str(managed.get("base_url") or "") if managed else ""
    from clawk_cli.auth import PROVIDER_REGISTRY

    pcfg = PROVIDER_REGISTRY.get(key)
    default = str(getattr(pcfg, "inference_base_url", "") or "") if pcfg else ""
    if not is_http_local(default):
        return ""  # a cloud provider stays cloud; only local-by-design rows read their override
    url = ""
    if getattr(pcfg, "base_url_env_var", ""):
        from agent.secret_scope import get_secret_str

        url = get_secret_str(
            pcfg.base_url_env_var
        ).strip()  # e.g. LM_BASE_URL → a LAN box
    url = url or default
    return url if is_http_local(url) else ""


def apply_locality(rows: list[dict]) -> None:
    """Stamp ``is_local`` on every row and ``local_url`` (where its models are served) on local
    rows. Purely computed from config/registry — no network."""
    for row in rows:
        api_url = str(row.get("api_url") or "").strip()
        url = api_url or builtin_local_url(str(row.get("slug") or ""))
        local = is_http_local(url) or row.get("source") in _LOCAL_ROW_SOURCES
        row["is_local"] = bool(local)
        if local and url:
            row["local_url"] = url.rstrip("/")


def _entry_url(entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""
    for key in ("base_url", "url", "api"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _referenced_provider_slugs(cfg: dict) -> set[str]:
    slugs: set[str] = set()
    model_cfg = cfg.get("model")
    if isinstance(model_cfg, dict):
        slugs.add(str(model_cfg.get("provider") or "").strip().lower())
    aux = cfg.get("auxiliary")
    if isinstance(aux, dict):
        slugs.update(
            str(slot.get("provider") or "").strip().lower()
            for slot in aux.values()
            if isinstance(slot, dict)
        )
    providers = cfg.get("providers")
    if isinstance(providers, dict):
        slugs.update(str(name).strip().lower() for name in providers)
    slugs.add("ollama")  # its picker row appears whenever the daemon answers
    slugs.discard("")
    return slugs


def configured_local_endpoints(cfg: dict) -> list[str]:
    """Every distinct local HTTP endpoint the config can route to, in a stable order."""
    from clawk_cli.config import get_compatible_custom_providers

    candidates: list[str] = []
    model_cfg = cfg.get("model")
    if isinstance(model_cfg, dict):
        candidates.append(_entry_url(model_cfg))
    candidates.extend(_entry_url(e) for e in get_compatible_custom_providers(cfg))
    aux = cfg.get("auxiliary")
    if isinstance(aux, dict):
        candidates.extend(_entry_url(slot) for slot in aux.values())
    candidates.extend(
        builtin_local_url(slug) for slug in sorted(_referenced_provider_slugs(cfg))
    )
    seen: set[str] = set()
    endpoints: list[str] = []
    for url in candidates:
        key = norm_url(url)
        if key and key not in seen and is_http_local(url):
            seen.add(key)
            endpoints.append(url.strip().rstrip("/"))
    return endpoints


def _model_ids(payload: Any) -> list[str] | None:
    """Model ids from an OpenAI ``{"data": [{"id"}]}`` list or an Ollama ``{"models": [{"name"}]}``."""
    if isinstance(payload, dict):
        rows = payload.get("data")
        if not isinstance(rows, list):
            rows = payload.get("models")
    else:
        rows = payload
    if not isinstance(rows, list):
        return None
    ids = []
    for item in rows:
        if isinstance(item, dict):
            ident = item.get("id") or item.get("name") or item.get("model")
        else:
            ident = item
        if isinstance(ident, str) and ident.strip():
            ids.append(ident.strip())
    return ids


def _candidate_model_urls(url: str) -> list[str]:
    base = url.rstrip("/")
    if base.lower().endswith("/v1"):
        return [base + "/models"]
    return [base + "/models", base + "/v1/models"]


async def _probe_one(url: str, headers: dict | None, timeout: float) -> dict:
    """GET the endpoint's model list. Any HTTP answer proves the server is up (a 401 means it wants
    a key); only a transport failure or timeout is "not reachable".

    ``trust_env=False``: every probed URL is local, and httpx honours ``HTTP(S)_PROXY`` but not its
    bypass list, so a system proxy would answer a loopback probe with its own error page (#63472)."""
    import httpx

    started = time.monotonic()
    result: dict[str, Any] = {
        "url": url,
        "reachable": False,
        "status": None,
        "models": None,
        "error": None,
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout), trust_env=False
    ) as client:
        for candidate in _candidate_model_urls(url):
            try:
                resp = await client.get(candidate, headers=headers)
            except (httpx.HTTPError, httpx.InvalidURL) as exc:
                result["error"] = type(exc).__name__
                continue
            result.update(reachable=True, status=resp.status_code, error=None)
            if resp.is_success:
                try:
                    result["models"] = _model_ids(resp.json())
                except ValueError:
                    result["error"] = "not an OpenAI-compatible model list"
                break
            result["error"] = f"HTTP {resp.status_code}"
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result


def local_status_targets(cfg: dict) -> tuple[list[str], dict]:
    """``(endpoints, managed)`` for ``probe_local_endpoints`` — resolve under the profile's scope:
    the config and the managed runtime's state are both read from the active home."""
    return configured_local_endpoints(cfg), _managed_llamacpp_endpoint() or {}


async def probe_local_endpoints(
    endpoints: list[str],
    managed: dict | None = None,
    *,
    timeout: float = _PROBE_TIMEOUT_S,
) -> list[dict]:
    """Probe every endpoint concurrently; the managed llama.cpp router is asked with its own key."""
    managed = managed or {}
    managed_url = norm_url(managed.get("base_url"))
    managed_key = str(managed.get("api_key") or "")

    def _headers(url: str) -> dict | None:
        if managed_key and norm_url(url) == managed_url:
            return {"Authorization": f"Bearer {managed_key}"}
        return None

    if managed_url and managed_url not in {norm_url(u) for u in endpoints}:
        endpoints = [*endpoints, str(managed.get("base_url")).rstrip("/")]
    return list(
        await asyncio.gather(
            *(_probe_one(url, _headers(url), timeout) for url in endpoints)
        )
    )
