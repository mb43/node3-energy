#!/bin/bash
cd "$(dirname "$0")"
echo "=== Scheduler/simulation output (no HTTP access logs) ==="
docker logs node3-portal 2>&1 | grep -v '"GET /api' | grep -v '"POST /api'
echo ""
echo "=== Current fleet_state.json ==="
cat fleet_state.json
echo ""
echo "=== DONE ==="
read -p "Press Enter to close..."
