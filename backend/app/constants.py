"""
Application constants with documented reasoning.

This file centralizes "magic numbers" used throughout the codebase,
providing clear documentation for why each value was chosen.
"""

# =============================================================================
# RATE LIMITING
# =============================================================================

# Login rate limiting - protects against brute force password attacks
# 5 attempts is generous for typos but catches automated attacks
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5

# 60 second window - short enough to catch rapid attacks, long enough
# that legitimate users won't hit it during normal login attempts
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60

# 5 minute block - long enough to discourage attackers, short enough
# that legitimate users can retry after a reasonable wait
LOGIN_RATE_LIMIT_BLOCK_SECONDS = 300

# =============================================================================
# HTTP CLIENT TIMEOUTS
# =============================================================================

# General HTTP client timeout (Plex, qBittorrent, SABnzbd, etc.)
# 30 seconds allows for slow networks while preventing indefinite hangs
HTTP_CLIENT_TIMEOUT_SECONDS = 30

# Webhook timeout - shorter because webhooks should be fast
# If Discord/Telegram takes >10s, something is wrong
WEBHOOK_TIMEOUT_SECONDS = 10

# Shutdown timeout for restoring client speeds
# Allows time for slow clients but doesn't hang shutdown indefinitely
SHUTDOWN_RESTORE_TIMEOUT_SECONDS = 15

# =============================================================================
# DATABASE
# =============================================================================

# SQLite busy timeout - wait for locks before failing
# 5 seconds handles most concurrent access without long hangs
# Prevents "database is locked" errors under normal load
SQLITE_BUSY_TIMEOUT_MS = 5000

# =============================================================================
# POLLING & MONITORING
# =============================================================================

# Stream data refresh interval
# 5 seconds balances responsiveness with API load on Plex server
STREAM_POLL_INTERVAL_SECONDS = 5

# Background task health check interval
# 60 seconds is frequent enough to catch crashes quickly
# without adding unnecessary overhead
TASK_MONITOR_CHECK_INTERVAL_SECONDS = 60

# Data retention cleanup interval
# Hourly is sufficient - retention is measured in days, not seconds
RETENTION_CLEANUP_INTERVAL_SECONDS = 3600

# =============================================================================
# SNMP MONITORING
# =============================================================================

# SNMP request timeout - short because SNMP should be fast on local network
SNMP_TIMEOUT_SECONDS = 2.0

# SNMP retries for quick requests (interface discovery, single OID)
SNMP_RETRIES_QUICK = 1

# SNMP timeout for bulk data collection (more data, may need more time)
SNMP_BULK_TIMEOUT_SECONDS = 5.0

# SNMP retries for bulk operations
SNMP_RETRIES_BULK = 2

# =============================================================================
# PLEX INTEGRATION
# =============================================================================

# Seconds to wait for Plex response before assuming no active streams
# 300s (5 min) is generous - Plex should respond much faster
# This is a failsafe to prevent getting stuck if Plex becomes unreachable
PLEX_FAILSAFE_TIMEOUT_SECONDS = 300

# =============================================================================
# AUTHENTICATION
# =============================================================================

# Default session timeout (24 hours in seconds)
# Long enough for day-long sessions, short enough to limit exposure
# if a token is compromised
SESSION_TIMEOUT_SECONDS = 86400

# =============================================================================
# NOTIFICATIONS
# =============================================================================

# Minimum seconds between same notification event type
# Prevents notification spam during rapid state changes
NOTIFICATION_RATE_LIMIT_SECONDS = 60

# =============================================================================
# BANDWIDTH METRICS
# =============================================================================

# Default interval for bandwidth history queries (in minutes)
# 5 minutes provides good granularity without excessive data points
DEFAULT_BANDWIDTH_HISTORY_INTERVAL_MINUTES = 5
