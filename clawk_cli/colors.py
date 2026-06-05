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
    # --- Paleta de marca Clawksis (vinotinto) ---
    # Mismos codigos 256-color que el banner ASCII y clawksis-cli.mjs.
    VINOTINTO = "\033[38;5;124m"  # burdeos principal (acento de marca)
    VINOTINTO_BRIGHT = "\033[38;5;160m"  # rojo vino vivo
    VINOTINTO_DARK = "\033[38;5;88m"  # vino oscuro

    # Los acentos "frios" del fork original se remapean a la marca:
    # cian/azul -> vinotinto y magenta -> rojo vino. Verde/amarillo/rojo
    # siguen siendo semanticos (exito / aviso / error).
    BLUE = VINOTINTO
    MAGENTA = VINOTINTO_BRIGHT
    CYAN = VINOTINTO


def color(text: str, *codes) -> str:
    """Apply color codes to text (only when color output is appropriate)."""
    if not should_use_color():
        return text
    return "".join(codes) + text + Colors.RESET
