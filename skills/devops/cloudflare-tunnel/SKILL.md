---
name: cloudflare-tunnel
description: >-
  Expose a local service to the public internet with a Cloudflare Quick Tunnel —
  no Cloudflare account, login, or DNS needed. Run
  `cloudflared tunnel --url http://localhost:PORT` and it prints a public
  https://<random>.trycloudflare.com URL that forwards to your local port. Use
  when you need to share a dev server, webhook receiver, demo, or local API with
  someone outside the machine. Covers installing cloudflared, starting the tunnel
  in the background, capturing the generated URL, and tearing it down. WARNING:
  Quick Tunnel URLs are PUBLIC and UNAUTHENTICATED — anyone with the link reaches
  your local service — and are ephemeral (they change on restart and are
  rate-limited). Do not expose sensitive services.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  clawk:
    tags: [cloudflare, tunnel, networking, expose, webhook, devops, ngrok-alternative]
---

# Cloudflare Quick Tunnel

Expose `http://localhost:PORT` to the internet over a public
`https://<random>.trycloudflare.com` URL using Cloudflare's free Quick Tunnels.
No account, login, certificate, or DNS configuration required.

## When to use this

- Share a local dev server / demo with someone remote.
- Give an external service (Stripe, GitHub, Meta, Telegram, Twilio…) a public
  HTTPS webhook URL that reaches a handler running on this machine.
- Quick public testing of a local API.

**Security:** the generated URL is public and unauthenticated — anyone who has
it can reach your local service. The URL is also ephemeral (a new random
subdomain each run) and rate-limited. Never expose a service holding secrets,
admin panels, or production data this way. Stop the tunnel when done.

## 1. Check / install cloudflared

```bash
cloudflared --version 2>/dev/null || echo "cloudflared not installed"
```

Install if missing:

```bash
# macOS
brew install cloudflared

# Debian/Ubuntu
curl -fsSL https://pkg.cloudflare.com/cloudflared-stable-linux-amd64.deb -o /tmp/cf.deb && sudo dpkg -i /tmp/cf.deb
#   (ARM: replace amd64 with arm64; or grab the static binary from
#    https://github.com/cloudflare/cloudflared/releases/latest)

# Windows
winget install --id Cloudflare.cloudflared
#   (or: download cloudflared.exe from the GitHub releases page above)
```

## 2. Start the tunnel and capture the URL

`cloudflared tunnel --url http://localhost:PORT` runs in the FOREGROUND and
blocks. The public URL is printed to **stderr** within a few seconds. Run it in
the background and read the URL out, e.g. for a service on port 8080:

```bash
# Start in the background, logging to a file
cloudflared tunnel --url http://localhost:8080 > /tmp/cf-tunnel.log 2>&1 &
echo $! > /tmp/cf-tunnel.pid

# Wait for and extract the public URL
for i in $(seq 1 20); do
  url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cf-tunnel.log | head -1)
  [ -n "$url" ] && break
  sleep 1
done
echo "Public URL: ${url:-<not ready — check /tmp/cf-tunnel.log>}"
```

If you have the `terminal` tool with `background=true`, prefer launching it that
way and `watch_patterns: ["trycloudflare.com"]` to get notified when the URL
appears, instead of polling a log file.

The forwarded URL maps `https://<random>.trycloudflare.com` → your
`http://localhost:PORT`. Hand that URL to whoever/whatever needs to reach the
service.

## 3. Stop the tunnel

```bash
# If you saved the PID:
kill "$(cat /tmp/cf-tunnel.pid)" 2>/dev/null && rm -f /tmp/cf-tunnel.pid

# Otherwise:
pkill -f 'cloudflared tunnel --url' 2>/dev/null
```

## Notes & troubleshooting

- **URL changes every run.** Quick Tunnels are throwaway. For a stable hostname
  you need a named tunnel + a Cloudflare account + a domain (`cloudflared tunnel
  login`, `cloudflared tunnel create <name>`, route DNS) — out of scope here.
- **`failed to request quick Tunnel` / 429:** Quick Tunnels are rate-limited;
  wait a bit and retry, or authenticate for a named tunnel.
- **Nothing reachable:** confirm the local service is actually listening on that
  port (`curl -sS http://localhost:PORT` locally first).
- **Protocol:** add `--protocol http2` if QUIC/UDP is blocked on the network.
- Quick Tunnels forward HTTP/HTTPS only. For raw TCP you need a named tunnel.
