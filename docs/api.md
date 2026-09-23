# API and integrations

[← Docs index](README.md)

This page is for automating Speedarr — from Home Assistant, Unraid User Scripts, curl, or anything else that speaks HTTP. It is not a settings reference; see [Settings reference](settings.md) for the UI.

## What it's for

Speedarr exposes an HTTP API. The same API drives the Speedarr web UI, so anything the dashboard can do, a script can do too — most usefully, setting or clearing a temporary bandwidth limit from another system (a game console coming on, a parity check starting, an Unraid mover run).

Interactive documentation is built in and needs no login: **`/docs`** (Swagger UI) and **`/redoc`** are both served unauthenticated, regardless of the Require login setting.

## Authentication

Speedarr supports two ways to authenticate:

- **API key** — created in [Settings › Integrations](settings.md#integrations), with a name and an optional expiry. Send it as the `X-API-Key` header. A key carries the same privileges as the admin account — there's no read-only or scoped key type. Revoking a key takes effect immediately: the next request with it is rejected. The full key is shown when you generate it, and any admin session can copy it again from the key list.
- **Browser session** — `POST /api/auth/login` with `{username, password}` returns a JWT. Send it as `Authorization: Bearer <token>` on later requests. Sessions last 24 hours.

Only `POST /api/auth/login` is rate-limited: 5 attempts per 60 seconds, then a 5-minute block per client IP. No other endpoint is rate-limited.

## What "Require login" changes

With **Require login** off (the default), these are public — no key or session needed:

- `GET /api/status/current`
- `GET /api/streams/*` (active streams, stream history, stream summary)
- `GET /api/bandwidth/history`, `/summary`, `/chart-data`
- `GET /api/bandwidth/temporary-limits`
- `GET /api/decisions/logs`

Turn Require login on in [Settings › General](settings.md#general) and each of those needs a key or session too.

Two endpoints are always public no matter what: `GET /api/status/health` and `GET /api/status/version`.

The control endpoints are never affected by this setting — they always need a key or session: everything under `/api/control/*`, and `POST`/`DELETE /api/bandwidth/temporary-limits`. Turning Require login off does not make automation calls anonymous; it only opens up the read-only endpoints above.

## Conventions

For how a temporary limit interacts with schedules and your normal limits, see [Scheduled and temporary limits](how-it-works.md#scheduled-and-temporary-limits).

- Every bandwidth figure in the API is **Mbps** (megabits per second) — there is no bytes-based field anywhere an integrator would touch.
- POST bodies must carry `Content-Type: application/json`, even for a small body like `{"reason": "..."}`. Without it, the request can't be parsed and the reply is 422.
- Two different fields express a duration, and they aren't interchangeable: `duration_hours` on the temporary-limits endpoints (a number, over 0 up to 168), and `duration_minutes` on `pause-monitoring` (a whole number, 1–10080). `manual-throttle` also takes a `duration_minutes` field, but it isn't range-checked and the code only echoes it back in the response — it doesn't schedule an expiry or an automatic restore.
- To mean "until cleared", omit the duration field entirely (or send `null`) — sending `0` is rejected.
- When a call is authenticated with an API key, the response records `set_by` as `API: <key name>` instead of a username.

## Endpoints

| Method and path | Auth | What it does | Body / query |
|---|---|---|---|
| `GET /api/bandwidth/temporary-limits` | public unless Require login | Current override | none — response: `{active, download_mbps, upload_mbps, expires_at, remaining_minutes, source, set_by}` |
| `POST /api/bandwidth/temporary-limits` | key or session | Set an override on the totals | `download_mbps` (0–100000, optional), `upload_mbps` (0–100000, optional), `duration_hours` (>0–168, optional, omit = until cleared), `source` (≤200 chars, optional) |
| `DELETE /api/bandwidth/temporary-limits` | key or session | Clear it | none |
| `POST /api/control/manual-throttle` | key or session | Per-client limits that override the engine | `clients: [{client_id, download_limit?, upload_limit?}]`, `duration_minutes?` (no range check, not enforced — see Conventions), `reason?`; 409 while throttling is off |
| `POST /api/control/restore-speeds` | key or session | Everything back to normal | `reason?` |
| `POST /api/control/pause-monitoring` | key or session | Throttling off, clients unlimited | `duration_minutes?` (1–10080) |
| `POST /api/control/resume-monitoring` | key or session | Throttling on | none |
| `GET /api/status/current` | public unless Require login | Dashboard snapshot: throttling state, per-client speeds and limits, stream counts, bandwidth totals | none |
| `GET /api/status/version` | always public | Version, commit, branch, update check | `force_refresh` (bool) |
| `GET /api/status/health` | always public | `{status, version, commit, branch}` | none |
| `GET /api/streams/active` | public unless Require login | Active streams and holds | none |
| `GET /api/auth/api-keys`, `POST /api/auth/api-keys`, `DELETE /api/auth/api-keys/{key_id}` | key or session | Manage keys | `POST`: `name` (1–100 chars), `expires_in_days` (1–365, optional) |

## Recipes

In each snippet below, replace `http://SPEEDARR:9494` with the address your automation host can reach Speedarr at, and `YOUR_API_KEY` with a key from [Settings › Integrations](settings.md#integrations).

### Home Assistant

`configuration.yaml`:

```yaml
rest_command:
  speedarr_set_limits:
    url: "http://SPEEDARR:9494/api/bandwidth/temporary-limits"
    method: POST
    headers:
      X-API-Key: "YOUR_API_KEY"
    content_type: "application/json"
    payload: >
      {"download_mbps": {{ download_mbps | default('null') }},
       "upload_mbps": {{ upload_mbps | default('null') }},
       "duration_hours": {{ duration_hours }},
       "source": "{{ source }}"}
  speedarr_clear_limits:
    url: "http://SPEEDARR:9494/api/bandwidth/temporary-limits"
    method: DELETE
    headers:
      X-API-Key: "YOUR_API_KEY"
```

Two example automations:

```yaml
alias: "Throttle downloads for gaming"
trigger:
  - platform: state
    entity_id: binary_sensor.gaming_pc
    from: "off"
    to: "on"
action:
  - service: rest_command.speedarr_set_limits
    data:
      download_mbps: 50
      upload_mbps: 25
      duration_hours: 4
      source: "Home Assistant - Gaming PC"
```

```yaml
alias: "Restore downloads after gaming"
trigger:
  - platform: state
    entity_id: binary_sensor.gaming_pc
    from: "on"
    to: "off"
action:
  - service: rest_command.speedarr_clear_limits
```

### Unraid User Scripts

Parity Check Monitor — schedule "At Startup of Array":

```bash
#!/bin/bash
# Parity Check Monitor — polls /proc/mdstat every 60s
# Schedule: "At Startup of Array" in UnRaid User Scripts
SPEEDARR_URL="http://SPEEDARR:9494"
API_KEY="YOUR_API_KEY"
DL_LIMIT_MBPS=5   # Download limit during parity check
UL_LIMIT_MBPS=5   # Upload limit during parity check
THROTTLED=false

while true; do
  if grep -qE 'check|reshape|recover|resync' /proc/mdstat 2>/dev/null; then
    if [ "$THROTTLED" = false ]; then
      curl -s -X POST "$SPEEDARR_URL/api/bandwidth/temporary-limits" \
        -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
        -d "{\"download_mbps\": $DL_LIMIT_MBPS, \"upload_mbps\": $UL_LIMIT_MBPS, \"source\": \"UnRaid Parity Check\"}"
      THROTTLED=true
    fi
  else
    if [ "$THROTTLED" = true ]; then
      curl -s -X DELETE "$SPEEDARR_URL/api/bandwidth/temporary-limits" \
        -H "X-API-Key: $API_KEY"
      THROTTLED=false
    fi
  fi
  sleep 60
done
```

Mover Start — schedule "Before Mover":

```bash
#!/bin/bash
# Schedule: "Before Mover" in UnRaid User Scripts
SPEEDARR_URL="http://SPEEDARR:9494"
API_KEY="YOUR_API_KEY"
DL_LIMIT_MBPS=5   # Download limit during mover
UL_LIMIT_MBPS=5   # Upload limit during mover
curl -s -X POST "$SPEEDARR_URL/api/bandwidth/temporary-limits" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d "{\"download_mbps\": $DL_LIMIT_MBPS, \"upload_mbps\": $UL_LIMIT_MBPS, \"source\": \"UnRaid Mover\"}"
```

Mover Stop — schedule "After Mover":

```bash
#!/bin/bash
# Schedule: "After Mover" in UnRaid User Scripts
SPEEDARR_URL="http://SPEEDARR:9494"
API_KEY="YOUR_API_KEY"
curl -s -X DELETE "$SPEEDARR_URL/api/bandwidth/temporary-limits" \
  -H "X-API-Key: $API_KEY"
```

These are plain scripts calling the temporary-limits endpoint — Speedarr itself doesn't talk to Unraid. The Unraid API has no reliable live parity signal (the live state only exists host-side in `/proc/mdstat`, see [#30](https://github.com/speedarr/Speedarr/issues/30)), so the scripts are the supported way.

## Errors

- `401` — `Not authenticated` (no key or session), `Invalid API key` (unknown or revoked), `API key has expired`.
- `403` — not an admin account.
- `409` — `POST /api/control/manual-throttle` while throttling is off.
- `422` — validation failure, or a POST body sent without `Content-Type: application/json`.

`detail` is a plain string on some endpoints and a `{code, message}` object on others — there's no single error shape across the whole API, so handle both.

The server's CORS list is same-origin, so browser JavaScript running on another origin is blocked by the browser itself before the request reaches Speedarr. curl and other server-side callers — Home Assistant, Unraid User Scripts — aren't affected.
