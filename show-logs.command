#!/bin/bash
cd "$(dirname "$0")"
echo "=== node3-portal Docker logs (last 100 lines) ==="
docker logs node3-portal --tail=100 2>&1
echo ""
echo "=== DONE ==="
read -p "Press Enter to close..."
