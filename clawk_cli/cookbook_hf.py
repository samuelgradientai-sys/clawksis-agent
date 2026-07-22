"""Hugging Face search client for the Cookbook — GGUF models for llama.cpp.

Búsqueda EN VIVO contra la API pública de Hugging Face (sin API key): nada de
precargar listas gigantes; cada tecleo del usuario dispara una consulta acotada
(`limit`) que se cachea unos minutos. Dos llamadas:

  * ``search_gguf(query)``  → repos GGUF que matchean (nombre, autor,
    descargas, likes, licencia, última actualización).
  * ``repo_gguf_files(repo)`` → los archivos .gguf del repo con tamaño y
    cuantización parseada (Q4_K_M, Q5_K_M, Q8_0, IQ…, F16…), para que el
    usuario elija QUÉ variante bajar.

Todo best-effort: sin red devuelve listas vacías, nunca levanta al caller.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

HF_API = "https://huggingface.co/api"

_HEADERS = {"User-Agent": "clawksis-cookbook/1.0"}

# TTL caches (mismo patrón que el scrape de ollama.com en cookbook.py).
_cache: Dict[str, tuple] = {}

_SEARCH_TTL = 300.0

_FILES_TTL = 600.0


def _get_json(url: str, timeout: float = 15.0) -> Optional[Any]:
    try:
        req = urllib.request.Request(url, headers=_HEADERS)

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if not (200 <= resp.status < 300):
                return None

            return json.loads(resp.read().decode("utf-8", "replace"))

    except Exception:
        return None


def _license_from_tags(tags: List[str]) -> str:
    for tag in tags:
        if tag.startswith("license:"):
            return tag.split(":", 1)[1]

    return ""


def search_gguf(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Repos GGUF de Hugging Face que matchean *query*, por descargas.

    Con ``expand[]=gguf`` HF devuelve la metadata extraída del GGUF: ventana
    de contexto real, arquitectura y total de parámetros — lo que permite
    filtrar por características ("modelos con 256k de contexto") y estimar
    el fit sin bajar nada. ``tool_use`` es heurístico: el chat_template del
    GGUF menciona tools ⇒ el modelo soporta function-calling.

    Shape por fila: {repo, author, name, downloads, likes, updated_at,
    license, gated, tags, context, architecture, params_b, size_q4_gb,
    tool_use}. Vacío sin query o sin red.
    """

    q = (query or "").strip()

    if not q:
        return []

    key = f"s:{q.lower()}:{limit}"

    cached = _cache.get(key)

    if cached and time.monotonic() - cached[0] < _SEARCH_TTL:
        return cached[1]

    expand = "&".join(
        f"expand[]={e}"
        for e in ("gguf", "downloads", "likes", "lastModified", "tags", "gated")
    )

    url = (
        f"{HF_API}/models?search={urllib.parse.quote(q)}"
        f"&filter=gguf&sort=downloads&direction=-1&limit={int(limit)}&{expand}"
    )

    data = _get_json(url)

    rows: List[Dict[str, Any]] = []

    if isinstance(data, list):
        for item in data:
            repo = str(item.get("id") or item.get("modelId") or "")

            if not repo:
                continue

            tags = [str(t) for t in (item.get("tags") or [])]

            gguf = item.get("gguf") if isinstance(item.get("gguf"), dict) else {}

            context = int(gguf.get("context_length") or 0)

            params_total = int(gguf.get("total") or 0)

            params_b = round(params_total / 1e9, 1) if params_total else 0.0

            # Estimación Q4_K_M: ~0.6 GB por B de parámetros + overhead runtime.

            size_q4_gb = round(params_b * 0.6 + 1.0, 1) if params_b else 0.0

            template = str(gguf.get("chat_template") or "")

            tool_use = "tool" in template.lower() if template else False

            rows.append({
                "repo": repo,
                "author": repo.split("/", 1)[0] if "/" in repo else "",
                "name": repo.split("/", 1)[-1],
                "downloads": int(item.get("downloads") or 0),
                "likes": int(item.get("likes") or 0),
                "updated_at": str(item.get("lastModified") or ""),
                "license": _license_from_tags(tags),
                "gated": bool(item.get("gated")),
                "tags": [t for t in tags if not t.startswith("license:")][:8],
                "context": context,
                "architecture": str(gguf.get("architecture") or ""),
                "params_b": params_b,
                "size_q4_gb": size_q4_gb,
                "tool_use": tool_use,
            })

    _cache[key] = (time.monotonic(), rows)

    return rows


# Cuantizaciones conocidas, de mejor-calidad a menor. El orden se usa para
# sugerir un default sensato (Q4_K_M es el sweet spot tamaño/calidad).
_QUANT_RE = re.compile(
    r"(IQ\d+_[A-Z0-9_]+|Q\d+_K_[MSL]|Q\d+_K|Q\d+_\d+|BF16|F16|F32)",
    re.IGNORECASE,
)

_MULTIPART_RE = re.compile(r"-\d{5}-of-\d{5}\.gguf$", re.IGNORECASE)


def _quant_of(filename: str) -> str:
    m = _QUANT_RE.search(filename)

    return m.group(1).upper() if m else ""


def repo_gguf_files(repo: str) -> List[Dict[str, Any]]:
    """Archivos .gguf de un repo HF, con tamaño y quant.

    Shape: {file, size_bytes, quant, multipart}. Los multipart (00001-of-000N)
    se marcan — la descarga simple no los soporta (habría que unirlos).
    """

    r = (repo or "").strip().strip("/")

    if not r or "/" not in r:
        return []

    key = f"f:{r}"

    cached = _cache.get(key)

    if cached and time.monotonic() - cached[0] < _FILES_TTL:
        return cached[1]

    data = _get_json(f"{HF_API}/models/{urllib.parse.quote(r, safe='/')}?blobs=true")

    rows: List[Dict[str, Any]] = []

    if isinstance(data, dict):
        for sib in data.get("siblings") or []:
            name = str(sib.get("rfilename") or "")

            if not name.lower().endswith(".gguf"):
                continue

            rows.append({
                "file": name,
                "size_bytes": int(sib.get("size") or 0),
                "quant": _quant_of(name),
                "multipart": bool(_MULTIPART_RE.search(name)),
            })

    rows.sort(key=lambda f: (f["multipart"], f["size_bytes"]))

    _cache[key] = (time.monotonic(), rows)

    return rows


def download_url(repo: str, filename: str) -> str:
    """URL directa de descarga de un archivo del repo (sigue redirect al CDN)."""

    r = urllib.parse.quote((repo or "").strip().strip("/"), safe="/")

    f = urllib.parse.quote((filename or "").strip())

    return f"https://huggingface.co/{r}/resolve/main/{f}?download=true"
