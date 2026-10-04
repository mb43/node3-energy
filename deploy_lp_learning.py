#!/usr/bin/env python3
"""
deploy_lp_learning.py — Teach the LP planner to use learned house load profile  [v2]
Run on Pi: python3 /tmp/deploy_lp_learning.py

Changes applied:
  1. simulate.py — add _BASE_DIR + _load_house_profile() helper
  2. simulate.py — build per-slot load array + cumulative sums for LP constraints
  3. simulate.py — LP SOC constraints use cumulative per-slot sums (not t * flat)
  4. simulate.py — rolling simulation uses per-slot learned load
  5. simulate.py — add _rebuild_house_profile() called before __main__
  6. server.py   — /api/house-profile endpoint
  7. server.py   — /api/grid-history endpoint
  8. dashboard.html — house load profile sparkline widget + JS
"""
from pathlib import Path

BASE = Path('/home/pi/node3')
SIM  = BASE / 'simulate.py'
SRV  = BASE / 'server.py'
DASH = BASE / 'dashboard.html'

def patch(path, old, new, label):
    text = path.read_text('utf-8')
    if old not in text:
        first_line = new.split('\n')[0].strip()
        if first_line and first_line in text:
            print(f'[SKIP] {label}')
        else:
            print(f'[WARN] {label} — anchor not found in {path.name}')
            print(f'       Looking for: {repr(old[:80])}')
        return False
    count = text.count(old)
    if count > 1:
        print(f'[WARN] {label} — {count} matches, need 1; skipping')
        return False
    path.write_text(text.replace(old, new, 1), 'utf-8')
    print(f'[OK]   {label}')
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# SIMULATE.PY — 1: add _BASE_DIR + _load_house_profile() after SOLAR_KWP line
# ═══════════════════════════════════════════════════════════════════════════════
patch(SIM,
    'SOLAR_KWP          = 0.0     # no solar modelled (pure arbitrage)',
    'SOLAR_KWP          = 0.0     # no solar modelled (pure arbitrage)\n'
    '\n'
    '# ── Learned house load profile ──────────────────────────────────────────────\n'
    '_BASE_DIR     = os.path.dirname(os.path.abspath(__file__))\n'
    '_PROFILE_FILE = os.path.join(_BASE_DIR, "house_profile.json")\n'
    '\n'
    'def _load_house_profile():\n'
    '    """Return 48-slot kWh list from house_profile.json, or None.\n'
    '    Built by house_profile.py from grid_history.csv after ~3 days of data.\n'
    '    """\n'
    '    try:\n'
    '        import json as _json\n'
    '        p = _json.loads(open(_PROFILE_FILE).read())\n'
    '        if isinstance(p, list) and len(p) == 48 and all(isinstance(x, (int, float)) for x in p):\n'
    '            return [float(x) for x in p]\n'
    '    except Exception:\n'
    '        pass\n'
    '    return None',
    'simulate.py: add _BASE_DIR + _load_house_profile()')


# ═══════════════════════════════════════════════════════════════════════════════
# SIMULATE.PY — 2: replace flat load_per_slot with per-slot profile + cum sums
# ═══════════════════════════════════════════════════════════════════════════════
patch(SIM,
    '    charge_per_slot    = CHARGE_KWH\n'
    '    load_per_slot      = daily_load_kwh / 48.0\n'
    '\n'
    '    n           = len(price_slots)\n'
    '    prices_vals = [s[\'value_inc_vat\'] for s in price_slots]',
    '    charge_per_slot    = CHARGE_KWH\n'
    '\n'
    '    # ── Learned per-slot house load ───────────────────────────────────────\n'
    '    # If house_profile.json exists, use it for per-slot load instead of flat.\n'
    '    # The learned profile captures when consumption actually peaks, letting\n'
    '    # the LP charge before peaks and discharge during cheap overnight slots.\n'
    '    _profile_raw = _load_house_profile()\n'
    '    if _profile_raw:\n'
    '        _psum = sum(_profile_raw) or 1.0\n'
    '        _scale = daily_load_kwh / _psum   # honour operator kWh/day setting\n'
    '        _profile_scaled = [v * _scale for v in _profile_raw]\n'
    '        print("[PLAN] Learned profile: " + str(round(_psum, 2)) +\n'
    '              " kWh/day raw -> scaled to " + str(round(daily_load_kwh, 2)) + " kWh/day")\n'
    '    else:\n'
    '        _flat = daily_load_kwh / 48.0\n'
    '        _profile_scaled = [_flat] * 48\n'
    '    load_per_slot = daily_load_kwh / 48.0   # kept for any non-LP fallback path\n'
    '\n'
    '    n           = len(price_slots)\n'
    '    prices_vals = [s[\'value_inc_vat\'] for s in price_slots]\n'
    '\n'
    '    # Map each LP slot index -> half-hour slot index (0..47) using valid_from timestamp.\n'
    '    def _halfhour_idx(iso_str):\n'
    '        try:\n'
    '            import datetime as _dt\n'
    '            d = _dt.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))\n'
    '            d = d.astimezone(_dt.timezone.utc)\n'
    '            return d.hour * 2 + (1 if d.minute >= 30 else 0)\n'
    '        except Exception:\n'
    '            return 0\n'
    '\n'
    '    # Per-slot kWh for each LP slot, time-aligned to real time-of-day\n'
    '    _lp_slot_loads = [\n'
    '        _profile_scaled[_halfhour_idx(s[\'valid_from\'])]\n'
    '        for s in price_slots\n'
    '    ]\n'
    '    # Cumulative sums: _cum_load[t] = total load for LP slots 0..t-1\n'
    '    _cum_load = [0.0]\n'
    '    for _v in _lp_slot_loads:\n'
    '        _cum_load.append(_cum_load[-1] + _v)',
    'simulate.py: build per-slot load array + cumulative sums')


# ═══════════════════════════════════════════════════════════════════════════════
# SIMULATE.PY — 3: LP SOC constraints use cumulative profile sums
# ═══════════════════════════════════════════════════════════════════════════════
patch(SIM,
    '            b_ub[rl]          = initial_soc_kwh - t * load_per_slot - min_soc_kwh\n'
    '            A_ub[ru, :t]      =  1;  A_ub[ru, n:n + t] = -1\n'
    '            b_ub[ru]          = battery_kwh - initial_soc_kwh + t * load_per_slot',
    '            b_ub[rl]          = initial_soc_kwh - _cum_load[t] - min_soc_kwh\n'
    '            A_ub[ru, :t]      =  1;  A_ub[ru, n:n + t] = -1\n'
    '            b_ub[ru]          = battery_kwh - initial_soc_kwh + _cum_load[t]',
    'simulate.py: LP SOC constraints use cumulative profile loads')


# ═══════════════════════════════════════════════════════════════════════════════
# SIMULATE.PY — 4: rolling simulation uses per-slot learned load
# ═══════════════════════════════════════════════════════════════════════════════
patch(SIM,
    '    slot_load_kwh = load_kwh_day / 48.0\n'
    '    solar_kwh     = get_solar_kwh_for_slot(weather, slot_dt, kwp=solar_kwp)',
    '    # Use learned profile if available, else flat (same fallback as LP planner)\n'
    '    _sim_profile = _load_house_profile()\n'
    '    if _sim_profile:\n'
    '        _sp_sum = sum(_sim_profile) or 1.0\n'
    '        _hh_idx = slot_dt.hour * 2 + (1 if slot_dt.minute >= 30 else 0)\n'
    '        slot_load_kwh = _sim_profile[_hh_idx] * (load_kwh_day / _sp_sum)\n'
    '    else:\n'
    '        slot_load_kwh = load_kwh_day / 48.0\n'
    '    solar_kwh     = get_solar_kwh_for_slot(weather, slot_dt, kwp=solar_kwp)',
    'simulate.py: slot simulation uses per-slot learned load')


# ═══════════════════════════════════════════════════════════════════════════════
# SIMULATE.PY — 5: add _rebuild_house_profile() before __main__
# ═══════════════════════════════════════════════════════════════════════════════
patch(SIM,
    '\nif __name__ == "__main__":',
    '\n\n# ── Rebuild house load profile before each simulate run ──────────────────────\n'
    'def _rebuild_house_profile():\n'
    '    """Silently rebuild house_profile.json from grid_history.csv.\n'
    '    No-ops when less than 3 days of data collected.\n'
    '    """\n'
    '    try:\n'
    '        import house_profile as _hp\n'
    '        _hp.run()\n'
    '    except Exception:\n'
    '        pass\n'
    '\n'
    '\nif __name__ == "__main__":',
    'simulate.py: add _rebuild_house_profile() before __main__')


# ═══════════════════════════════════════════════════════════════════════════════
# SERVER.PY — 6+7: /api/house-profile + /api/grid-history endpoints
# ═══════════════════════════════════════════════════════════════════════════════
patch(SRV,
    '@app.route("/api/fuse-status")',
    '@app.route("/api/house-profile")\n'
    'def api_house_profile():\n'
    '    """Return learned 48-slot house load profile + meta."""\n'
    '    import json as _json\n'
    '    profile_path = os.path.join(BASE_DIR, "house_profile.json")\n'
    '    meta_path    = os.path.join(BASE_DIR, "house_profile_meta.json")\n'
    '    profile, meta = [], {}\n'
    '    try:\n'
    '        if os.path.exists(profile_path):\n'
    '            profile = _json.loads(open(profile_path).read())\n'
    '    except Exception:\n'
    '        pass\n'
    '    try:\n'
    '        if os.path.exists(meta_path):\n'
    '            meta = _json.loads(open(meta_path).read())\n'
    '    except Exception:\n'
    '        pass\n'
    '    return jsonify({"profile": profile, "meta": meta, "ready": len(profile) == 48})\n'
    '\n'
    '\n'
    '@app.route("/api/grid-history")\n'
    'def api_grid_history():\n'
    '    """Return last N rows from grid_history.csv as JSON."""\n'
    '    import csv as _csv\n'
    '    rows_param = max(1, min(int(request.args.get("rows", 288)), 10000))\n'
    '    csv_path = os.path.join(BASE_DIR, "grid_history.csv")\n'
    '    rows = []\n'
    '    try:\n'
    '        if os.path.exists(csv_path):\n'
    '            with open(csv_path, newline="") as f:\n'
    '                for row in _csv.DictReader(f):\n'
    '                    rows.append(row)\n'
    '            rows = rows[-rows_param:]\n'
    '    except Exception as e:\n'
    '        return jsonify({"error": str(e), "rows": []}), 500\n'
    '    return jsonify({"rows": rows, "count": len(rows)})\n'
    '\n'
    '\n'
    '@app.route("/api/fuse-status")',
    'server.py: add /api/house-profile + /api/grid-history')


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD.HTML — 8: house load profile sparkline card + JS
# ═══════════════════════════════════════════════════════════════════════════════

PROFILE_CARD = '''    <div class="chart-card" style="margin-bottom:16px" id="house-profile-card">
      <div class="chart-title" style="margin-bottom:6px;display:flex;align-items:center;gap:8px">
        LEARNED HOUSE LOAD PROFILE
        <span id="hp-status" style="font-size:11px;color:var(--muted);font-weight:400;margin-left:auto">building...</span>
      </div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:10px">
        Actual consumption shape from live grid readings &mdash; LP planner charges before your peaks
      </div>
      <canvas id="hp-chart" height="80" style="width:100%;display:block"></canvas>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:10px;font-size:12px">
        <div><span style="color:var(--muted)">Daily total</span><br><b id="hp-daily">&mdash;</b></div>
        <div><span style="color:var(--muted)">Peak slot</span><br><b id="hp-peak">&mdash;</b></div>
        <div><span style="color:var(--muted)">Data age</span><br><b id="hp-updated">&mdash;</b></div>
      </div>
    </div>
'''

PROFILE_JS = r'''    // -- Learned house load profile sparkline ---------------------------------
    async function loadHouseProfile() {
      try {
        const r = await fetch('/api/house-profile');
        if (!r.ok) return;
        const d = await r.json();
        const st = document.getElementById('hp-status');
        if (!d.ready) { st.textContent = 'Collecting data (need 3+ days)...'; return; }
        const m = d.meta || {};
        st.textContent = (m.days_of_data || '?') + ' days of data';
        document.getElementById('hp-daily').textContent =
          m.total_daily_kwh ? m.total_daily_kwh.toFixed(1) + ' kWh/day' : '--';
        const slotLabel = i => ('0'+Math.floor(i/2)).slice(-2) + (i%2===0?':00':':30');
        document.getElementById('hp-peak').textContent =
          m.peak_slot != null ? slotLabel(m.peak_slot) + ' (' + (m.peak_kwh||0).toFixed(3) + ' kWh)' : '--';
        document.getElementById('hp-updated').textContent =
          m.updated ? m.updated.slice(0,10) : '--';
        const canvas = document.getElementById('hp-chart');
        const ctx = canvas.getContext('2d');
        canvas.width  = canvas.offsetWidth * devicePixelRatio;
        canvas.height = 80 * devicePixelRatio;
        ctx.scale(devicePixelRatio, devicePixelRatio);
        const W = canvas.offsetWidth, H = 80;
        const profile = d.profile;
        const maxV = Math.max(...profile, 0.001);
        const bW = W / 48;
        ctx.clearRect(0, 0, W, H);
        profile.forEach((v, i) => {
          const bH = (v / maxV) * (H - 10);
          const hr = Math.floor(i/2);
          const col = hr < 6 ? '#1f6feb' : hr < 9 ? '#d29922' : hr < 18 ? '#3fb950' : hr < 22 ? '#d29922' : '#1f6feb';
          ctx.fillStyle = col + 'aa';
          ctx.fillRect(i * bW + 1, H - bH - 2, bW - 2, bH);
        });
        ctx.fillStyle = '#6e7681'; ctx.font = '9px monospace';
        [0, 6, 12, 18, 23].forEach(hr => ctx.fillText(('0'+hr).slice(-2)+':00', hr*2*bW, H));
      } catch(e) {}
    }
    loadHouseProfile();
    setInterval(loadHouseProfile, 120000);
'''

dash_text = DASH.read_text('utf-8')

if 'id="house-profile-card"' in dash_text:
    print('[SKIP] house profile card already in dashboard')
else:
    # Primary anchor: LIVE PACK TELEMETRY
    anchor1 = '<div class="chart-card" style="margin-bottom:16px">\n      <div class="chart-title" style="margin-bottom:10px">LIVE PACK TELEMETRY</div>'
    if anchor1 in dash_text:
        dash_text = dash_text.replace(anchor1, PROFILE_CARD + '\n    ' + anchor1, 1)
        DASH.write_text(dash_text, 'utf-8')
        print('[OK]   house profile card inserted before LIVE PACK TELEMETRY')
    else:
        # Fallback: find chart-card before hw-source-card
        anchor2 = '<div class="stat-card" id="hw-source-card">'
        if anchor2 in dash_text:
            idx = dash_text.find(anchor2)
            back = dash_text.rfind('<div class="chart-card"', 0, idx)
            if back != -1:
                snippet = dash_text[back:back+35]
                dash_text = dash_text.replace(snippet, PROFILE_CARD + '\n    ' + snippet, 1)
                DASH.write_text(dash_text, 'utf-8')
                print('[OK]   house profile card inserted (fallback anchor)')
            else:
                print('[WARN] house profile card - no suitable anchor found; add manually')
        else:
            print('[WARN] house profile card - no anchors found; add manually')
    dash_text = DASH.read_text('utf-8')

if 'loadHouseProfile' not in dash_text:
    if '</body>' in dash_text:
        DASH.write_text(
            dash_text.replace('</body>', '  <script>\n' + PROFILE_JS + '  </script>\n</body>'),
            'utf-8'
        )
        print('[OK]   house profile JS inserted')
    else:
        print('[WARN] house profile JS - </body> not found')
else:
    print('[SKIP] house profile JS already present')


print('\n=== deploy_lp_learning.py DONE ===')
print()
print('Next steps:')
print('  1. docker restart node3-portal')
print('  2. fox_modbus_loop.py starts logging to grid_history.csv every 5s')
print('     house_profile.py auto-rebuilds every ~2h (1440 cycles)')
print('  3. After 3+ days: LP planner uses learned consumption shape')
print('     (charges before morning/evening peaks, not flat distribution)')
print()
print('View profile:   curl http://localhost:5000/api/house-profile')
print('View grid data: curl "http://localhost:5000/api/grid-history?rows=100"')
