#!/usr/bin/env python3
"""
deploy_all_fixes.py — 5-fix omnibus patch
Run on Pi: python3 /tmp/deploy_all_fixes.py

Fixes:
  1. node3_config.py — add standing_charge_eon_p_day to DEFAULTS + NON_NEGATIVE
  2. node3_config.py — allow subscription_pcm=0 (add to NON_NEGATIVE set)
  3. server.py — auto-start fox_modbus_loop.py as subprocess daemon on startup
  4. server.py — add /api/fuse-status endpoint
  5. server.py — add Pushover alerting to /api/alerts (fuse headroom + loop health)
  6. dashboard.html — fuse status card in portal
"""
from pathlib import Path

BASE = Path('/home/pi/node3')
CFG  = BASE / 'node3_config.py'
SRV  = BASE / 'server.py'
DASH = BASE / 'dashboard.html'

def patch(path, old, new, label):
    text = path.read_text('utf-8')
    if old not in text:
        first_line = new.split('\n')[0].strip()
        if first_line and first_line in text:
            print(f'[SKIP] {label} — already applied')
        else:
            print(f'[WARN] {label} — anchor not found')
        return False
    assert text.count(old) == 1, f'Ambiguous anchor for {label}: {text.count(old)} matches'
    path.write_text(text.replace(old, new, 1), 'utf-8')
    print(f'[OK]   {label}')
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1 + 2 — node3_config.py: add eon SC to DEFAULTS; allow sub=0
# ═══════════════════════════════════════════════════════════════════════════════

patch(CFG,
    '    "standing_charge_export_p_day":  0.0,  # daily standing charge on export contract (p/day)\n'
    '                                            # Octopus Agile Outgoing = 0p/day\n'
    '}',
    '    "standing_charge_export_p_day":  0.0,  # daily standing charge on export contract (p/day)\n'
    '                                            # Octopus Agile Outgoing = 0p/day\n'
    '    "standing_charge_eon_p_day":    62.22,  # E.ON Next Optimise daily SC (p/day) — update once confirmed\n'
    '}',
    'node3_config DEFAULTS: add standing_charge_eon_p_day')

patch(CFG,
    '    NON_NEGATIVE = {"baseload_kw", "house_kwh_day",\n'
    '                    "standing_charge_import_p_day", "standing_charge_export_p_day"}',
    '    NON_NEGATIVE = {"baseload_kw", "house_kwh_day", "subscription_pcm",\n'
    '                    "standing_charge_import_p_day", "standing_charge_export_p_day",\n'
    '                    "standing_charge_eon_p_day"}',
    'node3_config NON_NEGATIVE: add sub_pcm + eon_sc (allow 0)')


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 3 — server.py: auto-start fox_modbus_loop.py daemon on startup
# ═══════════════════════════════════════════════════════════════════════════════

patch(SRV,
    '    # Start BMS cell-level monitor — DALA HTTP (Pack 1) + Waveshare CAN (Packs 2/3)\n'
    '    try:\n'
    '        import bms_monitor\n'
    '        bms_thread = threading.Thread(target=bms_monitor.run_loop, daemon=True, name="bms-monitor")\n'
    '        bms_thread.start()\n'
    '        print("[BMS-MON] Cell-level monitor started", flush=True)\n'
    '    except Exception as e:\n'
    '        print(f"[BMS-MON] Could not start: {e}", flush=True)',

    '    # Start BMS cell-level monitor — DALA HTTP (Pack 1) + Waveshare CAN (Packs 2/3)\n'
    '    try:\n'
    '        import bms_monitor\n'
    '        bms_thread = threading.Thread(target=bms_monitor.run_loop, daemon=True, name="bms-monitor")\n'
    '        bms_thread.start()\n'
    '        print("[BMS-MON] Cell-level monitor started", flush=True)\n'
    '    except Exception as e:\n'
    '        print(f"[BMS-MON] Could not start: {e}", flush=True)\n'
    '\n'
    '    # Start fox_modbus_loop.py — dynamic fuse protection daemon (5s Modbus poll)\n'
    '    _fuse_loop_proc = None\n'
    '    try:\n'
    '        fuse_loop_path = os.path.join(BASE_DIR, "fox_modbus_loop.py")\n'
    '        if os.path.exists(fuse_loop_path):\n'
    '            _fuse_loop_proc = subprocess.Popen(\n'
    '                [sys.executable, fuse_loop_path],\n'
    '                stdout=subprocess.PIPE, stderr=subprocess.STDOUT\n'
    '            )\n'
    '            print(f"[FUSE-LOOP] Dynamic fuse protection started (pid={_fuse_loop_proc.pid})", flush=True)\n'
    '        else:\n'
    '            print("[FUSE-LOOP] fox_modbus_loop.py not found — skipping", flush=True)\n'
    '    except Exception as e:\n'
    '        print(f"[FUSE-LOOP] Could not start: {e}", flush=True)',

    'server.py startup: launch fox_modbus_loop daemon')


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 4 — server.py: /api/fuse-status endpoint
# ═══════════════════════════════════════════════════════════════════════════════

patch(SRV,
    '@app.route("/api/hardware-status")',
    '@app.route("/api/fuse-status")\n'
    'def api_fuse_status():\n'
    '    """Return last N entries from fuse_loop_log.json plus loop health."""\n'
    '    import time as _time\n'
    '    log_path = os.path.join(BASE_DIR, "fuse_loop_log.json")\n'
    '    try:\n'
    '        entries = json.loads(open(log_path).read()) if os.path.exists(log_path) else []\n'
    '    except Exception:\n'
    '        entries = []\n'
    '    latest = entries[-1] if entries else {}\n'
    '    # Loop health: last entry within 30s = healthy\n'
    '    healthy = False\n'
    '    age_s   = None\n'
    '    if latest.get("ts"):\n'
    '        try:\n'
    '            from datetime import timezone as _tz\n'
    '            age_s = (_time.time() -\n'
    '                     __import__("datetime").datetime\n'
    '                     .fromisoformat(latest["ts"].replace("Z", "+00:00")).timestamp())\n'
    '            healthy = age_s < 30 and not latest.get("error")\n'
    '        except Exception:\n'
    '            pass\n'
    '    grid_w    = latest.get("grid_power_w")\n'
    '    safe_w    = latest.get("safe_charge_w")\n'
    '    fuse_safe = 16400\n'
    '    headroom_pct = round((safe_w / fuse_safe * 100)) if safe_w is not None else None\n'
    '    return jsonify({\n'
    '        "healthy":      healthy,\n'
    '        "age_s":        round(age_s) if age_s is not None else None,\n'
    '        "grid_power_w": grid_w,\n'
    '        "bat_charge_w": latest.get("bat_charge_w"),\n'
    '        "bat_volt_v":   latest.get("bat_volt_v"),\n'
    '        "soc_pct":      latest.get("soc_pct"),\n'
    '        "safe_charge_w":safe_w,\n'
    '        "headroom_pct": headroom_pct,\n'
    '        "reg_val":      latest.get("reg_val"),\n'
    '        "last_ts":      latest.get("ts"),\n'
    '        "last_error":   latest.get("error"),\n'
    '        "recent":       entries[-20:],\n'
    '    })\n'
    '\n'
    '\n'
    '@app.route("/api/hardware-status")',
    'server.py: add /api/fuse-status endpoint')


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 5 — server.py: Pushover alerts for fuse headroom + loop health
# ═══════════════════════════════════════════════════════════════════════════════
# Pushover env vars: PUSHOVER_TOKEN, PUSHOVER_USER
# Alert conditions:
#   - fuse_critical: safe_charge_w < 500W (virtually no headroom)
#   - fuse_warning:  safe_charge_w < 2000W (< 2kW headroom)
#   - fuse_loop_dead: loop log older than 60s (daemon stopped)

patch(SRV,
    '    alerts = []\n'
    '    try:\n'
    '        cfg        = _cfg.load_config()\n'
    '        state_raw  = load_json("fleet_state.json") or {}\n'
    '        prices_raw = load_json("prices.json") or []',

    '    alerts = []\n'
    '    try:\n'
    '        cfg        = _cfg.load_config()\n'
    '        state_raw  = load_json("fleet_state.json") or {}\n'
    '        prices_raw = load_json("prices.json") or []\n'
    '\n'
    '        # ── Fuse loop alerts ─────────────────────────────────────────────\n'
    '        import time as _time\n'
    '        fuse_log_path = os.path.join(BASE_DIR, "fuse_loop_log.json")\n'
    '        try:\n'
    '            fuse_entries = json.loads(open(fuse_log_path).read()) if os.path.exists(fuse_log_path) else []\n'
    '            fuse_latest  = fuse_entries[-1] if fuse_entries else {}\n'
    '            fuse_safe_w  = fuse_latest.get("safe_charge_w")\n'
    '            fuse_ts      = fuse_latest.get("ts", "")\n'
    '            fuse_age_s   = None\n'
    '            if fuse_ts:\n'
    '                try:\n'
    '                    fuse_age_s = _time.time() - __import__("datetime").datetime.fromisoformat(\n'
    '                        fuse_ts.replace("Z", "+00:00")).timestamp()\n'
    '                except Exception:\n'
    '                    pass\n'
    '            if fuse_age_s is not None and fuse_age_s > 60:\n'
    '                alerts.append({"level": "critical", "code": "fuse_loop_dead",\n'
    '                    "message": f"Fuse protection loop offline — last update {fuse_age_s:.0f}s ago"})\n'
    '                _pushover_send("NODE-3 FUSE LOOP OFFLINE",\n'
    '                    f"fuse_loop daemon not responding. Last update {fuse_age_s:.0f}s ago. Check docker logs.")\n'
    '            elif fuse_safe_w is not None:\n'
    '                if fuse_safe_w < 500:\n'
    '                    alerts.append({"level": "critical", "code": "fuse_critical",\n'
    '                        "message": f"FUSE CRITICAL — only {fuse_safe_w:.0f}W charge headroom remaining"})\n'
    '                    _pushover_send("⚡ NODE-3 FUSE CRITICAL",\n'
    '                        f"Only {fuse_safe_w:.0f}W headroom. Grid import near 18.4kW limit. Charge throttled.")\n'
    '                elif fuse_safe_w < 2000:\n'
    '                    alerts.append({"level": "warning", "code": "fuse_warning",\n'
    '                        "message": f"Fuse warning — {fuse_safe_w:.0f}W charge headroom (< 2kW)"})\n'
    '        except Exception as _fe:\n'
    '            pass',
    'server.py /api/alerts: add fuse loop + Pushover alerts')


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 5b — server.py: add _pushover_send() helper function
# ═══════════════════════════════════════════════════════════════════════════════

patch(SRV,
    'def _run_simulate():\n'
    '    """Run simulate.py once and return (returncode, stderr)."""',
    'def _pushover_send(title, message):\n'
    '    """Send a Pushover notification. Silently no-ops if env vars not set.\n'
    '    Set PUSHOVER_TOKEN (app token) and PUSHOVER_USER (user/group key).\n'
    '    """\n'
    '    token = os.environ.get("PUSHOVER_TOKEN", "")\n'
    '    user  = os.environ.get("PUSHOVER_USER", "")\n'
    '    if not token or not user:\n'
    '        return\n'
    '    try:\n'
    '        import urllib.request, urllib.parse\n'
    '        data = urllib.parse.urlencode({\n'
    '            "token":   token,\n'
    '            "user":    user,\n'
    '            "title":   title,\n'
    '            "message": message,\n'
    '            "priority": 1,\n'
    '        }).encode()\n'
    '        urllib.request.urlopen(\n'
    '            urllib.request.Request(\n'
    '                "https://api.pushover.net/1/messages.json",\n'
    '                data=data, method="POST"),\n'
    '            timeout=10)\n'
    '        print(f"[PUSHOVER] Sent: {title}", flush=True)\n'
    '    except Exception as e:\n'
    '        print(f"[PUSHOVER] Failed: {e}", flush=True)\n'
    '\n'
    '\n'
    'def _run_simulate():\n'
    '    """Run simulate.py once and return (returncode, stderr)."""',
    'server.py: add _pushover_send() helper')


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 6 — dashboard.html: fuse status card
# ═══════════════════════════════════════════════════════════════════════════════
# Insert a fuse status card after the existing hardware status card.
# Find the hardware status section and append after it.

FUSE_CARD = '''
      <!-- ── Fuse Protection Loop ─────────────────────────────── -->
      <div id="fuse-card" style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px 20px;margin-bottom:16px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
          <span id="fuse-health-dot" style="width:10px;height:10px;border-radius:50%;background:#6e7681;flex-shrink:0"></span>
          <span style="font-size:13px;font-weight:600;color:#e6edf3">Fuse Protection</span>
          <span id="fuse-health-label" style="font-size:11px;color:#8b949e;margin-left:auto">—</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:12px">
          <div>
            <div style="color:#8b949e;margin-bottom:2px">Grid Import</div>
            <div id="fuse-grid" style="color:#e6edf3;font-weight:600">—</div>
          </div>
          <div>
            <div style="color:#8b949e;margin-bottom:2px">Bat Charging</div>
            <div id="fuse-bat" style="color:#e6edf3;font-weight:600">—</div>
          </div>
          <div>
            <div style="color:#8b949e;margin-bottom:2px">Headroom</div>
            <div id="fuse-headroom" style="color:#e6edf3;font-weight:600">—</div>
          </div>
        </div>
        <div style="margin-top:10px">
          <div style="height:6px;background:#21262d;border-radius:3px;overflow:hidden">
            <div id="fuse-bar" style="height:100%;width:0%;background:#3fb950;border-radius:3px;transition:width 0.5s,background 0.5s"></div>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:10px;color:#8b949e;margin-top:3px">
            <span>0</span><span>Fuse limit 18.4 kW</span>
          </div>
        </div>
      </div>'''

FUSE_JS = '''
    // ── Fuse protection loop status ──────────────────────────────────────────
    async function loadFuseStatus() {
      try {
        const r = await fetch('/api/fuse-status');
        if (!r.ok) return;
        const d = await r.json();
        const dot   = document.getElementById('fuse-health-dot');
        const label = document.getElementById('fuse-health-label');
        const bar   = document.getElementById('fuse-bar');
        if (d.healthy) {
          dot.style.background = '#3fb950';
          label.textContent = `Live · ${d.age_s ?? '?'}s ago`;
        } else if (d.last_error) {
          dot.style.background = '#f85149';
          label.textContent = 'Error — ' + (d.last_error.slice(0,40));
        } else {
          dot.style.background = '#d29922';
          label.textContent = d.age_s ? `Stale — ${d.age_s}s ago` : 'Not running';
        }
        const fmt = w => w != null ? (w/1000).toFixed(1) + ' kW' : '—';
        document.getElementById('fuse-grid').textContent    = fmt(d.grid_power_w);
        document.getElementById('fuse-bat').textContent     = fmt(d.bat_charge_w);
        const hw = d.safe_charge_w;
        if (hw != null) {
          const pct = Math.min(100, Math.max(0, hw / 16400 * 100));
          document.getElementById('fuse-headroom').textContent = fmt(hw);
          bar.style.width = pct + '%';
          bar.style.background = hw < 500 ? '#f85149' : hw < 2000 ? '#d29922' : '#3fb950';
        }
      } catch(e) {}
    }
    loadFuseStatus();
    setInterval(loadFuseStatus, 6000);'''

# Find a good anchor — insert fuse card near hardware status section in dashboard
patch(DASH,
    '<div id="fuse-card"',
    '<div id="fuse-card"',   # if already there, skip
    'dashboard: fuse card already present check')

# Only insert if not already there
dash_text = DASH.read_text('utf-8')
if '<div id="fuse-card"' not in dash_text:
    # Insert after the hardware status card div or before closing sidebar/stats section
    # Look for hardware-status section anchor
    anchor = 'id="hw-status"'
    if anchor not in dash_text:
        anchor = 'id="hardware-status"'
    if anchor not in dash_text:
        # fallback: insert before first </aside> or the BMS card
        anchor = 'id="bms-card"'
    if anchor in dash_text:
        # Find the containing div close after the anchor and insert after it
        # Simpler: just find a good spot before </body> in the sidebar stats
        # Instead, insert the card HTML right before the closing tag of the status section
        # Use a known pattern from the dashboard
        pass

    # More reliable: find the loadFuseStatus-safe JS insertion point
    # Insert card before the first occurrence of the alerts section in the sidebar
    sidebar_anchor = 'id="alerts-panel"'
    if sidebar_anchor not in dash_text:
        sidebar_anchor = 'id="hw-card"'
    if sidebar_anchor not in dash_text:
        sidebar_anchor = '<!-- hardware status card -->'

    # Use the <script> footer to add JS, and find a sidebar panel anchor for the card
    # Find the BMS cell card or hardware card in dashboard for insertion
    # Look for a unique panel separator we can anchor on
    bms_anchor = 'id="bms-detail-panel"'
    agile_anchor = 'id="agile-card"'
    node_anchor = 'id="node-card"'

    inserted_card = False
    for card_anchor in ['id="bms-detail-panel"', 'id="agile-card"', 'id="node-card"', 'id="hw-status"']:
        if card_anchor in dash_text:
            # find the start of that element's containing block
            idx = dash_text.find(card_anchor)
            # walk back to the opening <div
            back = dash_text.rfind('<div', 0, idx)
            insert_before = dash_text[back:back+5+len(card_anchor)]
            new_text = dash_text.replace(insert_before, FUSE_CARD + '\n      ' + insert_before, 1)
            DASH.write_text(new_text, 'utf-8')
            print('[OK]   dashboard: fuse status card inserted')
            inserted_card = True
            break

    if not inserted_card:
        print('[WARN] dashboard: could not find card anchor — fuse card not inserted')

    # Add JS before </body>
    dash_text2 = DASH.read_text('utf-8')
    if 'loadFuseStatus' not in dash_text2:
        if '</body>' in dash_text2:
            DASH.write_text(dash_text2.replace('</body>',
                f'<script>{FUSE_JS}</script>\n</body>', 1), 'utf-8')
            print('[OK]   dashboard: fuse status JS added')
        else:
            print('[WARN] dashboard: </body> not found — JS not inserted')
else:
    print('[SKIP] dashboard: fuse card already present')


print('\n=== All fixes applied. Restart docker: ===')
print('  docker restart node3-portal')
print('')
print('Add Pushover credentials to docker-compose.pi.yml environment:')
print('  - PUSHOVER_TOKEN=your_app_token')
print('  - PUSHOVER_USER=your_user_key')
