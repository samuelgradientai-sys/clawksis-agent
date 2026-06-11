# Dashboard login with your own OIDC provider (`self_hosted`)

The dashboard ships an OpenID Connect Relying Party plugin,
`plugins/dashboard_auth/self_hosted` (`SelfHostedOIDCProvider`), so you can put
**your own** identity provider (Auth0, Zitadel, Keycloak, Authentik, Okta, …)
in front of the dashboard login — no Nous Portal, and no OAuth code to write.
It is a **public PKCE client**, so there is no client secret to manage.

> The default bind stays `127.0.0.1`. The auth gate only engages when the
> dashboard binds to a non-loopback address (e.g. `--host 0.0.0.0` behind a
> reverse proxy or tunnel). On loopback it stays open, as before.

## Configure it

Point the plugin at any IdP that exposes a standard OIDC discovery document
(`<issuer>/.well-known/openid-configuration`).

### `~/.clawksis/config.yaml`

```yaml
dashboard:
  oauth:
    provider: self-hosted
    self_hosted:
      issuer: https://auth.clawksis.com/application/o/clawksis/   # required
      client_id: clawksis-dashboard                               # required
      scopes: "openid profile email"                              # optional
```

### Environment overrides

Env wins over `config.yaml` when set non-empty (handy for Docker / Fly secret
injection):

| Variable | Maps to | Notes |
|---|---|---|
| `CLAWK_DASHBOARD_OIDC_ISSUER` | `self_hosted.issuer` | required |
| `CLAWK_DASHBOARD_OIDC_CLIENT_ID` | `self_hosted.client_id` | required |
| `CLAWK_DASHBOARD_OIDC_SCOPES` | `self_hosted.scopes` | optional; defaults to `openid profile email` |

When the plugin loads but can't register (missing issuer / client_id) it records
a reason in `LAST_SKIP_REASON`, and the gate fails closed with that message
instead of a bare "no providers registered".

## How it fits together

1. Register an OIDC **application** in your IdP (e.g. `auth.clawksis.com`) and
   set its redirect/callback URI to the dashboard's `…/auth/callback`.
2. Drop the `issuer` + `client_id` into the config above.
3. Run the dashboard bound to a reachable address (behind a proxy/tunnel). The
   gate redirects unauthenticated visitors to your IdP's login.

This replaces the `nous` plugin's portal login with identity you control. The
`nous` plugin is left untouched — switching providers is just the
`dashboard.oauth.provider` / `issuer` values above.

## Personal API key (`clawk connect`)

The OIDC login authenticates the **dashboard**. A long-lived **personal API
key** (issued by your clawksis.com portal) is separate — store it on a machine
with:

```bash
clawk connect --key <YOUR_API_KEY>      # or: clawk connect  (prompts, no echo)
clawk disconnect                        # remove it
```

It's saved to `~/.clawksis/.env` as `CLAWKSIS_API_KEY` (reusing the standard
`api_key` plumbing) and never printed. If `CLAWKSIS_PORTAL_URL` is set, the key
is verified against `<portal>/api/keys/verify` first (best-effort). This is
distinct from `clawk login`, which authenticates an LLM inference provider.
