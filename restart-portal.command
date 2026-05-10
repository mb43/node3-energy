#!/bin/bash
# NODE-3 Arbitrage Portal — restart container (no rebuild)
# Applies updated docker-compose.yml volume mounts and restarts.

cd "$(dirname "$0")"

echo "============================================"
echo "  NODE-3 ARBITRAGE PORTAL — Restart"
echo "============================================"
echo ""
echo "Stopping and re-creating container (no rebuild)..."
docker compose up -d --no-build 2>/dev/null || docker compose up -d

echo ""
echo "Waiting for container to start..."
sleep 4
docker compose ps
echo ""
echo "Triggering backfill simulation..."
sleep 2
curl -s -X POST "http://localhost:8585/api/trigger?mode=backfill" | python3 -m json.tool 2>/dev/null || echo "(trigger request sent)"
echo ""
echo "✅ Done. Portal: http://localhost:8585"
echo ""
echo "Tailing logs (Ctrl+C to stop — container keeps running):"
docker compose logs -f
