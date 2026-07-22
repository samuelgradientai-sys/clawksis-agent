#!/usr/bin/env python3
"""model-fallback: audit providers / API keys / fallback chain and configure
automatic failover when a model runs out of billing or errors.

Original Clawksis skill (MIT, Gradient AI). Deterministic — pure stdlib + PyYAML,
no LLM needed, so it works even when the agent is out of tokens (and can run from
cron). It reads ~/.clawksis/.env + config.yaml, reports what failover you have,
and can wire `fallback_providers` so the runtime switches provider/model on its
own when the primary returns 402 / quota / billing errors.

  failover.py                 audit (read-only): model, keys, pool, chain, verdict
  failover.py --json          machine-readable
  failover.py --apply-chain   write fallback_providers from detected keys (backup)
  failover.py --apply-chain openai,deepseek   explicit order
  failover.py --switch MODEL  set the primary model now (backup)
  failover.py --home DIR --config FILE         overrides (testing)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Known providers: env-var that holds their API key -> (provider, default model).
# Models are sensible defaults and EDITABLE in config.yaml afterwards.
PROVIDERS: list[tuple[str, str, str]] = [
    ("OPENAI_API_KEY", "openai", "gpt-4o-mini"),
    ("DEEPSEEK_API_KEY", "deepseek", "deepseek-chat"),
    ("ANTHROPIC_API_KEY", "anthropic", "claude-3-5-sonnet-latest"),
    ("OPENROUTER_API_KEY", "openrouter", "openai/gpt-4o-mini"),
    ("XAI_API_KEY", "xai", "grok-2-latest"),
    ("GROQ_API_KEY", "groq", "llama-3.3-70b-versatile"),
    ("MISTRAL_API_KEY", "mistral", "mistral-large-latest"),
    ("GEMINI_API_KEY", "google", "gemini-2.0-flash"),
    ("GOOGLE_API_KEY", "google", "gemini-2.0-flash"),
    ("TOGETHER_API_KEY", "together", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
]


def resolve_home() -> Path:
    env = os.environ.get("CLAWK_HOME")
    if env:
        return Path(env).expanduser()
    # .../skills/model-fallback/scripts/failover.py -> parents[2] = skills, .parent = home
    return Path(__file__).resolve().parents[2].parent


def read_env(home: Path) -> dict:
    out = dict(os.environ)
    f = home / ".env"
    try:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass
    return out


def detect_providers(env: dict) -> list[dict]:
    """Detected providers (deduped, order of PROVIDERS), with the key masked."""
    seen: set = set()
    found = []
    for env_key, provider, default_model in PROVIDERS:
        val = (env.get(env_key) or "").strip()
        if not val or provider in seen:
            continue
        seen.add(provider)
        found.append({
            "provider": provider,
            "model": default_model,
            "env_key": env_key,
            "key_tail": val[-4:] if len(val) >= 4 else "****",
        })
    return found


def load_yaml(path: Path):
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def current_model(cfg: dict) -> str:
    m = cfg.get("model")
    if isinstance(m, dict):
        return str(m.get("default") or m.get("model") or "").strip()
    return str(m or "").strip()


def current_chain(cfg: dict) -> list[dict]:
    chain = cfg.get("fallback_providers") or cfg.get("fallback_model") or []
    if isinstance(chain, dict):
        chain = [chain]
    return [c for c in chain if isinstance(c, dict)]


def pool_status(provider: str):
    """Best-effort credential-pool status; returns None if not resolvable."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3].parent))
        from agent.credential_pool import load_pool  # type: ignore

        pool = load_pool(provider)
        if not pool.has_credentials():
            return None
        return len(pool.entries())
    except Exception:
        return None


def apply_chain(config_path: Path, providers: list[dict]) -> list[dict]:
    import yaml

    cfg = {}
    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8")
        cfg = yaml.safe_load(raw) or {}
        if not isinstance(cfg, dict):
            raise SystemExit("config.yaml is not a YAML mapping; refusing to edit.")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        config_path.with_name(config_path.name + f".bak-{ts}").write_text(
            raw, encoding="utf-8"
        )
    chain = [{"provider": p["provider"], "model": p["model"]} for p in providers]
    cfg["fallback_providers"] = chain
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return chain


def switch_model(config_path: Path, model: str) -> None:
    import yaml

    cfg = {}
    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8")
        cfg = yaml.safe_load(raw) or {}
        if not isinstance(cfg, dict):
            raise SystemExit("config.yaml is not a YAML mapping; refusing to edit.")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        config_path.with_name(config_path.name + f".bak-{ts}").write_text(
            raw, encoding="utf-8"
        )
    m = cfg.get("model")
    if isinstance(m, dict):
        m["default"] = model
    else:
        cfg["model"] = model
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(
        description="Audit + configure model/billing failover."
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--apply-chain",
        nargs="?",
        const="",
        default=None,
        help="write fallback_providers (optionally a CSV order of providers)",
    )
    ap.add_argument("--switch", default="", help="set the primary model now")
    ap.add_argument("--home", default="")
    ap.add_argument("--config", default="")
    args = ap.parse_args()

    home = Path(args.home).expanduser() if args.home else resolve_home()
    config_path = (
        Path(args.config).expanduser() if args.config else home / "config.yaml"
    )
    env = read_env(home)
    detected = detect_providers(env)

    if args.switch:
        try:
            switch_model(config_path, args.switch.strip())
        except SystemExit as exc:
            print(str(exc))
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"switch failed: {exc}")
            return 1
        print(
            f"Modelo principal → {args.switch.strip()}  (backup del config guardado)."
        )
        print("Reiniciá el gateway/agente para que tome efecto.")
        return 0

    if args.apply_chain is not None:
        if args.apply_chain.strip():
            order = [
                p.strip().lower() for p in args.apply_chain.split(",") if p.strip()
            ]
            by_prov = {d["provider"]: d for d in detected}
            chosen = [by_prov[p] for p in order if p in by_prov]
            # include any explicitly named provider even without a detected key,
            # using its default model so the user can add the key later
            for p in order:
                if p not in by_prov:
                    dm = next((m for k, pr, m in PROVIDERS if pr == p), "")
                    if dm:
                        chosen.append({"provider": p, "model": dm})
        else:
            chosen = detected
        if not chosen:
            print(
                "No detecté API keys de ningún provider en ~/.clawksis/.env. "
                "Agregá al menos una (ej. OPENAI_API_KEY=...) y reintentá."
            )
            return 1
        try:
            chain = apply_chain(config_path, chosen)
        except SystemExit as exc:
            print(str(exc))
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"apply-chain failed: {exc}")
            return 1
        print("Cadena de fallback escrita en config.yaml (backup al lado):")
        for c in chain:
            print(f"  → {c['provider']}: {c['model']}")
        print("Reiniciá el gateway/agente. Los modelos son editables en config.yaml.")
        return 0

    # --- audit (read-only) ---
    try:
        cfg = load_yaml(config_path) if config_path.exists() else {}
    except Exception:
        cfg = {}
    model = current_model(cfg)
    chain = current_chain(cfg)

    if args.json:
        print(
            json.dumps(
                {
                    "current_model": model,
                    "detected_providers": [
                        {"provider": d["provider"], "key_tail": d["key_tail"]}
                        for d in detected
                    ],
                    "fallback_chain": chain,
                    "has_chain": bool(chain),
                },
                indent=2,
            )
        )
        return 0

    print("🔁 model-fallback — estado del failover")
    print(f"Modelo actual: {model or '(no configurado)'}")
    print()
    if detected:
        print("API keys detectadas (por provider):")
        for d in detected:
            n = pool_status(d["provider"])
            pool = f" · pool: {n} key(s)" if n else ""
            print(f"  ✓ {d['provider']:<11} (…{d['key_tail']}){pool}")
    else:
        print("⚠️ No detecté API keys en ~/.clawksis/.env.")
    print()
    if chain:
        print("Cadena de fallback (fallback_providers):")
        for c in chain:
            print(f"  → {c.get('provider')}: {c.get('model')}")
    else:
        print("Cadena de fallback: (ninguna configurada)")
    print()

    # verdict
    provs = [d["provider"] for d in detected]
    if chain:
        print(
            "✅ Auto-failover configurado: ante billing/error el runtime cae por esa cadena."
        )
    elif len(provs) >= 2:
        print(f"⚠️ Tenés keys de {', '.join(provs)} pero SIN cadena de fallback.")
        print("   Configurala (cae solo a otro provider ante 402/error):")
        print(f'   python3 "{Path(__file__)}" --apply-chain')
    else:
        print("⚠️ Tenés una sola key/provider y sin cadena. Para resiliencia real:")
        print(
            "   - agregá una 2ª API key del MISMO provider (el pool la rota solo ante 402/429), o"
        )
        print("   - agregá una key de OTRO provider y corré --apply-chain.")
    print()
    print(
        "Recordá: el runtime ya rota keys del pool ante 402/429 sin intervención; "
        "esta cadena agrega el salto a otro provider/modelo."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
