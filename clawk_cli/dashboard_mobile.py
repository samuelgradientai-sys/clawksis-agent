"""``clawk dashboard mobile``: open the dashboard on a phone, safely, in one command.

The dashboard keeps listening on 127.0.0.1 with the login gate forced on; a phone reaches it
through one of two front doors that preserve that:

- a published domain (``clawk dashboard domain``: Caddy + Let's Encrypt), or
- Tailscale (``tailscale serve``): HTTPS inside the user's private tailnet, no public port.

This command uses the front door already set up (or the one asked for), prints the address with
a QR code to scan, says whether a login exists yet, and how to install it as a home-screen app.
It never installs Tailscale itself: lookup goes through ``clawk_platform`` and only reads.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from urllib.parse import urlparse

from clawk_cli import dashboard_service as ds

_TS_SERVE_HELP = (
    "Activá los certificados HTTPS de tu tailnet (consola de Tailscale → DNS → "
    "HTTPS Certificates) y reintentá."
)


def tailscale_host(status: dict | None) -> str | None:
    """This machine's MagicDNS name from ``tailscale status --json`` when logged in."""
    if not isinstance(status, dict) or status.get("BackendState") != "Running":
        return None
    me = status.get("Self")
    name = me.get("DNSName") if isinstance(me, dict) else None
    host = str(name or "").strip().rstrip(".").lower()
    return host or None


def _tailscale_exe() -> str | None:
    from clawk_platform.resolver import locate_command

    return locate_command("tailscale").command


def _tailscale_status(exe: str) -> dict | None:
    try:
        res = subprocess.run(
            [exe, "status", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        return json.loads(res.stdout) if res.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def published_hosts(unit_env: dict[str, str], public_url: str) -> list[str]:
    """Hosts the dashboard already answers on: ``dashboard.public_url`` + the unit's domain hosts."""
    hosts = [urlparse(public_url).hostname or ""] if public_url else []
    hosts += unit_env.get("CLAWK_DASHBOARD_PUBLIC_HOST", "").split(",")
    return list(dict.fromkeys(h.strip().lower() for h in hosts if h and h.strip()))


def _public_url() -> str:
    from clawk_cli.config import load_config

    dashboard = load_config().get("dashboard")
    return str(dashboard.get("public_url") or "") if isinstance(dashboard, dict) else ""


def _unit_bind_host() -> str:
    """Keep the installed unit's bind (0.0.0.0 when a Docker proxy needed it), else loopback."""
    try:
        match = re.search(r"--host (\S+)", ds.UNIT_PATH.read_text(encoding="utf-8"))
    except OSError:
        return "127.0.0.1"
    return match.group(1) if match else "127.0.0.1"


def _serve_on_tailscale(port: int) -> str:
    """Route ``https://<machine>.<tailnet>.ts.net`` to the dashboard and return that URL."""
    exe = _tailscale_exe()
    host = tailscale_host(_tailscale_status(exe)) if exe else None
    if not host:
        ds._fail(
            "Tailscale no está instalado o no inició sesión en este servidor.\n"
            "  Instalalo: curl -fsSL https://tailscale.com/install.sh | sh && tailscale up\n"
            "  y en el móvil instalá la app Tailscale con la misma cuenta."
        )
    ds._require_linux_systemd_root("mobile --tailscale")
    hosts = published_hosts(ds._existing_domain_env(), "") + [host]
    print(f"{ds._P}{ds._B}▸ Publicando el dashboard en tu tailnet (privado){ds._X}")
    ds._install_unit(
        _unit_bind_host(),
        port,
        {
            "CLAWK_DASHBOARD_FORCE_GATE": "1",
            "CLAWK_DASHBOARD_PUBLIC_HOST": ",".join(dict.fromkeys(hosts)),
        },
    )
    if not ds._probe_http(port, host_header=host):
        ds._fail("El dashboard no acepta el nombre de Tailscale. Corré `clawk update`.")
    res = subprocess.run(
        [exe, "serve", "--bg", "--https=443", f"http://127.0.0.1:{port}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if res.returncode != 0:
        detail = (res.stderr or res.stdout).strip()[-400:]
        ds._fail(f"`tailscale serve` falló: {detail}\n  {_TS_SERVE_HELP}")
    return f"https://{host}"


def _domain_url(domain: str, port: int) -> str:
    domain = domain.strip().lower().rstrip(".")
    if "://" in domain:
        domain = domain.split("://", 1)[1].split("/", 1)[0]
    ds.cmd_dashboard_domain(argparse.Namespace(domain=domain, port=port))
    return f"https://{domain}"


def _print_options() -> None:
    print(
        f"{ds._P}{ds._B}▸ Todavía no hay una forma segura de abrirlo desde el móvil.{ds._X}"
        " Elegí una:\n\n"
        f"  {ds._B}1) Tailscale{ds._X} (recomendado: privado, gratis, sin abrir puertos)\n"
        "     • En este servidor: curl -fsSL https://tailscale.com/install.sh | sh && tailscale up\n"
        "     • En el móvil: app Tailscale, misma cuenta\n"
        f"     • Después: {ds._B}clawk dashboard mobile --tailscale{ds._X}\n\n"
        f"  {ds._B}2) Tu dominio{ds._X} (público, con HTTPS automático y login)\n"
        f"     • {ds._B}clawk dashboard mobile --domain panel.tudominio.com{ds._X}\n"
    )


def print_qr(url: str) -> bool:
    """Draw *url* as a QR code in the terminal; False when the ``qrcode`` package is missing."""
    try:
        import qrcode  # type: ignore[import-untyped]
    except ImportError:
        return False
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    return True


def _login_configured() -> bool:
    from clawk_cli.dashboard_auth.first_run import (
        configured_username,
        env_credentials_present,
    )

    return bool(configured_username() or env_credentials_present())


def _print_phone_steps(url: str) -> None:
    print(f"\n{ds._G}{ds._B}✓ Abrilo en el móvil:{ds._X} {ds._B}{url}{ds._X}\n")
    if not print_qr(url):
        print(f"{ds._D}  (instalá `qrcode` para ver el código QR aquí){ds._X}")
    if not _login_configured():
        print(
            "\n  La primera visita te pide crear usuario y contraseña "
            "(o corré `clawk dashboard password` ahora)."
        )
    print(
        "\n  Como app: en iPhone, Compartir → «Añadir a pantalla de inicio»; en Android,"
        " ⋮ → «Instalar app». Se abre a pantalla completa."
    )


def cmd_dashboard_mobile(args) -> None:
    """Print a phone-ready dashboard address (+ QR), setting up the front door if asked."""
    port = int(getattr(args, "port", None) or 9119)
    if getattr(args, "domain", None):
        url = _domain_url(args.domain, port)
    elif getattr(args, "tailscale", False):
        url = _serve_on_tailscale(port)
    else:
        hosts = published_hosts(ds._existing_domain_env(), _public_url())
        if not hosts:
            _print_options()
            return
        url = f"https://{hosts[0]}"
        for other in hosts[1:]:
            print(f"{ds._D}  también: https://{other}{ds._X}")
    _print_phone_steps(url)
