---
name: cloudflare-tunnel
description: "Expose local services to the public internet via Cloudflare tunnels — both zero-auth quick tunnels (trycloudflare.com) and named token-based tunnels with custom domains. Covers install, DNS diagnosis, ingress configuration, tunnel types, background patterns, and custom-domain deployment with existing reverse proxies (Easypanel/Traefik)."
version: 3.1.0
author: Agent
metadata:
  clawk:
    tags: [cloudflare, tunnel, trycloudflare, devops, networking, dns, custom-domain]
    related_skills: [clawksis-agent, dashboard]
---

# Cloudflare Tunnel

## Install

```bash
curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

## Basic Usage

```bash
# Expose a local server (any port)
cloudflared tunnel --url http://127.0.0.1:PORT
```

Output shows:
```
Your quick Tunnel has been created! Visit it at:
https://<random-words>.trycloudflare.com
```

## Background Process Pattern (Reliable URL Extraction)

Always redirect stderr to a file for reliable URL extraction — `process(action='poll')` can time out during the slow QUIC handshake:

```bash
terminal(background=true, command="cloudflared tunnel --url http://127.0.0.1:9119 2>/tmp/cloudflared.log")

# Wait generously (15-30s on some VPS providers)
sleep 15

# Extract URL from log file
grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log | head -1
```

The URL is printed ~15 lines before `Registered tunnel connection`. If you see that connection line in the log, the URL was already emitted.

## HTTP2 Fallback (When QUIC Stalls)

If QUIC takes >30s or repeatedly stalls:

```bash
cloudflared tunnel --url http://127.0.0.1:PORT --protocol http2
```

## Common Patterns

| Service | Start Command | Tunnel Command |
|---------|--------------|----------------|
| Static files | `python3 -m http.server 8080` | `cloudflared tunnel --url http://127.0.0.1:8080` |
| Clawksis Dashboard | `clawk dashboard --host 0.0.0.0 --port 9119 --no-open --insecure --skip-build` | `cloudflared tunnel --url http://127.0.0.1:9119` |
| Any HTTP server | `./server --port PORT` | `cloudflared tunnel --url http://127.0.0.1:PORT` |

## Named Tunnels (Token-Based, Custom Domains)

For production use with a custom domain, use a named tunnel authenticated via a **connector token** (Cloudflare Zero Trust dashboard → Tunnels → Create tunnel).

### How Token-Based Tunnels Work

```
Cloudflare creates the tunnel in Zero Trust Dashboard
       ↓
You run: cloudflared tunnel run --token <TOKEN>
       ↓
Cloudflare edge accepts connections for your custom domains
       ↓
Traffic is routed according to ingress rules (cloud-managed OR local config)
```

### Checking If a Tunnel Is Running

```bash
# Find active tunnel processes
ps aux | grep cloudflared | grep -v grep

# Typical token-based process:
# cloudflared --no-autoupdate tunnel --no-autoupdate run --token eyJhIj...

# Check tunnel info (if you have the tunnel name/ID)
cloudflared tunnel info <name-or-id>
```

Without an origin cert (`cloudflared tunnel login`), `cloudflared tunnel list` will fail. Token-based tunnels are managed in the Cloudflare Zero Trust dashboard.

### Checking DNS

```bash
# Check if a domain uses Cloudflare DNS
dig clawksis.com NS +short
# → ursula.ns.cloudflare.com.
# → reese.ns.cloudflare.com.

# Check if a subdomain already has a record
dig agente.clawksis.com +short
# → (empty = no record yet)
```

### Custom Domain Deployment: Requirements

To serve a local service at `https://your-service.yourdomain.com`:

| # | What | How |
|---|------|-----|
| 1 | **DNS Record** | CNAME `your-service.yourdomain.com` → `<tunnel-id>.cfargotunnel.com` |
| 2 | **Ingress Rule** | Map `your-service.yourdomain.com` → `localhost:PORT` in tunnel config |
| 3 | **Host Header** | The upstream service must accept the custom Host header |

### Three Options for Setup

| Option | What's needed | Who does it |
|--------|---------------|-------------|
| **A — API token** | Cloudflare API token (DNS:Edit + Tunnel:Edit) | Agent automates everything |
| **B — Manual DNS + local config** | User creates CNAME in Cloudflare dashboard; agent creates local `config.yml` for ingress | User does DNS, agent does ingress |
| **C — Manual everything** | User creates DNS record + tunnel ingress rule in Cloudflare dashboard | User |

### Local Ingress Config (Option B)

Create a `~/.cloudflared/config.yml` named for the tunnel (e.g. from the token prefix):

```yaml
tunnel: <tunnel-id-or-name>
credentials-file: /root/.cloudflared/<uuid>.json
ingress:
  - hostname: agente.clawksis.com
    service: http://localhost:9119
  - service: http_status:404
```

Then restart cloudflared:

```bash
pkill cloudflared
cloudflared tunnel --config ~/.cloudflared/config.yml run
```

### Diagnosing Tunnel Issues

| Symptom | Likely cause |
|---------|-------------|
| `Cannot determine default origin certificate path` | No `cert.pem` — token-based tunnel is fine, this error is harmless |
| No DNS response for subdomain | CNAME record doesn't exist yet in Cloudflare DNS |
| 502 Bad Gateway from tunnel | Upstream service rejecting Host header — check `--insecure` / host validation |
| Tunnel process running but no traffic | Ingress rule missing for the domain (configure in Dashboard or local config) |

### Token-Based vs Quick Tunnel

| Feature | Quick Tunnel | Named Tunnel (Token) |
|---------|-------------|---------------------|
| Auth needed | None | Cloudflare account + token |
| URL | `random.trycloudflare.com` | Custom domain |
| Uptime | Ephemeral | Production-grade |
| DNS | Auto-generated | Manual CNAME required |
| Ingress | Auto | Must configure |

## Production Dashboard Deployment (`clawk dashboard domain`)

For publishing the Clawksis Dashboard behind a custom domain with HTTPS:

```bash
clawk dashboard domain agente.tudominio.com
```

This command:
1. Installs the dashboard as a systemd service (bound to loopback + login gate forced on)
2. Installs Caddy if missing, writes reverse-proxy config, reloads it
3. If Caddy would collide with an existing proxy (Traefik, Nginx, Easypanel), it skips Caddy install and prints the upstream proxy rule needed

### After `clawk dashboard domain` detects an existing proxy

The command accepts the existing reverse proxy and prints the rule to add:

```
Regla genérica: agente.tudominio.com → http://127.0.0.1:9119
```

But in practice (Docker-based proxies like Traefik or Easypanel), **the dashboard must listen on `0.0.0.0`**, not `127.0.0.1`, because Docker containers reach the host via the Docker bridge gateway (normally `172.17.0.1`), not loopback.

```bash
# Edit the systemd unit:
sed -i 's/--host 127.0.0.1/--host 0.0.0.0/' /etc/systemd/system/clawk-dashboard.service
sed -i 's/--skip-build/--skip-build --insecure/' /etc/systemd/system/clawk-dashboard.service
systemctl daemon-reload && systemctl restart clawk-dashboard
```

Then add a reverse-proxy route in the existing proxy's config:

| Proxy | Config location | Rule |
|-------|----------------|------|
| **Traefik** | `/etc/easypanel/traefik/config/main.yaml` (JSON with `.yaml` ext) | Router + service pointing to `http://172.17.0.1:9119` |
| **Nginx** | `/etc/nginx/sites-available/` | `proxy_pass http://127.0.0.1:9119;` |
| **Caddy** | Auto-installed by `clawk dashboard domain` | Automatic |

### Cloudflare Proxy DNS (orange cloud)

When `clawksis.com` is managed by Cloudflare DNS, create an A record:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `agente` | server_public_ip | ✅ Proxied (orange cloud) |

With the orange cloud enabled:
- Cloudflare terminates HTTPS — the origin (Traefik/Nginx) receives **plain HTTP**
- The Traefik/Nginx router for this domain must **NOT redirect HTTP→HTTPS** (would create a redirect loop)
- Let's Encrypt on the origin will fail (NXDᴏᴍᴀɪɴ from Cloudflare's perspective); Cloudflare handles the cert instead
- Cloudflare Origin CA can issue a cert for Full (Strict) mode if needed

Traefik JSON config example with proxy compat (no redirect):

```json
{
  "http": {
    "routers": {
      "http-clawksis-dashboard-0": {
        "middlewares": ["bad-gateway-error-page"],    /* no "redirect-to-https" */
        "priority": 0,
        "rule": "Host(`agente.tudominio.com`) && PathPrefix(`/`)",
        "service": "clawksis-dashboard-0",
        "entryPoints": ["http"]
      },
      "https-clawksis-dashboard-0": {
        "middlewares": ["bad-gateway-error-page"],
        "priority": 0,
        "rule": "Host(`agente.tudominio.com`) && PathPrefix(`/`)",
        "service": "clawksis-dashboard-0",
        "tls": {
          "certResolver": "letsencrypt",
          "domains": [{"main": "agente.tudominio.com"}]
        },
        "entryPoints": ["https"]
      }
    },
    "services": {
      "clawksis-dashboard-0": {
        "loadBalancer": {
          "passHostHeader": true,
          "servers": [{"url": "http://172.17.0.1:9119"}]
        }
      }
    }
  }
}
```

## Named Tunnels (Token-Based, Production)

For persistent custom domains without managing a reverse proxy:

```bash
# Create a tunnel in Cloudflare Zero Trust dashboard → generate connector token
# Run with the token:
cloudflared tunnel --no-autoupdate run --token eyJh...aiJ9

# Or as a Docker container:
docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token eyJh...aiJ9
```

Ingress rules for token-based tunnels are managed in the Cloudflare Zero Trust dashboard, **not** in a local config file. To add a local service, create an ingress rule pointing `agente.tudominio.com` → `localhost:9119` in the dashboard's Tunnel → Public Hostname page.

## Pitfalls

- **ICMP proxy warning** (`Group ID 0 is not between ping group 1 to 0`) — harmless, ignore it.
- **Cannot determine default configuration path** — also harmless for quick tunnels.
- **502 Bad Gateway** — the upstream service isn't accepting connections from the tunnel's IP. Check Host header validation (add `--insecure` flag to the upstream service).
- **QUIC can stall for 15-60s** — happens on some VPS providers. Use the file-based log pattern above instead of `process(action='wait')`.
- **No uptime guarantee** — ephemeral tunnels for testing/demos only. Subject to Cloudflare Online Services ToS.
- **Host header rejection** — the upstream service must accept arbitrary Host headers. Many local servers need `--insecure` or `--host 0.0.0.0` flags.
- **Cleanup**: killing and restarting cloudflared multiple times can leave processes. `pkill cloudflared` before restarting.
- **Docker proxy collision**: If ports 80/443 are held by docker-proxy (Traefik/Easypanel), `clawk dashboard domain` skips Caddy install. You must configure the existing proxy manually.
- **Dashboard bound to 127.0.0.1**: Default systemd unit binds loopback only. Change to `0.0.0.0` for Docker-network reachability.
- **Cloudflare proxy redirect loop**: With orange-cloud DNS, remove `redirect-to-https` from the HTTP router — Cloudflare handles client-side TLS, origin receives HTTP. Adding redirect causes an infinite loop.

## Clawksis Dashboard: Deploy Behind Existing Reverse Proxy (Easypanel/Traefik)

When the server runs **Easypanel** (or Coolify) with **Traefik** already handling ports 80/443, use the built-in `clawk dashboard domain` command instead of a quick tunnel:

### Step 1 — Set up the dashboard for a custom domain

```bash
clawk dashboard domain agente.tudominio.com
```

This command:
- Installs the dashboard as a systemd service (`clawk-dashboard.service`) bound to loopback
- Forces the login gate ON
- Detects if an existing reverse proxy (Traefik, Caddy, Nginx) already uses ports 80/443 → skips Caddy install
- Adds the custom domain to the dashboard's allowed Host headers
- Prints instructions to configure your proxy and DNS

### Step 2 — Add ingress rule to Traefik (Easypanel)

**Config file**: `/etc/easypanel/traefik/config/main.yaml` (JSON format despite `.yaml` extension)

Add to `http.routers`:
```json
"http-clawksis-dashboard-0": {
  "middlewares": ["redirect-to-https", "bad-gateway-error-page"],
  "priority": 0,
  "rule": "Host(`agente.tudominio.com`) && PathPrefix(`/`)",
  "service": "clawksis-dashboard-0",
  "entryPoints": ["http"]
},
"https-clawksis-dashboard-0": {
  "middlewares": ["bad-gateway-error-page"],
  "priority": 0,
  "rule": "Host(`agente.tudominio.com`) && PathPrefix(`/`)",
  "service": "clawksis-dashboard-0",
  "tls": {
    "certResolver": "letsencrypt",
    "domains": [{"main": "agente.tudominio.com"}]
  },
  "entryPoints": ["https"]
}
```

Add to `http.services`:
```json
"clawksis-dashboard-0": {
  "loadBalancer": {
    "passHostHeader": true,
    "servers": [{"url": "http://172.17.0.1:9119"}]
  }
}
```

The Docker bridge IP (`172.17.0.1`) is the standard gateway from containers to the host. Use `host.docker.internal` on Docker Desktop environments instead.

After editing, restart Traefik:
```bash
docker ps --filter "name=traefik" --format '{{.Names}}' | head -1 | xargs docker restart
```

> **⚠️ Pitfall — container names change after restart** Easypanel runs Traefik as a Docker Swarm service, so container IDs get a new random suffix each time. Always use `docker ps --filter "name=traefik"` to find the current name, don't hardcode it.

### Step 3 — DNS

Create an **A record** pointing `agente.tudominio.com` → your server's public IP. Traefik's Let's Encrypt integration auto-provisions the HTTPS certificate once DNS propagates.

```bash
# Get your server's public IP
curl -s ifconfig.me
```

### Pitfalls

- **Don't mix stderr into JSON output**: when generating config with Python, redirect stderr separately (`> file 2>/dev/null`), or use a heredoc to avoid contaminating the JSON with subprocess debug output.
- **Dashboard Host header**: run `clawk dashboard domain` FIRST before adding the Traefik rule — it registers the Host header acceptance.
- **Login gate is mandatory** when using `clawk dashboard domain` — create username/password on first visit or via `clawk dashboard password`.
- **The dashboard runs on 127.0.0.1:9119**, not in Docker. Traefik reaches it via the Docker bridge IP.
- **If the quick tunnel approach is preferred** (no DNS needed), use the `cloudflared tunnel --url` commands in the **Basic Usage** section above instead.
