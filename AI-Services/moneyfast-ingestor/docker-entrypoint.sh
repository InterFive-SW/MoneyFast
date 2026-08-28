#!/bin/sh
set -eu

# A pre-existing named volume may have been initialized as root. Repair only
# the dedicated state directory, then drop privileges before Python starts.
mkdir -p /app/state
chown -R ingestuser:ingestuser /app/state

exec gosu ingestuser "$@"
