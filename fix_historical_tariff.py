#!/usr/bin/env python3
"""fix_historical_tariff.py — Make /api/backtest tariff-aware.

Adds ?tariff_mode=agile|split|optimise to /api/backtest so the Historical tab
can show the correct 12-month figures for whichever tariff the user has selected.
Each tariff mode gets its own cache file so they don't collide.

Also patches dashboard.html to:
  - Pass current tariff to backtest fetch
  - Reload historical data when tariff mode changes
  - Auto-refresh every 30 minutes
  - Update the subtitle to say which tariff the data represents

Run on Pi: python3 /tmp/fix_historical_tariff.py
"""
from pathlib import Path

SRV  = Path('/home/pi/node3/server.py')
DASH = Path('/home/pi/node3/dashboard.html')

# ══════════════════════════════════════════════════════════════════════════════
# PATCH 1 — server.py: add tariff_mode to /api/backtest route + per-mode cache
# ══════════════════════════════════════════════════════════════════════════════
srv = SRV.read_text('utf-8')

OLD_BACKTEST_ROUTE = '''@app.route("/api/backtest")
def api_backtest():
    """12-month backtest. ?mode=founder uses baseload_kw; default uses baseload_kw_consumer."""
    founder    = request.args.get('mode', '').lower() == 'founder'
    cache_file = "backtest_cache_founder.json" if founder else "backtest_cache.json"
    cache_path = os.path.join(BASE_DIR, cache_file)
    force      = request.args.get('force', '').lower() in ('1', 'true', 'yes')'''

NEW_BACKTEST_ROUTE = '''@app.route("/api/backtest")
def api_backtest():
    """12-month backtest. ?mode=founder uses baseload_kw; default uses baseload_kw_consumer.
    ?tariff_mode=agile|split|optimise controls which LP scenario to simulate (default: agile).
    Each tariff_mode has its own cache file so they don\'t stomp each other."""
    founder      = request.args.get('mode', '').lower() == 'founder'
    tariff_mode  = request.args.get('tariff_mode', 'agile').lower()
    if tariff_mode not in ('agile', 'split', 'optimise'):
        tariff_mode = 'agile'
    # Separate cache per (founder × tariff_mode) combination
    if founder:
        cache_file = f"backtest_cache_founder_{tariff_mode}.json"
    else:
        cache_file = f"backtest_cache_{tariff_mode}.json"
    # Backwards compat: keep legacy "backtest_cache.json" name for agile/non-founder
    if not founder and tariff_mode == 'agile':
        cache_file = "backtest_cache.json"
    cache_path = os.path.join(BASE_DIR, cache_file)
    force      = request.args.get('force', '').lower() in ('1', 'true', 'yes')'''

if OLD_BACKTEST_ROUTE in srv:
    srv = srv.replace(OLD_BACKTEST_ROUTE, NEW_BACKTEST_ROUTE, 1)
    print('[OK]   server.py: /api/backtest now accepts ?tariff_mode=')
elif 'tariff_mode  = request.args.get(\'tariff_mode\'' in srv:
    print('[SKIP] server.py: tariff_mode param already present')
else:
    print('[WARN] server.py: /api/backtest anchor not found')

# Also pass tariff_mode to _run_backtest() in the background thread
OLD_BG_CALL = "            d = _run_backtest(founder=founder_flag)"
NEW_BG_CALL = "            d = _run_backtest(founder=founder_flag, tariff_mode=tariff_mode_flag)"

OLD_BG_DEF = "    def _bg(founder_flag, key, cpath):\n        print(f'[BACKTEST] bg thread start mode={key}')\n        try:\n            d = _run_backtest(founder=founder_flag)"
NEW_BG_DEF = "    def _bg(founder_flag, tariff_mode_flag, key, cpath):\n        print(f'[BACKTEST] bg thread start mode={key} tariff={tariff_mode_flag}')\n        try:\n            d = _run_backtest(founder=founder_flag, tariff_mode=tariff_mode_flag)"

if OLD_BG_DEF in srv:
    srv = srv.replace(OLD_BG_DEF, NEW_BG_DEF, 1)
    print('[OK]   server.py: _bg() thread now passes tariff_mode to _run_backtest')
elif 'tariff_mode_flag' in srv:
    print('[SKIP] server.py: tariff_mode_flag already in _bg()')
else:
    print('[WARN] server.py: _bg() def anchor not found')

# Update the thread spawn to pass tariff_mode
OLD_SPAWN = "            _th.Thread(target=_bg,args=(founder,mode_key,cache_path),daemon=True).start()"
NEW_SPAWN = "            _th.Thread(target=_bg,args=(founder,tariff_mode,mode_key,cache_path),daemon=True).start()"

if OLD_SPAWN in srv:
    srv = srv.replace(OLD_SPAWN, NEW_SPAWN, 1)
    print('[OK]   server.py: thread spawn passes tariff_mode')
elif NEW_SPAWN in srv:
    print('[SKIP] server.py: thread spawn already updated')
else:
    print('[WARN] server.py: thread spawn anchor not found')

# Make mode_key tariff-aware so concurrent agile+optimise runs don't clash
OLD_MODE_KEY = '    mode_key = "founder" if founder else "consumer"'
NEW_MODE_KEY = '    mode_key = ("founder" if founder else "consumer") + "_" + tariff_mode'

if OLD_MODE_KEY in srv:
    srv = srv.replace(OLD_MODE_KEY, NEW_MODE_KEY, 1)
    print('[OK]   server.py: mode_key is now tariff-scoped')
elif NEW_MODE_KEY in srv:
    print('[SKIP] server.py: mode_key already tariff-scoped')
else:
    print('[WARN] server.py: mode_key anchor not found')

# Surface tariff_mode in the cached payload so dashboard knows what it got
OLD_CACHE_RETURN = '''                out['_generated_at'] = datetime.fromtimestamp(cached_at, tz=timezone.utc).isoformat()
                return jsonify(out)'''
NEW_CACHE_RETURN = '''                out['_generated_at'] = datetime.fromtimestamp(cached_at, tz=timezone.utc).isoformat()
                out['_tariff_mode']   = tariff_mode
                return jsonify(out)'''

if OLD_CACHE_RETURN in srv:
    srv = srv.replace(OLD_CACHE_RETURN, NEW_CACHE_RETURN, 1)
    print('[OK]   server.py: cache return now includes _tariff_mode')
elif "'_tariff_mode'   = tariff_mode" in srv:
    print('[SKIP] server.py: _tariff_mode already in cache return')
else:
    print('[WARN] server.py: cache return anchor not found')

SRV.write_text(srv, 'utf-8')
print('[DONE] server.py patches applied\n')

# ══════════════════════════════════════════════════════════════════════════════
# PATCH 2 — dashboard.html: tariff-aware historical fetch + auto-refresh 30 min
# ══════════════════════════════════════════════════════════════════════════════
dash = DASH.read_text('utf-8')

# Patch loadHistoricalData() to pass current tariff_mode
OLD_LOAD_URL = '''    const _founderMode = (cfg.baseload_kw || 0) > 0;
    const _btBase = '/api/backtest' + (_founderMode ? '?mode=founder' : '');
    const url = _btBase + (force ? (_founderMode ? '&force=1' : '?force=1') : '');'''

NEW_LOAD_URL = '''    const _founderMode = (cfg.baseload_kw || 0) > 0;
    // Pass current tariff mode so Historical shows the right scenario
    const _histTariff  = (window._currentTariffMode || 'agile');
    const _btBase = '/api/backtest' + (_founderMode ? '?mode=founder&' : '?') + 'tariff_mode=' + _histTariff;
    const url = _btBase + (force ? '&force=1' : '');'''

if OLD_LOAD_URL in dash:
    dash = dash.replace(OLD_LOAD_URL, NEW_LOAD_URL, 1)
    print('[OK]   dashboard.html: loadHistoricalData() passes tariff_mode')
elif '_histTariff' in dash:
    print('[SKIP] dashboard.html: tariff_mode in loadHistoricalData already present')
else:
    print('[WARN] dashboard.html: loadHistoricalData URL anchor not found')

# Expose _currentTariffMode globally when setTariffMode runs
OLD_APPLY_TARIFF = "async function setTariffMode(mode) {"
NEW_APPLY_TARIFF = """async function setTariffMode(mode) {
  window._currentTariffMode = mode;  // expose for loadHistoricalData()"""

if OLD_APPLY_TARIFF in dash and 'window._currentTariffMode = mode' not in dash:
    dash = dash.replace(OLD_APPLY_TARIFF, NEW_APPLY_TARIFF, 1)
    print('[OK]   dashboard.html: setTariffMode() sets window._currentTariffMode')
elif 'window._currentTariffMode = mode' in dash:
    print('[SKIP] dashboard.html: _currentTariffMode already set in setTariffMode')
else:
    print('[WARN] dashboard.html: setTariffMode anchor not found')

# When tariff changes while historical tab is open, reload it
OLD_APPLY_UI = "    _applyTariffUI(d.tariff_mode || d.tariff_mode);"
# That anchor may vary — search for the actual line
import re
# Find _applyTariffUI call inside setTariffMode
m = re.search(r"(_applyTariffUI\(d\.tariff_mode \|\|[^\n]+\);)", dash)
if m:
    old_apply = m.group(1)
    new_apply = old_apply + """
    // If the user is viewing the Historical tab, reload with new tariff
    if (document.getElementById('tab-historical')?.style.display !== 'none') {
      histResultsCache = null;
      loadHistoricalData(true);
    }"""
    if 'reload with new tariff' not in dash:
        dash = dash.replace(old_apply, new_apply, 1)
        print('[OK]   dashboard.html: tariff change triggers historical reload')
    else:
        print('[SKIP] dashboard.html: historical reload on tariff change already present')
else:
    # Try the line we know from the source
    OLD_APPLY_UI2 = "    _applyTariffUI(d.tariff_mode || mode);"
    NEW_APPLY_UI2 = """    _applyTariffUI(d.tariff_mode || mode);
    // If the user is viewing the Historical tab, reload with new tariff
    if (document.getElementById('tab-historical')?.style.display !== 'none') {
      histResultsCache = null;
      loadHistoricalData(true);
    }"""
    if OLD_APPLY_UI2 in dash and 'reload with new tariff' not in dash:
        dash = dash.replace(OLD_APPLY_UI2, NEW_APPLY_UI2, 1)
        print('[OK]   dashboard.html: tariff change triggers historical reload (v2 anchor)')
    elif 'reload with new tariff' in dash:
        print('[SKIP] dashboard.html: historical reload on tariff change already present')
    else:
        print('[WARN] dashboard.html: _applyTariffUI anchor not found for historical reload')

# Update the rolling12 subtitle to mention the tariff mode
OLD_RANGE_TEXT = '''  rangeEl.textContent = `${monthLabel(months[0])} → ${monthLabel(months[months.length - 1])}`
    + ` · real Octopus Agile prices · recalculates automatically, rolls forward each day`;'''
NEW_RANGE_TEXT = '''  const _tariffLabel = {
    agile:    'real Octopus Agile prices',
    split:    'E.ON Optimise import + Agile export (split)',
    optimise: 'E.ON Next Optimise (−3p 00-06 import, +3p 16-19 export)',
  }[res._tariff_mode || window._currentTariffMode || 'agile'] || 'real Octopus Agile prices';
  rangeEl.textContent = `${monthLabel(months[0])} → ${monthLabel(months[months.length - 1])}`
    + ` · ${_tariffLabel} · recalculates automatically, rolls forward each day`;'''

if OLD_RANGE_TEXT in dash:
    dash = dash.replace(OLD_RANGE_TEXT, NEW_RANGE_TEXT, 1)
    print('[OK]   dashboard.html: rolling12 subtitle is tariff-aware')
elif '_tariffLabel' in dash:
    print('[SKIP] dashboard.html: tariff label already present')
else:
    print('[WARN] dashboard.html: range text anchor not found')

# Also update the big ROLLING 12 MONTHS heading to show the active tariff
OLD_HEADING_SUBTITLE = "      SEPT 2025 → OCT 2026 · REAL OCTOPUS AGILE PRICES · RECALCULATES AUTOMATICALLY, ROLLS FORWARD EACH DAY"
# This is a static text — replace with a dynamic span
if OLD_HEADING_SUBTITLE in dash:
    dash = dash.replace(
        OLD_HEADING_SUBTITLE,
        '      <span id="rolling12-range-static">SEPT 2025 → OCT 2026 · REAL OCTOPUS AGILE PRICES · RECALCULATES AUTOMATICALLY, ROLLS FORWARD EACH DAY</span>',
        1
    )
    print('[OK]   dashboard.html: static heading replaced with dynamic span')
else:
    print('[INFO] dashboard.html: static heading already dynamic or not found (OK if already patched)')

# Auto-refresh historical data every 30 minutes when tab is active
OLD_30MIN_REFRESH = "      loadHistoricalData(false);  // 24h cache serves fresh backtest; no need to force every 30min"
NEW_30MIN_REFRESH = """      // Auto-refresh: if Historical tab is visible, reload every 30 min so the
      // headline figure and chart stay current throughout a long session.
      if (document.getElementById('tab-historical')?.style.display !== 'none') {
        loadHistoricalData(false);  // false = honour 24h cache (server decides if stale)
      }"""
if OLD_30MIN_REFRESH in dash:
    dash = dash.replace(OLD_30MIN_REFRESH, NEW_30MIN_REFRESH, 1)
    print('[OK]   dashboard.html: 30-min auto-refresh is tab-aware')
elif 'Auto-refresh: if Historical tab is visible' in dash:
    print('[SKIP] dashboard.html: 30-min refresh already tab-aware')
else:
    print('[WARN] dashboard.html: 30-min refresh anchor not found')

DASH.write_text(dash, 'utf-8')
print('\n[DONE] All patches applied.')
print('       Restart: docker restart node3-portal')
print('       Test:    curl "http://localhost:5000/api/backtest?tariff_mode=optimise&force=1"')
