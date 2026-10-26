"""``clawk config`` subcommand parser."""

from __future__ import annotations

from typing import Callable

from clawk_cli.subcommands._shared import add_json_flag


def _cmd_config_permissions(args) -> None:
    from clawk_cli.config_permissions import cmd_config_permissions

    cmd_config_permissions(args)


def build_config_parser(subparsers, *, cmd_config: Callable) -> None:
    """Attach the ``config`` subcommand to ``subparsers``."""
    config_parser = subparsers.add_parser(
        "config",
        help="View and edit configuration",
        description="Manage Clawksis configuration",
    )
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    config_subparsers.add_parser("show", help="Show current configuration")
    config_subparsers.add_parser("edit", help="Open config file in editor")

    config_get = config_subparsers.add_parser(
        "get", help="Print a resolved configuration value"
    )
    config_get.add_argument("key", nargs="?", help="Configuration key (e.g., model)")
    add_json_flag(config_get, "Print value as JSON")
    config_get.add_argument(
        "--raw",
        action="store_true",
        help="Print credential values unmasked (default masks api_key/token/secret-shaped values)",
    )

    config_set = config_subparsers.add_parser("set", help="Set a configuration value")
    config_set.add_argument(
        "key", nargs="?", help="Configuration key (e.g., model, terminal.backend)"
    )
    config_set.add_argument("value", nargs="?", help="Value to set")
    config_set.add_argument(
        "--force",
        action="store_true",
        help="Write a key the running version doesn't recognize: an unknown path under a known "
        "section is otherwise refused, and an unknown top-level key is written with a notice.",
    )

    config_unset = config_subparsers.add_parser(
        "unset", help="Remove a configuration value"
    )
    config_unset.add_argument("key", nargs="?", help="Configuration key to remove")

    config_permissions = config_subparsers.add_parser(
        "permissions",
        help="How much the agent may do: full access, default, or show the current state",
        description=(
            "full: the agent runs commands without approval prompts (cron and unattended "
            "runs too), may edit its instruction files and schedule jobs from cron, and "
            "changes its own settings with `clawk config set`. default: the shipped, safe "
            "values. No argument: show each setting. The hardline floor (wiping / or /home, "
            "formatting disks, shutting the host down) always stays."
        ),
    )
    config_permissions.add_argument("level", nargs="?", choices=["full", "default"])
    config_permissions.add_argument(
        "--yes",
        action="store_true",
        help="Confirm `full` without the interactive prompt",
    )
    config_permissions.set_defaults(func=_cmd_config_permissions)

    config_subparsers.add_parser("path", help="Print config file path")
    config_subparsers.add_parser("env-path", help="Print .env file path")
    config_subparsers.add_parser("check", help="Check for missing/outdated config")
    config_subparsers.add_parser("migrate", help="Update config with new options")

    config_parser.set_defaults(func=cmd_config)
