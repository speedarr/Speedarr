# Settings reference

[← Docs index](README.md)

This is a field-by-field reference for the Settings page. Settings is admin-only — anyone not logged in as an admin is redirected away from it.

## General

### Throttling Control

Duration, Disable Throttling and Re-enable Now take effect immediately — there is no save button.

| Setting | Default | What it does |
|---|---|---|
| Duration | Indefinitely | How long to disable throttling for: Indefinitely, 30 minutes, 1 hour, 2 hours, or Custom (1–10080 minutes). Shown before you disable. |
| Disable Throttling | — | Stops applying limits and restores all download client speeds. Monitoring and the dashboard stay live. |
| Re-enable Now | — | Turns throttling back on immediately, shown once it's disabled. |

### System Configuration

| Setting | Default | What it does |
|---|---|---|
| Polling Interval (seconds) | 5 | How often Speedarr polls media servers, download clients, and SNMP. Form accepts 5–300. |
| Log Level | Info | Sets the application's logging verbosity: Debug, Info, Warning, Error, Critical. |
| Require login to view dashboard | Off | When on, the dashboard and read APIs require authentication — anyone not logged in is sent to the login screen. |
| Download Logs | — | Downloads application logs with sensitive data (passwords, API keys) redacted. |

**Notes:** Log Level currently has no effect — only the `DEBUG` environment variable changes verbosity ([#103](https://github.com/speedarr/Speedarr/issues/103)). With Require login off, control calls (throttling, temporary limits, and so on) still always need a session or an API key regardless of this setting — see [what Require login changes](api.md#what-require-login-changes).

### About

Read-only: Version, Commit, Branch, an update check ("Up to date" / a newer build or version available / an error), and Report a Bug / Request a Feature buttons that open GitHub issue templates.

## Account

### Change Password

| Setting | Default | What it does |
|---|---|---|
| Current Password | — | Your existing password. |
| New Password | — | Your new password, 8–72 characters. |
| Confirm New Password | — | Must match New Password. |

**Notes:** The backend counts bytes, not characters, so accented letters and emoji count for more than one byte each toward the 72-byte limit.

## Integrations

### API Keys

| Setting | Default | What it does |
|---|---|---|
| Name | — | A label for the key, up to 100 characters. |
| Expiration | Never | When the key stops working: Never, 30 days, 90 days, 180 days, or 1 year. |
| Generate | — | Creates the key and shows it once in a dialog. It is not shown again. |
| Revoke | — | Immediately disables an active key. |

**Notes:** The copy button on each row in the key list hands out the full key again, so anyone with an admin session can read every active key, not just a newly generated one ([#104](https://github.com/speedarr/Speedarr/issues/104)).

### Integration Guide

Copyable Home Assistant (`rest_command:` YAML) and UnRaid (bash script) snippets for calling the temporary-limits API. See [API recipes](api.md#recipes).

## Services

### Media Servers

| Setting | Default | What it does |
|---|---|---|
| Add Media Server | — | Adds a Plex, Emby or Jellyfin server. |
| Enabled | — | Whether this server is polled. |
| Display Name | — | Label shown in the UI. |
| Server URL | — | Address of the media server. |
| X-Plex-Token / API Key | — | Plex uses X-Plex-Token; Emby and Jellyfin use an API Key. |
| Include LAN Streams in Bandwidth | Off | Counts this server's LAN streams in bandwidth calculations. When off, only its WAN streams affect limits. See [which streams count](how-it-works.md#which-streams-count). |
| LAN Networks (override) | — | Comma or newline-separated CIDRs that count as LAN. Leave blank to auto-detect from the media server or use private-IP defaults. |
| Test Connection | — | Checks the server is reachable. |
| Remove Server | — | Deletes the server card. |
| Save All Changes | — | Saves every media server card on the page. |

**Notes:** Saving a media server, or running Test Connection on it, re-reads its LAN subnets — you don't need to restart Speedarr after changing them on the server. On the dashboard, the measured-bandwidth figure comes from a Plex Pass endpoint; Emby and Jellyfin streams show a bitrate but no measured throughput.

### Download Clients

| Setting | Default | What it does |
|---|---|---|
| Add Client | — | Adds qBittorrent, SABnzbd, NZBGet, Transmission, or Deluge. |
| Enabled | — | Whether this client is managed. |
| Display Name | — | Label shown in the UI. |
| Server URL | — | Address of the client, with a hint for that client's own speed units. |
| Username + Password | — | Used by qBittorrent, NZBGet, and Transmission. |
| API Key | — | Used by SABnzbd. |
| Password | — | Used by Deluge (no username). |
| Test Connection | — | Checks the client is reachable. |
| Remove Client | — | Deletes the client card. |
| Save All Changes | — | Saves every download client card. |

**Notes:** The save result message depends on the outcome: all clients connect → "Saved successfully. All N client(s) connected."; all fail → "Saved, but all N client(s) failed to connect."; a mix shows both the success and the error together. See [which streams count](how-it-works.md#which-streams-count) for what LAN means.

## Bandwidth

### Download Bandwidth

| Setting | Default | What it does |
|---|---|---|
| Total Download Limit (Mbps) | — | Required. Total download bandwidth for your clients. 10–20% less than your actual line speed is recommended. |
| Minimum Speed per Client (Mbps) | 1.0 | Each client is never throttled below this, even when streams consume all bandwidth. Applies to every client; 0 slows a client to a trickle instead of removing the limit. |
| Demand-aware allocation | On | Shown once you have 2+ clients. When on, a client that isn't using its share lends the unused part to clients that are; when off, active clients are held to their configured percentages. |
| Active Downloads Allocation | Equal split | How to split bandwidth when multiple clients are actively downloading. Must total 100%. |
| Inactive Safety Net % | 5 | Minimum % held for an inactive client so its activity can be detected. Form accepts 0–20. |

### Scheduled Download Settings

| Setting | Default | What it does |
|---|---|---|
| Enable | Off | Turns the schedule on, independent of the card being expanded. |
| Start Time / End Time | 22:00 / 06:00 | The schedule window, in your browser's local time. |
| Total Download Limit During Schedule (Mbps) | 0 | The total download limit while the window is open, plus its own per-client split. |

### Upload Bandwidth

| Setting | Default | What it does |
|---|---|---|
| Total Upload Limit (Mbps) | — | Total upload bandwidth, same idea as the download limit. |
| Minimum Speed per Client (Mbps) | 1.0 | Same behaviour as the download minimum. |
| Upload Allocation | Equal split | Split between clients. Only applies to torrent clients — the ones that can upload. |

### Scheduled Upload Settings

Same shape as Scheduled Download Settings, for the upload side.

### Stream Bandwidth Calculation

| Setting | Default | What it does |
|---|---|---|
| Calculation Method | Auto | Auto reads the bitrate from your media server(s); Manual uses a fixed value per stream. |
| Bandwidth Per Stream (Mbps) | 15 | Manual mode only. Exact bandwidth reserved per active stream, no overhead added. |
| Protocol Overhead % | 100 | Auto mode only. Extra bandwidth to account for protocol overhead. Form accepts 0–300. |
| Download Bandwidth Reserve % | 20 | Percentage of stream upload bandwidth reserved from downloads for TCP ACKs and control traffic. Form accepts 0–100; set to 0 to disable. |

**Notes:** Saving new totals moves the Failsafe shutdown speeds along only while they still equal the old 10% default — a manual edit to a shutdown speed stops it from auto-following bandwidth changes ([#96](https://github.com/speedarr/Speedarr/issues/96)). There is no separate upload safety-net field; upload reuses the download value. The ranges above are what the form accepts, not a server-side guarantee — only Protocol Overhead % is clamped server-side. See [sharing between download clients](how-it-works.md#sharing-between-download-clients).

## Holding Times

| Setting | Default | What it does |
|---|---|---|
| Episode End Hold Time (seconds) | 600 s (10 min) | Holds bandwidth after a TV episode ends, so the next episode can start without a speed change. |
| Movie End Hold Time (seconds) | 1800 s (30 min) | Holds bandwidth after a movie ends, so credits or the next pick don't trigger a speed change. |

**Notes:** A new stream from the same user and player cancels the hold. See [holding times](how-it-works.md#holding-times).

## Notifications

Five cards, each with an Enable toggle, its own credential fields, a Test button, and the same Events to Send checklist: Stream Started, Stream Ended, Stream Count Exceeded, Stream Bitrate Exceeded, Service Unreachable.

| Card | Fields |
|---|---|
| Webhook (Discord, Slack and compatible) | Webhook URL, Test Webhook |
| Pushover | User Key, API Token |
| Telegram | Bot Token, Chat ID |
| Gotify | Server URL, Application Token |
| ntfy | Server URL (default `https://ntfy.sh`), Topic |

| Setting | Default | What it does |
|---|---|---|
| Threshold (Stream Count Exceeded) | — | Number of concurrent streams that triggers the alert. |
| Threshold (Stream Bitrate Exceeded) | — | Bitrate (Mbps) that triggers the alert. |
| Threshold alert cooldown (minutes) | 0 | Suppresses repeat threshold alerts of the same type within this window. Form accepts 0–1440; 0 means no cooldown. |

**Notes:** The two thresholds and the cooldown are single global values, even though every card shows them — setting one on any card changes it for all five. The cooldown applies only to the two threshold alerts; stream start/stop and service-unreachable events always send. The webhook is tested on save, and a failed test blocks the save. Priority (Pushover, Gotify, ntfy), the webhook rate limit (Discord/Slack), and named generic webhooks all exist in the config but have no UI control ([#106](https://github.com/speedarr/Speedarr/issues/106)).

## History

| Setting | Default | What it does |
|---|---|---|
| Retention Period (days) | 3 | How long historical data is kept before automatic cleanup. Form accepts 1–90. |

**Notes:** Cleanup runs hourly and covers stream history, bandwidth metrics, throttle decisions, events, notifications, and config history. See [retention](operations.md#retention).

## Failsafe

| Setting | Default | What it does |
|---|---|---|
| Media Server Timeout (seconds) | 300 | Intended to assume no active streams after this many seconds without a media server response. |
| Download Speed on Shutdown | Off | Toggle + Mbps value, seeded at 10% of the current download total when first turned on. Sets download clients to this speed when Speedarr shuts down; 0 floors to a trickle, never unlimited. |
| Client Split (download) | Equal split | Per-client percentage split for the shutdown download speed. Hidden with only one client. |
| Upload Speed on Shutdown | Off | Same pattern as Download Speed on Shutdown, for torrent clients only. |
| Client Split (upload) | Equal split | Per-client percentage split for the shutdown upload speed. |

**Notes:** Media Server Timeout is never read by the code — it has no effect. Limits hold in place during an outage instead; see [when a server or client goes away](how-it-works.md#when-a-server-or-client-goes-away) ([#102](https://github.com/speedarr/Speedarr/issues/102)). The grace period that actually governs how long a down media server's last-known streams are kept (300 s / 5 min) has no field on this tab at all — it isn't user-configurable. When Speedarr stops while throttling is switched off, the shutdown speeds above are skipped, but clients are still restored to their normal speeds.

## SNMP

| Setting | Default | What it does |
|---|---|---|
| Enable SNMP Monitoring | Off | Turns on router/firewall bandwidth monitoring over SNMP. Optional. |
| SNMP Host | — | Address of your router or switch. |
| Port | 161 | SNMP port. |
| Community String | `public` | SNMP v2c community string. |
| Network Interface | — | The interface to monitor, picked manually or from Discover Interfaces. |
| Test Connection | — | Checks the SNMP host is reachable. |
| Discover Interfaces | — | Scans for about 45 s, then runs 30 s of live traffic per interface, flagging a "Likely WAN Interface" badge on its best guess. |

**Notes:** SNMP v2c only. Optional — Speedarr works without it. See [SNMP](how-it-works.md#snmp).

## Dashboard controls

These aren't on the Settings page, but they're settings in disguise.

### Throttling banner

Shown on the dashboard while throttling is off. Read-only status plus a Re-enable now button for admins; it doesn't offer the duration picker that Settings › General does.

### Temporary Limits panel

| Setting | Default | What it does |
|---|---|---|
| Download (Mbps) | — | Overrides the normal download limit. Blank uses the normal limit for that direction. |
| Upload (Mbps) | — | Overrides the normal upload limit. Blank uses the normal limit for that direction. |
| Duration (Hours) | Blank (until cleared) | How long the override lasts. Blank means it persists until manually cleared. |
| Set Limits | — | Admin only. Applies the override. |
| Clear | — | Removes the override. Non-admins see a sign-in dialog instead of clearing it directly. |

The panel also shows Source (where the override came from, e.g. an API integration) and who set it.

**Notes:** Temporary limits are stored but not enforced while throttling is off. They're saved to the database, so they survive a restart.

### Panel menu

Every dashboard panel has a "..." menu and a collapse chevron.

| Setting | Default | What it does |
|---|---|---|
| Move up / Move down | — | Reorders panels. Disabled at the top/bottom of the stack. |
| Reset layout | — | Restores the default panel order and collapse state. Disabled when already at default. |
| Collapse | Expanded | Shows a one-line summary instead of full content, and stops polling that panel while collapsed. |

**Notes:** The layout is saved per browser.
