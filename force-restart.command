#!/bin/bash
# NODE-3 Arbitrage Portal — FORCE RECREATE (busts Python pyc cache)
# Use when server.py or simulate.py changes aren't being picked up.

cd "$(dirname "$0")"

echo "============================================"
echo "  NODE-3 ARBITRAGE PORTAL — Force Restart"
echo "============================================"
echo ""
echo "Force-recreating container (clears pyc cache)..."
# NOTE: previously ran with --no-build, which meant this script could NEVER
# pick up Dockerfile or requirements.txt changes (new COPY'd files, new pip
# deps) — it only ever recreated a container from whatever image already
# existed, however old or broken. That's why node3_config.py went missing
# (never in the image) and scipy stayed broken (stale cached install layer)
# even after both were fixed in source. Now always rebuilds — Docker's own
# layer cache keeps this fast when nothing relevant changed.
docker compose up -d --force-recreate --build

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
