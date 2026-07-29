"""Contexto ambiental de conversacion (contextvars).

Upstream usaba este modulo para etiquetar cada llamada LLM con tags del Nous
Portal. Clawksis es BYOK y no habla con el Portal, asi que aca sobrevive
UNICAMENTE la parte generica y util: publicar el id de conversacion activo en
un ``ContextVar`` para que todo lo que corre dentro del turno (loop principal,
compresion, vision, web_extract, session_search, slots de MoA, forks de
background-review) pueda leerlo sin plumbing por call-site.

Las funciones de tagging del Portal (``nous_portal_tags``, ``conversation_tag``,
``clawk_client_tag``) NO se portan: reintroducirlas volveria a acoplar el fork
al Portal. Si en el futuro se quiere telemetria propia, el hook natural es
``get_conversation_context()``.

El nombre del modulo se conserva porque ``run_agent.py`` y
``agent/title_generator.py`` ya lo importan; renombrarlo es un refactor
aparte.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

# ContextVar (no threading.local): cada turno corre en su propio Context, asi
# que turnos concurrentes no se pisan el id de conversacion. Los threads
# lanzados via ``tools.thread_context.propagate_context_to_thread`` lo heredan
# por el Context copiado; los threads pelados (title generator) lo capturan
# explicitamente al spawnear.
_conversation_id: ContextVar[Optional[str]] = ContextVar(
    "clawksis_conversation_id", default=None
)


def set_conversation_context(conversation_id: Optional[str]):
    """Publica el id de conversacion activo para el turno en curso.

    Lo llama el loop del agente al entrar al turno con el id estable de la
    conversacion (el ROOT del linaje de sesion, para que sobreviva a la
    rotacion de sesion por compresion de contexto). Pasar ``None`` limpia.
    Devuelve el token del ContextVar para poder
    ``reset_conversation_context(token)`` al salir del turno.
    """

    return _conversation_id.set(conversation_id or None)


def reset_conversation_context(token) -> None:
    """Restaura el contexto anterior (se usa en par con ``set_...``)."""

    try:
        _conversation_id.reset(token)
    except Exception:
        # Token de otro Context (p.ej. reset en otro thread): limpiar en vez
        # de romper en un camino de cleanup.
        _conversation_id.set(None)


def get_conversation_context() -> Optional[str]:
    """Devuelve el id de conversacion ambiental, o ``None`` si no hay."""

    return _conversation_id.get()
