#!/usr/bin/env python3
"""
Comprehensive audit fixes for Node3 dashboard.
Applies 5 confirmed bugs found during the full audit.
Run on Pi: python3 audit_fixes.py
"""
import re, os

BASE = '/home/pi/node3'
DASH = os.path.join(BASE, 'dashboard.html')
SRV  = os.path.join(BASE, 'server.py')

def patch(path, old, new, label, count=1):
    with open(path) as f:
        src = f.read()
    if old not in src:
        print(f'✗ NOT FOUND: {label}')
        return False
    occurrences = src.count(old)
    if count == 1 and occurrences > 1:
        print(f'✗ AMBIGUOUS ({occurrences} matches): {label}')
        return False
    replaced = src.replace(old, new, count)
    with open(path, 'w') as f:
        f.write(replaced)
    print(f'✓ {label}')
    return True

# ─────────────────────────────────────────────
# FIX 1: Calibration stuck at 4.2 days
# Raise max_rows from 200 to 10000 so full history loads
# ─────────────────────────────────────────────
patch(SRV,
    'def load_history(max_rows=200):',
    'def load_history(max_rows=10000):',
    'FIX 1: Raise load_history max_rows from 200 to 10000')

# ─────────────────────────────────────────────
# FIX 2: Add 'days' field to backtest response
# Currently 'd.days' is always undefined in JS, so annualisation falls back to 365
# but backtest covers ~372 days (12 × 31). Add the actual day count to the response.
# ─────────────────────────────────────────────
patch(SRV,
    "    return {\n        'total':                round(net, 4),\n        'monthly':              monthly,\n        'totalSlots':           n,",
    "    return {\n        'total':                round(net, 4),\n        'monthly':              monthly,\n        'totalSlots':           n,\n        'days':                 round(n / 48, 1),",
    'FIX 2: Add days field to backtest return dict')

# ─────────────────────────────────────────────
# FIX 3: CRITICAL — stop force-running LP backtest every 30 minutes
# The FOUNDER HQ IIFE schedules loadHistoricalData(true) at every slot boundary.
# force=true bypasses the 24h cache and runs a full LP optimisation (minutes of CPU).
# This means 48 full backtests per day instead of 1. Change to force=false.
# ─────────────────────────────────────────────
old3 = """  setTimeout(() => {
    loadHistoricalData(true);   // force=true: re-run backtest with new history data
    setInterval(() => {
      console.log('[NODE-3] Slot boundary — refreshing historical data (force)…');
      loadHistoricalData(true); // force=true every slot boundary so cached result is never stale
    }, 1800000); // every 30 minutes thereafter
  }, slotDelay);"""

new3 = """  setTimeout(() => {
    loadHistoricalData(false);  // slot boundary: refresh history display only; backtest uses 24h cache
    setInterval(() => {
      console.log('[NODE-3] Slot boundary — refreshing live history display…');
      loadHistoricalData(false); // 24h cache serves fresh backtest; no need to force every 30min
    }, 1800000); // every 30 minutes thereafter
  }, slotDelay);"""

patch(DASH, old3, new3, 'FIX 3: Stop force-running LP backtest 48x/day at slot boundaries')

# ─────────────────────────────────────────────
# FIX 4: Use actual backtest days for daily average on LIVE tab
# Was dividing 372-day backtest total by hardcoded 365 → 1.9% overstatement
# ─────────────────────────────────────────────
patch(DASH,
    '  const backtestDailyAvg = histResultsCache ? (histResultsCache.total / 365) : null;',
    '  const backtestDailyAvg = histResultsCache ? (histResultsCache.total / (histResultsCache.days || 365)) : null;',
    'FIX 4: Use actual backtest days for LIVE tab daily average')

# ─────────────────────────────────────────────
# FIX 5: Use actual backtest days in calibration backtestDaily calculation
# Same issue — was dividing total by hardcoded 365
# ─────────────────────────────────────────────
patch(DASH,
    '  const backtestDaily  = histResultsCache ? (histResultsCache.total / 365) : null;',
    '  const backtestDaily  = histResultsCache ? (histResultsCache.total / (histResultsCache.days || 365)) : null;',
    'FIX 5: Use actual backtest days in calibration backtestDaily')

# Also fix FOUNDER HQ annualisation to use d.days when available
old_fhq = """      var days = d.days || 365;
        var exportYr = Math.round((d.totalExportIncome  || 0) / days * 365);
        var chargeYr = Math.round((d.totalChargeCost    || 0) / days * 365);
        var arbYr    = Math.round((d.total              || 0) / days * 365);
        var scYr     = Math.round((d.totalHomeEnergySaved || 0) / days * 365);"""

new_fhq = """      var days = d.days || (d.totalSlots ? d.totalSlots / 48 : 365);
        var exportYr = Math.round((d.totalExportIncome  || 0) / days * 365);
        var chargeYr = Math.round((d.totalChargeCost    || 0) / days * 365);
        var arbYr    = Math.round((d.total              || 0) / days * 365);
        var scYr     = Math.round((d.totalHomeEnergySaved || 0) / days * 365);"""

patch(DASH, old_fhq, new_fhq, 'FIX 6: FOUNDER HQ annualisation uses actual backtest days')

print('\nAll fixes applied. On Pi: docker compose restart node3 (or docker restart node3)')
print('Backtest caches should be cleared to reflect server.py changes:')
print('  rm -f /home/pi/node3/backtest_cache*.json')
