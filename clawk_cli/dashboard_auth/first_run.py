"""First-run setup del login del dashboard — crear usuario y contraseña.

Cuando el gate de auth está activo pero nadie configuró credenciales todavía
(``dashboard.basic_auth`` vacío y sin ``CLAWK_DASHBOARD_BASIC_AUTH_*`` en el
entorno), ``GET /login`` muestra un formulario de primera vez: el operador
elige usuario y contraseña, se guardan solos en ``~/.clawksis/config.yaml``
(hash scrypt + secret aleatorio — nunca texto plano at rest), el provider
``basic`` se registra en vivo (sin reiniciar) y la sesión queda iniciada.

Para cambiar u olvidar la contraseña después::

    clawk dashboard password            # setear / cambiar (interactivo)
    clawk dashboard password --clear    # quitar el login configurado

Este módulo es importable sin FastAPI: el comando CLI lo usa directo y las
rutas lo importan lazy. La comparación/almacenamiento del password vive en
``plugins.dashboard_auth.basic`` (mismo scrypt del provider).
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
from typing import Tuple

logger = logging.getLogger(__name__)

MIN_USERNAME_LEN = 3

MIN_PASSWORD_LEN = 8


def _basic_section() -> dict:
    """``dashboard.basic_auth`` de config.yaml, o ``{}`` ante cualquier fallo."""

    try:
        from clawk_cli.config import cfg_get, load_config

        cfg = load_config()

    except Exception:  # noqa: BLE001 — sin config legible = sin credenciales
        return {}

    section = cfg_get(cfg, "dashboard", "basic_auth", default=None)

    return section if isinstance(section, dict) else {}


def env_credentials_present() -> bool:
    """True si hay username/password de basic auth vía variables de entorno."""

    return bool(
        os.environ.get("CLAWK_DASHBOARD_BASIC_AUTH_USERNAME", "").strip()
        or os.environ.get("CLAWK_DASHBOARD_BASIC_AUTH_PASSWORD", "").strip()
        or os.environ.get("CLAWK_DASHBOARD_BASIC_AUTH_PASSWORD_HASH", "").strip()
    )


def configured_username() -> str:
    """Username configurado (env gana sobre config), o cadena vacía."""

    env = os.environ.get("CLAWK_DASHBOARD_BASIC_AUTH_USERNAME", "").strip()

    if env:
        return env

    return str(_basic_section().get("username", "") or "").strip()


def basic_auth_configured() -> bool:
    """True si hay credenciales configuradas por env o config (aunque rotas).

    "Rotas" (p.ej. username sin password) cuenta como configurado: en ese
    caso el operador ya tomó una decisión y el fix es arreglar su config,
    no ofrecerle a cualquiera en la red el formulario de primera vez.
    """

    return env_credentials_present() or bool(
        str(_basic_section().get("username", "") or "").strip()
    )


def setup_available() -> bool:
    """True si corresponde ofrecer el formulario de primera vez.

    Requiere que NO haya ningún provider registrado (ni basic ni OAuth) y
    que no existan credenciales de basic auth en env/config.
    """

    from clawk_cli.dashboard_auth import list_providers

    if list_providers():
        return False

    return not basic_auth_configured()


def _validate(username: str, password: str) -> Tuple[str, str]:

    username = (username or "").strip()

    if len(username) < MIN_USERNAME_LEN:
        raise ValueError(f"Username must be at least {MIN_USERNAME_LEN} characters")

    password = password or ""

    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} characters")

    return username, password


def save_basic_auth_credentials(username: str, password: str) -> Tuple[str, bytes]:
    """Hashea y persiste las credenciales en config.yaml.

    Escribe ``dashboard.basic_auth.{username,password_hash}``, elimina
    cualquier ``password`` en texto plano que hubiera, y genera un
    ``secret`` (32 bytes, base64) si no había uno — así las sesiones
    sobreviven reinicios desde el primer login.

    Returns:
        ``(password_hash, secret_bytes)`` — lo justo para construir un
        ``BasicAuthProvider`` en vivo sin re-leer la config.
    """

    username, password = _validate(username, password)

    from plugins.dashboard_auth.basic import hash_password

    from clawk_cli.config import load_config, save_config

    password_hash = hash_password(password)

    cfg = load_config()

    dashboard = cfg.get("dashboard")

    if not isinstance(dashboard, dict):
        dashboard = {}

        cfg["dashboard"] = dashboard

    section = dashboard.get("basic_auth")

    if not isinstance(section, dict):
        section = {}

        dashboard["basic_auth"] = section

    section["username"] = username

    section["password_hash"] = password_hash

    # Nunca texto plano at rest: si había un password legacy, lo purgamos.

    section.pop("password", None)

    secret_raw = str(section.get("secret", "") or "").strip()

    if secret_raw:
        secret = _decode_secret(secret_raw)

    else:
        secret = secrets.token_bytes(32)

        section["secret"] = base64.b64encode(secret).decode()

    save_config(cfg)

    logger.info(
        "dashboard-auth: saved basic_auth credentials for %r (scrypt hash)",
        username,
    )

    return password_hash, secret


def _decode_secret(raw: str) -> bytes:
    """Mismo decode tolerante del provider: base64, hex o UTF-8 crudo."""

    for decoder in (base64.b64decode, bytes.fromhex):
        try:
            decoded = decoder(raw)

            if len(decoded) >= 16:
                return decoded

        except (ValueError, TypeError):
            pass

    return raw.encode("utf-8")


def clear_basic_auth_credentials() -> bool:
    """Quita ``dashboard.basic_auth`` de config.yaml. True si había algo."""

    from clawk_cli.config import load_config, save_config

    cfg = load_config()

    dashboard = cfg.get("dashboard")

    if not isinstance(dashboard, dict) or "basic_auth" not in dashboard:
        return False

    dashboard.pop("basic_auth", None)

    save_config(cfg)

    return True


def complete_first_run_setup(username: str, password: str):
    """Persiste credenciales, registra el provider en vivo y abre sesión.

    Returns:
        ``(provider, session)`` — el ``BasicAuthProvider`` recién
        registrado y una ``Session`` ya iniciada para el usuario creado
        (el navegador queda logueado sin un segundo formulario).

    Raises:
        ValueError: username/password inválidos (mensaje apto para UI).
    """

    username, password = _validate(username, password)

    password_hash, secret = save_basic_auth_credentials(username, password)

    from plugins.dashboard_auth.basic import BasicAuthProvider

    from clawk_cli.dashboard_auth import get_provider, register_provider

    provider = BasicAuthProvider(
        username=username,
        password_hash=password_hash,
        secret=secret,
    )

    try:
        register_provider(provider)

    except ValueError:
        # Carrera perdida: otro request completó el setup primero. Usamos
        # el provider ya registrado — nuestras credenciales quedaron en
        # config pero la sesión la valida el ganador.

        existing = get_provider(provider.name)

        if existing is None:
            raise

        provider = existing

    session = provider.complete_password_login(username=username, password=password)

    return provider, session
