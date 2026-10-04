#!/usr/bin/env python3
"""
deploy_connection_compare.py
Replaces the G98/G99 dual-tab with a proper 3-column connection comparison.
Columns: G98 (32A) | ★ G99 5.5kW (NORM / live) | G99 Full (10.5kW inverter cap)
Run on Pi: python3 deploy_connection_compare.py
"""
import os, sys

BASE = '/home/pi/node3'
DASH = os.path.join(BASE, 'dashboard.html')

def patch(path, old, new, label):
    with open(path) as f:
        src = f.read()
    if old not in src:
        print(f'✗ NOT FOUND: {label}')
        return False
    c = src.count(old)
    if c > 1:
        print(f'✗ AMBIGUOUS ({c} matches): {label}')
        return False
    with open(path, 'w') as f:
        f.write(src.replace(old, new, 1))
    print(f'✓ {label}')
    return True

# ──────────────────────────────────────────────────────────────────
# PATCH 1: CSS — add 3-column variant and g98-dim / g99-norm styles
# ──────────────────────────────────────────────────────────────────
patch(DASH,
    '    .scenario-compare {\n      display: grid;\n      grid-template-columns: 1fr 1fr;\n      gap: 16px;\n      margin-bottom: 16px;\n    }\n    @media (max-width:800px) { .scenario-compare { grid-template-columns: 1fr; } }',
    '''    .scenario-compare {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 16px;
    }
    .scenario-compare.three-col {
      grid-template-columns: 1fr 1.1fr 1fr;
    }
    @media (max-width:900px) { .scenario-compare.three-col { grid-template-columns: 1fr; } }
    @media (max-width:800px) { .scenario-compare { grid-template-columns: 1fr; } }
    .scenario-card.g98-dim { border-top: 3px solid rgba(255,176,0,0.4); }
    .scenario-card.g99-norm {
      border-top: 3px solid var(--green);
      background: rgba(63,185,80,0.06);
      box-shadow: 0 0 0 1px rgba(63,185,80,0.15);
    }
    .scenario-card.g99-full { border-top: 3px solid rgba(163,113,247,0.5); }
    .norm-badge {
      display:inline-block;
      background:rgba(63,185,80,0.15);
      color:var(--green);
      font-size:10px;font-weight:700;letter-spacing:1px;
      border:1px solid rgba(63,185,80,0.35);
      border-radius:4px;padding:2px 7px;margin-left:8px;
      vertical-align:middle;
    }''',
    'PATCH 1: Add 3-column CSS + norm badge styles')

# ──────────────────────────────────────────────────────────────────
# PATCH 2: G98 tab HTML — replace 2-col with 3-col comparison
# ──────────────────────────────────────────────────────────────────
OLD_G98_TAB = '''  <!-- ══ TAB: G98 — REMOVED: G99 5.5kW is the confirmed live cap ══════════ -->
  <div class="tab-panel" id="tab-g98" style="display:none">
    <div class="chart-card" style="margin-bottom:16px">
      <div class="chart-title" style="flex-direction:column;align-items:flex-start;gap:4px">
        G99 CONFIRMED LIVE — 5.5kW / 2.75kWh PER SLOT
        <span style="color:var(--muted);font-size:10px;font-weight:normal">SSEN confirmed G99 at 5.5kW (ref 260420-000198/FJJ907/1). G98/G99 comparison removed — this IS the live cap.</span>
      </div>
    </div>
    <div class="scenario-compare">
      <div class="scenario-card g98">
        <div class="scenario-title g98">📊 G99 Backtest (Live Config)</div>
        <div class="scenario-metric"><span class="sm-lbl">Export cap / slot</span><span class="sm-val" style="color:var(--green)">2.75 kWh</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Max export rate</span><span class="sm-val" style="color:var(--green)">5.5kW (G99 confirmed)</span></div>
        <div class="scenario-metric"><span class="sm-lbl">DNO standard</span><span class="sm-val" style="color:var(--text)">G99</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Current profit (window)</span><span class="sm-val" style="color:var(--green)" id="g98-current-profit">—</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Annualised (extrapolated)</span><span class="sm-val" style="color:var(--green)" id="g98-annual">—</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Last action</span><span class="sm-val" style="color:var(--purple)" id="g98-last-action">—</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Battery SOC</span><span class="sm-val" style="color:var(--blue)" id="g98-soc">—</span></div>
      </div>
      <div class="scenario-card" style="background:rgba(63,185,80,0.04);border-top:3px solid rgba(63,185,80,0.3)">
        <div class="scenario-title" style="color:var(--muted)">📊 G98 Monthly Backtest</div>
        <div id="g98-monthly-stats" style="color:var(--muted);font-size:12px">Load Historical data to populate →</div>
      </div>
    </div>
    <div class="chart-card">
      <div class="chart-title">G98 SLOT PROFIT HISTORY <span id="g98-chart-span">last -- slots</span></div>
      <canvas id="g98-profit-chart" height="150"></canvas>
    </div>
  </div><!-- /tab-g98 -->'''

NEW_G98_TAB = '''  <!-- ══ TAB: G98/G99 CONNECTION COMPARISON ══════════════════════ -->
  <div class="tab-panel" id="tab-g98" style="display:none">
    <div class="chart-card" style="margin-bottom:16px">
      <div class="chart-title" style="flex-direction:column;align-items:flex-start;gap:4px">
        DNO CONNECTION COMPARISON
        <span style="color:var(--muted);font-size:10px;font-weight:normal">
          All income figures from 12-month LP backtest (G99 5.5kW = live confirmed). G98 &amp; G99 Full are export-scaled estimates.
          SSEN confirmed G99 at 5.5kW (ref 260420-000198/FJJ907/1) · FoxESS KH10.5 inverter cap = 10.5kW.
        </span>
      </div>
    </div>
    <div class="scenario-compare three-col">

      <!-- ── COLUMN 1: G98 (32A standard) ── -->
      <div class="scenario-card g98-dim">
        <div class="scenario-title" style="color:var(--amber)">📊 G98 Standard</div>
        <div class="scenario-metric"><span class="sm-lbl">DNO standard</span><span class="sm-val" style="color:var(--amber)">G98</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Connection</span><span class="sm-val">32A</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Max export rate</span><span class="sm-val">3.68 kW</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Export / slot</span><span class="sm-val">1.84 kWh</span></div>
        <div class="scenario-metric" style="border-top:1px solid var(--border);margin-top:8px;padding-top:8px">
          <span class="sm-lbl">Est. arb P&amp;L / yr</span>
          <span class="sm-val" style="color:var(--amber)" id="g98-est-annual">—</span>
        </div>
        <div class="scenario-metric">
          <span class="sm-lbl">Est. total (+ self-con)</span>
          <span class="sm-val" style="color:var(--amber)" id="g98-est-total">—</span>
        </div>
        <div style="font-size:10px;color:var(--muted);margin-top:8px;line-height:1.5">
          Standard residential export limit. Lower export income than G99 — may need different subscription pricing to make economics viable.
        </div>
      </div>

      <!-- ── COLUMN 2: G99 5.5kW — NORM ── -->
      <div class="scenario-card g99-norm">
        <div class="scenario-title" style="color:var(--green)">
          ⚡ G99 5.5kW <span class="norm-badge">YOUR SITE · NORM</span>
        </div>
        <div class="scenario-metric"><span class="sm-lbl">DNO standard</span><span class="sm-val" style="color:var(--green)">G99</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Connection</span><span class="sm-val" style="color:var(--green)">50A</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Max export rate</span><span class="sm-val" style="color:var(--green)">5.5 kW (SSEN confirmed)</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Export / slot</span><span class="sm-val" style="color:var(--green)">2.75 kWh</span></div>
        <div class="scenario-metric" style="border-top:1px solid rgba(63,185,80,0.2);margin-top:8px;padding-top:8px">
          <span class="sm-lbl">12-mo backtest arb / yr</span>
          <span class="sm-val" style="color:var(--green);font-weight:bold" id="g99-norm-annual">—</span>
        </div>
        <div class="scenario-metric">
          <span class="sm-lbl">Total (+ actual self-con)</span>
          <span class="sm-val" style="color:var(--green);font-weight:bold" id="g99-norm-total">—</span>
        </div>
        <div id="g98-monthly-stats" style="font-size:11px;color:var(--muted);margin-top:8px">
          Load Historical tab data to populate.
        </div>
        <div style="font-size:10px;color:var(--muted);margin-top:8px;line-height:1.5">
          SSEN ref 260420-000198/FJJ907/1 · This is the confirmed live export cap and the default for all customer sites.
        </div>
      </div>

      <!-- ── COLUMN 3: G99 Full (inverter cap) ── -->
      <div class="scenario-card g99-full">
        <div class="scenario-title" style="color:var(--purple)">🚀 G99 Full Inverter</div>
        <div class="scenario-metric"><span class="sm-lbl">DNO standard</span><span class="sm-val" style="color:var(--purple)">G99</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Connection</span><span class="sm-val">50A</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Max export rate</span><span class="sm-val" style="color:var(--purple)">10.5 kW (FoxESS KH10.5)</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Export / slot</span><span class="sm-val" style="color:var(--purple)">5.25 kWh</span></div>
        <div class="scenario-metric" style="border-top:1px solid rgba(163,113,247,0.2);margin-top:8px;padding-top:8px">
          <span class="sm-lbl">Est. arb P&amp;L / yr</span>
          <span class="sm-val" style="color:var(--purple)" id="g99-full-annual">—</span>
        </div>
        <div class="scenario-metric">
          <span class="sm-lbl">Est. total (+ self-con)</span>
          <span class="sm-val" style="color:var(--purple)" id="g99-full-total">—</span>
        </div>
        <div style="font-size:10px;color:var(--muted);margin-top:8px;line-height:1.5">
          Full inverter capacity if DNO permits higher export. Estimate assumes proportional slot utilisation — actual uplift depends on LP re-optimisation.
        </div>
      </div>
    </div>

    <!-- Slot profit chart (live config = G99 5.5kW) -->
    <div class="chart-card">
      <div class="chart-title">SLOT PROFIT — 24HR WINDOW (G99 5.5kW LIVE) <span id="g98-chart-span">last -- slots</span></div>
      <canvas id="g98-profit-chart" height="150"></canvas>
    </div>
  </div><!-- /tab-g98 -->'''

patch(DASH, OLD_G98_TAB, NEW_G98_TAB, 'PATCH 2: Replace G98 tab with 3-column comparison')

# ──────────────────────────────────────────────────────────────────
# PATCH 3: renderG98Tab() — populate all 3 columns
# ──────────────────────────────────────────────────────────────────
OLD_RENDER = '''// G98 TAB RENDER
// ══════════════════════════════════════════════════════════════
function renderG98Tab() {
  // Live stats — 48-slot window (24hr)
  const today48g98 = get48Window();
  const daily24g98 = window24hrProfit(today48g98);
  const annual24g98 = daily24g98 * 365;
  document.getElementById('g98-current-profit').textContent = daily24g98 >= 0 ? '£' + daily24g98.toFixed(4) : '−£' + Math.abs(daily24g98).toFixed(4);
  document.getElementById('g98-annual').textContent = '~£' + Math.round(annual24g98) + '/yr';
  if (fleet.length) {
    const h = fleet[0];
    document.getElementById('g98-last-action').textContent = (h.lastAction || 'idle').toUpperCase();
    document.getElementById('g98-soc').textContent = (h.soc || 0).toFixed(1) + 'kWh';
  }

  // Monthly stats from histResultsCache
  const monthEl = document.getElementById('g98-monthly-stats');
  if (histResultsCache && monthEl) {
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
    // Self-consumption range: spot (min) → actual (best) → contractual (max)
    const scSpot   = totalHomeEnergySaved.toFixed(0);
    const scTrue   = totalHomeEnergySavedTrue  > 0 ? totalHomeEnergySavedTrue.toFixed(0)  : '—';
    const scContr  = totalHomeEnergySavedContract > 0 ? totalHomeEnergySavedContract.toFixed(0) : '—';
    const scBest   = totalHomeEnergySavedTrue > 0 ? totalHomeEnergySavedTrue : totalHomeEnergySaved;
    monthEl.innerHTML = `
      <div class="scenario-metric"><span class="sm-lbl">Annual grid P&L (arb)</span><span class="sm-val" style="color:var(--green)">£${total.toFixed(0)}</span></div>
      <div class="scenario-metric" title="Min: Agile spot-price vs SVT. Underestimates — zeroes slots where Agile &gt; SVT even though battery stored cheap overnight energy."><span class="sm-lbl">Self-con saving (min · spot basis)</span><span class="sm-val" style="color:var(--amber)">£${scSpot}</span></div>
      <div class="scenario-metric" title="Best estimate: avg charge cost ${avgChargeP.toFixed(1)}p/kWh paid, ${(avgChargeP/0.88).toFixed(1)}p/kWh delivered, vs 25p SVT. All load inc. miner."><span class="sm-lbl">Self-con saving (est. actual)</span><span class="sm-val" style="color:var(--green);font-weight:bold">£${scTrue} ← use this</span></div>
      <div class="scenario-metric" title="Max: 100% of load × 25p SVT, ignoring battery charge cost. Your contractual ceiling / service promise."><span class="sm-lbl">Self-con saving (max · contractual)</span><span class="sm-val" style="color:var(--cyan)">£${scContr}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Total value (arb + actual self-con)</span><span class="sm-val" style="color:var(--green);font-weight:bold">£${(total + scBest).toFixed(0)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Best month P&L</span><span class="sm-val" style="color:var(--green)">£${best.toFixed(2)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Worst month P&L</span><span class="sm-val" style="color:var(--amber)">£${worst.toFixed(2)}</span></div>
      <div class="scenario-metric"><span class="sm-lbl">Monthly avg P&L</span><span class="sm-val">£${avg.toFixed(2)}</span></div>
    `;
  } else if (monthEl && !histResultsCache) {
    monthEl.innerHTML = '<div style="color:var(--muted);font-size:11px;padding:8px 0">Switch to Historical tab and load 12-month data to see backtest results here.</div>';
  }'''

NEW_RENDER = '''// G98 TAB RENDER — 3-column connection comparison
// ══════════════════════════════════════════════════════════════
// Export slot capacities (kWh/slot = kW × 0.5h):
//   G98:      3.68kW × 0.5h = 1.84 kWh/slot  (32A standard)
//   G99 5.5k: 5.5kW  × 0.5h = 2.75 kWh/slot  (SSEN confirmed — LIVE)
//   G99 Full: 10.5kW × 0.5h = 5.25 kWh/slot  (FoxESS KH10.5 inverter cap)
const _EXP_G98      = 1.84;
const _EXP_G99_NORM = 2.75;
const _EXP_G99_FULL = 5.25;

function renderG98Tab() {
  // ── Populate 3-column comparison from histResultsCache (12-month LP backtest) ──
  const monthEl = document.getElementById('g98-monthly-stats');
  if (histResultsCache) {
    const {
      total               = 0,
      totalExportIncome   = 0,
      totalChargeCost     = 0,
      totalHomeEnergySaved = 0,
      totalHomeEnergySavedTrue = 0,
      totalHomeEnergySavedContract = 0,
      avgChargeP          = 0,
      monthly             = {}
    } = histResultsCache;

    // Export income scales with export cap; charge cost is the same
    // (we charged the same, just curtailed how much we export per slot)
    const exportScaleG98  = _EXP_G98  / _EXP_G99_NORM;   // 0.669
    const exportScaleFull = _EXP_G99_FULL / _EXP_G99_NORM; // 1.909, capped at what battery can give

    const arbG98  = Math.round(totalExportIncome * exportScaleG98  - totalChargeCost);
    const arbNorm = Math.round(total);
    const arbFull = Math.round(totalExportIncome * exportScaleFull - totalChargeCost);

    const scBest = totalHomeEnergySavedTrue > 0 ? totalHomeEnergySavedTrue : totalHomeEnergySaved;

    const totalG98  = arbG98  + Math.round(scBest);
    const totalNorm = arbNorm + Math.round(scBest);
    const totalFull = arbFull + Math.round(scBest);

    // G98 column
    const el98a = document.getElementById('g98-est-annual');
    const el98t = document.getElementById('g98-est-total');
    if (el98a) el98a.textContent = '~£' + arbG98.toLocaleString() + '/yr (est.)';
    if (el98t) el98t.textContent = '~£' + totalG98.toLocaleString() + '/yr (est.)';

    // G99 Norm column (actual backtest data)
    const el99a = document.getElementById('g99-norm-annual');
    const el99t = document.getElementById('g99-norm-total');
    if (el99a) el99a.textContent = '£' + arbNorm.toLocaleString() + '/yr';
    if (el99t) el99t.textContent = '£' + totalNorm.toLocaleString() + '/yr';

    // G99 Full column
    const elFa = document.getElementById('g99-full-annual');
    const elFt = document.getElementById('g99-full-total');
    if (elFa) elFa.textContent = '~£' + arbFull.toLocaleString() + '/yr (est.)';
    if (elFt) elFt.textContent = '~£' + totalFull.toLocaleString() + '/yr (est.)';

    // G99 Norm column — monthly detail
    const scSpot  = totalHomeEnergySaved.toFixed(0);
    const scTrue  = totalHomeEnergySavedTrue  > 0 ? totalHomeEnergySavedTrue.toFixed(0)  : '—';
    const scContr = totalHomeEnergySavedContract > 0 ? totalHomeEnergySavedContract.toFixed(0) : '—';
    const months  = Object.keys(monthly).sort();
    const profits = months.map(m => monthly[m].profit);
    const best    = Math.max(...profits);
    const worst   = Math.min(...profits);
    const avg     = profits.reduce((s,v) => s+v, 0) / (profits.length || 1);
    if (monthEl) {
      monthEl.innerHTML = `
        <div class="scenario-metric"><span class="sm-lbl">Best month P&L</span><span class="sm-val" style="color:var(--green)">£${best.toFixed(2)}</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Worst month P&L</span><span class="sm-val" style="color:var(--amber)">£${worst.toFixed(2)}</span></div>
        <div class="scenario-metric"><span class="sm-lbl">Monthly avg P&L</span><span class="sm-val">£${avg.toFixed(2)}</span></div>
        <div class="scenario-metric" title="Spot (min) → Actual (est.) → Contractual (max)">
          <span class="sm-lbl">Self-con range (£/yr)</span>
          <span class="sm-val" style="color:var(--green)">£${scSpot} → <b>£${scTrue}</b> → £${scContr}</span>
        </div>
        <div class="scenario-metric"><span class="sm-lbl">Avg charge cost</span><span class="sm-val">${avgChargeP.toFixed(1)}p/kWh</span></div>
      `;
    }
  } else if (monthEl) {
    monthEl.innerHTML = '<div style="color:var(--muted);font-size:11px;padding:8px 0">Load Historical tab first to populate comparison figures.</div>';
  }

  // Live stats — 48-slot window slot-profit chart
  const today48g98 = get48Window();'''

ok = patch(DASH, OLD_RENDER, NEW_RENDER, 'PATCH 3: Replace renderG98Tab with 3-column logic')
if not ok:
    print('  ↳ Patch 3 failed — check that dashboard.html matches the old text exactly')

print('\nDone. On Pi:')
print('  docker compose restart node3')
print('  (or: docker restart node3)')
print('\nThen load Historical tab first to populate the column figures.')
