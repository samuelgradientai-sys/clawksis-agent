#!/usr/bin/env python3
"""
Daily spend tracker for DeepSeek + OpenAI + OpenRouter.
Records balance snapshots and projects monthly spend.

Usage:
    python3 daily-spend-tracker.py              # Show current + projection
    python3 daily-spend-tracker.py --record     # Record today's snapshot to history
    python3 daily-spend-tracker.py --history    # Show all recorded snapshots
    python3 daily-spend-tracker.py --project    # Show monthly projection only

History stored in: ~/.clawksis/data/billing-history.json
"""

import json, os, sys
from datetime import datetime, timedelta

HISTORY_FILE = os.path.expanduser("~/.clawksis/data/billing-history.json")
ENV_FILE = os.path.expanduser("~/.clawksis/.env")

def load_env():
    keys = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    keys[k] = v.strip("\"'")
    return keys

def fetch_balances(keys):
    """Fetch current balances from all providers."""
    import urllib.request, json as j

    results = {}

    # DeepSeek
    if "DEEPSEEK_API_KEY" in keys:
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": f"Bearer {keys['DEEPSEEK_API_KEY']}"}
            )
            resp = j.loads(urllib.request.urlopen(req, timeout=10).read())
            bi = resp.get("balance_infos", [{}])[0]
            results["deepseek"] = float(bi.get("total_balance", 0))
        except Exception as e:
            results["deepseek"] = {"error": str(e)}

    # OpenAI
    if "OPENAI_API_KEY" in keys:
        try:
            key = keys["OPENAI_API_KEY"]
            req = urllib.request.Request(
                f"https://api.openai.com/v1/usage?date={datetime.utcnow().strftime('%Y-%m-%d')}",
                headers={"Authorization": f"Bearer {key}"}
            )
            resp = j.loads(urllib.request.urlopen(req, timeout=10).read())
            data = resp.get("data", [])
            total = sum(float(x.get("cost", 0)) for x in data)
            results["openai_usage_today"] = total
            results["openai_key_type"] = (
                "project" if key.startswith("sk-proj-") else
                "org" if key.startswith("sk-org-") else "legacy"
            )
        except Exception as e:
            results["openai"] = {"error": str(e)}

        # Also fetch account info
        try:
            req2 = urllib.request.Request(
                "https://api.openai.com/v1/me",
                headers={"Authorization": f"Bearer {keys['OPENAI_API_KEY']}"}
            )
            resp2 = j.loads(urllib.request.urlopen(req2, timeout=10).read())
            results["openai_account"] = resp2.get("email", "unknown")
        except Exception:
            pass

    # OpenRouter
    if "OPENROUTER_API_KEY" in keys:
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {keys['OPENROUTER_API_KEY']}"}
            )
            resp = j.loads(urllib.request.urlopen(req, timeout=10).read())["data"]
            results["openrouter_usage"] = resp["usage"]
            results["openrouter_limit"] = resp.get("limit")
        except Exception as e:
            results["openrouter"] = {"error": str(e)}

    return results

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []

def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def record_snapshot(keys):
    history = load_history()
    balances = fetch_balances(keys)

    snapshot = {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if isinstance(balances.get("deepseek"), (int, float)):
        snapshot["deepseek_balance"] = balances["deepseek"]

    snapshot["openai_account"] = balances.get("openai_account", "unknown")
    snapshot["openai_key_type"] = balances.get("openai_key_type", "unknown")
    snapshot["openai_usage_today"] = balances.get("openai_usage_today", 0)

    if "openrouter_usage" in balances:
        snapshot["openrouter_usage"] = balances["openrouter_usage"]

    # Avoid duplicates on same day — update if exists
    for i, entry in enumerate(history):
        if entry["date"] == snapshot["date"]:
            history[i] = snapshot
            break
    else:
        history.append(snapshot)

    save_history(history)
    return snapshot

def compute_projections(history):
    """Compute daily spend and monthly projection from history."""
    if len(history) < 2:
        return {"error": "Need at least 2 snapshots for projection"}

    sorted_hist = sorted(history, key=lambda x: x["date"])

    # DeepSeek daily spend
    ds_spends = {}
    for i in range(1, len(sorted_hist)):
        prev = sorted_hist[i - 1]
        curr = sorted_hist[i]
        if "deepseek_balance" in prev and "deepseek_balance" in curr:
            diff = prev["deepseek_balance"] - curr["deepseek_balance"]
            if diff > 0:
                ds_spends[curr["date"]] = round(diff, 4)

    # Averages
    ds_daily = sum(ds_spends.values()) / len(ds_spends) if ds_spends else 0

    projection = {}
    projection["deepseek"] = {
        "days_with_data": len(ds_spends),
        "daily_avg": round(ds_daily, 4),
        "monthly_projection": round(ds_daily * 30, 2),
        "last_balance": sorted_hist[-1].get("deepseek_balance", 0),
        "days_remaining": round(sorted_hist[-1].get("deepseek_balance", 0) / ds_daily, 1) if ds_daily > 0 else float("inf"),
    }

    # Compute total across all platforms
    monthly_total = projection["deepseek"]["monthly_projection"]

    projection["combined"] = {
        "monthly_total_projected": round(monthly_total, 2),
        "recommended_topup_every_months": 2,
        "recommended_topup_amount": round(monthly_total * 2, 0),
    }

    return projection

def print_report(projection, history):
    if "error" in projection:
        print(f"⚠️  {projection['error']}")
        return

    ds = projection["deepseek"]
    comb = projection["combined"]

    print("📊 BILLING PROJECTION")
    print("=" * 50)
    print(f"📆  Data from {len(history)} snapshots over {ds['days_with_data']} day(s)")
    print()
    print("🤖  DEEPSEEK")
    print(f"     Daily avg:     ${ds['daily_avg']:.4f}")
    print(f"     Monthly proj:  ${ds['monthly_projection']:.2f}")
    print(f"     Balance:       ${ds['last_balance']:.2f}")
    print(f"     Days left:     ~{ds['days_remaining']:.0f} days")
    print()
    print("💵  COMBINED (DeepSeek + OpenAI)")
    print(f"     Total monthly: ${comb['monthly_total_projected']:.2f}")
    print(f"     Recommended:   ${comb['recommended_topup_amount']:.0f} every {comb['recommended_topup_every_months']} months")
    print()

    # History table
    print("📋  Recent history:")
    print(f"  {'Date':<12} {'DeepSeek':<12} {'OpenAI Acct':<25}")
    print(f"  {'-'*12} {'-'*12} {'-'*25}")
    for entry in sorted(history, key=lambda x: x["date"])[-10:]:
        ds_b = f"${entry.get('deepseek_balance', '?'):<8}" if isinstance(entry.get("deepseek_balance"), (int, float)) else "?"
        oa = entry.get("openai_account", "?")
        print(f"  {entry['date']:<12} {ds_b:<12} {oa:<25}")

def main():
    keys = load_env()
    history = load_history()

    if "--record" in sys.argv:
        snap = record_snapshot(keys)
        print(f"✅  Snapshot recorded for {snap['date']}")
        return

    if "--history" in sys.argv:
        if not history:
            print("No history yet. Use --record to start.")
            return
        print(f"{'Date':<12} {'DeepSeek':<12} {'OpenAI Acct':<25}")
        print(f"{'-'*12} {'-'*12} {'-'*25}")
        for entry in sorted(history, key=lambda x: x["date"]):
            ds_b = f"${entry.get('deepseek_balance', '?'):<8}" if isinstance(entry.get("deepseek_balance"), (int, float)) else "?"
            oa = entry.get("openai_account", "?")
            print(f"{entry['date']:<12} {ds_b:<12} {oa:<25}")
        return

    if "--project" in sys.argv or len(sys.argv) == 1:
        projection = compute_projections(history)
        print_report(projection, history)
        return

if __name__ == "__main__":
    main()
