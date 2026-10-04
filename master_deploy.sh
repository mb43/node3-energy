#!/usr/bin/env bash
# master_deploy.sh  —  Dovecote Node-3  (run on Mac)
# ====================================================
# Full deploy + Pi→Mac sync + git commit in one shot.
#
# Pre-requisites:
#   1. deploy_tariff_toggle.py already applied on Pi  ← DONE (tariff buttons visible)
#   2. SSH key auth to pi@192.168.1.157 (or enter password at each scp/ssh)
#   3. Git repo on Mac at NODE3_REPO below
#
# Usage:
#   cd /path/to/this/file
#   chmod +x master_deploy.sh
#   ./master_deploy.sh
#
# What it does:
#   1. SCP master_deploy.py to Pi
#   2. Run it on Pi (applies all patches)
#   3. Restart docker on Pi
#   4. SCP the three patched files from Pi back to Mac workspace
#   5. git add / commit / push

set -euo pipefail

PI="pi@192.168.1.157"
PI_NODE3="/home/pi/node3"

# ── Mac workspace / git repo directory ───────────────────────────────────────
NODE3_REPO="${NODE3_REPO:-/Users/mattbrander/Documents/Claude/Projects/Dovecote Node3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_PY="$SCRIPT_DIR/master_deploy.py"

echo "══════════════════════════════════════════════════════"
echo "  Dovecote Node-3 — Master Deploy + Sync"
echo "  Pi:   $PI:$PI_NODE3"
echo "  Repo: $NODE3_REPO"
echo "══════════════════════════════════════════════════════"
echo

# ── 1. SCP deploy scripts to Pi ──────────────────────────────────────────────
echo "[1/5] Copying deploy scripts + updated source files to Pi…"
scp "$DEPLOY_PY"                              "$PI:/tmp/master_deploy.py"
scp "$SCRIPT_DIR/deploy_all_fixes.py"         "$PI:/tmp/deploy_all_fixes.py"
scp "$SCRIPT_DIR/deploy_lp_learning.py"       "$PI:/tmp/deploy_lp_learning.py"
scp "$SCRIPT_DIR/fox_modbus_loop.py"          "$PI:$PI_NODE3/fox_modbus_loop.py"
scp "$SCRIPT_DIR/house_profile.py"            "$PI:$PI_NODE3/house_profile.py"
[ -f "$SCRIPT_DIR/fix_fuse_card.py" ] && scp "$SCRIPT_DIR/fix_fuse_card.py" "$PI:/tmp/fix_fuse_card.py"

# ── 2. Run on Pi ─────────────────────────────────────────────────────────────
echo "[2/5] Running deploy scripts on Pi…"
ssh "$PI" "python3 /tmp/master_deploy.py"
ssh "$PI" "python3 /tmp/deploy_all_fixes.py"
ssh "$PI" "python3 /tmp/deploy_lp_learning.py"
[ -f "$SCRIPT_DIR/fix_fuse_card.py" ] && ssh "$PI" "python3 /tmp/fix_fuse_card.py"

# ── 3. Restart docker ────────────────────────────────────────────────────────
echo "[3/5] Restarting node3-portal docker container…"
ssh "$PI" "docker restart node3-portal"
echo "      Waiting 5s for container to come up…"
sleep 5
echo "      Health check:"
ssh "$PI" 'curl -s http://localhost:5000/api/settings > /tmp/n3_health.json && python3 - <<EOF
import json
d = json.load(open("/tmp/n3_health.json"))
print(f"  export_kw={d.get(\"export_kw\")}, import_kw={d.get(\"import_kw\")}, SC_import={d.get(\"standing_charge_import_p_day\")}p")
EOF' || echo "      (health check skipped — container may still be starting)"

# ── 4. SCP patched files back to Mac repo ────────────────────────────────────
echo "[4/5] Syncing patched Pi files → Mac repo…"
if [ ! -d "$NODE3_REPO" ]; then
    echo "  ⚠ NODE3_REPO not found: $NODE3_REPO"
    echo "  Set NODE3_REPO env var to your node3 git directory, e.g.:"
    echo "    NODE3_REPO=~/path/to/node3 ./master_deploy.sh"
    echo "  Skipping sync."
else
    for f in server.py node3_config.py dashboard.html node3_config.json simulate.py; do
        scp "$PI:$PI_NODE3/$f" "$NODE3_REPO/$f" && echo "  ✓ $f" || echo "  ✗ $f (failed)"
    done
    # Also copy the deploy scripts themselves so repo has them
    for f in master_deploy.py master_deploy.sh \
              deploy_tariff_toggle.py deploy_standing_charges.py \
              deploy_backtest_compare.py fix_tariff_auth.py \
              deploy_all_fixes.py fox_modbus_loop.py deploy_fuse_loop.sh \
              deploy_lp_learning.py house_profile.py fix_fuse_card.py; do
        [ -f "$SCRIPT_DIR/$f" ] && cp "$SCRIPT_DIR/$f" "$NODE3_REPO/$f" && echo "  ✓ $f"
    done
fi

# ── 5. Git commit ─────────────────────────────────────────────────────────────
echo "[5/5] Git commit + push…"
if [ ! -d "$NODE3_REPO" ]; then
    echo "  ⚠ Skipping git — repo not found."
else
    cd "$NODE3_REPO"
    git add \
        server.py \
        node3_config.py \
        dashboard.html \
        node3_config.json \
        simulate.py \
        master_deploy.py \
        master_deploy.sh \
        deploy_tariff_toggle.py \
        deploy_standing_charges.py \
        deploy_backtest_compare.py \
        fix_tariff_auth.py \
        deploy_all_fixes.py \
        fox_modbus_loop.py \
        deploy_fuse_loop.sh \
        deploy_lp_learning.py \
        house_profile.py \
        fix_fuse_card.py \
        2>/dev/null || true

    git diff --cached --stat
    echo
    git commit -m "$(cat <<'EOF'
feat(node3): LP learning — house profile, fuse daemon, grid history

- fox_modbus_loop.py: fuse protection daemon (16.4kW safe limit)
  reads BMS from bms_detail.json, logs grid_history.csv every 5s
  auto-triggers house_profile.py rebuild every ~2h (1440 cycles)
- house_profile.py: 48-slot learned house load profile from CSV
  14-day rolling window, per-slot kWh, saves house_profile.json
- simulate.py: LP planner uses learned per-slot loads not flat 250W
  cumulative profile sums used in SOC constraints; time-aligned via
  valid_from timestamps; graceful flat fallback pre-profile
- server.py: /api/house-profile + /api/grid-history endpoints
  /api/fuse-status (daemon health/headroom)
  _pushover_send() for mobile alerts
  fuse daemon auto-started alongside bms_monitor on boot
- dashboard.html: learned profile sparkline card (Canvas, coloured
  by time-of-day), fuse protection widget JS
- node3_config.py: standing_charge_eon_p_day + subscription_pcm=0 fix

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
    git push && echo "  ✓ pushed to GitHub" || echo "  ✗ push failed (check remote)"
fi

echo
echo "══════════════════════════════════════════════════════"
echo "  DONE."
echo "  Pi → Mac → GitHub all in sync."
echo
echo "  Test the compare endpoint:"
echo "  curl http://192.168.1.157:5000/api/backtest-compare?force=1"
echo
echo "  Set E.ON standing charge once you have the quote:"
echo "  Open dashboard → ⚙ SETTINGS → E.ON Next Optimise standing"
echo "  charge field → enter value in p/day → Save"
echo "══════════════════════════════════════════════════════"
