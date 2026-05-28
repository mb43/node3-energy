#!/bin/bash
cd "$(dirname "$0")"

echo "=== Clearing stale git locks ==="
rm -f .git/HEAD.lock .git/index.lock 2>/dev/null && echo "Locks cleared" || echo "No locks found"

echo ""
echo "=== Committing: asymmetric rates (charge 5.25kWh, G98 export 3.68, G99 export 5.75) ==="
git add simulate.py server.py dashboard.html
git commit -m "fix asymmetric rates: charge 5.25kWh/slot, export 3.68 G98 / 5.75 G99

FoxESS KH10.5 charges at inverter max (10.5kW = 5.25kWh/slot).
G98 caps EXPORT at 3.68kWh/slot — charging was always unrestricted.
G99 raises export to 5.75kWh/slot; charge rate unchanged.

- simulate.py: CHARGE_RATE_KW=INVERTER_KW; CHARGE_KWH=5.25
  plan_optimal_dispatch LP uses charge_per_slot=CHARGE_KWH (5.25)
- server.py: CHARGE_KWH=5.25 in /api/plan and /api/backtest-lp
  /api/plan returns annual_g98, annual_g99, annual_delta
  /api/backtest-lp runs G99 LP and returns lp_g99_total_gbp
- dashboard.html: CFG.CHARGE_KWH=5.25; G98/G99 annual projection
  panel in LIVE tab schedule; LP backtest 3-way comparison section"

echo ""
echo "=== Pushing to GitHub ==="
git push origin main

echo ""
echo "=== Deleting stale backtest caches (forces recalculation) ==="
rm -f backtest_cache.json && echo "Greedy cache cleared"
rm -f backtest_lp_cache.json && echo "LP cache cleared"

echo ""
echo "=== Restarting Docker ==="
docker compose restart

echo ""
echo "=== Waiting 10s for container to boot ==="
sleep 10

echo ""
echo "=== Checking plan endpoint (G98 + G99 annual projections) ==="
curl -s "http://localhost:8585/api/plan" | python3 -c "
import json,sys
d=json.load(sys.stdin)
s=d.get('summary',{})
slots=d.get('slots',[])
print(f'Plan slots: {len(slots)}')
print(f'G98 net (window): £{s.get(\"net_g98\",0):.4f}')
print(f'G99 net (window): £{s.get(\"net_g99\",0):.4f}')
print(f'G98 annual (LP extrapolated): ~£{s.get(\"annual_g98\",0):.2f}/yr')
print(f'G99 annual (LP extrapolated): ~£{s.get(\"annual_g99\",0):.2f}/yr')
print(f'G99 uplift vs G98:            +£{s.get(\"annual_delta\",0):.2f}/yr')
" && echo "" || echo "Plan check failed — check docker logs"

echo ""
echo "=== DONE ==="
echo ""
echo "Portal now shows both G98 and G99 LP annual projections in the LIVE tab."
echo "Historical tab: click 'LOAD LP BACKTEST (G98 + G99 vs GREEDY)' for 12-month comparison."
echo ""
echo "Expected annual ranges (today's spread):"
echo "  G98 LP:  ~£1,572-1,627/yr  (asymmetric: charge 5.25, export 3.68)"
echo "  G99 LP:  ~£1,927-1,990/yr  (asymmetric: charge 5.25, export 5.75)"
echo "  Uplift:  ~+£355-418/yr from G99 approval"
read -p "Press Enter to close..."
