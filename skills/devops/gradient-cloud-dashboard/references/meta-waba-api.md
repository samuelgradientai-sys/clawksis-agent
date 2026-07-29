# Meta WABA API Reference — Gradient Cloud

## Users (Meta Direct, no YCloud)

| User ID | Email | Empresa | WABA ID | Phone Number ID | Token Prefix | Status |
|---|---|---|---|---|---|---|
| `0f8ec8c2` | samuelgradientai@gmail.com | Gradient AI | `1882258442488384` | `1103545326182176` | `EAARR0cGA51Q...` | ✅ CONNECTED |
| `2bde4a72` | opticaluzdevida318@gmail.com | Optica Luz De Vida | `756871830749447` | `1200819219772799` | `EAARR0cGA51Q...` | ⚠️ cancelled |
| `50ee069a` | davidgradientai@gmail.com | 3PL | `2046617999568779` | `1201598023026506` | `EAARR0cGA51Q...` | pending |

**Note**: Samuel's profile also appears as "Samuel Gomez" with empresa "Gradient AI" on the Meta side. The WABA display number is **+57 313 846 6734**.

## Meta Graph API Endpoint

### Send Text Message

```
POST https://graph.facebook.com/v22.0/{phone_number_id}/messages
Authorization: Bearer {business_credential_from_meta_waba_onboardings}
Content-Type: application/json

{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "573202685612",
  "type": "text",
  "text": {
    "preview_url": false,
    "body": "Message text here"
  }
}
```

### Success Response

```json
{
  "messaging_product": "whatsapp",
  "contacts": [{"input": "573202685612", "wa_id": "573202685612"}],
  "messages": [{"id": "wamid.HBgMNTczMjAyNjg1NjEyFQIAERgUQ0VEQ0FEOThDNTkxNjRBNDE4RUYA"}]
}
```

### Error Response

```json
{
  "error": {
    "message": "(#100) Param to is not a valid WhatsApp ID",
    "type": "OAuthException",
    "code": 100,
    "error_subcode": 2662001,
    "fbtrace_id": "Axxxxxxxxxx"
  }
}
```

## Webhook (Inbound)

All Meta users share the same webhook endpoint:
```
POST https://qqmtyqxtopxedevduxxm.supabase.co/functions/v1/meta-webhook
```

3PL additionally has a custom n8n webhook:
```
https://n8n-n8n.jjggv4.easypanel.host/webhook-test/d354135b-98c2-4156-ab8a-7c20eb0e7640
```
Events: `["message.received"]`

## How to Get Credentials Programmatically

```sql
-- Get WABA credentials for a user
SELECT 
    w.phone_number_id,
    w.waba_id,
    w.business_credential AS waba_token,
    w.display_number,
    w.last_known_status,
    w.client,
    p.full_name,
    p.email,
    p.nombre_de_empresa
FROM meta_waba_onboardings w
JOIN profiles p ON p.id = w.user_id
WHERE w.user_id = '{user_uuid}';
```

## Phone Format

All phone numbers in the system use **E.164 without `+`**:
- `573202685612` (not `+573202685612` or `573202685612`)
- Store this format in the `to` field of Meta API calls
- The `wa_id` in the response uses the same format

## Rate Limits

- **Unverified business**: ~250 messages/day per number
- **Verified business**: up to 100K+ depending on quality rating
- Meta applies the WABA **quality rating** (Green/Yellow/Red) which affects throughput
- Use the business_credential token from `meta_waba_onboardings` — these are long-lived tokens (don't expire quickly)
