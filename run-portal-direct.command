#!/bin/bash
# NODE-3 Portal — direct Python launcher (no Docker required)
cd "$(dirname "$0")"

echo "============================================"
echo "  NODE-3 ARBITRAGE PORTAL — Direct Launch"
echo "============================================"
echo ""

# Install / upgrade dependencies quietly
# IMPORTANT: installs from requirements.txt (not a hand-picked list) so the LP
# optimiser's scipy/numpy deps are never silently missing again. A previous
# version of this script only installed flask/flask-cors/requests/pytz, which
# meant plan_optimal_dispatch()'s `from scipy.optimize import linprog` failed
# on every run, silently fell back to the crude greedy heuristic, and the
# dashboard never showed any indication that LP-optimal dispatch wasn't
# actually running. Confirmed 19 Aug 2026 as the root cause of a persistent
# negative 24hr arbitrage figure caused by the fallback's mis-calibrated
# breakeven threshold buying power the (already full) battery couldn't use.
echo "Checking dependencies (from requirements.txt — includes scipy for LP dispatch)..."
pip3 install --quiet -r requirements.txt 2>&1 | tail -5
echo ""

# Kill any existing instance on 8585
lsof -ti:8585 | xargs kill -9 2>/dev/null && echo "Stopped old instance on :8585" || true
sleep 1

echo "Starting portal on http://localhost:8585 ..."
echo "(Close this window to stop the server)"
echo ""
python3 server.py --port 8585
