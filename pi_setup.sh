#!/usr/bin/env bash
# pi_setup.sh — NODE-3 first-time Pi deployment
# Run this on the Pi once Docker is installed.
# Safe to re-run (git pull + rebuild if already cloned).
set -e

REPO="https://github.com/mb43/node3-energy"
DIR="$HOME/node3"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.pi.yml"

echo "═══════════════════════════════════════════════════"
echo "  NODE-3 Pi Setup"
echo "═══════════════════════════════════════════════════"
echo "  Pi IP: $(hostname -I | awk '{print $1}')"
echo "  Hostname: $(hostname)"
echo ""

# ── Install Python test deps (not in Docker — for hardware_test.py) ──────────
echo "→ Installing Python test dependencies..."
pip3 install paho-mqtt pymodbus pyserial --break-system-packages --quiet 2>/dev/null || true

# ── Clone or update ──────────────────────────────────────────────────────────
if [ -d "$DIR/.git" ]; then
    echo "→ Existing repo found at $DIR — pulling latest..."
    cd "$DIR"
    git pull origin main
else
    echo "→ Cloning $REPO into $DIR..."
    git clone "$REPO" "$DIR"
    cd "$DIR"
fi

# ── Ensure data files exist before Docker tries to mount them ────────────────
# Docker will create directories instead of files if these don't exist
touch fleet_state.json history.csv hardware_log.json
[ -s fleet_state.json ] || echo '{"soc_kwh":36.0,"battery_kwh":72.0}' > fleet_state.json
[ -s hardware_log.json ] || echo '[]' > hardware_log.json

# ── Show USB devices so user can confirm assignments ─────────────────────────
echo ""
echo "→ USB serial devices currently detected:"
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "   (none — plug in adapters first)"
echo ""

# ── Build and start ───────────────────────────────────────────────────────────
echo "→ Building Docker images (this takes a few minutes first time)..."
$COMPOSE build --no-cache

echo "→ Starting containers..."
$COMPOSE up -d

echo "→ Waiting 10s for startup..."
sleep 10

echo ""
echo "→ Container status:"
docker ps --format "  {{.Names}}\t{{.Status}}"

echo ""
echo "→ Last 20 log lines (node3-portal):"
docker logs node3-portal --tail 20

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Done. Portal should be at:"
echo "    http://$(hostname -I | awk '{print $1}'):8585"
echo "    http://$(hostname).local:8585"
echo ""
echo "  Next steps:"
echo "    1. Run LV hardware tests:  python3 hardware_test.py"
echo "    2. Confirm T-2CAN MQTT:    python3 hardware_test.py --mqtt"
echo "    3. Confirm RS485:          python3 hardware_test.py --modbus"
echo "═══════════════════════════════════════════════════"
