---
name: deploy-dashboard-custom-domain
description: "USE THIS to publish the Clawksis dashboard on a custom domain (https://tu-dominio.com) when the server ALREADY has a reverse proxy — EasyPanel/Coolify (Traefik), nginx, or a Cloudflare Tunnel — so `clawk dashboard domain` skips Caddy. Covers the two real pitfalls: a proxy in Docker can't reach the host's 127.0.0.1 (bind 0.0.0.0 + point the proxy at the docker gateway 172.17.0.1), and Cloudflare orange-cloud + redirect-to-https = infinite loop. Trigger ES+EN: 'publicar el dashboard en un dominio', 'exponer clawksis en mi dominio', 'dashboard en https', 'dominio con Traefik/EasyPanel/Cloudflare', 'clawk dashboard domain', 'deploy dashboard to a domain', 'expose the dashboard', 'dashboard behind Traefik/nginx/Cloudflare'."
argument-hint: 'deploy-dashboard-custom-domain tu-dominio.com'
allowed-tools: Bash, Read
author: Clawksis (Gradient AI)
license: MIT
user-invocable: true
version: 1.1.0
metadata:
  clawk:
    tags: [dashboard, domain, cloudflare, traefik, easypanel, nginx, deployment, reverse-proxy]
  clawksis:
    emoji: "🌐"
  openclaw:
    emoji: "🌐"
---

# Publicar el dashboard en un dominio propio (detrás de un proxy existente)

El comando **`clawk dashboard domain <dominio>`** ya hace casi todo. Esta skill
es para el caso en que el servidor **ya tiene un reverse proxy** ocupando 80/443
(EasyPanel/Coolify con Traefik, nginx, un Cloudflare Tunnel) — ahí el comando
**no** instala Caddy y hay que enrutar por el proxy que ya corre, con dos
trampas conocidas.

## Regla de oro de seguridad

**Nunca uses `--insecure`.** Un bind no-loopback (`0.0.0.0` o la gateway docker)
**mantiene el login gate activo** por sí solo. `--insecure` lo APAGA y deja el
dashboard sin contraseña. El comando ya deja el gate forzado
(`CLAWK_DASHBOARD_FORCE_GATE=1`); no lo desarmes.

## Paso 1 — Correr el comando

```bash
sudo clawk dashboard domain tu-dominio.com
```

Qué hace (autodetecta el escenario):
- Escribe/actualiza `/etc/systemd/system/clawk-dashboard.service` con el login
  gate forzado y `CLAWK_DASHBOARD_PUBLIC_HOST=tu-dominio.com`.
- Sondea 80/443. Si están **libres** → instala Caddy con HTTPS automático y
  listo (bind loopback). Si están **ocupados** → no instala Caddy, y si el
  proxy está en **Docker** deja el dashboard escuchando en `0.0.0.0` (gate ON)
  para que el contenedor lo alcance.
- Imprime el destino exacto al que apuntar tu proxy.

## Paso 2 — Enrutar por tu proxy

El destino depende de dónde corre el proxy:

- **Proxy en el host** (nginx del sistema): `http://127.0.0.1:9119`
- **Proxy en Docker** (Traefik de EasyPanel/Coolify, nginx en contenedor): la
  **gateway del bridge docker**, típicamente `http://172.17.0.1:9119`
  (verificá con `ip -4 addr show docker0`). Desde el contenedor, `127.0.0.1`
  es el propio contenedor, NO el host — por eso hay que usar la gateway y por
  eso el dashboard bindea a `0.0.0.0`.

Verificá la conectividad desde Docker antes de seguir:

```bash
docker run --rm alpine wget -q -O- http://172.17.0.1:9119/ | head -c 80
# → <!doctype html>…  (el dashboard responde)
```

### Traefik (EasyPanel/Coolify) — routers + service

Editá el archivo de config dinámica de Traefik (en EasyPanel:
`/etc/easypanel/traefik/config/main.yaml`, es JSON con extensión `.yaml`).
Agregá un router HTTP y uno HTTPS + un service:

```json
{
  "http": {
    "routers": {
      "http-clawksis-dashboard": {
        "rule": "Host(`tu-dominio.com`)",
        "entryPoints": ["http"],
        "service": "clawksis-dashboard"
      },
      "https-clawksis-dashboard": {
        "rule": "Host(`tu-dominio.com`)",
        "entryPoints": ["https"],
        "service": "clawksis-dashboard",
        "tls": { "certResolver": "letsencrypt", "domains": [{ "main": "tu-dominio.com" }] }
      }
    },
    "services": {
      "clawksis-dashboard": {
        "loadBalancer": {
          "passHostHeader": true,
          "servers": [{ "url": "http://172.17.0.1:9119" }]
        }
      }
    }
  }
}
```

Traefik recarga la config dinámica solo (watch). `passHostHeader: true` es
importante para que el dashboard reciba el `Host` correcto.

### nginx (en el host)

```nginx
server {
  server_name tu-dominio.com;
  location / {
    proxy_pass http://127.0.0.1:9119;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
  # TLS con certbot, o dejá que Cloudflare termine el SSL (ver pitfall abajo).
}
```

### Cloudflare Tunnel

En el panel Zero Trust → Networks → Tunnels → tu tunnel → Public Hostnames:
agregá `tu-dominio.com` → `http://172.17.0.1:9119` (o `127.0.0.1:9119` si el
cloudflared corre en el host, no en Docker).

## Pitfall #1 — El proxy en Docker no alcanza loopback

Síntoma: 502/Bad Gateway desde el proxy aunque el dashboard corre. Causa: el
dashboard bindea `127.0.0.1` y el proxy está en un contenedor, para el que
`127.0.0.1` es él mismo. Cura: el comando ya bindea `0.0.0.0` cuando detecta un
proxy en Docker; apuntá el service a la **gateway** `172.17.0.1:9119`, no a
`127.0.0.1`.

## Pitfall #2 — Cloudflare naranja + redirect HTTP→HTTPS = loop infinito

Síntoma: `ERR_TOO_MANY_REDIRECTS`. Causa: con la nube **naranja** (proxied),
Cloudflare termina el SSL y manda **HTTP** al origen; si tu proxy además
redirige HTTP→HTTPS, el request vuelve a Cloudflare y se cicla. Cura: **quitá el
redirect-to-https** del router/middleware HTTP del dashboard — dejá que Traefik/
nginx sirvan HTTP plano y que Cloudflare ponga el HTTPS al cliente.

## Paso 3 — DNS

Registro `A` de `tu-dominio.com` → IP del server (o el tunnel). Con Cloudflare:
- **Naranja (proxied):** Cloudflare pone el HTTPS; seguí el pitfall #2.
- **Gris (DNS only):** tu proxy tiene que emitir el certificado (Let's Encrypt).

## Verificación final

```bash
ss -tlnp | grep 9119                       # 0.0.0.0:9119 (proxy en docker) o 127.0.0.1:9119
curl -sI -H 'Host: tu-dominio.com' http://172.17.0.1:9119/ | head -1   # 302 → login (gate ON)
curl -sI https://tu-dominio.com/ | head -1 # 200/302 vía el proxy
```

La primera visita a `https://tu-dominio.com` muestra el setup y crea tu usuario
y contraseña (o corré `clawk dashboard password`).
