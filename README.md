<p align="center">
  <img src="https://raw.githubusercontent.com/speedarr/Speedarr/main/docs/logos/speedarr_banner_clean.png" alt="Speedarr" width="200">
</p>


<p align="center">
  <a href="https://github.com/speedarr/Speedarr/releases/latest"><img src="https://img.shields.io/github/v/release/speedarr/Speedarr?style=flat-square&color=blue" alt="Release"></a>
  <a href="https://hub.docker.com/r/speedarr/speedarr"><img src="https://img.shields.io/docker/pulls/speedarr/speedarr?style=flat-square" alt="Docker Pulls"></a>
</p>

<h3 align="center">Dynamic bandwidth management for Plex and download clients</h3>

<p align="center">
  Speedarr monitors your Plex streams and dynamically throttles uploads to prevent buffering.<br>
  Streaming always gets priority. Will also balance multiple download clients.
</p>

---

<!-- Replace with actual screenshot -->
<p align="center">
  <img src="https://raw.githubusercontent.com/speedarr/Speedarr/main/docs/screenshots/dashboard.png" alt="Speedarr Dashboard" width="800">
</p>

## Main Features

- Real-time dashboard with bandwidth charts, active stream monitoring, and stream history
- Direct Plex API polling for stream detection
- Support for **qBittorrent**, **SABnzbd**, **NZBGet**, **Transmission**, and **Deluge**
- Separate upload and download management with per-client allocation
- Scheduled bandwidth limits for time-based rules (e.g. different speeds during peak or off-peak)
- Temporary speed limit overrides with automatic expiration
- Restoration delays based on media type — episodes restore faster than movies
- SNMP monitoring for real WAN bandwidth from your router (Unifi currently, more coming soon)
- Notifications via Discord, Pushover, Telegram, Gotify, ntfy, and custom webhooks

## ⚠️ Disclaimer ⚠️

> **This project is entirely vibe coded using AI (Claude).** While I have found it works well and is actively used and I have thoroughly tested, the codebase has not been manually reviewed line-by-line. Use at your own discretion and please report any issues you encounter.

## Quick Start

### Prerequisites

- Plex Media Server with an API token
- At least one download client

### Unraid

1. Open the **Community Applications** (CA) plugin
2. Search for **Speedarr**
3. Click **Install** and apply the default template

The container will be available at **http://[UNRAID-IP]:9494**.


### Docker

1. Download the `docker-compose.yml` file from this repository.
2. Pull the latest image:
```bash
docker compose pull
```

3. Start the container:
```bash
docker compose up -d
```

Open **http://localhost:9494** — the setup wizard will walk you through connecting Plex and your download clients.

> **Tip**: If your services use `.lan` or `.local` hostnames, add `dns: [192.168.1.1]` (your router IP) to the service in `docker-compose.yml`.

### Finding Your Plex Token

1. Open any media item in the Plex web app
2. Click **Get Info** → **View XML**
3. Copy the `X-Plex-Token` value from the URL

## Configuration

First time run will present a wizard to guide you through the process

The Wizard will configure the mandatory settings but other options are configurable from the **Settings** page after setup:

- **Plex** — Server URL, token, LAN stream handling
- **Download Clients** — Add/remove clients, set max speeds, assign colors
- **Bandwidth** — Total limits, allocation percentages, scheduled limits, overhead
- **Restoration** — Delays for episodes vs movies
- **SNMP** — Router monitoring with interface auto-discovery
- **Notifications** — Per-platform setup with event filtering and thresholds
- **Failsafe** — Plex timeout behavior, shutdown speeds


## SNMP Monitoring

Measure actual WAN bandwidth from your router, this is more of a nice-to-have rather than requirement:

1. Enable SNMP on your router
2. Go to **Settings** → **SNMP** → Enable
3. Enter your router IP and SNMP credentials
4. Click **Test Connection** → **Discover Interfaces**
5. Select your WAN interface and save

Speedarr will suggest the most likely WAN interface based on current traffic patterns.

## Notifications

Configure alerts in **Settings** → **Notifications** for any combination of:

| Platform | Setup |
|----------|-------|
| **Discord** | Webhook URL |
| **Pushover** | User key + API token |
| **Telegram** | Bot token + chat ID |
| **Gotify** | Server URL + app token |
| **ntfy** | Server URL + topic |
| **Webhooks** | Any URL with custom headers |

**Available events**: Stream started/ended, stream count exceeded, stream bitrate exceeded, service unreachable/recovered.



## Support

- [GitHub Issues](https://github.com/speedarr/Speedarr/issues) — Bug reports and feature requests


## License

[MIT](LICENSE)
