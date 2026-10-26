"""``clawk dashboard`` subcommands for running the web UI on a server and reaching it remotely.

``password`` (the built-in login), ``service`` (systemd unit), ``domain`` (public HTTPS behind
Caddy) and ``mobile`` (open it on a phone: Tailscale or a domain, a QR code, the login check).
Handlers are injected so this module never imports ``clawk_cli.main``.
"""

from __future__ import annotations

from typing import Callable


def _add_password(subparsers, handler: Callable) -> None:
    """``clawk dashboard password``."""
    # `clawk dashboard password` — set/change/remove the built-in login
    # (dashboard.basic_auth). Same credentials the first-run setup page
    # creates; forgot the password → run this again to overwrite it.
    password_parser = subparsers.add_parser(
        "password",
        help="Set or change the dashboard login (username + password)",
        description=(
            "Set, change, or remove the dashboard's built-in login "
            "(dashboard.basic_auth in ~/.clawksis/config.yaml). The password "
            "is stored as a scrypt hash — never plaintext. Forgot it? Run "
            "this command again to overwrite it."
        ),
    )
    password_parser.add_argument(
        "--username",
        default=None,
        help="Login username (prompted interactively if omitted)",
    )
    password_parser.add_argument(
        "--password",
        default=None,
        help=(
            "New password (prompted interactively — recommended — if omitted, "
            "so it doesn't land in your shell history)"
        ),
    )
    password_parser.add_argument(
        "--clear",
        action="store_true",
        help="Remove the configured login (the first-run setup page returns)",
    )
    password_parser.set_defaults(func=handler)


def _add_service(subparsers, handler: Callable) -> None:
    """``clawk dashboard service``."""
    # `clawk dashboard service` — instala/actualiza la unit systemd en un
    # comando (unit + daemon-reload + enable + start + verificación HTTP).
    service_parser = subparsers.add_parser(
        "service",
        help="Install the dashboard as a systemd service (starts on boot, one command)",
        description=(
            "Write/refresh /etc/systemd/system/clawk-dashboard.service pointing "
            "at this install, reload systemd, enable + start it, and verify it "
            "answers HTTP. Linux + root. --uninstall removes it; --status shows it."
        ),
    )
    service_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "Bind host for the service (default 127.0.0.1 — local/SSH-tunnel "
            "only; 0.0.0.0 exposes it with the login gate active)"
        ),
    )
    service_parser.add_argument(
        "--port", type=int, default=9119, help="Port (default 9119)"
    )
    service_parser.add_argument(
        "--plain",
        action="store_true",
        help=(
            "Write a clean unit, discarding any domain-mode env preserved from "
            "a previous `clawk dashboard domain` (use to leave domain mode)"
        ),
    )
    service_parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Disable and remove the systemd service",
    )
    service_parser.add_argument(
        "--status",
        action="store_true",
        help="Show the systemd service status and exit",
    )
    service_parser.set_defaults(func=handler)


def _add_domain(subparsers, handler: Callable) -> None:
    """``clawk dashboard domain <domain>``."""
    # `clawk dashboard domain <dominio>` — publica el dashboard en
    # https://<dominio>: unit en modo reverse-proxy (loopback + login gate
    # forzado) + Caddy con HTTPS automático. Solo falta el registro DNS.
    domain_parser = subparsers.add_parser(
        "domain",
        help="Publish the dashboard at https://<domain> (reverse proxy + HTTPS, one command)",
        description=(
            "One-command public deploy: installs the systemd service bound to "
            "loopback with the login gate FORCED on, installs Caddy if missing, "
            "writes the reverse-proxy block and reloads it. HTTPS is automatic "
            "(Let's Encrypt) once the domain's DNS A record points at this "
            "server — the command prints the exact record to create."
        ),
    )
    domain_parser.add_argument(
        "domain",
        help="Domain to serve the dashboard at, e.g. panel.tudominio.com",
    )
    domain_parser.add_argument(
        "--port",
        type=int,
        default=9119,
        help="Dashboard port to proxy to (default 9119)",
    )
    domain_parser.set_defaults(func=handler)


def _add_mobile(subparsers, handler: Callable) -> None:
    """``clawk dashboard mobile`` — the phone-friendly front door to ``domain`` / Tailscale."""
    mobile_parser = subparsers.add_parser(
        "mobile",
        help="Open the dashboard on your phone: secure URL + QR code (Tailscale or your domain)",
        description=(
            "Prints the address to open the dashboard from your phone, with a QR code, and "
            "makes sure the login is required. Uses your published domain if you ran "
            "`clawk dashboard domain`; --tailscale publishes it privately to your tailnet "
            "(HTTPS, no open ports); --domain publishes it at https://<domain>. Tip: on the "
            "phone, 'Add to Home Screen' opens it full screen like an app."
        ),
    )
    route = mobile_parser.add_mutually_exclusive_group()
    route.add_argument(
        "--tailscale",
        action="store_true",
        help="Serve it privately on your tailnet with `tailscale serve` (recommended)",
    )
    route.add_argument(
        "--domain",
        default=None,
        help="Publish it at https://<domain> (same as `clawk dashboard domain`)",
    )
    mobile_parser.add_argument(
        "--port", type=int, default=9119, help="Dashboard port (default 9119)"
    )
    mobile_parser.set_defaults(func=handler)


def build_dashboard_extras(
    dashboard_subparsers,
    *,
    cmd_dashboard_password: Callable,
    cmd_dashboard_service: Callable,
    cmd_dashboard_domain: Callable,
    cmd_dashboard_mobile: Callable,
) -> None:
    """Attach ``password`` / ``service`` / ``domain`` / ``mobile`` under ``clawk dashboard``."""
    _add_password(dashboard_subparsers, cmd_dashboard_password)
    _add_service(dashboard_subparsers, cmd_dashboard_service)
    _add_domain(dashboard_subparsers, cmd_dashboard_domain)
    _add_mobile(dashboard_subparsers, cmd_dashboard_mobile)
