#!/bin/bash
cd "$(dirname "$0")"

echo "=== Clearing stale git locks ==="
rm -f .git/HEAD.lock .git/index.lock 2>/dev/null && echo "Locks cleared" || echo "No locks found"

echo ""
echo "=== Pushing Phase 2 price cap fix (prevent expensive reserve refill) ==="

echo ""
echo "=== Pushing to GitHub ==="
git push origin main

echo ""
echo "=== Restarting Docker ==="
docker compose down && docker compose up -d

echo ""
echo "=== Waiting 8s ==="
sleep 8

echo ""
echo "=== /api/plan summary ==="
curl -s http://localhost:8585/api/plan | python3 -c "
import json,sys
d=json.load(sys.stdin)
s=d['summary']
slots=d['slots']
print('charge_slots:     ', s['charge_slots'])
print('export_slots:     ', s['export_slots'])
print('net_g98:          £' + str(round(s['net_g98'],4)))
print('arbitrage_net_g98:£' + str(round(s.get('arbitrage_net_g98',0),4)))
print('hosting_cost:     £' + str(round(s.get('hosting_cost',0),4)))
print('house_load_kwh:   ' + str(round(s.get('house_load_kwh',0),3)) + ' kWh')
socvals=[x['planSoc'] for x in slots]
print('SOC range:        ' + str(min(socvals)) + ' → ' + str(max(socvals)) + ' kWh')
print('Final SOC:        ' + str(slots[-1]['planSoc']) + ' kWh')
print()
print('SANITY: arbitrage_net <= net_g98?', round(s.get('arbitrage_net_g98',0),4), '<=', round(s['net_g98'],4), '->', s.get('arbitrage_net_g98',0) <= s['net_g98'])
"

echo ""
echo "=== fleet_state ==="
cat fleet_state.json

echo ""
echo "=== DONE ==="
read -p "Press Enter to close..."
