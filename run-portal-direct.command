#!/bin/bash
# NODE-3 Portal — direct Python launcher (no Docker required)
cd "$(dirname "$0")"

echo "============================================"
echo "  NODE-3 ARBITRAGE PORTAL — Direct Launch"
echo "============================================"
echo ""

# Install / upgrade dependencies quietly
echo "Checking dependencies..."
pip3 install --quiet flask flask-cors requests pytz 2>&1 | tail -3
echo ""

# Kill any existing instance on 8585
lsof -ti:8585 | xargs kill -9 2>/dev/null && echo "Stopped old instance on :8585" || true
sleep 1

echo "Starting portal on http://localhost:8585 ..."
echo "(Close this window to stop the server)"
echo ""
python3 server.py --port 8585
