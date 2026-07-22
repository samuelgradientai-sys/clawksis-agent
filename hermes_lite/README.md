# Hermes Lite

Hermes Lite is a fast, safe, allowlist-based command executor for controlled VPS operations.

## Security model

- Executes only predefined allowlisted commands.
- Does not use shell=True.
- Does not use sudo.
- Blocks sensitive paths such as /root, /etc, /home/andres, /home/clawksis and .env files.
- Supports human output, JSON output and dry-run mode.
- Writes audit logs when deployed on the VPS.

## Examples

```bash
python3 hermes_lite.py "qué usuario soy"
python3 hermes_lite.py --json "cuánta memoria ram tiene el servidor"
python3 hermes_lite.py --dry-run "muéstrame el espacio en disco"
```
