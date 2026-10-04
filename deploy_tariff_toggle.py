#!/usr/bin/env python3
"""
deploy_tariff_toggle.py  — Dovecote Node-3
Adds AGILE / SPLIT / OPTIMISE tariff mode support:
  1. node3_config.py   — tariff_mode + E.ON modifier fields
  2. simulate.py       — asymmetric LP buy/sell price vectors
  3. server.py         — lp_day gets modifier arrays; /api/tariff endpoint
  4. dashboard.html    — 3-state toggle in header + JS
"""
import re
import shutil
from pathlib import Path

BASE = Path('/home/pi/node3')


def patch(path, old, new, label):
    text = path.read_text('utf-8')
    count = text.count(old)
    assert count == 1, f"[{label}] Expected 1 match, got {count}: {repr(old[:120])}"
    path.write_text(text.replace(old, new, 1), 'utf-8')
    print(f"[OK] {label}")


def patch_regex(path, pattern, new, label):
    """Patch using regex — use when comment text may vary between Pi and workspace."""
    text = path.read_text('utf-8')
    matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
    assert len(matches) == 1, f"[{label}] Expected 1 regex match, got {len(matches)}"
    path.write_text(re.sub(pattern, new, text, count=1, flags=re.MULTILINE | re.DOTALL), 'utf-8')
    print(f"[OK] {label}")


# Backups
for f in ['node3_config.py', 'simulate.py', 'server.py', 'dashboard.html']:
    shutil.copy(BASE / f, str(BASE / f) + '.bak_tariff')
print("[OK] Backups done")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. node3_config.py
# ═══════════════════════════════════════════════════════════════════════════════

cfg = BASE / 'node3_config.py'

# Add tariff_mode + modifier fields to DEFAULTS
# Anchor on the closing } of DEFAULTS followed by def load_config — works regardless
# of what the last field is or what comments say (Pi file is older than workspace copy)
def _insert_tariff_defaults(path, label):
    text = path.read_text('utf-8')
    # Find the closing brace of the DEFAULTS dict: \n} then blank lines then def load_config
    m = re.search(r'\n\}(\n+def load_config)', text)
    assert m, f"[{label}] Could not find DEFAULTS closing brace before def load_config"
    insert_pos = m.start() + 1   # position of the } character
    addition = (
        '    # ── Tariff mode (added Oct 2026) ──────────────────────────────────────────\n'
        '    "tariff_mode":           "agile",  # active tariff: \'agile\' | \'split\' | \'optimise\'\n'
        '    "optimise_import_mod_p": 3.0,      # p/kWh import discount 00:00-06:00 (E.ON Optimise early-bird)\n'
        '    "optimise_export_mod_p": 3.0,      # p/kWh export bonus 16:00-19:00   (E.ON Optimise early-bird)\n'
    )
    new_text = text[:insert_pos] + addition + text[insert_pos:]
    path.write_text(new_text, 'utf-8')
    print(f"[OK] {label}")

_insert_tariff_defaults(cfg, 'node3_config: add tariff_mode + modifier fields')

# load_config: handle tariff_mode as string (float() would explode on it)
patch(cfg,
    '            if isinstance(saved, dict):\n'
    '                for k in DEFAULTS:\n'
    '                    if k in saved:\n'
    '                        cfg[k] = float(saved[k])',
    '            if isinstance(saved, dict):\n'
    '                for k in DEFAULTS:\n'
    '                    if k in saved:\n'
    '                        if isinstance(DEFAULTS[k], str):\n'
    '                            cfg[k] = str(saved[k])\n'
    '                        else:\n'
    '                            cfg[k] = float(saved[k])',
    'node3_config: load_config handles string tariff_mode'
)

# save_config: allow tariff_mode as string key
# Pi's actual NON_NEGATIVE = {"baseload_kw", "house_kwh_day"} (older file, no consumer fields)
patch(cfg,
    '    NON_NEGATIVE = {"baseload_kw", "house_kwh_day"}\n'
    '    cfg = load_config()\n'
    '    for k in DEFAULTS:\n'
    '        if k in updates:\n'
    '            try:\n'
    '                v = float(updates[k])\n'
    '                if k in NON_NEGATIVE and v >= 0:\n'
    '                    cfg[k] = v\n'
    '                elif k not in NON_NEGATIVE and v > 0:\n'
    '                    cfg[k] = v\n'
    '            except (TypeError, ValueError):\n'
    '                pass',
    '    NON_NEGATIVE = {"baseload_kw", "house_kwh_day"}\n'
    '    STRING_KEYS  = {"tariff_mode"}\n'
    '    VALID_MODES  = {"agile", "split", "optimise"}\n'
    '    cfg = load_config()\n'
    '    for k in DEFAULTS:\n'
    '        if k in updates:\n'
    '            if k in STRING_KEYS:\n'
    '                v = str(updates[k]).lower().strip()\n'
    '                if v in VALID_MODES:\n'
    '                    cfg[k] = v\n'
    '            else:\n'
    '                try:\n'
    '                    v = float(updates[k])\n'
    '                    if k in NON_NEGATIVE and v >= 0:\n'
    '                        cfg[k] = v\n'
    '                    elif k not in NON_NEGATIVE and v > 0:\n'
    '                        cfg[k] = v\n'
    '                except (TypeError, ValueError):\n'
    '                    pass',
    'node3_config: save_config handles string tariff_mode'
)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. simulate.py — asymmetric LP price vectors
# ═══════════════════════════════════════════════════════════════════════════════

sim = BASE / 'simulate.py'

# Replace symmetric LP objective with asymmetric buy/sell vectors
patch(sim,
    '        prices = np.array(prices_vals, dtype=float)\n'
    '\n'
    '        # Objective vector: minimise [p, −p*RTE] @ [c, d]\n'
    '        c_obj = np.concatenate([prices, -prices * ROUND_TRIP_EFF])',

    '        # ── Tariff-mode asymmetric price vectors ─────────────────────────────\n'
    '        # Re-read config each call so a toggle takes effect on the next slot\n'
    '        _t_cfg   = _cfg.load_config()\n'
    '        _tariff  = _t_cfg.get("tariff_mode", "agile")\n'
    '        _imp_mod = float(_t_cfg.get("optimise_import_mod_p", 3.0))\n'
    '        _exp_mod = float(_t_cfg.get("optimise_export_mod_p", 3.0))\n'
    '        buy_vals  = list(prices_vals)   # effective buy  price per slot (p/kWh)\n'
    '        sell_vals = list(prices_vals)   # effective sell price per slot (p/kWh)\n'
    '        if _tariff in (\'split\', \'optimise\'):\n'
    '            # E.ON import discount 00:00-06:00 UK time (Agile slots are UTC)\n'
    '            for _i, _s in enumerate(price_slots):\n'
    '                try:\n'
    '                    _h = datetime.fromisoformat(\n'
    '                        _s[\'valid_from\'].replace(\'Z\', \'+00:00\')).hour\n'
    '                    if 0 <= _h < 6:\n'
    '                        buy_vals[_i] = max(0.0, prices_vals[_i] - _imp_mod)\n'
    '                except Exception:\n'
    '                    pass\n'
    '        if _tariff == \'optimise\':\n'
    '            # E.ON export bonus 16:00-19:00 UK time\n'
    '            for _i, _s in enumerate(price_slots):\n'
    '                try:\n'
    '                    _h = datetime.fromisoformat(\n'
    '                        _s[\'valid_from\'].replace(\'Z\', \'+00:00\')).hour\n'
    '                    if 16 <= _h < 19:\n'
    '                        sell_vals[_i] = prices_vals[_i] + _exp_mod\n'
    '                except Exception:\n'
    '                    pass\n'
    '        if _tariff != \'agile\':\n'
    '            print("[PLAN] Tariff: " + _tariff\n'
    '                  + "  buy_mod=" + str(-_imp_mod) + "p 00-06"\n'
    '                  + ("  sell_mod=+" + str(_exp_mod) + "p 16-19"\n'
    '                     if _tariff == \'optimise\' else ""))\n'
    '        prices  = np.array(prices_vals, dtype=float)\n'
    '        buy_p   = np.array(buy_vals,    dtype=float)\n'
    '        sell_p  = np.array(sell_vals,   dtype=float)\n'
    '\n'
    '        # Objective: minimise [buy_p, −sell_p*RTE] @ [c, d]\n'
    '        c_obj = np.concatenate([buy_p, -sell_p * ROUND_TRIP_EFF])',

    'simulate.py: asymmetric LP buy/sell vectors'
)

# Revenue calculation: use effective buy/sell prices, not raw
patch(sim,
    '            rev_p  = float(sum(\n'
    '                d_vals[i] * prices_vals[i] * ROUND_TRIP_EFF - c_vals[i] * prices_vals[i]\n'
    '                for i in range(n)\n'
    '            ))',
    '            rev_p  = float(sum(\n'
    '                d_vals[i] * sell_vals[i] * ROUND_TRIP_EFF - c_vals[i] * buy_vals[i]\n'
    '                for i in range(n)\n'
    '            ))',
    'simulate.py: revenue uses effective buy/sell prices'
)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. server.py — lp_day modifier support + /api/tariff endpoint
# ═══════════════════════════════════════════════════════════════════════════════

srv = BASE / 'server.py'

# a) Add _slot_modifiers helper + update lp_day signature
patch(srv,
    '    def lp_day(prices_p, init_soc, charge_kwh=CHARGE_KWH, export_kwh=EXPORT_G98):',
    '    def _slot_modifiers(slots, tariff_mode, imp_mod, exp_mod):\n'
    '        """(import_delta[], export_delta[]) — p/kWh adjustment per slot."""\n'
    '        n = len(slots)\n'
    '        id_ = [0.0] * n\n'
    '        ed_ = [0.0] * n\n'
    '        if tariff_mode == \'agile\':\n'
    '            return id_, ed_\n'
    '        for i, s in enumerate(slots):\n'
    '            try:\n'
    '                h = datetime.fromisoformat(\n'
    '                    s[\'valid_from\'].replace(\'Z\', \'+00:00\')).hour\n'
    '            except Exception:\n'
    '                continue\n'
    '            if tariff_mode in (\'split\', \'optimise\') and 0 <= h < 6:\n'
    '                id_[i] = -imp_mod\n'
    '            if tariff_mode == \'optimise\' and 16 <= h < 19:\n'
    '                ed_[i] = exp_mod\n'
    '        return id_, ed_\n'
    '\n'
    '    def lp_day(prices_p, init_soc, charge_kwh=CHARGE_KWH, export_kwh=EXPORT_G98,\n'
    '               import_delta=None, export_delta=None):',
    'server.py: add _slot_modifiers helper + new lp_day signature'
)

# b) lp_day body: build asymmetric b_arr / s_arr
patch(srv,
    '        p       = np.array(prices_p, dtype=float)\n'
    '        c_obj   = np.concatenate([p, -p * RTE])',
    '        p       = np.array(prices_p, dtype=float)\n'
    '        id_arr  = np.array(import_delta, dtype=float) if import_delta is not None else np.zeros(n)\n'
    '        ed_arr  = np.array(export_delta, dtype=float) if export_delta is not None else np.zeros(n)\n'
    '        b_arr   = p + id_arr   # effective buy  prices\n'
    '        s_arr   = p + ed_arr   # effective sell prices\n'
    '        c_obj   = np.concatenate([b_arr, -s_arr * RTE])',
    'server.py: lp_day asymmetric LP vectors'
)

# c) lp_day revenue: use effective buy/sell
patch(srv,
    '        rev_p = sum(d_v[i]*prices_p[i]*RTE - c_v[i]*prices_p[i] for i in range(n))',
    '        rev_p = sum(d_v[i]*s_arr[i]*RTE - c_v[i]*b_arr[i] for i in range(n))',
    'server.py: lp_day revenue uses effective buy/sell prices'
)

# d) /api/tariff endpoint — insert before the ALERTS block
patch(srv,
    '# ─────────────────────────────────────────────\n'
    '# ALERTS — baseload / SOC / grid import warnings',
    '@app.route("/api/tariff", methods=["GET", "POST"])\n'
    'def api_tariff():\n'
    '    """\n'
    '    GET  -> {tariff_mode, optimise_import_mod_p, optimise_export_mod_p}\n'
    '    POST -> {mode: "agile"|"split"|"optimise"}  — persists to node3_config.json.\n'
    '    Effect: next simulate.py run and next /api/plan call use the new mode.\n'
    '    """\n'
    '    cfg = _cfg.load_config()\n'
    '    if request.method == "GET":\n'
    '        return jsonify({\n'
    '            "tariff_mode":            cfg.get("tariff_mode", "agile"),\n'
    '            "optimise_import_mod_p":  cfg.get("optimise_import_mod_p", 3.0),\n'
    '            "optimise_export_mod_p":  cfg.get("optimise_export_mod_p", 3.0),\n'
    '        })\n'
    '    if not _check_api_key():\n'
    '        return jsonify({"error": "invalid or missing API key"}), 401\n'
    '    body = request.get_json(silent=True) or {}\n'
    '    mode = str(body.get("mode", "")).lower().strip()\n'
    '    if mode not in ("agile", "split", "optimise"):\n'
    '        return jsonify({"error": "mode must be agile | split | optimise"}), 400\n'
    '    merged = _cfg.save_config({"tariff_mode": mode})\n'
    '    print(f"[TARIFF] Mode set to: {mode}")\n'
    '    return jsonify({"tariff_mode": merged.get("tariff_mode", mode), "ok": True})\n'
    '\n'
    '\n'
    '# ─────────────────────────────────────────────\n'
    '# ALERTS — baseload / SOC / grid import warnings',
    'server.py: add /api/tariff endpoint'
)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. dashboard.html — tariff toggle UI in header + JS
# ═══════════════════════════════════════════════════════════════════════════════

dash = BASE / 'dashboard.html'

# a) Insert toggle pill before the ⚙ SETTINGS button
patch(dash,
    '      <button onclick="openSettings()" title="Battery capacity / import / export rate settings"',
    '      <!-- TARIFF MODE TOGGLE — AGILE | SPLIT | OPTIMISE -->\n'
    '      <span id="tariff-toggle"\n'
    '        style="display:inline-flex;border:1px solid rgba(88,166,255,0.35);border-radius:20px;\n'
    '               overflow:hidden;margin-right:8px;vertical-align:middle">\n'
    '        <button id="tt-agile" onclick="setTariffMode(\'agile\')"\n'
    '          title="Octopus Agile only — symmetric LP, raw EPEX spot prices&#10;Agile Import + Agile Outgoing&#10;Standing charge: ~61p/day import + ~0p/day export"\n'
    '          style="padding:3px 11px;font-size:11px;letter-spacing:0.5px;border:none;\n'
    '                 cursor:pointer;font-family:inherit;background:rgba(88,166,255,0.25);\n'
    '                 color:var(--blue);font-weight:bold">AGILE</button>\n'
    '        <button id="tt-split" onclick="setTariffMode(\'split\')"\n'
    '          title="Import E.ON Optimise (−3p 00-06 h) / Export Octopus Agile&#10;Split supplier — legal in UK&#10;Keeps Agile export spikes; E.ON import discount overnight"\n'
    '          style="padding:3px 11px;font-size:11px;letter-spacing:0.5px;border:none;\n'
    '                 border-left:1px solid rgba(88,166,255,0.35);cursor:pointer;\n'
    '                 font-family:inherit;background:transparent;color:#8b949e">SPLIT</button>\n'
    '        <button id="tt-opt" onclick="setTariffMode(\'optimise\')"\n'
    '          title="E.ON Next Optimise — import −3p 00-06 h, export +3p 16-19 h&#10;Both import and export via E.ON&#10;12-month early-bird bonus (first 1,000 customers)"\n'
    '          style="padding:3px 11px;font-size:11px;letter-spacing:0.5px;border:none;\n'
    '                 border-left:1px solid rgba(88,166,255,0.35);cursor:pointer;\n'
    '                 font-family:inherit;background:transparent;color:#8b949e">OPTIMISE</button>\n'
    '      </span>\n'
    '      <button onclick="openSettings()" title="Battery capacity / import / export rate settings"',
    'dashboard.html: insert tariff toggle pill in header'
)

# b) Add tariff toggle JS — insert before the closing </script> of the main script block
# Find a unique anchor: the last function in the main JS block
# We'll append the tariff JS just before the closing of openSettings / saveSettings area
# by inserting after the loadTariffMode call in the init section — but easier: append to end of script

# Find the settings-related JS to anchor near
TARIFF_JS = '''
// ── TARIFF TOGGLE ──────────────────────────────────────────────────────────
async function loadTariffMode() {
  try {
    const r = await fetch('/api/tariff');
    const d = await r.json();
    _applyTariffUI(d.tariff_mode || 'agile');
  } catch (e) { /* server may not have restarted yet */ }
}

function _applyTariffUI(mode) {
  const ids = {agile: 'tt-agile', split: 'tt-split', optimise: 'tt-opt'};
  for (const [m, id] of Object.entries(ids)) {
    const el = document.getElementById(id);
    if (!el) continue;
    const active = m === mode;
    el.style.background = active ? 'rgba(88,166,255,0.25)' : 'transparent';
    el.style.color      = active ? 'var(--blue)' : '#8b949e';
    el.style.fontWeight = active ? 'bold' : 'normal';
  }
  // Update SETTINGS button tooltip to show current tariff
  const modeLabel = {agile:'Agile', split:'Split (E.ON import / Agile export)', optimise:'E.ON Optimise'}[mode] || mode;
  const sb = document.querySelector('button[onclick="openSettings()"]');
  if (sb) sb.title = 'Battery / rates settings  |  Tariff: ' + modeLabel;
}

async function setTariffMode(mode) {
  try {
    const r = await fetch('/api/tariff', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode}),
    });
    const d = await r.json();
    if (d.error) { console.warn('[tariff]', d.error); return; }
    _applyTariffUI(d.tariff_mode || mode);
    console.log('[tariff] Mode set to:', d.tariff_mode);
  } catch (e) {
    console.error('[tariff] toggle failed', e);
  }
}
'''

# Insert tariff JS just before the closing </script> of the large inline script
# Anchor: the very last </script> after a bunch of JS content
# We look for a unique section ending just before the last </script>
# Use the closeSessions call area as anchor
patch(dash,
    'async function saveSettings() {',
    TARIFF_JS + '\nasync function saveSettings() {',
    'dashboard.html: inject tariff toggle JS'
)

init_anchor_old = 'async function openSettings() {'
init_anchor_new = ('// Initialise tariff toggle UI on load\n'
                   'document.addEventListener(\'DOMContentLoaded\', function() {\n'
                   '  loadTariffMode();\n'
                   '});\n\n'
                   'async function openSettings() {')
patch(dash, init_anchor_old, init_anchor_new,
      'dashboard.html: call loadTariffMode on DOMContentLoaded')


print("\n[DONE] All patches applied.")
print("Deploy: scp /tmp/deploy_tariff_toggle.py pi@192.168.1.157:/tmp/ && "
      "ssh pi@192.168.1.157 'python3 /tmp/deploy_tariff_toggle.py && docker restart node3-portal'")
