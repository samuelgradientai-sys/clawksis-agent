"""Provider architecture for the Cookbook — backends de modelos locales.

Cada backend implementa la MISMA superficie (status / instalación / listado /
descarga / borrado / use), así el Cookbook crece agregando providers sin
reescribir nada. Hoy:

  * ``ollama``   — adapter fino sobre ``clawk_cli.cookbook`` (todo reuso).
  * ``llamacpp`` — ``clawk_cli.cookbook_llamacpp`` (GGUF de Hugging Face).

Mañana (mismo contrato): LM Studio, vLLM, SGLang, MLX, cualquier server
OpenAI-compatible. Los endpoints del dashboard y el CLI hablan SOLO con esta
capa (``get_provider(name)`` / ``providers_status()``), nunca con un backend
directo.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class LocalModelProvider(Protocol):
    """Contrato mínimo de un backend de modelos locales."""

    name: str

    display_name: str

    def status(self) -> Dict[str, Any]:
        """Estado: installed / running / modelos / base_url / extras."""
        ...

    def start_install(self) -> Dict[str, Any]:
        """Instala el backend en este host, en background."""
        ...

    def install_status(self) -> str:
        """ "installing" | "done" | "error: ..." | ""."""
        ...

    def installed_models(self) -> List[Dict[str, Any]]:
        """Modelos instalados, shape {id, name, size_bytes?, provider, ...}."""
        ...

    def delete_model(self, model_id: str) -> Dict[str, Any]: ...

    def use_model(self, model_id: str) -> Dict[str, Any]:
        """Deja *model_id* como modelo del agente (config custom-provider)."""
        ...


# ── Ollama (adapter sobre cookbook.py — cero lógica duplicada) ───────────────


class OllamaProvider:
    name = "ollama"

    display_name = "Ollama"

    def status(self) -> Dict[str, Any]:
        from clawk_cli import cookbook

        return cookbook.ollama_status()

    def start_install(self) -> Dict[str, Any]:
        from clawk_cli import cookbook

        return cookbook.start_ollama_install()

    def install_status(self) -> str:
        from clawk_cli import cookbook

        return cookbook.ollama_install_status()

    def installed_models(self) -> List[Dict[str, Any]]:
        from clawk_cli import cookbook

        return [
            {
                "id": f"ollama:{tag}",
                "name": tag,
                "provider": self.name,
                "size_bytes": info.get("size", 0),
                "path": "",
                "quant": "",
            }
            for tag, info in cookbook.ollama_models_detailed().items()
        ]

    def delete_model(self, model_id: str) -> Dict[str, Any]:
        from clawk_cli import cookbook

        return cookbook.delete_ollama_model(self._tag(model_id))

    def use_model(self, model_id: str) -> Dict[str, Any]:
        from clawk_cli import cookbook

        return cookbook.use_model(self._tag(model_id))

    @staticmethod
    def _tag(model_id: str) -> str:
        return model_id.split(":", 1)[1] if model_id.startswith("ollama:") else model_id


# ── llama.cpp ────────────────────────────────────────────────────────────────


class LlamaCppProvider:
    name = "llamacpp"

    display_name = "llama.cpp"

    def status(self) -> Dict[str, Any]:
        from clawk_cli import cookbook_llamacpp

        return cookbook_llamacpp.status()

    def start_install(self) -> Dict[str, Any]:
        from clawk_cli import cookbook_llamacpp

        return cookbook_llamacpp.start_install()

    def install_status(self) -> str:
        from clawk_cli import cookbook_llamacpp

        return cookbook_llamacpp.install_status()

    def installed_models(self) -> List[Dict[str, Any]]:
        from clawk_cli import cookbook_llamacpp

        return [{**e, "provider": self.name} for e in cookbook_llamacpp.list_models()]

    def delete_model(self, model_id: str) -> Dict[str, Any]:
        from clawk_cli import cookbook_llamacpp

        return cookbook_llamacpp.delete_model(model_id)

    def use_model(self, model_id: str) -> Dict[str, Any]:
        from clawk_cli import cookbook_llamacpp

        return cookbook_llamacpp.use_model(model_id)


_PROVIDERS: Dict[str, Any] = {
    "ollama": OllamaProvider(),
    "llamacpp": LlamaCppProvider(),
}


def get_provider(name: str) -> Optional[Any]:
    return _PROVIDERS.get((name or "").strip().lower())


def all_providers() -> List[Any]:
    return list(_PROVIDERS.values())


def providers_status() -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    for p in all_providers():
        try:
            out[p.name] = p.status()

        except Exception as exc:  # noqa: BLE001 — un backend roto no tira el resto
            out[p.name] = {"installed": False, "error": str(exc)[:200]}

    return out


def all_installed_models() -> List[Dict[str, Any]]:
    """Listado unificado de modelos instalados de TODOS los providers."""

    out: List[Dict[str, Any]] = []

    for p in all_providers():
        try:
            out.extend(p.installed_models())

        except Exception:
            continue

    return out
