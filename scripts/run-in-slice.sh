#!/usr/bin/env bash
# Launch war games worker inside a systemd simulation slice
set -euo pipefail

SLICE="${1:-simulation.slice}"
CONFIG="${2:-$HOME/PROJECTz/war-games/config/default.toml}"

echo "Starting war games in slice: $SLICE"
echo "Config: $CONFIG"

systemd-run --user --slice="$SLICE" --unit=wargames-worker \
    --description="War Games Worker" \
    -- bash -c "cd $HOME/PROJECTz/war-games && python -m wargames.cli start --config $CONFIG"
