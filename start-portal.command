#!/bin/bash
# NODE-3 Arbitrage Portal — Docker launcher
# Double-click this file in Finder to build and start the container.

set -e

# Navigate to the folder this script lives in
cd "$(dirname "$0")"

echo "============================================"
echo "  NODE-3 ARBITRAGE PORTAL — Docker Launch"
echo "============================================"
echo ""

# Ensure data files exist (Docker volumes need them to be present)
touch fleet_state.json history.csv prices.json

# Build and start
echo "Building image and starting container..."
docker compose up --build -d

echo ""
echo "✅ Container started. Portal is at:"
echo "   http://localhost:8585"
echo ""
echo "Waiting for healthcheck..."
sleep 5
docker compose ps
echo ""
echo "Tailing logs (Ctrl+C to stop following, container keeps running):"
docker compose logs -f
