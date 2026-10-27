# eToro API key permissions (scopes)

What each checkbox in **Settings > Trading > API Key Management** grants, from the key creation
wizard (two steps: *Detalles*, then *Permisos*) and the live scope list the API returns from
`GET /api/v1/me`.

## Key creation screen

- Step 1 chooses the **account**: *Cuenta principal* = real money, the demo portfolio = virtual.
  One key pair belongs to ONE environment; a demo pair answers 401/403 against the real routes
  and vice versa.
- Step 2 shows the permissions, with shortcuts *Leer todo* (all reads) / *Escribir todo* (all
  writes). **Never suggest *Escribir todo*** — it grants `trade.real:write`.
- The confirmation screen prints **Clave privada** and **Clave pública**. Private = the user key
  (`x-user-key` → `ETORO_USER_KEY`); public = the API key (`x-api-key` → `ETORO_API_KEY`). The
  private one is displayed once.

## Read-only set to request (enough for forecast + portfolio review)

| UI section | Scope |
|---|---|
| Datos de mercado | `etoro-public:market-data:read` |
| Trading – Real · Read | `etoro-public:trade.real:read`, `etoro-public:real:read` |
| Información del usuario | `etoro-public:user-info:read` |
| Dinero · Balance | `etoro-public:money.balance:read` |
| Cripto (only for BTC/ETH) | `etoro-public:crypto:read` |

`market-data:read` is the one that must never be missing: candles and symbol search go through
it, so without it there is no forecast at all.

## Full catalog

| UI section | Read | Write | What the write side does |
|---|---|---|---|
| Dinero | `money.balance:read`, `money.cash-transactions:read`, `money.transfer:read` | `money.transfer:write` | move money between accounts |
| Trading – Real | `trade.real:read`, `real:read` | `trade.real:write`, `real:write` | open/close/modify real orders |
| Trading – Demo | `trade.demo:read`, `demo:read` | `trade.demo:write`, `demo:write` | same, virtual money |
| Datos de mercado | `market-data:read` | — | candles, quotes, instrument search |
| Cripto | `crypto:read` | `crypto:write` | crypto-specific routes |
| Cartera de agente | `agent-portfolio:read` | `agent-portfolio:write` | eToro agent portfolios + user tokens |
| Lista de seguimiento | `watchlist:read` | `watchlist:write` | edit watchlists |
| Feed | `feed:read` | `feed:write` | post/comment/like on your behalf |
| Notificaciones | `notifications:read` | `notifications:write` | mark read |
| Club | `club:read` | — | Club dashboard |
| Alcances SSO | `sso-scopes:read`, `sso-applications:read` | `sso-applications:write` | register OAuth apps + secrets |
| Pi Data | `pi-data:read` | — | public copier info |
| Pnl Alerts / Price Alerts | `pnl-alerts:read` | `pnl-alerts:write` | create/delete alerts |
| Sub Accounts | `sub-accounts:read` | `sub-accounts:write` | create sub-accounts, move money |
| Otros | `eToro-public:realtime` | — | WebSocket streaming (unused: the scripts are REST) |

`crypto:*` and `pnl-alerts:*` appear on live pairs even though the published OpenAPI scope list
omits them — trust `etoro_data.py check` over the swagger for what a key actually holds.

## Auditing a pair

```bash
python3 scripts/etoro_data.py check      # {ok, username, scopes: [...]}
```

- `ok: true` + username proves `x-api-key`/`x-user-key` are a valid pair.
- Filter the list for `:write` and tell the user, in one line, what the pair could change.
- `trade.real:write` absent = it cannot trade real money, whatever else it holds.
