"""``clawk config permissions``: one switch for how much the agent may do on this machine.

``full`` lets the agent act without asking: commands run without approval prompts (also in
cron jobs and unattended runs), it may edit its own instruction files (SOUL.md / AGENTS.md)
and schedule jobs from cron, and the terminal runs on this machine. It can change its own
settings with ``clawk config set`` from its terminal (direct writes to config.yaml stay
refused, so every change goes through the validated setter). ``default`` restores the
shipped values; no argument shows where each setting stands.

What ``full`` never lifts: the hardline floor (wiping / or /home, formatting disks, shutting
the host down), the user's own ``approvals.deny`` list and secret redaction. The settings are
plain config.yaml keys, so ``clawk config set`` can fine-tune any of them afterwards.
"""

from __future__ import annotations

import contextlib
import io
import sys

# key -> (value under "full", what it means for the user)
FULL_ACCESS: dict[str, tuple[str, str]] = {
    "approvals.mode": ("off", "comandos sin pedir aprobación"),
    "approvals.cron_mode": ("approve", "las tareas programadas también"),
    "approvals.unattended_mode": ("approve", "webhooks y API sin nadie mirando"),
    "approvals.single_query_mode": ("approve", "consultas sueltas (clawk -q)"),
    "security.protected_instruction_files": ("false", "editar SOUL.md / AGENTS.md"),
    "cron.allow_agent_scheduling": ("true", "crear tareas desde un cron"),
    "terminal.backend": ("local", "terminal en esta máquina, sin sandbox"),
}


def _default_values() -> dict[str, str]:
    from clawk_cli.config_defaults import DEFAULT_CONFIG

    out = {}
    for key in FULL_ACCESS:
        node = DEFAULT_CONFIG
        for part in key.split("."):
            node = node[part]
        out[key] = str(node).lower() if isinstance(node, bool) else str(node)
    return out


def _current_values() -> dict[str, str]:
    from clawk_cli.config import load_config

    config = load_config()
    out = {}
    for key in FULL_ACCESS:
        node = config
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        out[key] = str(node).lower() if isinstance(node, bool) else str(node)
    return out


def access_level(current: dict[str, str]) -> str:
    """``full`` when every switch is open, ``default`` when none is, else ``custom``."""
    open_ = [current.get(k) == v for k, (v, _) in FULL_ACCESS.items()]
    defaults = _default_values()
    if all(open_):
        return "full"
    if all(current.get(k) == defaults[k] for k in FULL_ACCESS):
        return "default"
    return "custom"


def _apply(values: dict[str, str]) -> None:
    from clawk_cli.config import set_config_value

    # set_config_value prints one line per key; the summary below says it once.
    with contextlib.redirect_stdout(io.StringIO()):
        for key, value in values.items():
            set_config_value(key, value)


def _print_status() -> None:
    current = _current_values()
    labels = {
        "full": "acceso total",
        "default": "por defecto (seguro)",
        "custom": "personalizado",
    }
    print(f"Permisos del agente: {labels[access_level(current)]}\n")
    for key, (value, meaning) in FULL_ACCESS.items():
        mark = "✓" if current[key] == value else "·"
        print(f"  {mark} {key} = {current[key]}   ({meaning})")
    print(
        "\n  clawk config permissions full     → acceso total"
        "\n  clawk config permissions default  → volver a lo seguro"
    )


_FULL_WARNING = """El agente podrá, sin preguntarte:
  • ejecutar cualquier comando en esta máquina (también desde tareas programadas),
  • editar sus instrucciones (SOUL.md / AGENTS.md) y su configuración (`clawk config set`).
Quien pueda escribirle (Telegram, WhatsApp, Discord, el panel) controla esta máquina:
mantené las listas de usuarios permitidos y el login del panel.
Siguen bloqueados siempre: borrar / o /home, formatear discos y apagar el servidor."""


def _confirmed(args) -> bool:
    if getattr(args, "yes", False):
        return True
    if not sys.stdin.isatty():
        print("Sin terminal interactiva: repetí con --yes para confirmar.")
        return False
    answer = input("¿Dar acceso total al agente? Escribí «si» para confirmar: ")
    return answer.strip().lower() in {"si", "sí", "yes", "y", "s"}


def cmd_config_permissions(args) -> None:
    level = getattr(args, "level", None)
    if level is None:
        _print_status()
        return
    if level == "full":
        print(_FULL_WARNING + "\n")
        if not _confirmed(args):
            print("Sin cambios.")
            return
        _apply({k: v for k, (v, _) in FULL_ACCESS.items()})
        print(
            "✓ Acceso total activado. Las aprobaciones cambian al instante; abrí una "
            "conversación nueva para que todo tome efecto."
        )
        print("  Para volver: clawk config permissions default")
        return
    _apply(_default_values())
    print("✓ Permisos por defecto restaurados (aprobación inteligente de comandos).")
