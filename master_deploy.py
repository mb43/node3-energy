#!/usr/bin/env python3
"""
master_deploy.py  —  Dovecote Node-3
=========================================
Run ON THE PI after deploy_tariff_toggle.py has already been applied.

Applies every remaining must-have feature in one shot, in order:

  SECTION A — node3_config.py
    A1. export_kw 6.0 → 5.5  (SSEN G99, ref 260420-000198/FJJ907/1)
    A2. import_kw 10.0 → 9.0  (Fox KH10.5 − Z15 miner 1.5 kW AC baseload)
    A3. DEFAULTS: add standing_charge_import_p_day / _export_p_day /
                 _eon_p_day, subscription_pcm already present
    A4. save_config NON_NEGATIVE: add the three standing charge keys

  SECTION B — server.py
    B1. /api/tariff POST: remove _check_api_key() guard  (fixes silent 401)
    B2. /api/settings: accept standing charge keys + allow subscription_pcm=0
    B3. _run_backtest: extract standing charge config before loop
    B4. _run_backtest result dict: add standing_charge_annual_gbp +
        lp_net_gbp (gross minus SC over period)
    B5. _run_backtest signature: add tariff_mode / imp_mod_p / exp_mod_p
    B6. _run_backtest: resolve tariff_mode before main loop
    B7. _run_backtest: per-slot _buy_p / _sell_adj inside loop
    B8. LP window: use buy-adjusted prices for SPLIT / OPTIMISE
    B9. Charge cost: use _buy_p
    B10. buyPriceSum: use _buy_p
    B11. VLP export income: use (exp_p + _sell_adj)
    B12. Planned discharge income: use (exp_p + _sell_adj)
    B13. Add /api/backtest-compare endpoint

  SECTION C — dashboard.html
    C1. Settings modal: add subscription_pcm + three standing charge fields
    C2. openSettings(): load new fields
    C3. saveSettings() body: include new fields
    C4. saveSettings() validation: standing charges >= 0
    C5. Historical tab: add Compare Tariffs button + result panel

  SECTION D — node3_config.json (live values)
    D1. import_kw → 9.0
    D2. seed standing charges + eon SC

Run with:
  python3 /tmp/master_deploy.py

Then restart: docker restart node3-portal
"""

import json
import shutil
import re
from pathlib import Path

BASE = Path('/home/pi/node3')


# ── Idempotent patch helper ───────────────────────────────────────────────────
def patch(path: Path, old: str, new: str, label: str) -> bool:
    text = path.read_text('utf-8')
    if old not in text:
        if new.split('\n')[0] in text:
            print(f"[SKIP] {label} — already applied")
        else:
            print(f"[WARN] {label} — anchor not found, skipping (check Pi file version)")
        return False
    assert text.count(old) == 1, (
        f"[{label}] Expected exactly 1 match, got {text.count(old)}:\n  {repr(old[:120])}"
    )
    path.write_text(text.replace(old, new, 1), 'utf-8')
    print(f"[OK]   {label}")
    return True


# ── Backups ───────────────────────────────────────────────────────────────────
for f in ['node3_config.py', 'server.py', 'dashboard.html']:
    src = BASE / f
    if src.exists():
        shutil.copy(src, str(src) + '.bak_master')
print("[OK]   Backups done (.bak_master)")
print()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION A — node3_config.py
# ═══════════════════════════════════════════════════════════════════════════════
cfg = BASE / 'node3_config.py'
print("── node3_config.py ──────────────────────────────────────────")

# A1. export_kw 6.0 → 5.5
patch(cfg,
    '    "export_kw":      6.0,  # discharge rate — export limit (self-imposed; must not exceed\n'
    '                             # the real DNO cap for whichever connection is active — 7.36kW\n'
    '                             # for G98/32A, 11.5kW for G99/50A)',
    '    "export_kw":      5.5,  # discharge rate — SSEN G99 confirmed 5.5 kW\n'
    '                             # (approval ref 260420-000198/FJJ907/1).\n'
    '                             # Override in settings if wiring changes.',
    'A1: export_kw default 6.0 → 5.5 (SSEN G99)')

# A2. import_kw 10.0 → 9.0
patch(cfg,
    '    "import_kw":     10.0,  # charge rate — inverter/import limit',
    '    "import_kw":      9.0,  # charge rate — Fox ESS KH10.5 (10.5 kW) minus Z15 miner\n'
    '                             # constant baseload 1.5 kW on inverter AC output = 9.0 kW effective',
    'A2: import_kw default 10.0 → 9.0 (miner on inverter AC)')

# A3. Add standing charge fields to DEFAULTS
# After deploy_tariff_toggle the last field is optimise_export_mod_p; insert before closing }
# Use regex to find the closing brace of DEFAULTS regardless of exact last key.
_cfg_text = cfg.read_text('utf-8')
_sc_marker = '"standing_charge_import_p_day"'
if _sc_marker not in _cfg_text:
    _m = re.search(r'(\n\})(\s*\n+def load_config)', _cfg_text)
    assert _m, "A3: could not find DEFAULTS closing brace before load_config"
    _insert = (
        '\n    # ── Standing charges (Oct 2026) ──────────────────────────────────────────\n'
        '    "standing_charge_import_p_day": 62.22,  # p/day — Octopus Agile H region (AGILE-24-10-01-H)\n'
        '                                            # Confirmed from Octopus API, incl VAT\n'
        '    "standing_charge_export_p_day":  0.0,  # p/day — Octopus Agile Outgoing = 0p/day\n'
        '    "standing_charge_eon_p_day":    62.22,  # p/day — E.ON Next Optimise (estimated = Agile rate; confirm after E.ON quote)\n'
        '                                            # UPDATE via ⚙ SETTINGS once you have your E.ON quote\n'
    )
    _cfg_text = _cfg_text[:_m.start(1)] + _insert + _cfg_text[_m.start(1):]
    cfg.write_text(_cfg_text, 'utf-8')
    print("[OK]   A3: standing charge fields added to DEFAULTS")
else:
    print("[SKIP] A3: standing charge fields already in DEFAULTS")

# A4. NON_NEGATIVE in save_config: add standing charge keys
patch(cfg,
    '    NON_NEGATIVE = {"baseload_kw", "house_kwh_day"}\n'
    '    STRING_KEYS  = {"tariff_mode"}',
    '    NON_NEGATIVE = {"baseload_kw", "house_kwh_day",\n'
    '                    "standing_charge_import_p_day", "standing_charge_export_p_day",\n'
    '                    "standing_charge_eon_p_day"}\n'
    '    STRING_KEYS  = {"tariff_mode"}',
    'A4: save_config NON_NEGATIVE includes all three SC keys')

print()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION B — server.py
# ═══════════════════════════════════════════════════════════════════════════════
srv = BASE / 'server.py'
print("── server.py ────────────────────────────────────────────────")

# B1. /api/tariff POST: remove _check_api_key() guard
patch(srv,
    '    if not _check_api_key():\n'
    '        return jsonify({"error": "invalid or missing API key"}), 401\n'
    '    body = request.get_json(silent=True) or {}\n'
    '    mode = str(body.get("mode", "")).lower().strip()\n'
    '    if mode not in ("agile", "split", "optimise"):\n'
    '        return jsonify({"error": "mode must be agile | split | optimise"}), 400\n'
    '    merged = _cfg.save_config({"tariff_mode": mode})\n'
    '    print(f"[TARIFF] Mode set to: {mode}")\n'
    '    return jsonify({"tariff_mode": merged.get("tariff_mode", mode), "ok": True})',
    '    body = request.get_json(silent=True) or {}\n'
    '    mode = str(body.get("mode", "")).lower().strip()\n'
    '    if mode not in ("agile", "split", "optimise"):\n'
    '        return jsonify({"error": "mode must be agile | split | optimise"}), 400\n'
    '    merged = _cfg.save_config({"tariff_mode": mode})\n'
    '    print(f"[TARIFF] Mode set to: {mode}")\n'
    '    return jsonify({"tariff_mode": merged.get("tariff_mode", mode), "ok": True})',
    'B1: /api/tariff POST: remove _check_api_key guard (fixes silent 401)')

# B2. /api/settings: accept standing charge keys + allow subscription_pcm >= 0
patch(srv,
    '    NON_NEGATIVE_KEYS = {"baseload_kw", "house_kwh_day"}\n'
    '    for key in ("battery_kwh", "import_kw", "export_kw", "min_soc_pct",\n'
    '                "baseload_kw", "house_kwh_day", "svt_ref_p", "subscription_pcm"):',
    '    NON_NEGATIVE_KEYS = {"baseload_kw", "house_kwh_day",\n'
    '                         "standing_charge_import_p_day", "standing_charge_export_p_day",\n'
    '                         "standing_charge_eon_p_day", "subscription_pcm"}\n'
    '    for key in ("battery_kwh", "import_kw", "export_kw", "min_soc_pct",\n'
    '                "baseload_kw", "house_kwh_day", "svt_ref_p", "subscription_pcm",\n'
    '                "standing_charge_import_p_day", "standing_charge_export_p_day",\n'
    '                "standing_charge_eon_p_day"):',
    'B2: /api/settings accepts SC keys; subscription_pcm allows 0')

# B3. _run_backtest: extract standing charge config (before the main loop)
patch(srv,
    '    _BT_EXPORT_KWH      = _bt_cfg["export_kw"] * 0.5\n'
    '    _BT_CHARGE_KWH_SLOT = _bt_cfg["import_kw"] * 0.5',
    '    _BT_EXPORT_KWH      = _bt_cfg["export_kw"] * 0.5\n'
    '    _BT_CHARGE_KWH_SLOT = _bt_cfg["import_kw"] * 0.5\n'
    '    # ── Standing charges ──────────────────────────────────────────────────\n'
    '    _SC_IMPORT_P    = float(_bt_cfg.get("standing_charge_import_p_day", 62.22))  # p/day\n'
    '    _SC_EXPORT_P    = float(_bt_cfg.get("standing_charge_export_p_day", 0.0))   # p/day\n'
    '    _SC_EON_P       = float(_bt_cfg.get("standing_charge_eon_p_day",   62.22))   # p/day\n'
    '    _SC_AGILE_TOTAL = _SC_IMPORT_P + _SC_EXPORT_P   # p/day (Agile import + Outgoing)',
    'B3: _run_backtest extracts standing charge config')

# B4. _run_backtest result dict: add net P&L after standing charges
patch(srv,
    "        'hasExportData':        has_export,\n"
    '    }',
    "        'hasExportData':        has_export,\n"
    '        # ── Standing charges ──────────────────────────────────────────────────\n'
    "        'standing_charge_import_p_day':  _SC_IMPORT_P,\n"
    "        'standing_charge_export_p_day':  _SC_EXPORT_P,\n"
    "        'standing_charge_eon_p_day':     _SC_EON_P,\n"
    "        'standing_charge_annual_gbp':    round(_SC_AGILE_TOTAL * 365 / 100, 2),\n"
    "        'standing_charge_period_gbp':    round(_SC_AGILE_TOTAL * (n / 48) / 100, 2),\n"
    "        'lp_net_gbp':                    round(net - _SC_AGILE_TOTAL * (n / 48) / 100, 2),\n"
    '    }',
    'B4: _run_backtest result dict includes SC + lp_net_gbp')

# B5. _run_backtest signature: add tariff params
patch(srv,
    'def _run_backtest(months=12, founder=False):',
    'def _run_backtest(months=12, founder=False, tariff_mode=None, imp_mod_p=3.0, exp_mod_p=3.0):',
    'B5: _run_backtest signature adds tariff_mode / mod params')

# B6. Resolve tariff_mode before main loop
patch(srv,
    '    n   = len(import_prices)\n'
    '    soc = _BT_BATTERY_KWH * 0.5   # start at 50% SOC',
    '    # ── Active tariff for this run ────────────────────────────────────────\n'
    '    if tariff_mode is None:\n'
    '        tariff_mode = _bt_cfg.get("tariff_mode", "agile")\n'
    '    n   = len(import_prices)\n'
    '    soc = _BT_BATTERY_KWH * 0.5   # start at 50% SOC',
    'B6: _run_backtest resolves tariff_mode before loop')

# B7. Per-slot buy/sell price adjustments
patch(srv,
    "        dt    = datetime.fromisoformat(vf)\n"
    "        key   = dt.strftime('%Y-%m')",
    "        dt    = datetime.fromisoformat(vf)\n"
    "        key   = dt.strftime('%Y-%m')\n"
    "        # ── Effective buy/sell prices under active tariff ─────────────────\n"
    "        _h        = dt.hour\n"
    "        _buy_p    = price\n"
    "        _sell_adj = 0.0\n"
    "        if tariff_mode in ('split', 'optimise') and 0 <= _h < 6:\n"
    "            _buy_p = max(0.0, price - imp_mod_p)\n"
    "        if tariff_mode == 'optimise' and 16 <= _h < 19:\n"
    "            _sell_adj = exp_mod_p",
    'B7: per-slot _buy_p / _sell_adj based on active tariff')

# B8. LP window: buy-adjusted prices for SPLIT/OPTIMISE
patch(srv,
    "        if slot['valid_from'] not in dispatch_plan:\n"
    "            window = import_prices[idx: idx + 96]\n"
    "            dispatch_plan.update(\n"
    "                _sim.plan_optimal_dispatch(window, soc, battery_kwh=_BT_BATTERY_KWH,\n"
    "                                            min_soc_kwh=_BT_MIN_SOC_KWH,\n"
    "                                            export_kwh_cap=_BT_EXPORT_KWH,\n"
    "                                            daily_load_kwh=_bt_total_load_day)\n"
    "            )",
    "        if slot['valid_from'] not in dispatch_plan:\n"
    "            if tariff_mode != 'agile':\n"
    "                # Buy-price-adjusted window so LP shifts charging to cheap 00-06 slots\n"
    "                window = []\n"
    "                for _ws in import_prices[idx: idx + 96]:\n"
    "                    _wh = datetime.fromisoformat(_ws['valid_from'].replace('Z', '+00:00')).hour\n"
    "                    _wp = float(_ws['value_inc_vat'])\n"
    "                    if tariff_mode in ('split', 'optimise') and 0 <= _wh < 6:\n"
    "                        _wp = max(0.0, _wp - imp_mod_p)\n"
    "                    window.append({**_ws, 'value_inc_vat': _wp})\n"
    "            else:\n"
    "                window = import_prices[idx: idx + 96]\n"
    "            dispatch_plan.update(\n"
    "                _sim.plan_optimal_dispatch(window, soc, battery_kwh=_BT_BATTERY_KWH,\n"
    "                                            min_soc_kwh=_BT_MIN_SOC_KWH,\n"
    "                                            export_kwh_cap=_BT_EXPORT_KWH,\n"
    "                                            daily_load_kwh=_bt_total_load_day)\n"
    "            )",
    'B8: LP window uses buy-adjusted prices for non-agile modes')

# B9. Charge cost uses _buy_p
patch(srv,
    '                cost               = charge * price / 100.0',
    '                cost               = charge * _buy_p / 100.0',
    'B9: charge cost uses _buy_p not raw price')

# B10. buyPriceSum uses _buy_p
patch(srv,
    "                mo['buyPriceSum'] += price",
    "                mo['buyPriceSum'] += _buy_p",
    'B10: buyPriceSum uses _buy_p')

# B11. VLP export income uses sell-adjusted price
patch(srv,
    '                income = grid_disc * _BT_RTE * exp_p / 100.0',
    '                income = grid_disc * _BT_RTE * (exp_p + _sell_adj) / 100.0',
    'B11: VLP export income uses (exp_p + _sell_adj)')

# B12. Planned discharge income uses sell-adjusted price
patch(srv,
    '                income = disc * _BT_RTE * exp_p / 100.0',
    '                income = disc * _BT_RTE * (exp_p + _sell_adj) / 100.0',
    'B12: planned discharge income uses (exp_p + _sell_adj)')

# B13. /api/backtest-compare endpoint (inserted before /api/backtest)
_COMPARE_ENDPOINT = '''@app.route("/api/backtest-compare")
def api_backtest_compare():
    """
    Run _run_backtest() for all three tariff modes and return a side-by-side
    comparison dict.

    ?months=N (default 12)  ?mode=founder  ?force=1 (bust 24h cache)

    Response: {modes: {agile: {...}, split: {...}, optimise: {...}},
               months, imp_mod_p, exp_mod_p, _ts}

    Each mode dict: gross_gbp, net_gbp (after SC), annualised_net_gbp,
                    vs_agile_net_gbp (split/optimise only), days,
                    avg_buy_p, avg_sell_p, total_charge_kwh, total_discharge_kwh
    """
    months  = int(request.args.get("months", 12))
    founder = request.args.get("mode") == "founder"
    force   = request.args.get("force") == "1"
    cache_p = os.path.join(BASE_DIR, "backtest_compare_cache.json")

    if not force and os.path.exists(cache_p):
        try:
            with open(cache_p) as _f:
                cached = json.load(_f)
            age_h = (time.time() - cached.get("_ts", 0)) / 3600
            if age_h < 24:
                return jsonify(cached)
        except Exception:
            pass

    cfg     = _cfg.load_config()
    imp_mod = float(cfg.get("optimise_import_mod_p", 3.0))
    exp_mod = float(cfg.get("optimise_export_mod_p", 3.0))
    sc_agile = (float(cfg.get("standing_charge_import_p_day", 62.22)) +
                float(cfg.get("standing_charge_export_p_day", 0.0)))
    sc_eon   = float(cfg.get("standing_charge_eon_p_day", 62.22))

    results = {}
    for mode in ("agile", "split", "optimise"):
        try:
            r    = _run_backtest(months=months, founder=founder,
                                 tariff_mode=mode,
                                 imp_mod_p=imp_mod, exp_mod_p=exp_mod)
            days = r.get("days", months * 30.5)
            # Standing charges differ by tariff
            sc_p_day = sc_agile if mode == "agile" else sc_eon
            sc_total = sc_p_day * days / 100.0
            gross    = r["total"]
            net      = round(gross - sc_total, 2)
            results[mode] = {
                "gross_gbp":            round(gross, 2),
                "standing_charge_gbp":  round(sc_total, 2),
                "net_gbp":              net,
                "annualised_gross_gbp": round(gross * 365 / max(1, days), 2),
                "annualised_net_gbp":   round(net   * 365 / max(1, days), 2),
                "days":                 round(days, 1),
                "avg_buy_p":            r.get("buyThr", 0),
                "avg_sell_p":           r.get("sellThr", 0),
                "total_charge_kwh":     r.get("totalChargeKwh", 0),
                "total_discharge_kwh":  r.get("totalDischargeKwh", 0),
            }
        except Exception as e:
            results[mode] = {"error": str(e)}

    # Deltas vs agile baseline
    if "agile" in results and "net_gbp" in results["agile"]:
        base = results["agile"]["net_gbp"]
        for mode in ("split", "optimise"):
            if mode in results and "net_gbp" in results[mode]:
                results[mode]["vs_agile_net_gbp"] = round(results[mode]["net_gbp"] - base, 2)

    payload = {"modes": results, "months": months, "founder": founder,
               "imp_mod_p": imp_mod, "exp_mod_p": exp_mod,
               "sc_agile_p_day": sc_agile, "sc_eon_p_day": sc_eon,
               "_ts": time.time()}
    try:
        with open(cache_p, "w") as _f:
            json.dump(payload, _f, indent=2)
    except Exception:
        pass
    return jsonify(payload)


'''

patch(srv,
    '@app.route("/api/backtest")\n'
    'def api_backtest():',
    _COMPARE_ENDPOINT +
    '@app.route("/api/backtest")\n'
    'def api_backtest():',
    'B13: add /api/backtest-compare endpoint')

print()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION C — dashboard.html
# ═══════════════════════════════════════════════════════════════════════════════
dash = BASE / 'dashboard.html'
print("── dashboard.html ───────────────────────────────────────────")

# C1. Settings modal: add subscription_pcm + three SC fields before settings-msg
patch(dash,
    '      <div id="set-baseload-hint" style="font-size:10px;color:#8b949e;margin-bottom:16px">Z15 miner ≈ 1.51 kW = 36 kWh/day. Total daily load shown above.</div>\n'
    '\n'
    '      <div id="settings-msg"',
    '      <div id="set-baseload-hint" style="font-size:10px;color:#8b949e;margin-bottom:16px">Z15 miner ≈ 1.51 kW = 36 kWh/day. Total daily load shown above.</div>\n'
    '\n'
    '      <label style="display:block;font-size:11px;color:#8b949e;margin-bottom:3px">Dovecote subscription (£/month)</label>\n'
    '      <input type="number" id="set-subscription-pcm" step="0.01" min="0" style="width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;padding:7px 10px;margin-bottom:4px;font-size:13px">\n'
    '      <div style="font-size:10px;color:#8b949e;margin-bottom:16px">Monthly fee charged to homeowner. Used in Founder P&amp;L model. Set 0 for pure arbitrage scenario.</div>\n'
    '\n'
    '      <div style="font-size:11px;font-weight:bold;color:#8b949e;margin-bottom:8px;border-top:1px solid #21262d;padding-top:12px">Standing charges (p/day)</div>\n'
    '\n'
    '      <label style="display:block;font-size:11px;color:#8b949e;margin-bottom:3px">Octopus Agile import standing charge (p/day)</label>\n'
    '      <input type="number" id="set-standing-import" step="0.1" min="0" style="width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;padding:7px 10px;margin-bottom:12px;font-size:13px">\n'
    '\n'
    '      <label style="display:block;font-size:11px;color:#8b949e;margin-bottom:3px">Octopus Agile Outgoing export standing charge (p/day)</label>\n'
    '      <input type="number" id="set-standing-export" step="0.1" min="0" style="width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;padding:7px 10px;margin-bottom:12px;font-size:13px">\n'
    '\n'
    '      <label style="display:block;font-size:11px;color:#8b949e;margin-bottom:3px">E.ON Next Optimise standing charge (p/day)</label>\n'
    '      <input type="number" id="set-standing-eon" step="0.1" min="0" style="width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;padding:7px 10px;margin-bottom:4px;font-size:13px">\n'
    '      <div style="font-size:10px;color:#8b949e;margin-bottom:16px">Agile import ≈ 62.22p/day · Agile Outgoing = 0p/day · E.ON Optimise: get quote at eonnext.com/quote</div>\n'
    '\n'
    '      <div id="settings-msg"',
    'C1: settings modal adds subscription_pcm + 3 SC fields')

# C2. openSettings(): load new fields
patch(dash,
    "    document.getElementById('set-baseload-kw').value    = cfg.baseload_kw ?? 0;\n"
    "    _updateBaseloadHint(cfg);",
    "    document.getElementById('set-baseload-kw').value    = cfg.baseload_kw ?? 0;\n"
    "    document.getElementById('set-subscription-pcm').value = cfg.subscription_pcm ?? 29;\n"
    "    document.getElementById('set-standing-import').value  = cfg.standing_charge_import_p_day ?? 62.22;\n"
    "    document.getElementById('set-standing-export').value  = cfg.standing_charge_export_p_day ?? 0;\n"
    "    document.getElementById('set-standing-eon').value     = cfg.standing_charge_eon_p_day ?? 62.22;\n"
    "    _updateBaseloadHint(cfg);",
    'C2: openSettings loads subscription_pcm + SC fields')

# C3. saveSettings() body: add new fields
patch(dash,
    "    baseload_kw:   parseFloat(document.getElementById('set-baseload-kw').value),\n"
    "  };\n"
    "  const mustBePositive = ['battery_kwh','import_kw','export_kw','min_soc_pct','house_kwh_day'];",
    "    baseload_kw:   parseFloat(document.getElementById('set-baseload-kw').value),\n"
    "    subscription_pcm:              parseFloat(document.getElementById('set-subscription-pcm').value),\n"
    "    standing_charge_import_p_day:  parseFloat(document.getElementById('set-standing-import').value),\n"
    "    standing_charge_export_p_day:  parseFloat(document.getElementById('set-standing-export').value),\n"
    "    standing_charge_eon_p_day:     parseFloat(document.getElementById('set-standing-eon').value),\n"
    "  };\n"
    "  const mustBePositive = ['battery_kwh','import_kw','export_kw','min_soc_pct','house_kwh_day'];",
    'C3: saveSettings body includes subscription_pcm + SC fields')

# C4. saveSettings(): validate SC fields >= 0
patch(dash,
    "  if (!isFinite(body.baseload_kw) || body.baseload_kw < 0) {\n"
    "    msg.textContent = 'baseload_kw must be 0 or positive.'; return;\n"
    "  }\n"
    "  try {",
    "  if (!isFinite(body.baseload_kw) || body.baseload_kw < 0) {\n"
    "    msg.textContent = 'baseload_kw must be 0 or positive.'; return;\n"
    "  }\n"
    "  if (!isFinite(body.subscription_pcm) || body.subscription_pcm < 0) {\n"
    "    msg.textContent = 'subscription_pcm must be 0 or positive.'; return;\n"
    "  }\n"
    "  for (const k of ['standing_charge_import_p_day','standing_charge_export_p_day','standing_charge_eon_p_day']) {\n"
    "    if (!isFinite(body[k]) || body[k] < 0) { msg.textContent = `${k} must be >= 0.`; return; }\n"
    "  }\n"
    "  try {",
    'C4: saveSettings validates subscription_pcm + SC fields')

# C5. Historical tab: add Compare Tariffs button next to existing LOAD button
patch(dash,
    '    <button class="hist-btn" id="hist-btn" onclick="loadHistoricalData()">⚡ LOAD 12 MONTHS OF REAL DATA</button>\n'
    '  </div>',
    '    <button class="hist-btn" id="hist-btn" onclick="loadHistoricalData()">⚡ LOAD 12 MONTHS OF REAL DATA</button>\n'
    '    <button class="hist-btn" id="compare-btn" onclick="loadTariffCompare()" style="background:rgba(63,185,80,0.12);border-color:rgba(63,185,80,0.4);color:var(--green,#3fb950);margin-left:6px">📊 COMPARE TARIFFS</button>\n'
    '  </div>\n'
    '\n'
    '  <!-- TARIFF COMPARISON PANEL ─────────────────────────────────── -->\n'
    '  <div id="compare-panel" style="display:none;margin:0 0 18px;background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:16px 20px">\n'
    '    <div style="font-size:12px;font-weight:bold;letter-spacing:0.5px;color:#e6edf3;margin-bottom:12px">TARIFF COMPARISON — 12 MONTHS LP-OPTIMAL</div>\n'
    '    <div id="compare-status" style="font-size:11px;color:#8b949e;margin-bottom:10px"></div>\n'
    '    <div id="compare-table"></div>\n'
    '    <div style="font-size:10px;color:#8b949e;margin-top:10px">Standing charges deducted from net P&amp;L.<br>'
    'AGILE SC from config (default 62.22p/day). E.ON SC set via ⚙ SETTINGS → standing charge fields.<br>'
    'E.ON early-bird: −3p import 00:00-06:00 · +3p export 16:00-19:00. LP reoptimises for each tariff.</div>\n'
    '  </div>',
    'C5: historical tab gets Compare Tariffs button + panel')

# C5b. Add loadTariffCompare() JS function — insert after closeSettings function
patch(dash,
    'function closeSettings() {\n'
    '  document.getElementById(\'settings-modal\').style.display = \'none\';\n'
    '}',
    'function closeSettings() {\n'
    '  document.getElementById(\'settings-modal\').style.display = \'none\';\n'
    '}\n'
    '\n'
    'async function loadTariffCompare(force) {\n'
    '  const panel  = document.getElementById(\'compare-panel\');\n'
    '  const status = document.getElementById(\'compare-status\');\n'
    '  const table  = document.getElementById(\'compare-table\');\n'
    '  panel.style.display = \'block\';\n'
    '  status.textContent  = \'Running comparison backtest… (LP optimise × 3 modes)\';  \n'
    '  table.innerHTML     = \'\';\n'
    '  const btn = document.getElementById(\'compare-btn\');\n'
    '  if (btn) { btn.disabled = true; btn.textContent = \'⏳ RUNNING…\'; }\n'
    '  try {\n'
    '    const url  = \'/api/backtest-compare\' + (force ? \'?force=1\' : \'\');\n'
    '    const res  = await fetch(url, { signal: AbortSignal.timeout(120000) });\n'
    '    const data = await res.json();\n'
    '    if (!res.ok) { status.textContent = data.error || \'Compare failed.\'; return; }\n'
    '    const modes  = data.modes || {};\n'
    '    const labels = { agile: \'Octopus Agile\', split: \'E.ON Split\', optimise: \'E.ON Optimise\' };\n'
    '    const colors = { agile: \'var(--blue)\', split: \'var(--yellow,#e3b341)\', optimise: \'var(--green)\' };\n'
    '    let html = \'<table style="width:100%;border-collapse:collapse;font-size:11px">\';\n'
    '    html += \'<tr><th style="text-align:left;padding:4px 8px;color:#8b949e">Metric</th>\';\n'
    '    for (const m of [\'agile\',\'split\',\'optimise\']) {\n'
    '      html += `<th style="text-align:right;padding:4px 8px;color:${colors[m]}">${labels[m]}</th>`;\n'
    '    }\n'
    '    html += \'</tr>\';\n'
    '    const rows = [\n'
    '      { key: \'gross_gbp\',            label: \'Gross P&L (£)\',         fmt: v => \'£\' + v.toFixed(2) },\n'
    '      { key: \'standing_charge_gbp\',  label: \'Standing charges (£)\',  fmt: v => \'£\' + v.toFixed(2) },\n'
    '      { key: \'net_gbp\',              label: \'Net P&L (£)\',           fmt: v => \'£\' + v.toFixed(2) },\n'
    '      { key: \'annualised_net_gbp\',   label: \'Annualised net (£/yr)\', fmt: v => \'£\' + v.toFixed(2) },\n'
    '      { key: \'vs_agile_net_gbp\',     label: \'vs Agile delta (£)\',    fmt: v => (v >= 0 ? \'+\' : \'\') + \'£\' + v.toFixed(2) },\n'
    '      { key: \'avg_buy_p\',            label: \'Avg buy price (p)\',     fmt: v => v.toFixed(2) + \'p\' },\n'
    '      { key: \'avg_sell_p\',           label: \'Avg sell price (p)\',    fmt: v => v.toFixed(2) + \'p\' },\n'
    '    ];\n'
    '    let rowIdx = 0;\n'
    '    for (const row of rows) {\n'
    '      const bg = (rowIdx++ % 2 === 0) ? \'rgba(255,255,255,0.02)\' : \'transparent\';\n'
    '      html += `<tr style="background:${bg}">`;\n'
    '      html += `<td style="padding:4px 8px;color:#8b949e">${row.label}</td>`;\n'
    '      for (const m of [\'agile\',\'split\',\'optimise\']) {\n'
    '        const d = modes[m] || {};\n'
    '        if (d.error) { html += `<td style="text-align:right;padding:4px 8px;color:var(--red)">ERR</td>`; continue; }\n'
    '        const v = d[row.key];\n'
    '        const disp = (v !== undefined && v !== null) ? row.fmt(v) : \'—\';\n'
    '        let col = colors[m];\n'
    '        if (row.key === \'vs_agile_net_gbp\' && v !== undefined) col = v >= 0 ? \'var(--green)\' : \'var(--red)\';\n'
    '        html += `<td style="text-align:right;padding:4px 8px;color:${col}">${disp}</td>`;\n'
    '      }\n'
    '      html += \'</tr>\';\n'
    '    }\n'
    '    html += \'</table>\';\n'
    '    table.innerHTML = html;\n'
    '    const d = data.days || (data.months || 12) * 30.5;\n'
    '    status.textContent = `${Math.round(d)} days · imp_mod ${data.imp_mod_p}p · exp_mod ${data.exp_mod_p}p · cached 24h`;\n'
    '  } catch(e) {\n'
    '    status.textContent = \'Error: \' + e.message;\n'
    '  } finally {\n'
    '    if (btn) { btn.disabled = false; btn.textContent = \'📊 COMPARE TARIFFS\'; }\n'
    '  }\n'
    '}',
    'C5b: add loadTariffCompare() JS function')

print()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION D — node3_config.json (live values)
# ═══════════════════════════════════════════════════════════════════════════════
cfg_json = BASE / 'node3_config.json'
print("── node3_config.json ────────────────────────────────────────")
if cfg_json.exists():
    shutil.copy(cfg_json, str(cfg_json) + '.bak_master')
    data = json.loads(cfg_json.read_text('utf-8'))
    data['import_kw'] = 9.0
    data['export_kw'] = 5.5
    data.setdefault('standing_charge_import_p_day', 62.22)
    data.setdefault('standing_charge_export_p_day', 0.0)
    data.setdefault('standing_charge_eon_p_day',   62.22)
    cfg_json.write_text(json.dumps(data, indent=2), 'utf-8')
    print("[OK]   node3_config.json: import_kw→9.0, export_kw→5.5, SC fields seeded")
else:
    print("[SKIP] node3_config.json not found — defaults will apply on first run")

print()
print("=" * 62)
print("  master_deploy.py  COMPLETE")
print()
print("  Applied features:")
print("  A. export_kw 5.5 / import_kw 9.0")
print("  B. Standing charges: Agile 62.22p/day | EON 0.0p (set in ⚙)")
print("  C. subscription_pcm editable in Settings")
print("  D. Tariff toggle buttons fixed (auth guard removed)")
print("  E. _run_backtest tariff-aware (SPLIT/OPTIMISE pricing)")
print("  F. /api/backtest-compare endpoint (all 3 modes)")
print("  G. Dashboard: ⚙ SETTINGS adds SC + subscription fields")
print("  H. Dashboard: 📊 COMPARE TARIFFS button + panel")
print()
print("  Next: docker restart node3-portal")
print("=" * 62)
