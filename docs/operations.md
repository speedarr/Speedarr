# Running Speedarr

[← Docs index](README.md)

This page covers what's on disk, how to back it up, and what to check when something's not behaving.

## The data folder

Everything Speedarr keeps lives in `/data` inside the container — `./data` on the host with the default compose file:

- `speedarr.db` — the SQLite database. While the container is running you'll also see `speedarr.db-wal` and `speedarr.db-shm` next to it (WAL mode is on for every connection); they get folded back into the main file on a clean shutdown or a retention cleanup, but treat all three as one unit.
- `.jwt_secret` — the JWT signing key, auto-generated on first run if you haven't set `AUTH__SECRET_KEY`.
- `.encryption_key` — the Fernet key used to encrypt every password, token, API key and webhook URL stored in the database, auto-generated if you haven't set `CONFIG_ENCRYPTION_KEY`.
- `logs/speedarr.log` — the application log, rotated at 10 MB and kept for 7 days, always at INFO regardless of the `DEBUG` environment variable. This rotation is separate from the [retention](#retention) setting below — it isn't affected by it either way.

PUID and PGID default to 99:100 (Unraid's `nobody:users`); see [PUID and PGID](install.md#puid-and-pgid) for how to change the ownership of these files. `AUTH__SECRET_KEY`, `CONFIG_ENCRYPTION_KEY` and `DEBUG` are documented in [environment variables](install.md#environment-variables).

## Backups

Stop the container, copy the whole data folder somewhere safe, start it again. All three database files belong together — copying `speedarr.db` on its own while `-wal`/`-shm` exist can leave you with a backup that's missing recent writes.

`.encryption_key` matters more than it looks: it's what decrypts every stored password and token, so a database backup without the matching encryption key is not restorable — you'd have a config full of passwords Speedarr can no longer read. `.jwt_secret` is much lower stakes; lose it and everyone's just signed out, nothing else changes.

If you set `AUTH__SECRET_KEY` or `CONFIG_ENCRYPTION_KEY` yourself via the environment rather than letting Speedarr generate them, back those values up instead — the files won't exist.

## Retention

History is kept for 3 days by default, adjustable from 1 to 90 in [Settings › History](settings.md#history). A cleanup job runs every hour and trims stream history, bandwidth metrics, throttle decisions, events, notifications and configuration-change history down to that window, then checkpoints the database's WAL file to reclaim the disk space.

## Logs

**Settings › General › Download Logs** gives you the last 10,000 lines with API keys, tokens and passwords redacted — safe to attach to a GitHub issue. For more detail than that, set `DEBUG=true` in the environment, which turns on verbose console logging (and SQL query logging); it doesn't change what's written to `speedarr.log` on disk, only the container's own console output.

The **Log Level** dropdown in Settings › General looks like it should control this, but it's currently wired to nothing — changing it has no effect ([#103](https://github.com/speedarr/Speedarr/issues/103)). `DEBUG` is the only thing that actually changes verbosity.

## Backing up

Everything Speedarr knows lives under `/data`: the database, `.encryption_key` and `.jwt_secret`. Back up that directory as a whole, because the database can't be read without its key file. There's no configuration export endpoint.

## Health endpoints

`GET /api/status/health` returns status, version, commit and branch, needs no auth, and is what the Docker healthcheck in the compose file calls.

Two more exist if you want finer-grained checks: `GET /api/status/live` is a bare liveness probe (just confirms the process is up), and `GET /api/status/ready` answers 503 until the database, the loaded config and the polling monitor are all ready.

## Upgrading notes

Coming from before v2026.09.21: qBittorrent, NZBGet, Deluge and SABnzbd limits will run about 2–5% tighter than before at the same settings. That's not a regression — those four clients were being over-allocated because of a unit-conversion bug (each one talks kibibytes, kilobytes or raw bytes internally, and the conversion wasn't matching), so the fix brings actual throughput in line with what you'd configured all along. Transmission was unaffected.

You'll also start seeing `speedarr.db-wal` and `speedarr.db-shm` next to the database now that WAL mode is confirmed working — make sure your backup process picks them up (see [Backups](#backups)).

## Troubleshooting

- **`.lan` or `.local` hostnames don't resolve.** Docker's default DNS doesn't know about your local network. Add `dns:` with your router's IP to the `speedarr` service in `docker-compose.yml` — see [Local hostnames](install.md#local-hostnames).
- **A client shows unreachable.** Speedarr marks a client unreachable after six failed polls in a row — about 30 s at the default interval — and sends a notification once that threshold is crossed. Check the URL and credentials, and use Test Connection in Settings › Services.
- **Streams play but nothing is throttled.** They're most likely LAN streams, and either the server's Include LAN Streams toggle is off (the default) or its LAN Networks override doesn't match the client's real address. See [which streams count](how-it-works.md#which-streams-count).
- **A trailer or preview reserves 10 Mbps.** Plex sometimes reports exactly 10000 for a trailer's bitrate or bandwidth — a known Plex quirk, not a real number. Speedarr clamps it down to 10 Mbps rather than reserving 10 Gbps for a preview clip.
- **The limit in the client is a few percent off Speedarr's figure.** Different clients speak different units internally — kibibytes, kilobytes, or raw bytes — while Speedarr always works in Mbps. The Services tab shows each client's own units next to the field so you can sanity-check the conversion.
- **Downloads are unlimited and a banner says throttling is disabled.** Someone turned it off — from the dashboard or Settings › General — possibly with a timer running. Click Re-enable Now on the banner, or go to Settings › General.
- **Speeds didn't restore when the media server went down.** They will, just not straight away: a silent server's last-known streams stay reserved for the Media Server Timeout (Settings › Failsafe, 300 s by default), then count as ended and the usual holding time runs. If you want full speed back right now, use Disable Throttling.
- **A new password is rejected.** Passwords are capped at 72 bytes, not 72 characters — accented letters, symbols and emoji can each count as 2 to 4 bytes, so a shorter-looking password can still hit the limit.
- **Automation gets a 401 although Require login is off.** Require login only affects read-only endpoints. Every control call — manual throttle, temporary limits, pause/resume — always needs a valid API key or session regardless of that setting. See [what Require login changes](api.md#what-require-login-changes).
