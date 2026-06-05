"""Shared ANSI color utilities for Clawksis CLI modules."""

import os
import sys


def should_use_color() -> bool:
    """Return True when colored output is appropriate.

    Respects the NO_COLOR environment variable (https://no-color.org/)
    and TERM=dumb, in addition to the existing TTY check.
    """
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if not sys.stdout.isatty():
        return False
    return True


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"

    # --- Paleta de marca Clawksis (morado) ---
    # Truecolor. Base ~ #6C4FD0 (morado real / royal purple).
    MORADO = "\033[38;2;108;79;208m"  # acento principal de marca
    MORADO_BRIGHT = "\033[38;2;141;112;240m"  # morado claro / vivo
    MORADO_DARK = "\033[38;2;74;52;150m"  # morado profundo

    # Alias de marca (compat con el nombre anterior):
    VINOTINTO = MORADO
    VINOTINTO_BRIGHT = MORADO_BRIGHT
    VINOTINTO_DARK = MORADO_DARK

    # Los acentos "frios" del fork original se remapean a la marca:
    # cian/azul/magenta -> morado. Verde/amarillo/rojo siguen siendo
    # semanticos (exito / aviso / error).
    BLUE = MORADO
    CYAN = MORADO
    MAGENTA = MORADO_BRIGHT


def color(text: str, *codes) -> str:
    """Apply color codes to text (only when color output is appropriate)."""
    if not should_use_color():
        return text
    return "".join(codes) + text + Colors.RESET
