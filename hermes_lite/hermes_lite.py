#!/usr/bin/env python3
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


VERSION = "0.2.2"

AUDIT_LOG = Path("/var/log/hermes/hermes_lite_audit.log")

SAFE_COMMANDS = {
    "whoami": ["whoami"],
    "pwd": ["pwd"],
    "uptime": ["uptime"],
    "date": ["date"],
    "disk": ["df", "-h", "/"],
    "memory": ["free", "-h"],
    "list_hermes_data": ["ls", "-la", os.getenv("HERMES_LITE_DATA_DIR", str(Path(__file__).resolve().parent / "data"))],
}

DANGEROUS_PATTERNS = [
    r"\bborra\b",
    r"\bborrar\b",
    r"\belimina\b",
    r"\beliminar\b",
    r"\bdestruye\b",
    r"\bdestruir\b",
    r"\bformatea\b",
    r"\bformatear\b",
    r"\bdelete\b",
    r"\bremove\b",
    r"\bwipe\b",
    r"\bdestroy\b",
    r"\bsudo\b",
    r"\bsu\b",
    r"\brm\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\bpasswd\b",
    r"\buseradd\b",
    r"\busermod\b",
    r"\bapt\b",
    r"\bapt-get\b",
    r"\bsystemctl\b",
    r"\breboot\b",
    r"\bshutdown\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bscp\b",
    r"\brsync\b",
    r"\bssh\b",
    r"/root",
    r"/etc",
    r"/home/andres",
    r"/opt/clawksis-agent",
    r"/home/clawksis",
    r"id_rsa",
    r"authorized_keys",
    r"\.env",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_dangerous(text: str) -> bool:
    t = text.lower()
    return any(re.search(pattern, t) for pattern in DANGEROUS_PATTERNS)


def detect_intent(text: str) -> str | None:
    t = text.lower().strip()

    if re.search(r"\b(qu[ié]n soy|usuario|whoami)\b", t):
        return "whoami"

    if re.search(r"\b(d[oó]nde estoy|ubicaci[oó]n actual|directorio actual|pwd)\b", t):
        return "pwd"

    if re.search(r"\b(uptime|tiempo encendido|cu[aá]nto lleva encendido)\b", t):
        return "uptime"

    if re.search(r"\b(fecha|hora|date)\b", t):
        return "date"

    if re.search(r"\b(disco|espacio|almacenamiento|df)\b", t):
        return "disk"

    if re.search(r"\b(memoria|ram|free)\b", t):
        return "memory"

    if re.search(r"\b(lista|listar|archivos|mu[eé]strame).*(hermes|datos|data)\b", t):
        return "list_hermes_data"

    return None


def audit(record: dict) -> None:
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Nunca romper la ejecución principal por un fallo de logging.
        pass


def run_safe_command(intent: str) -> tuple[int, str, str, float]:
    cmd = SAFE_COMMANDS[intent]
    start = time.time()

    result = subprocess.run(
        cmd,
        shell=False,
        capture_output=True,
        text=True,
        timeout=10,
        cwd=os.getenv("HERMES_LITE_WORKDIR", str(Path(__file__).resolve().parent)),
    )

    duration = round(time.time() - start, 3)
    return result.returncode, result.stdout.strip(), result.stderr.strip(), duration


def build_response(
    *,
    status: str,
    user_text: str,
    intent: str | None = None,
    command: list[str] | None = None,
    exit_code: int | None = None,
    stdout: str = "",
    stderr: str = "",
    duration: float | None = None,
    message: str = "",
) -> dict:
    return {
        "version": VERSION,
        "timestamp": now_iso(),
        "status": status,
        "intent": intent,
        "command": shlex.join(command) if command else None,
        "exit_code": exit_code,
        "duration_seconds": duration,
        "message": message,
        "stdout": stdout,
        "stderr": stderr,
        "user_text_preview": user_text[:200],
        "effective_user": os.getenv("USER") or "",
    }


def print_human(response: dict) -> None:
    print(f"STATUS={response['status']}")

    if response.get("intent"):
        print(f"INTENCION={response['intent']}")

    if response.get("command"):
        print(f"COMANDO_SEGURO={response['command']}")

    if response.get("exit_code") is not None:
        print(f"EXIT_CODE={response['exit_code']}")

    if response.get("duration_seconds") is not None:
        print(f"DURACION_SEGUNDOS={response['duration_seconds']}")

    if response.get("message"):
        print(f"MENSAJE={response['message']}")

    if response.get("stdout"):
        print("SALIDA:")
        print(response["stdout"])

    if response.get("stderr"):
        print("ERROR_STDERR:")
        print(response["stderr"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes Lite - ejecutor seguro por allowlist")
    parser.add_argument("text", nargs="+", help="Orden en lenguaje natural")
    parser.add_argument("--dry-run", action="store_true", help="Detecta intención y comando, pero no ejecuta")
    parser.add_argument("--json", action="store_true", help="Imprime salida en JSON")
    args = parser.parse_args()

    user_text = " ".join(args.text)

    if is_dangerous(user_text):
        response = build_response(
            status="blocked",
            user_text=user_text,
            message="Orden bloqueada por contener términos o rutas peligrosas.",
        )
        audit(response)
        if args.json:
            print(json.dumps(response, ensure_ascii=False, indent=2))
        else:
            print_human(response)
        return 1

    intent = detect_intent(user_text)

    if not intent:
        response = build_response(
            status="not_understood",
            user_text=user_text,
            message="Orden no permitida o no reconocida. Permitidas: usuario, ubicación, uptime, fecha, disco, memoria, listar datos Hermes.",
        )
        audit(response)
        if args.json:
            print(json.dumps(response, ensure_ascii=False, indent=2))
        else:
            print_human(response)
        return 1

    cmd = SAFE_COMMANDS[intent]

    if args.dry_run:
        response = build_response(
            status="dry_run",
            user_text=user_text,
            intent=intent,
            command=cmd,
            message="Comando detectado pero no ejecutado.",
        )
        audit(response)
        if args.json:
            print(json.dumps(response, ensure_ascii=False, indent=2))
        else:
            print_human(response)
        return 0

    try:
        code, out, err, duration = run_safe_command(intent)
        response = build_response(
            status="executed",
            user_text=user_text,
            intent=intent,
            command=cmd,
            exit_code=code,
            stdout=out,
            stderr=err,
            duration=duration,
        )
        audit(response)

        if args.json:
            print(json.dumps(response, ensure_ascii=False, indent=2))
        else:
            print_human(response)

        return code

    except subprocess.TimeoutExpired:
        response = build_response(
            status="timeout",
            user_text=user_text,
            intent=intent,
            command=cmd,
            exit_code=124,
            message="Comando excedió el tiempo máximo permitido.",
        )
        audit(response)
        if args.json:
            print(json.dumps(response, ensure_ascii=False, indent=2))
        else:
            print_human(response)
        return 124

    except Exception as e:
        response = build_response(
            status="error",
            user_text=user_text,
            intent=intent,
            command=cmd,
            exit_code=1,
            message=f"{type(e).__name__}: {e}",
        )
        audit(response)
        if args.json:
            print(json.dumps(response, ensure_ascii=False, indent=2))
        else:
            print_human(response)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
