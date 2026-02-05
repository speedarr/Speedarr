#!/bin/bash
set -e

echo "=== Speedarr Starting ==="

# Default PUID/PGID to 99:100 (Unraid's nobody:users)
PUID=${PUID:-99}
PGID=${PGID:-100}

echo "Running with UID: $PUID, GID: $PGID"

# Update speedarr group GID if different
if [ "$(id -g speedarr)" != "$PGID" ]; then
    groupmod -o -g "$PGID" speedarr
fi

# Update speedarr user UID if different
if [ "$(id -u speedarr)" != "$PUID" ]; then
    usermod -o -u "$PUID" speedarr
fi

# Ensure /data is owned by speedarr
chown -R speedarr:speedarr /data

# Fix permissions on stdout/stderr for logging
chmod 777 /dev/stdout /dev/stderr 2>/dev/null || true

# Switch to speedarr user and run command
exec gosu speedarr "$@"
