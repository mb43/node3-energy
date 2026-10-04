#!/usr/bin/env python3
"""
deploy_standing_charges.py  — Dovecote Node-3
Run AFTER deploy_tariff_toggle.py.

Patches:
  1. node3_config.py  — export_kw 6.0→5.5, import_kw 10.0→9.0 (miner confirmed on inverter AC)
  2. node3_config.py  — add standing_charge_import_p_day + standing_charge_export_p_day to DEFAULTS
  3. node3_config.py  — add new fields to NON_NEGATIVE in save_config
  4. server.py        — /api/settings accepts the two new keys
  5. server.py        — backtest extracts standing charges from config
  6. server.py        — backtest result includes standing_charge_annual_gbp, lp_net_gbp, lp_g99_net_gbp
  7. dashboard.html   — settings modal: two new input fields
  8. dashboard.html   — openSettings() loads new fields
  9. dashboard.html   — saveSettings() posts + validates new fields
 10. node3_config.json — live JSON: import_kw → 9.0 (takes effect immediately)
"""
import json
import shutil
from pathlib import Path

BASE = Path('/home/pi/node3')


def patch(path: Path, old: str, new: str, label: str):
    text = path.read_text('utf-8')
    count = text.count(old)
    assert count == 1, f"[{label}] Expected 1 match, got {count}:\n  {repr(old[:160])}"
    path.write_text(text.replace(old, new, 1), 'utf-8')
    print(f"[OK] {label}")


# ── Backups ──────────────────────────────────────────────────────────────────
for f in ['node3_config.py', 'server.py', 'dashboard.html']:
    src = BASE / f
    if src.exists():
        shutil.copy(src, str(src) + '.bak_standing')
print("[OK] Backups done")


# ═══════════════════════════════════════════════════════════════════════════════
# 1–3. node3_config.py
# ═══════════════════════════════════════════════════════════════════════════════
cfg = BASE / 'node3_config.py'

# 1a. Fix export_kw default: 6.0 → 5.5  (SSEN G99 confirmed at 5.5 kW)
patch(cfg,
    '    "export_kw":      6.0,  # discharge rate — export limit (self-imposed; must not exceed\n'
    '                             # the real DNO cap for whichever connection is active — 7.36kW\n'
    '                             # for G98/32A, 11.5kW for G99/50A)',
    '    "export_kw":      5.5,  # discharge rate — SSEN G99 confirmed at 5.5 kW\n'
    '                             # (approval ref 260420-000198/FJJ907/1).\n'
    '                             # Override in settings if wiring changes.',
    'node3_config: export_kw default 6.0 → 5.5 (SSEN G99)')

# 1b. Fix import_kw default: 10.0 → 9.0  (Fox ESS KH10.5 with Z15 miner on AC output)
patch(cfg,
    '    "import_kw":     10.0,  # charge rate — inverter/import limit',
    '    "import_kw":      9.0,  # charge rate — Fox ESS KH10.5 (10.5 kW) minus Z15 miner\n'
    '                             # constant baseload 1.5 kW on inverter AC output = 9.0 kW effective',
    'node3_config: import_kw default 10.0 → 9.0 (miner on inverter)')

# 2. Add standing charge fields to DEFAULTS (post-tariff-toggle: last field is optimise_export_mod_p)
patch(cfg,
    '    "optimise_export_mod_p": 3.0,      # p/kWh export bonus 16:00-19:00   (E.ON Optimise early-bird)\n}',
    '    "optimise_export_mod_p": 3.0,      # p/kWh export bonus 16:00-19:00   (E.ON Optimise early-bird)\n'
    '    # ── Standing charges (added Oct 2026) ────────────────────────────────────\n'
    '    "standing_charge_import_p_day": 62.22,  # daily standing charge on import tariff (p/day)\n'
    '                                            # Octopus Agile H region ≈ 62.22p/day incl VAT\n'
    '    "standing_charge_export_p_day":  0.0,  # daily standing charge on export contract (p/day)\n'
    '                                            # Octopus Agile Outgoing = 0p/day\n'
    '}',
    'node3_config: add standing charge fields to DEFAULTS')

# 3. Add standing charge keys to NON_NEGATIVE in save_config
# After tariff_toggle runs, Pi has: NON_NEGATIVE = {"baseload_kw", "house_kwh_day"}
# (Pi's file is older — no baseload_kw_consumer/svt_ref_p/subscription_pcm in NON_NEGATIVE)
patch(cfg,
    '    NON_NEGATIVE = {"baseload_kw", "house_kwh_day"}\n'
    '    STRING_KEYS  = {"tariff_mode"}',
    '    NON_NEGATIVE = {"baseload_kw", "house_kwh_day",\n'
    '                    "standing_charge_import_p_day", "standing_charge_export_p_day"}\n'
    '    STRING_KEYS  = {"tariff_mode"}',
    'node3_config: save_config NON_NEGATIVE includes standing charge fields')


# ═══════════════════════════════════════════════════════════════════════════════
# 4–6. server.py
# ═══════════════════════════════════════════════════════════════════════════════
srv = BASE / 'server.py'

# 4. /api/settings: add standing charge keys to accepted set + NON_NEGATIVE_KEYS
patch(srv,
    '    NON_NEGATIVE_KEYS = {"baseload_kw", "house_kwh_day"}\n'
    '    for key in ("battery_kwh", "import_kw", "export_kw", "min_soc_pct",\n'
    '                "baseload_kw", "house_kwh_day", "svt_ref_p", "subscription_pcm"):',
    '    NON_NEGATIVE_KEYS = {"baseload_kw", "house_kwh_day",\n'
    '                         "standing_charge_import_p_day", "standing_charge_export_p_day"}\n'
    '    for key in ("battery_kwh", "import_kw", "export_kw", "min_soc_pct",\n'
    '                "baseload_kw", "house_kwh_day", "svt_ref_p", "subscription_pcm",\n'
    '                "standing_charge_import_p_day", "standing_charge_export_p_day"):',
    'server: /api/settings accepts standing charge keys')

# 5. Backtest config block: extract standing charges after EXPORT_G98 line
patch(srv,
    '    EXPORT_G98     = _lp_cfg["export_kw"] * 0.5   # configurable G98 export rate',
    '    EXPORT_G98     = _lp_cfg["export_kw"] * 0.5   # configurable G98 export rate\n'
    '    _SC_IMPORT_P   = _lp_cfg.get("standing_charge_import_p_day", 62.22)  # p/day\n'
    '    _SC_EXPORT_P   = _lp_cfg.get("standing_charge_export_p_day", 0.0)   # p/day\n'
    '    _SC_TOTAL_P_DAY = _SC_IMPORT_P + _SC_EXPORT_P  # total p/day standing charges',
    'server: backtest extracts standing charge config values')

# 6. Backtest result dict: add net P&L fields
patch(srv,
    "        'battery_kwh':         BATTERY,\n"
    "        'run_at':              datetime.now(timezone.utc).isoformat(),\n"
    "    }",
    "        'battery_kwh':         BATTERY,\n"
    "        'run_at':              datetime.now(timezone.utc).isoformat(),\n"
    "        # ── Net P&L after standing charges ───────────────────────────────────\n"
    "        'standing_charge_annual_gbp':  round((_SC_IMPORT_P + _SC_EXPORT_P) * 365 / 100, 2),\n"
    "        'standing_charge_period_gbp':  round(_SC_TOTAL_P_DAY * len(days_sorted) / 100, 2),\n"
    "        'lp_net_gbp':          round(lp_total  - _SC_TOTAL_P_DAY * len(days_sorted) / 100, 2),\n"
    "        'lp_g99_net_gbp':      round(g99_total - _SC_TOTAL_P_DAY * len(days_sorted) / 100, 2),\n"
    "    }",
    'server: backtest result includes standing charge + net P&L fields')


# ═══════════════════════════════════════════════════════════════════════════════
# 7–9. dashboard.html
# ═══════════════════════════════════════════════════════════════════════════════
dash = BASE / 'dashboard.html'

# 7. Settings modal: add two new input fields between baseload hint and settings-msg
patch(dash,
    '      <div id="set-baseload-hint" style="font-size:10px;color:#8b949e;margin-bottom:16px">Z15 miner ≈ 1.51 kW = 36 kWh/day. Total daily load shown above.</div>\n'
    '\n'
    '      <div id="settings-msg"',
    '      <div id="set-baseload-hint" style="font-size:10px;color:#8b949e;margin-bottom:16px">Z15 miner ≈ 1.51 kW = 36 kWh/day. Total daily load shown above.</div>\n'
    '\n'
    '      <label style="display:block;font-size:11px;color:#8b949e;margin-bottom:3px">Import standing charge (p/day)</label>\n'
    '      <input type="number" id="set-standing-import" step="0.1" min="0" style="width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;padding:7px 10px;margin-bottom:12px;font-size:13px">\n'
    '\n'
    '      <label style="display:block;font-size:11px;color:#8b949e;margin-bottom:3px">Export standing charge (p/day)</label>\n'
    '      <input type="number" id="set-standing-export" step="0.1" min="0" style="width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;padding:7px 10px;margin-bottom:4px;font-size:13px">\n'
    '      <div style="font-size:10px;color:#8b949e;margin-bottom:16px">Deducted from backtest P&amp;L. Agile import ≈ 62.22p/day; Agile Outgoing = 0p/day.</div>\n'
    '\n'
    '      <div id="settings-msg"',
    'dashboard: settings modal adds standing charge input fields')

# 8. openSettings(): load new fields from cfg
patch(dash,
    "    document.getElementById('set-baseload-kw').value    = cfg.baseload_kw ?? 0;\n"
    "    _updateBaseloadHint(cfg);",
    "    document.getElementById('set-baseload-kw').value    = cfg.baseload_kw ?? 0;\n"
    "    document.getElementById('set-standing-import').value = cfg.standing_charge_import_p_day ?? 62.22;\n"
    "    document.getElementById('set-standing-export').value = cfg.standing_charge_export_p_day ?? 0;\n"
    "    _updateBaseloadHint(cfg);",
    'dashboard: openSettings loads standing charge fields')

# 9a. saveSettings(): add new fields to POST body
patch(dash,
    "    baseload_kw:   parseFloat(document.getElementById('set-baseload-kw').value),\n"
    "  };\n"
    "  const mustBePositive = ['battery_kwh','import_kw','export_kw','min_soc_pct','house_kwh_day'];",
    "    baseload_kw:   parseFloat(document.getElementById('set-baseload-kw').value),\n"
    "    standing_charge_import_p_day: parseFloat(document.getElementById('set-standing-import').value),\n"
    "    standing_charge_export_p_day: parseFloat(document.getElementById('set-standing-export').value),\n"
    "  };\n"
    "  const mustBePositive = ['battery_kwh','import_kw','export_kw','min_soc_pct','house_kwh_day'];",
    'dashboard: saveSettings body includes standing charge fields')

# 9b. saveSettings(): validate standing charges >= 0
patch(dash,
    "  if (!isFinite(body.baseload_kw) || body.baseload_kw < 0) {\n"
    "    msg.textContent = 'baseload_kw must be 0 or positive.'; return;\n"
    "  }\n"
    "  try {",
    "  if (!isFinite(body.baseload_kw) || body.baseload_kw < 0) {\n"
    "    msg.textContent = 'baseload_kw must be 0 or positive.'; return;\n"
    "  }\n"
    "  for (const k of ['standing_charge_import_p_day','standing_charge_export_p_day']) {\n"
    "    if (!isFinite(body[k]) || body[k] < 0) { msg.textContent = `${k} must be >= 0.`; return; }\n"
    "  }\n"
    "  try {",
    'dashboard: saveSettings validates standing charges >= 0')


# ═══════════════════════════════════════════════════════════════════════════════
# 10. node3_config.json — update live config: import_kw → 9.0
# ═══════════════════════════════════════════════════════════════════════════════
cfg_json = BASE / 'node3_config.json'
if cfg_json.exists():
    shutil.copy(cfg_json, str(cfg_json) + '.bak_standing')
    data = json.loads(cfg_json.read_text('utf-8'))
    data['import_kw'] = 9.0
    # Seed standing charges if not already present
    data.setdefault('standing_charge_import_p_day', 62.22)
    data.setdefault('standing_charge_export_p_day', 0.0)
    cfg_json.write_text(json.dumps(data, indent=2), 'utf-8')
    print(f"[OK] node3_config.json: import_kw→9.0, standing charges seeded")
else:
    print("[SKIP] node3_config.json not found — defaults will apply on first run")


print()
print("=" * 60)
print("deploy_standing_charges.py COMPLETE")
print("  export_kw default: 6.0 → 5.5 (SSEN G99)")
print("  import_kw default: 10.0 → 9.0 (Fox KH10.5 − Z15 miner)")
print("  import_kw live:    updated in node3_config.json")
print("  Standing charges:  added to config + settings + backtest")
print()
print("Restart docker: docker restart node3-portal")
print("=" * 60)
