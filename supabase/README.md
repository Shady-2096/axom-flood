# Credential-free reporting backend

This directory contains the private reporting inbox for Axom Flood. Supabase is
not a public read dependency: a separate repository pipeline will export
aggregate-only, content-hashed JSON for the static SvelteKit site.

## Safety boundary

- Axom Flood is a reporting channel, not an emergency service.
- No responder is monitoring the bots.
- Every emergency branch says that no rescue request was sent and directs the
  user to the reviewed ASDMA State Emergency Operation Centre number, **1070**.
- Reports begin `pending`; community evidence never changes the official CWC
  river status.
- Raw phone numbers, Telegram identifiers, browser device tokens, IP addresses,
  full webhook bodies, full-precision coordinates, and free text are never
  persisted.
- Coordinates are rounded server-side to three decimals before insertion.
- `reporting` is not an exposed Data API schema. The exposed `api` schema
  contains only `SECURITY INVOKER` routines granted to `service_role`.
- `anon` and `authenticated` have no table or routine privileges.

The canonical pure reducer is
`functions/_shared/conversation.js`. Platform parsing and Deno runtime code stay
outside it, so the web UI can use the same flow without importing server code.

## Local verification

```sh
node --test supabase/functions/tests/*.test.js
supabase start
supabase db reset
supabase test db
supabase functions serve web-intake --env-file supabase/.env.local --no-verify-jwt
```

`supabase start`, database reset, pgTAP, and local Edge Function serving require
Docker. The pure reducer and adapter fixture tests require no credentials or
containers.

## Web intake contract

`POST /functions/v1/web-intake`, at most 16 KiB:

```json
{
  "delivery_id": "a-client-generated-uuid",
  "device_token": "a-random-token-kept-on-this-browser",
  "event": {
    "type": "location_shared",
    "payload": {
      "latitude": 26.912345,
      "longitude": 94.680123,
      "localityId": "karbi-anglong-silonijan"
    }
  }
}
```

The token and full coordinate exist only for the duration of the request. The
function persists a monthly keyed hash and a rounded point.

## Bot registration

Credential-dependent setup deliberately remains undone:

1. Create/link the Supabase project and apply the migration.
2. Set secrets from `.env.example`.
3. Deploy all three functions.
4. Register the Telegram webhook with a `secret_token`.
5. Configure Meta webhook verification and signing, then set the WhatsApp
   webhook URL.
6. Set the website runtime submission URL only after the deployed web intake
   passes live abuse, privacy, and real-device tests.

Do not put a secret/service-role key in Svelte or any public bundle.
