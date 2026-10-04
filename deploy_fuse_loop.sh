#!/bin/bash
# deploy_fuse_loop.sh — copy fox_modbus_loop.py to Pi and test it
set -e
PI="pi@192.168.1.157"
REMOTE="/home/pi/node3"
MAC_REPO="${MAC_REPO:-/Users/mattbrander/Documents/Claude/Projects/Dovecote Node3}"

echo "=== Copying fox_modbus_loop.py to Pi ==="
scp "$MAC_REPO/fox_modbus_loop.py" "$PI:$REMOTE/fox_modbus_loop.py"

echo ""
echo "=== Dry run (read-only, no writes to inverter) ==="
ssh "$PI" "cd $REMOTE && python3 fox_modbus_loop.py --once --dry-run"

echo ""
echo "=== Deploy complete ==="
echo ""
echo "To run the daemon in background on Pi:"
echo "  ssh $PI 'cd $REMOTE && nohup python3 fox_modbus_loop.py > /tmp/fuse_loop.log 2>&1 &'"
echo ""
echo "To run a single live shot (WRITES to inverter):"
echo "  ssh $PI 'cd $REMOTE && python3 fox_modbus_loop.py --once'"
echo ""
echo "To check recent fuse loop log:"
echo "  ssh $PI 'python3 $REMOTE/fox_modbus_loop.py --status'"
echo ""
echo "To add to docker-compose (docker-compose.pi.yml) so it starts with the container,"
echo "see the integration note in fox_modbus_loop.py header."
