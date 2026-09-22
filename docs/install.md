# Installing Speedarr

[← Docs index](README.md)

## What you need

A media server — Plex, or Emby or Jellyfin (both marked experimental in the app, but fully usable). And at least one download client: qBittorrent, SABnzbd, NZBGet, Transmission, or Deluge.

## Docker

1. Download the `docker-compose.yml` file from this repository:

```yaml
services:
  speedarr:
    image: speedarr/speedarr:latest
    container_name: speedarr
    ports:
      - "9494:9494"
    volumes:
      - ./data:/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:9494/api/status/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    # Set to your local DNS server/router IP to resolve local hostnames (.lan, .local, etc.)
    #dns:
    #  - 192.168.10.1
    restart: unless-stopped
```

2. Pull the latest image:

```bash
docker compose pull
```

3. Start the container:

```bash
docker compose up -d
```

Open **http://localhost:9494** — the setup wizard will walk you through connecting Plex and your download clients.

## Windows (Docker Desktop)

1. Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop/), default settings are fine
2. Open Docker Desktop **Settings > General** and ensure **Start Docker Desktop when you sign in** is enabled, so Speedarr starts automatically on reboot
3. Open **PowerShell** and run the following commands:

```powershell
mkdir C:\Speedarr
cd C:\Speedarr
curl -o docker-compose.yml https://raw.githubusercontent.com/speedarr/Speedarr/main/docker-compose.yml
docker compose up -d
```

Open **http://localhost:9494** — the setup wizard will walk you through connecting Plex and your download clients.

> **Note**: `C:\Speedarr` is just a suggestion — you can use any folder you like.

## Unraid

1. Open the **Community Applications** (CA) plugin
2. Search for **Speedarr**
3. Click **Install** and apply the default template

The container will be available at **http://[UNRAID-IP]:9494**.

## The container

### Port

Speedarr always listens on port 9494 inside the container. To use a different port on your host, change the host side of the mapping in `docker-compose.yml`, e.g. `"8080:9494"`.

There used to be a `PORT` environment variable, but it never did anything — supervisord always starts uvicorn with `--port 9494` hardcoded — so it's been removed. Remap the host port in the compose file instead.

### PUID and PGID

PUID and PGID default to 99:100 — Unraid's `nobody:users`. The entrypoint script remaps the container's `speedarr` user to match whatever you set and takes ownership of `/data`. If you want the files in your data folder to belong to a specific user on your host, set both in the compose file's `environment:` block:

```yaml
environment:
  - PUID=1000
  - PGID=1000
```

### Local hostnames

> **Tip**: If your services use `.lan` or `.local` hostnames, add `dns: [192.168.1.1]` (your router IP) to the service in `docker-compose.yml`.

The shipped compose file has this commented out already, ready to uncomment and point at your own router or local DNS server:

```yaml
# Set to your local DNS server/router IP to resolve local hostnames (.lan, .local, etc.)
#dns:
#  - 192.168.10.1
```

### Environment variables

All of these are optional — Speedarr runs fine with none of them set.

| Variable | What it does | Default |
|---|---|---|
| `AUTH__SECRET_KEY` | JWT signing key for authentication | Auto-generated and saved to `/data/.jwt_secret` if unset |
| `CONFIG_ENCRYPTION_KEY` | Fernet key used to encrypt stored secrets (passwords, tokens, API keys, webhook URLs) at rest | Auto-generated and saved to `/data/.encryption_key` if unset |
| `DEBUG` | `true` turns on DEBUG-level console logs and SQL query logging | `false` |

The generated keys live in your data folder alongside the database, so make sure they're covered by whatever you use for [backups](operations.md#backups).

## Updating

To update Speedarr, navigate to the folder containing your `docker-compose.yml` and run:

```bash
docker compose pull
docker compose up -d
```

This pulls the latest image and recreates the container. Your data and settings are preserved.

## First run

Open Speedarr in your browser. The first screen asks you to create an admin account — a username and password. Once that's done, the setup wizard starts.

### The wizard

The wizard has seven steps:

1. **Welcome** — an intro screen, nothing to fill in.
2. **Media Servers** (required) — add one or more media servers. Each needs a Server URL and either an X-Plex-Token (Plex) or an API Key (Emby/Jellyfin). Test Connection checks each one. LAN stream handling isn't set here — that's Settings-only.
3. **Download Client** (required) — add at least one download client. Each needs a Server URL and the auth that client type wants: Username + Password for qBittorrent, NZBGet, and Transmission; an API Key for SABnzbd; a Password only for Deluge. Each card shows that client's own speed units next to Speedarr's Mbps. Display names aren't editable here — also Settings-only.
4. **Bandwidth** (required) — enter your total download and upload limits, in Mbps, 10–20% under your real line speed. If you added two or more clients, you'll also set how to split bandwidth between them. Protocol overhead and the download reserve percentage aren't set here — Settings-only.
5. **SNMP** (optional) — skip it if you don't use it.
6. **Notifications** (optional) — skip it if you don't want alerts yet.
7. **Summary** — review what you entered, then click Complete Setup.

If you refresh the page partway through, your progress is saved and the wizard picks up where you left off.

## Finding your token or API key

**Plex**

1. Open any media item in the Plex web app
2. Click **Get Info** → **View XML**
3. Copy the `X-Plex-Token` value from the URL

Plex also has a support article on this: [How to find your X-Plex-Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

**Emby and Jellyfin**

Dashboard → Advanced → API Keys.

**SABnzbd**

Config → General → Security → API Key.

## After setup

Once setup's done, everything else lives on the Settings page:

- Whether LAN streams count toward bandwidth, and which networks count as LAN — [Settings → Services](settings.md#services)
- Client display names — [Settings → Services](settings.md#services)
- Protocol overhead and the download reserve percentage — [Settings → Bandwidth](settings.md#bandwidth)
- How long bandwidth is held after a stream ends — [Settings → Holding Times](settings.md#holding-times)
- Shutdown speeds, for when Speedarr's own process stops — [Settings → Failsafe](settings.md#failsafe)
- How long history is kept before cleanup — [Settings → History](settings.md#history)
- API keys, for Home Assistant, Unraid, and other automation — [Settings → Integrations](settings.md#integrations)
- Requiring login to view the dashboard — [Settings → General](settings.md#general)
