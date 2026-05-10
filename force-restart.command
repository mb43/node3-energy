#!/bin/bash
# NODE-3 Arbitrage Portal — FORCE RECREATE (busts Python pyc cache)
# Use when server.py or simulate.py changes aren't being picked up.

cd "$(dirname "$0")"

echo "============================================"
echo "  NODE-3 ARBITRAGE PORTAL — Force Restart"
echo "============================================"
echo ""
echo "Force-recreating container (clears pyc cache)..."
docker compose up -d --force-recreate --no-build 2>/dev/null || docker compose up -d --force-recreate

echo ""
echo "Waiting for container to start (6s)..."
sleep 6
docker compose ps
echo ""
echo "Checking server..."
sleep 2
curl -s "http://localhost:8585/api/status" | python3 -m json.tool 2>/dev/null || echo "(status check sent)"
echo ""
echo "Triggering backfill..."
sleep 1
curl -s -X POST "http://localhost:8585/api/trigger?mode=backfill" | python3 -m json.tool 2>/dev/null || echo "(backfill triggered)"
echo ""
echo "✅ Done. Portal: http://localhost:8585"
echo ""
echo "Tailing logs (Ctrl+C to stop — container keeps running):"
docker compose logs -f
