# Meta status page notes

Session-derived notes for monitoring Meta business product status.

## Official page

- Status page: `https://metastatus.com`
- Page title: `Status and outages of Meta business products`
- The page is a React app backed by public JSON under `/data/`.

## Useful public endpoints

- `https://metastatus.com/data/orgs.json`
- `https://metastatus.com/data/outages/<org_id>.json`
- `https://metastatus.com/data/outages/<org_id>.history.json`

## Discovered org / service IDs

- Org id for WhatsApp Business Platform: `whatsapp-business-api`
- Relevant services observed in this session:
  - `Cloud API`
  - `Cloud API - Calling`
  - `WhatsApp Business Account Management`
  - `Embedded Signup`
  - `WhatsApp Flows`
  - `Marketing Messages API for WhatsApp`
  - `Coexistence - Messaging`
  - `Coexistence - Onboarding`

## Status interpretation seen in this session

- Healthy values: `No known issues`, `Resolved`
- Degraded values: `Medium disruptions`, `High disruptions`

## Monitoring pattern

The watchdog used a silent script that:

1. fetched `orgs.json`
2. selected the org with `id == 'whatsapp-business-api'`
3. checked each service status
4. printed nothing while any service remained degraded
5. printed a concise recovery message once everything was healthy again

## Example cron behavior

- Schedule: `every 15m`
- Delivery: `origin`
- Mode: `no_agent: true`
- Output: silent until recovery
