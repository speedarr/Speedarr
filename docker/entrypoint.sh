#!/bin/bash
set -e

echo "=== Speedarr Starting ==="

# Verify data directory is writable
if [ ! -w "/data" ]; then
    echo "ERROR: /data is not writable. Check volume permissions."
    exit 1
fi
exec "$@"
