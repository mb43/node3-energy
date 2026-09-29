#!/usr/bin/env python3
"""
Node-3 comprehensive audit fixes — deploy directly to Pi.
Run as: python3 deploy_to_pi.py
All changes from the 29 Sep 2026 audit session.
"""
import os, json

BASE = '/home/pi/node3'
SRV  = os.path.join(BASE, 'server.py')
DASH = os.path.join(BASE, 'dashboard.html')
CFGPY= os.path.join(BASE, 'node3_config.py')
CFGJ = os.path.join(BASE, 'node3_config.json')

errors = []

def patch(path, old, new, label, count=1):
    with open(path) as f:
        src = f.read()
    if old not in src:
        errors.append(f'✗ NOT FOUND: {label}')
        return False
    occ = src.count(old)
    if count == 1 and occ > 1:
        errors.append(f'✗ AMBIGUOUS ({occ}×): {label}')
        return False
    with open(path, 'w') as f:
        f.write(src.replace(old, new, count))
    print(f'✓ {label}')
    return True

print('=== Node-3 Audit Fixes — 29 Sep 2026 ===\n')

# ══════════════════════════════════════════════════════════════
# SESSION 1 FIXES (may already be applied — idempotent)
# ══════════════════════════════════════════════════════════════

# F1: Raise load_history max_rows
patch(SRV, 'def load_history(max_rows=200):', 'def load_history(max_rows=10000):', 'F1: Raise load_history 200→10000')

# F2: Add days to backtest return dict
patch(SRV,
    "    return {\n        'total':                round(net, 4),\n        'monthly':              monthly,\n        'totalSlots':           n,",
    "    return {\n        'total':                round(net, 4),\n        'monthly':              monthly,\n        'totalSlots':           n,\n        'days':                 round(n / 48, 1),",
    'F2: Add days field to backtest response')

# F3: Stop force-running LP backtest every 30 min
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
patch(DASH, old3, new3, 'F3: Stop force-running LP backtest 48x/day')

# F4: LIVE tab daily avg uses actual backtest days
patch(DASH,
    '  const backtestDailyAvg = histResultsCache ? (histResultsCache.total / 365) : null;',
    '  const backtestDailyAvg = histResultsCache ? (histResultsCache.total / (histResultsCache.days || 365)) : null;',
    'F4: LIVE tab daily avg uses actual backtest days')

# F5: Calibration uses actual backtest days
patch(DASH,
    '  const backtestDaily  = histResultsCache ? (histResultsCache.total / 365) : null;',
    '  const backtestDaily  = histResultsCache ? (histResultsCache.total / (histResultsCache.days || 365)) : null;',
    'F5: Calibration uses actual backtest days')

# F6: FOUNDER HQ uses actual days for annualisation
patch(DASH,
    '      var days = d.days || 365;',
    '      var days = d.days || (d.totalSlots ? d.totalSlots / 48 : 365);',
    'F6: FOUNDER HQ annualisation uses actual backtest days')

# ══════════════════════════════════════════════════════════════
# SESSION 2 FIXES
# ══════════════════════════════════════════════════════════════

print()

# node3_config.py: add new keys to DEFAULTS
patch(CFGPY,
    '    "house_kwh_day": 12.0,  # profiled household consumption per day (Elexon PC1 shape)\n}',
    '    "house_kwh_day": 12.0,  # profiled household consumption per day (Elexon PC1 shape)\n'
    '    "svt_ref_p":     25.0,  # Ofgem SVT reference (p/kWh)\n'
    '    "subscription_pcm": 29.0,  # monthly subscription per consumer site (£)\n'
    '}',
    'node3_config.py: add svt_ref_p + subscription_pcm to DEFAULTS')

# node3_config.py: fix save_config NON_NEGATIVE (remove duplicate if present)
with open(CFGPY) as f:
    cfgpy_src = f.read()
if cfgpy_src.count('NON_NEGATIVE') > 1:
    old_dup = ('    NON_NEGATIVE = {"baseload_kw", "house_kwh_day"}\n'
               '    cfg = load_config()\n'
               '    NON_NEGATIVE = {"baseload_kw", "baseload_kw_consumer", "house_kwh_day", "svt_ref_p", "subscription_pcm"}')
    new_dup = ('    NON_NEGATIVE = {"baseload_kw", "baseload_kw_consumer", "house_kwh_day", "svt_ref_p", "subscription_pcm"}\n'
               '    cfg = load_config()')
    if old_dup in cfgpy_src:
        with open(CFGPY, 'w') as f:
            f.write(cfgpy_src.replace(old_dup, new_dup, 1))
        print('✓ node3_config.py: dedup NON_NEGATIVE')
    else:
        print('  node3_config.py: NON_NEGATIVE dedup not needed (already clean)')
else:
    # Single occurrence — add the new keys
    patch(CFGPY,
        '    NON_NEGATIVE = {"baseload_kw", "house_kwh_day"}',
        '    NON_NEGATIVE = {"baseload_kw", "baseload_kw_consumer", "house_kwh_day", "svt_ref_p", "subscription_pcm"}',
        'node3_config.py: expand NON_NEGATIVE in save_config')

# node3_config.py: allow new keys in /api/settings POST
patch(SRV,
    '    for key in ("battery_kwh", "import_kw", "export_kw", "min_soc_pct",\n'
    '                "baseload_kw", "house_kwh_day"):\n'
    '        if key in body:',
    '    for key in ("battery_kwh", "import_kw", "export_kw", "min_soc_pct",\n'
    '                "baseload_kw", "house_kwh_day", "svt_ref_p", "subscription_pcm"):\n'
    '        if key in body:',
    'server.py: api/settings accepts svt_ref_p + subscription_pcm')

# node3_config.json: add new fields if missing
try:
    with open(CFGJ) as f:
        cfgj = json.load(f)
    changed = False
    for k, v in [('svt_ref_p', 25.0), ('subscription_pcm', 29.0)]:
        if k not in cfgj:
            cfgj[k] = v
            changed = True
    if changed:
        with open(CFGJ, 'w') as f:
            json.dump(cfgj, f, indent=2)
        print('✓ node3_config.json: added svt_ref_p + subscription_pcm')
    else:
        print('  node3_config.json: already has new fields')
except Exception as e:
    errors.append(f'✗ node3_config.json update failed: {e}')

# server.py: include miner baseload in spot-basis home_val (issue 3)
patch(SRV,
    '        home_val            = home_load * max(0.0, _BT_SVT_REF_P - price) / 100.0',
    '        home_val            = (home_load + _bt_baseload_slot) * max(0.0, _BT_SVT_REF_P - price) / 100.0',
    'server.py: include miner baseload in spot-basis home_val')

# server.py: add true + contractual self-con calc after loop (issue 6)
patch(SRV,
    '        total_home_saved       += home_val\n\n    # ── Post-process monthly averages ────────────────────────',
    '        total_home_saved       += home_val\n\n'
    '    # ── True self-con: actual avg charge cost / RTE vs SVT ───────────────────\n'
    '    if total_charge_kwh > 0:\n'
    '        _avg_charge_p = total_charge_cost / total_charge_kwh * 100.0\n'
    '        _eff_cost_p   = _avg_charge_p / _BT_RTE\n'
    '    else:\n'
    '        _eff_cost_p   = _BT_SVT_REF_P * 0.40\n'
    '    _all_load_kwh             = _bt_total_load_day * (n / 48)\n'
    '    total_home_saved_true     = max(0.0, _BT_SVT_REF_P - _eff_cost_p) * _all_load_kwh / 100.0\n'
    '    total_home_saved_contract = _BT_SVT_REF_P * _all_load_kwh / 100.0\n'
    '    avg_charge_p_out = round(total_charge_cost / total_charge_kwh * 100.0, 2) if total_charge_kwh > 0 else 0.0\n\n'
    '    # ── Post-process monthly averages ────────────────────────',
    'server.py: add true+contractual self-con after loop')

# server.py: add new fields to return dict
patch(SRV,
    "        'totalHomeEnergySaved': round(total_home_saved, 4),",
    "        'totalHomeEnergySaved':         round(total_home_saved, 4),\n"
    "        'totalHomeEnergySavedTrue':     round(total_home_saved_true, 4),\n"
    "        'totalHomeEnergySavedContract': round(total_home_saved_contract, 4),\n"
    "        'avgChargeP':                   avg_charge_p_out,",
    'server.py: add True/Contract/avgChargeP to return dict')

# dashboard.html: LIVE tab uses founder backtest when baseload_kw > 0 (issue 8)
patch(DASH,
    "    const url = '/api/backtest' + (force ? '?force=1' : '');",
    "    const _founderMode = (cfg.baseload_kw || 0) > 0;\n"
    "    const _btBase = '/api/backtest' + (_founderMode ? '?mode=founder' : '');\n"
    "    const url = _btBase + (force ? (_founderMode ? '&force=1' : '?force=1') : '');",
    'dashboard.html: LIVE tab uses founder backtest when baseload_kw > 0')

# dashboard.html: G98 tab — three-value self-con range (issue 6)
old_g98 = """  if (histResultsCache && monthEl) {
    const { monthly, total, totalHomeEnergySaved = 0 } = histResultsCache;
    const months = Object.keys(monthly).sort();
    const profits = months.map(m => monthly[m].profit);
    const best = Math.max(...profits);
    const worst = Math.min(...profits);
    const avg = profits.reduce((s,v) => s+v, 0) / profits.length;
    monthEl.innerHTML = `
      <div class="scenario-metric"><span class="sm-lbl">Annual grid P&L (arb)</span><span class="sm-val" style="color:var(--green)">£${total.toFixed(2)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Home energy saving</span><span class="sm-val" style="color:var(--cyan)">£${totalHomeEnergySaved.toFixed(2)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Total annual value</span><span class="sm-val" style="color:var(--green);font-weight:bold">£${(total + totalHomeEnergySaved).toFixed(2)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Best month</span><span class="sm-val" style="color:var(--green)">£${best.toFixed(2)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Worst month</span><span class="sm-val" style="color:var(--amber)">£${worst.toFixed(2)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Monthly avg (net)</span><span class="sm-val">£${avg.toFixed(2)}</span></div>
    `;"""

new_g98 = """  if (histResultsCache && monthEl) {
    const { monthly, total,
      totalHomeEnergySaved = 0,
      totalHomeEnergySavedTrue = 0,
      totalHomeEnergySavedContract = 0,
      avgChargeP = 0
    } = histResultsCache;
    const months = Object.keys(monthly).sort();
    const profits = months.map(m => monthly[m].profit);
    const best = Math.max(...profits);
    const worst = Math.min(...profits);
    const avg = profits.reduce((s,v) => s+v, 0) / profits.length;
    const scBest = totalHomeEnergySavedTrue > 0 ? totalHomeEnergySavedTrue : totalHomeEnergySaved;
    monthEl.innerHTML = `
      <div class="scenario-metric"><span class="sm-lbl">Annual grid P&L (arb)</span><span class="sm-val" style="color:var(--green)">£${total.toFixed(0)}</span></div>
      <div class="scenario-metric" title="Conservative: counts only slots where Agile < SVT. Underestimates — ignores battery storage of cheap off-peak energy."><span class="sm-lbl">Self-con (min · spot basis)</span><span class="sm-val" style="color:var(--amber)">£${totalHomeEnergySaved.toFixed(0)}</span></div>
      <div class="scenario-metric" title="Best estimate: avg charge cost ${avgChargeP.toFixed(1)}p/kWh paid ÷ 0.88 RTE vs 25p SVT. Most accurate."><span class="sm-lbl">Self-con (est. actual) ← use</span><span class="sm-val" style="color:var(--green);font-weight:bold">£${(totalHomeEnergySavedTrue||totalHomeEnergySaved).toFixed(0)}</span></div>
      <div class="scenario-metric" title="Maximum: 100% load × 25p SVT, ignoring battery charge cost. Your contractual promise ceiling."><span class="sm-lbl">Self-con (max · contractual)</span><span class="sm-val" style="color:var(--cyan)">£${(totalHomeEnergySavedContract||totalHomeEnergySaved).toFixed(0)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Total value (arb + actual)</span><span class="sm-val" style="color:var(--green);font-weight:bold">£${(total + scBest).toFixed(0)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Best month P&L</span><span class="sm-val" style="color:var(--green)">£${best.toFixed(2)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Worst month P&L</span><span class="sm-val" style="color:var(--amber)">£${worst.toFixed(2)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Monthly avg P&L</span><span class="sm-val">£${avg.toFixed(2)}</span></div>
    \`;"""
patch(DASH, old_g98, new_g98, 'dashboard.html: G98 tab three-value self-con range')

# dashboard.html: HIST tab sub + SVT from config (issue 9)
patch(DASH,
    '  const HIST_SUB_PCM = 29;  // £29/mo subscription — Dovecote income, not consumer saving',
    '  const HIST_SUB_PCM = cfg.subscription_pcm || 29;',
    'dashboard.html: HIST tab sub from cfg')

patch(DASH,
    '  const _gKwhDayScale = cfg.house_kwh_day || 12;\n'
    '  const scaleHomeSaved = Object.keys(monthly).reduce((s, m) => {\n'
    '    const [y, mn] = m.split(\'-\');\n'
    '    return s + _gKwhDayScale * 0.25 * new Date(+y, +mn, 0).getDate();\n'
    '  }, 0);',
    '  const _gKwhDayScale = cfg.house_kwh_day || 12;\n'
    '  const _svtRef = (cfg.svt_ref_p || 25) / 100;\n'
    '  const scaleHomeSaved = Object.keys(monthly).reduce((s, m) => {\n'
    '    const [y, mn] = m.split(\'-\');\n'
    '    return s + _gKwhDayScale * _svtRef * new Date(+y, +mn, 0).getDate();\n'
    '  }, 0);',
    'dashboard.html: HIST tab SVT ref from cfg')

patch(DASH,
    '    return _gKwhDay * 0.25 * new Date(+y, +mn, 0).getDate();\n  });\n  const HIST_SUB_PCM',
    '    return _gKwhDay * _svtRef * new Date(+y, +mn, 0).getDate();\n  });\n  const HIST_SUB_PCM',
    'dashboard.html: HIST per-month array uses _svtRef')

# dashboard.html: revenue breakdown from cfg (issue 9)
patch(DASH,
    '  const DOVECOTE_SUB_PCM = 29;          // £29/month subscription per home',
    '  const DOVECOTE_SUB_PCM = cfg.subscription_pcm || 29;',
    'dashboard.html: revenue sub from cfg')

patch(DASH,
    '  const SVT_PPU    = 0.25;          // 25p/kWh SVT reference rate\n'
    '  const SUB_PCM    = 29;            // £29/month subscription',
    '  const SVT_PPU    = (cfg.svt_ref_p || 25) / 100;\n'
    '  const SUB_PCM    = cfg.subscription_pcm || 29;',
    'dashboard.html: revenue breakdown SVT + sub from cfg')

# dashboard.html: fix self-consumption label (issue 12)
patch(DASH,
    "    if (homeSub) homeSub.textContent = '12kWh/day vs 25p SVT · £' + avgHomeSaved.toFixed(2) + '/mo avg';",
    "    if (homeSub) homeSub.textContent = '12kWh/day × SVT ref · contractual guarantee · £' + avgHomeSaved.toFixed(2) + '/mo avg';",
    'dashboard.html: fix self-con label')

# dashboard.html: FOUNDER HQ uses totalHomeEnergySavedTrue for self-con
patch(DASH,
    '      var scYr     = Math.round((d.totalHomeEnergySaved || 0) / days * 365);',
    '      var scYr     = Math.round(((d.totalHomeEnergySavedTrue || d.totalHomeEnergySaved) || 0) / days * 365);',
    'dashboard.html: FOUNDER HQ uses True self-con')

# ══════════════════════════════════════════════════════════════
# CLEAR CACHES — force fresh backtest with all new fields
# ══════════════════════════════════════════════════════════════
print()
for cf in ['backtest_cache.json', 'backtest_cache_founder.json']:
    p = os.path.join(BASE, cf)
    if os.path.exists(p):
        os.remove(p)
        print(f'✓ Cleared {cf}')

print()
if errors:
    print('ERRORS:')
    for e in errors: print(e)
else:
    print('All patches OK.')

print('\nNext steps:')
print('  docker compose restart node3    # or: docker restart node3')
print('  Then in a new terminal: docker logs -f node3')
print('  Then commit: git add -A && git commit -m "Comprehensive audit fixes" && git push')
