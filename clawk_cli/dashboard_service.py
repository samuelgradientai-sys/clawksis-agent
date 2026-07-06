"""``clawk dashboard service`` / ``clawk dashboard domain`` — deploy en un comando.

Antes, dejar el dashboard fijo en un servidor era una página de README:
escribir la unit systemd a mano, chmod, daemon-reload, enable, y para un
dominio además instalar y configurar un reverse proxy con TLS. Estos dos
subcomandos lo hacen solos:

``clawk dashboard service``
    Instala (o actualiza) ``/etc/systemd/system/clawk-dashboard.service``
    apuntando a ESTE python/instalación, recarga systemd, lo deja corriendo
    y arrancando al boot, y verifica que responda HTTP.

``clawk dashboard domain <dominio>``
    Publica el dashboard en ``https://<dominio>``: reescribe la unit en modo
    reverse-proxy (bind loopback + login gate forzado + Host del dominio
    permitido — ver CLAWK_DASHBOARD_FORCE_GATE / CLAWK_DASHBOARD_PUBLIC_HOST
    en web_server.py), instala Caddy si falta, escribe un bloque marcado en
    /etc/caddy/Caddyfile con el reverse_proxy y recarga Caddy. El HTTPS es
    automático (Let's Encrypt) en cuanto el DNS del dominio apunta al server.

Solo Linux + systemd. El dashboard queda escuchando únicamente en loopback
en modo dominio: lo único expuesto es Caddy (80/443).
"""

import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_P = "\033[38;2;108;79;214m"
_B = "\033[1m"
_D = "\033[2m"
_X = "\033[0m"
_R = "\033[0;31m"
_G = "\033[0;32m"

UNIT_PATH = Path("/etc/systemd/system/clawk-dashboard.service")

CADDYFILE = Path("/etc/caddy/Caddyfile")

_MARK_BEGIN = "# >>> clawksis-dashboard (autogenerado por `clawk dashboard domain`) >>>"

_MARK_END = "# <<< clawksis-dashboard <<<"

_DOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _fail(msg: str) -> "None":
    print(f"{_R}✗ {msg}{_X}")
    sys.exit(1)


def _require_linux_systemd_root(cmd_label: str) -> None:
    if sys.platform != "linux":
        _fail(
            f"`clawk dashboard {cmd_label}` requiere Linux con systemd "
            "(en tu PC usá `clawk dashboard` directo, o `clawk dashboard --remote user@host`)."
        )
    if shutil.which("systemctl") is None:
        _fail("systemctl no está disponible — este sistema no usa systemd.")
    if os.geteuid() != 0:
        clawk_bin = shutil.which("clawk") or "clawk"
        _fail(
            f"Hace falta root para escribir la unit/config. Reintentá con:\n"
            f"    sudo {clawk_bin} dashboard {cmd_label}"
        )


def _run(cmd: list, check: bool = True) -> "subprocess.CompletedProcess":
    print(f"{_D}  $ {' '.join(cmd)}{_X}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if check and res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip()
        _fail(f"`{' '.join(cmd)}` falló ({res.returncode}): {err}")
    return res


def _build_unit(host: str, port: int, extra_env: "dict[str, str]") -> str:
    python = sys.executable
    root = _project_root()
    home = str(Path.home())
    env_lines = "".join(
        f"Environment={k}={v}\n" for k, v in ({"HOME": home} | extra_env).items()
    )
    return (
        "[Unit]\n"
        "Description=Clawksis Dashboard (web UI :%d)\n"
        % port
        + "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        "User=root\n"
        f"{env_lines}"
        f"WorkingDirectory={root}\n"
        f"ExecStart={python} -m clawk_cli.main dashboard --no-open "
        f"--host {host} --port {port} --skip-build\n"
        "Restart=always\n"
        "RestartSec=3\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


_DOMAIN_ENV_KEYS = ("CLAWK_DASHBOARD_FORCE_GATE", "CLAWK_DASHBOARD_PUBLIC_HOST")


def _existing_domain_env() -> "dict[str, str]":
    """Env de modo dominio ya presente en la unit instalada (si la hay).

    Sin esto, ``clawk dashboard service`` reescribiría la unit desde cero y
    borraría CLAWK_DASHBOARD_FORCE_GATE/PUBLIC_HOST — dejando el dominio
    publicado respondiendo 400 (Host rechazado) en silencio, porque el bloque
    de Caddy sigue proxyando.
    """
    if not UNIT_PATH.exists():
        return {}
    try:
        text = UNIT_PATH.read_text(encoding="utf-8")
    except OSError:
        return {}
    found: dict[str, str] = {}
    for m in re.finditer(r"^Environment=([A-Z0-9_]+)=(.*)$", text, re.M):
        key, val = m.group(1), m.group(2).strip()
        if key in _DOMAIN_ENV_KEYS:
            found[key] = val
    return found


def _install_unit(host: str, port: int, extra_env: "dict[str, str]") -> None:
    content = _build_unit(host, port, extra_env)
    if UNIT_PATH.exists() and UNIT_PATH.read_text(encoding="utf-8") == content:
        print(f"{_D}  unit sin cambios: {UNIT_PATH}{_X}")
    else:
        UNIT_PATH.write_text(content, encoding="utf-8")
        print(f"  unit escrita: {_B}{UNIT_PATH}{_X}")
    # La unit puede llevar credenciales por env en setups viejos — 600 siempre.
    os.chmod(UNIT_PATH, 0o600)
    _run(["systemctl", "daemon-reload"])
    _run(["systemctl", "enable", "--now", "clawk-dashboard"])
    # enable --now no reinicia si ya corría con la unit vieja.
    _run(["systemctl", "restart", "clawk-dashboard"])


def _probe_http(
    port: int, host_header: "str | None" = None, timeout_s: int = 90
) -> bool:
    url = f"http://127.0.0.1:{port}/"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        req = urllib.request.Request(url)
        if host_header:
            req.add_header("Host", host_header)
        try:
            urllib.request.urlopen(req, timeout=2).close()
            return True
        except urllib.error.HTTPError as e:
            # 302/401 del login gate = el server está vivo; 400 = Host rechazado.
            if e.code != 400:
                return True
            return False
        except Exception:
            time.sleep(0.5)
    return False


def print_dashboard_command_list() -> None:
    """Chuleta de todos los comandos del dashboard (se imprime en los banners)."""
    rows = [
        ("clawk dashboard", "inicia la web UI (en un servidor queda en 2º plano)"),
        ("clawk dashboard --stop", "la detiene · --status lista los procesos"),
        ("clawk dashboard password", "crea/cambia el login (--clear lo borra)"),
        (
            "clawk dashboard service",
            "la instala como servicio systemd (arranca sola al boot)",
        ),
        (
            "clawk dashboard domain <dominio>",
            "la publica en https://<dominio> (proxy + HTTPS solos)",
        ),
        ("clawk dashboard --remote user@host", "túnel SSH + navegador, desde tu PC"),
        ("clawk update", "actualiza Clawksis y reconstruye la web UI"),
    ]
    print(f"\n{_P}{_B}▸ Comandos del dashboard{_X}")
    width = max(len(r[0]) for r in rows)
    for cmd, desc in rows:
        print(f"  {_B}{cmd.ljust(width)}{_X}  {_D}{desc}{_X}")


def cmd_dashboard_service(args) -> None:
    """Instala/actualiza el dashboard como servicio systemd, en un comando."""

    if getattr(args, "status", False):
        if sys.platform != "linux" or shutil.which("systemctl") is None:
            _fail("Este comando requiere Linux con systemd.")
        subprocess.run(["systemctl", "status", "clawk-dashboard", "--no-pager"])
        return

    if getattr(args, "uninstall", False):
        _require_linux_systemd_root("service --uninstall")
        _run(["systemctl", "disable", "--now", "clawk-dashboard"], check=False)
        if UNIT_PATH.exists():
            UNIT_PATH.unlink()
            print(f"  unit borrada: {UNIT_PATH}")
        _run(["systemctl", "daemon-reload"])
        print(f"{_G}✓ Servicio desinstalado.{_X}")
        return

    _require_linux_systemd_root("service")

    host = getattr(args, "host", None) or "127.0.0.1"
    port = int(getattr(args, "port", None) or 9119)

    # Preservar el modo dominio si ya está configurado: `service` reinstala la
    # unit, pero no debe desconfigurar un `domain` previo (Caddy sigue vivo).
    # `--plain` fuerza una unit limpia (para salir del modo dominio a propósito).
    domain_env = {} if getattr(args, "plain", False) else _existing_domain_env()
    domain_host = domain_env.get("CLAWK_DASHBOARD_PUBLIC_HOST", "")

    print(f"{_P}{_B}▸ Instalando el dashboard como servicio (systemd){_X}")
    if domain_host:
        print(
            f"{_D}  Modo dominio detectado ({domain_host}) — preservado. "
            f"Usá --plain para quitarlo.{_X}"
        )
    _install_unit(host, port, domain_env)

    # En modo dominio el bind es loopback pero el Host válido es el dominio: la
    # sonda debe mandar ese Host, si no un 400 legítimo se leería como caída.
    probe_host = domain_host.split(",")[0].strip() if domain_host else None
    if not _probe_http(port, host_header=probe_host):
        _fail(
            "El servicio quedó instalado pero no responde HTTP.\n"
            "  Mirá el log:  journalctl -u clawk-dashboard -n 50 --no-pager"
        )

    print(
        f"\n{_G}{_B}✓ Dashboard corriendo como servicio{_X} — arranca solo al bootear."
    )
    if host in {"127.0.0.1", "localhost", "::1"}:
        print(
            f"  Local/túnel: {_B}http://127.0.0.1:{port}{_X}"
            f"  {_D}(desde tu PC: clawk dashboard --remote user@este-server){_X}"
        )
        print(
            f"  ¿Querés un dominio con HTTPS? "
            f"{_B}clawk dashboard domain panel.tudominio.com{_X}"
        )
    else:
        print(
            f"  Expuesto en {_B}http://{host}:{port}{_X} con login activo — "
            f"la primera visita a /login crea usuario y contraseña."
        )
    print(f"  Logs: {_D}journalctl -u clawk-dashboard -f{_X}")
    print_dashboard_command_list()


def _apt_add_caddy_repo() -> bool:
    """Agrega el repo oficial de Caddy (cloudsmith). Ubuntu 22.04 / Debian ≤11

    no traen ``caddy`` en sus repos base; 24.04 y Debian 12+ sí. Devuelve True
    si el repo quedó configurado."""
    key = "/usr/share/keyrings/caddy-stable-archive-keyring.gpg"
    listf = "/etc/apt/sources.list.d/caddy-stable.list"
    steps = [
        [
            "apt-get",
            "install",
            "-y",
            "-qq",
            "debian-keyring",
            "debian-archive-keyring",
            "apt-transport-https",
            "curl",
        ],
        [
            "bash",
            "-c",
            "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' "
            f"| gpg --dearmor -o {key}",
        ],
        [
            "bash",
            "-c",
            "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' "
            f"> {listf}",
        ],
        ["apt-get", "update", "-qq"],
    ]
    for step in steps:
        if _run(step, check=False).returncode != 0:
            return False
    return True


def _ensure_caddy() -> None:
    if shutil.which("caddy"):
        return
    print(f"{_P}▸ Caddy no está instalado — instalándolo…{_X}")
    if shutil.which("apt-get"):
        _run(["apt-get", "update", "-qq"], check=False)
        if (
            _run(["apt-get", "install", "-y", "-qq", "caddy"], check=False).returncode
            != 0
        ):
            # No está en los repos base (Ubuntu 22.04 / Debian ≤11): sumar el
            # repo oficial de Caddy y reintentar.
            print(
                f"{_D}  caddy no está en los repos base — agregando el repo oficial…{_X}"
            )
            if _apt_add_caddy_repo():
                _run(["apt-get", "install", "-y", "-qq", "caddy"])
    elif shutil.which("dnf"):
        _run(["dnf", "install", "-y", "caddy"])
    else:
        _fail(
            "No pude instalar Caddy automáticamente (sin apt/dnf).\n"
            "  Instalalo según https://caddyserver.com/docs/install y reintentá."
        )
    if not shutil.which("caddy"):
        _fail(
            "Caddy no quedó disponible tras la instalación.\n"
            "  Instalalo a mano (https://caddyserver.com/docs/install) y reintentá."
        )


def _write_caddy_block(domain: str, port: int) -> None:
    block = (
        f"{_MARK_BEGIN}\n"
        f"{domain} {{\n"
        f"\treverse_proxy 127.0.0.1:{port}\n"
        f"}}\n"
        f"{_MARK_END}\n"
    )
    CADDYFILE.parent.mkdir(parents=True, exist_ok=True)
    existing = CADDYFILE.read_text(encoding="utf-8") if CADDYFILE.exists() else ""
    if _MARK_BEGIN in existing and _MARK_END in existing:
        pattern = re.compile(
            re.escape(_MARK_BEGIN) + r".*?" + re.escape(_MARK_END) + r"\n?",
            re.DOTALL,
        )
        updated = pattern.sub(block, existing, count=1)
    else:
        if existing and not CADDYFILE.with_suffix(".bak-clawksis").exists():
            # Primer toque a un Caddyfile ajeno: backup una sola vez.
            CADDYFILE.with_suffix(".bak-clawksis").write_text(
                existing, encoding="utf-8"
            )
        sep = "\n" if existing.endswith("\n") or not existing else "\n\n"
        updated = existing + sep + block
    if updated != existing:
        CADDYFILE.write_text(updated, encoding="utf-8")
        print(f"  bloque escrito en {_B}{CADDYFILE}{_X}")
    else:
        print(f"{_D}  Caddyfile sin cambios{_X}")
    valid = subprocess.run(
        ["caddy", "validate", "--config", str(CADDYFILE)],
        capture_output=True,
        text=True,
    )
    if valid.returncode != 0:
        # No dejar un Caddyfile inválido en disco: rompería el próximo
        # reload/boot de Caddy. Restaurar el contenido previo antes de abortar.
        if existing:
            CADDYFILE.write_text(existing, encoding="utf-8")
        else:
            CADDYFILE.unlink(missing_ok=True)
        _fail(
            "El Caddyfile resultante no valida (se restauró el anterior):\n"
            + (valid.stderr or valid.stdout or "").strip()
        )
    _run(["systemctl", "enable", "--now", "caddy"], check=False)
    reload_res = subprocess.run(
        ["systemctl", "reload", "caddy"], capture_output=True, text=True
    )
    if reload_res.returncode != 0:
        _run(["systemctl", "restart", "caddy"])


def _public_ip() -> "str | None":
    for svc in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(svc, timeout=5) as res:
                ip = res.read().decode().strip()
            if ip and len(ip) <= 45:
                return ip
        except Exception:
            continue
    return None


def cmd_dashboard_domain(args) -> None:
    """Publica el dashboard en https://<dominio> (systemd + Caddy), en un comando."""

    domain = (getattr(args, "domain", "") or "").strip().lower().rstrip(".")
    if domain.startswith(("http://", "https://")):
        domain = domain.split("://", 1)[1].split("/", 1)[0]
    if not _DOMAIN_RE.match(domain):
        _fail(f"'{domain}' no parece un dominio válido (ej: panel.tudominio.com).")

    _require_linux_systemd_root(f"domain {domain}")

    port = int(getattr(args, "port", None) or 9119)

    print(f"{_P}{_B}▸ Publicando el dashboard en https://{domain}{_X}")

    # 1) Servicio en modo reverse-proxy: solo loopback escucha, pero el login
    #    gate queda FORZADO y el Host del dominio permitido (anti-rebinding).
    print(f"{_P}▸ 1/3 Servicio systemd (bind loopback + login gate){_X}")
    _install_unit(
        "127.0.0.1",
        port,
        {
            "CLAWK_DASHBOARD_FORCE_GATE": "1",
            "CLAWK_DASHBOARD_PUBLIC_HOST": domain,
        },
    )
    if not _probe_http(port, host_header=domain):
        _fail(
            "El dashboard no acepta el Host del dominio — ¿la versión instalada "
            "es vieja? Corré `clawk update` y reintentá.\n"
            "  Log: journalctl -u clawk-dashboard -n 50 --no-pager"
        )

    # 2) Caddy: reverse proxy con HTTPS automático.
    print(f"{_P}▸ 2/3 Reverse proxy (Caddy, HTTPS automático){_X}")
    _ensure_caddy()
    _write_caddy_block(domain, port)

    # 3) DNS: lo único que no podemos hacer por vos.
    print(f"{_P}▸ 3/3 DNS{_X}")
    ip = _public_ip()
    print(f"\n{_G}{_B}✓ Todo listo del lado del servidor.{_X} Falta UN paso tuyo:")
    print(
        f"  Creá un registro DNS {_B}A{_X} en tu proveedor:  "
        f"{_B}{domain} → {ip or '<IP pública de este server>'}{_X}"
    )
    print(
        f"  {_D}Si usás Cloudflare: dejá la nube GRIS (DNS only) al menos hasta "
        f"que Caddy emita el certificado; después podés activar el proxy.{_X}"
    )
    print(f"\n  En cuanto el DNS propague: {_B}https://{domain}{_X}")
    print(
        "  La primera visita a /login crea tu usuario y contraseña "
        "(o corré `clawk dashboard password`)."
    )
    print(
        f"  {_D}El dashboard solo escucha en 127.0.0.1:{port} — lo único expuesto "
        f"es Caddy (80/443). Login activo incluso detrás del proxy.{_X}"
    )
    print_dashboard_command_list()
