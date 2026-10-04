#!/usr/bin/env python3
"""
deploy_backtest_compare.py  — Dovecote Node-3
Run AFTER deploy_standing_charges.py.

Adds tariff-aware pricing to _run_backtest() and a new /api/backtest-compare
endpoint that runs all three modes (agile / split / optimise) against the same
historical price data and returns a side-by-side comparison dict.

Patches:
  1. server.py  — _run_backtest signature: add tariff_mode / mod params
  2. server.py  — resolve tariff_mode before main loop
  3. server.py  — per-slot _buy_p / _sell_adj inside the loop
  4. server.py  — LP window uses buy-adjusted prices (SPLIT/OPTIMISE plan better)
  5. server.py  — charge cost uses _buy_p (not raw price)
  6. server.py  — charge buyPriceSum uses _buy_p
  7. server.py  — VLP export income uses (exp_p + _sell_adj)
  8. server.py  — planned discharge income uses (exp_p + _sell_adj)
  9. server.py  — add /api/backtest-compare endpoint
"""
import shutil
from pathlib import Path

BASE = Path('/home/pi/node3')


def patch(path: Path, old: str, new: str, label: str):
    text = path.read_text('utf-8')
    count = text.count(old)
    assert count == 1, f"[{label}] Expected 1 match, got {count}:\n  {repr(old[:200])}"
    path.write_text(text.replace(old, new, 1), 'utf-8')
    print(f"[OK] {label}")


srv = BASE / 'server.py'
shutil.copy(srv, str(srv) + '.bak_compare')
print("[OK] Backup done")


# ── 1. Signature ──────────────────────────────────────────────────────────────
patch(srv,
    'def _run_backtest(months=12, founder=False):',
    'def _run_backtest(months=12, founder=False, tariff_mode=None, imp_mod_p=3.0, exp_mod_p=3.0):',
    'server: _run_backtest signature adds tariff params')


# ── 2. Resolve tariff_mode before loop ────────────────────────────────────────
patch(srv,
    '    n   = len(import_prices)\n'
    '    soc = _BT_BATTERY_KWH * 0.5   # start at 50% SOC',
    '    # ── Tariff mode for this run ──────────────────────────────────────────\n'
    '    if tariff_mode is None:\n'
    '        tariff_mode = _bt_cfg.get("tariff_mode", "agile")\n'
    '    n   = len(import_prices)\n'
    '    soc = _BT_BATTERY_KWH * 0.5   # start at 50% SOC',
    'server: _run_backtest resolves tariff_mode before loop')


# ── 3. Per-slot buy/sell adjustments ─────────────────────────────────────────
patch(srv,
    '        dt    = datetime.fromisoformat(vf)\n'
    '        key   = dt.strftime(\'%Y-%m\')',
    '        dt    = datetime.fromisoformat(vf)\n'
    '        key   = dt.strftime(\'%Y-%m\')\n'
    '        # ── Effective buy/sell prices under active tariff ─────────────────\n'
    '        _h       = dt.hour\n'
    '        _buy_p   = price\n'
    '        _sell_adj = 0.0\n'
    '        if tariff_mode in (\'split\', \'optimise\') and 0 <= _h < 6:\n'
    '            _buy_p = max(0.0, price - imp_mod_p)\n'
    '        if tariff_mode == \'optimise\' and 16 <= _h < 19:\n'
    '            _sell_adj = exp_mod_p',
    'server: _run_backtest per-slot buy/sell price adjustment')


# ── 4. LP window uses buy-adjusted prices for non-agile modes ────────────────
patch(srv,
    '        if slot[\'valid_from\'] not in dispatch_plan:\n'
    '            window = import_prices[idx: idx + 96]\n'
    '            dispatch_plan.update(\n'
    '                _sim.plan_optimal_dispatch(window, soc, battery_kwh=_BT_BATTERY_KWH,\n'
    '                                            min_soc_kwh=_BT_MIN_SOC_KWH,\n'
    '                                            export_kwh_cap=_BT_EXPORT_KWH,\n'
    '                                            daily_load_kwh=_bt_total_load_day)\n'
    '            )',
    '        if slot[\'valid_from\'] not in dispatch_plan:\n'
    '            if tariff_mode != \'agile\':\n'
    '                # Build buy-price-adjusted window so LP plans charging in cheap slots\n'
    '                window = []\n'
    '                for _ws in import_prices[idx: idx + 96]:\n'
    '                    _wh = datetime.fromisoformat(_ws[\'valid_from\'].replace(\'Z\', \'+00:00\')).hour\n'
    '                    _wp = float(_ws[\'value_inc_vat\'])\n'
    '                    if tariff_mode in (\'split\', \'optimise\') and 0 <= _wh < 6:\n'
    '                        _wp = max(0.0, _wp - imp_mod_p)\n'
    '                    window.append({**_ws, \'value_inc_vat\': _wp})\n'
    '            else:\n'
    '                window = import_prices[idx: idx + 96]\n'
    '            dispatch_plan.update(\n'
    '                _sim.plan_optimal_dispatch(window, soc, battery_kwh=_BT_BATTERY_KWH,\n'
    '                                            min_soc_kwh=_BT_MIN_SOC_KWH,\n'
    '                                            export_kwh_cap=_BT_EXPORT_KWH,\n'
    '                                            daily_load_kwh=_bt_total_load_day)\n'
    '            )',
    'server: _run_backtest LP window uses buy-adjusted prices')


# ── 5. Charge cost uses _buy_p ────────────────────────────────────────────────
patch(srv,
    '                cost               = charge * price / 100.0',
    '                cost               = charge * _buy_p / 100.0',
    'server: _run_backtest charge cost uses _buy_p')


# ── 6. buyPriceSum uses _buy_p ────────────────────────────────────────────────
patch(srv,
    '                mo[\'buyPriceSum\'] += price',
    '                mo[\'buyPriceSum\'] += _buy_p',
    'server: _run_backtest buyPriceSum uses _buy_p')


# ── 7. VLP export income uses (exp_p + _sell_adj) ─────────────────────────────
patch(srv,
    '                income = grid_disc * _BT_RTE * exp_p / 100.0',
    '                income = grid_disc * _BT_RTE * (exp_p + _sell_adj) / 100.0',
    'server: _run_backtest VLP export income uses sell-adjusted price')


# ── 8. Planned discharge income uses (exp_p + _sell_adj) ─────────────────────
patch(srv,
    '                income = disc * _BT_RTE * exp_p / 100.0',
    '                income = disc * _BT_RTE * (exp_p + _sell_adj) / 100.0',
    'server: _run_backtest discharge income uses sell-adjusted price')


# ── 9. /api/backtest-compare endpoint ────────────────────────────────────────
# Insert before /api/backtest endpoint
COMPARE_ENDPOINT = (
    '@app.route("/api/backtest-compare")\n'
    'def api_backtest_compare():\n'
    '    """\n'
    '    Run _run_backtest() for all three tariff modes and return a side-by-side\n'
    '    comparison. ?months=N (default 12). ?mode=founder uses baseload_kw.\n'
    '    Cached 24h in backtest_compare_cache.json (force-busted with ?force=1).\n'
    '    """\n'
    '    months  = int(request.args.get("months", 12))\n'
    '    founder = request.args.get("mode") == "founder"\n'
    '    force   = request.args.get("force") == "1"\n'
    '    cache_p = os.path.join(BASE_DIR, "backtest_compare_cache.json")\n'
    '    if not force and os.path.exists(cache_p):\n'
    '        try:\n'
    '            with open(cache_p) as _f:\n'
    '                cached = json.load(_f)\n'
    '            age_h = (time.time() - cached.get("_ts", 0)) / 3600\n'
    '            if age_h < 24:\n'
    '                return jsonify(cached)\n'
    '        except Exception:\n'
    '            pass\n'
    '    results = {}\n'
    '    cfg = _cfg.load_config()\n'
    '    imp_mod = float(cfg.get("optimise_import_mod_p", 3.0))\n'
    '    exp_mod = float(cfg.get("optimise_export_mod_p", 3.0))\n'
    '    for mode in ("agile", "split", "optimise"):\n'
    '        try:\n'
    '            r = _run_backtest(months=months, founder=founder,\n'
    '                              tariff_mode=mode,\n'
    '                              imp_mod_p=imp_mod, exp_mod_p=exp_mod)\n'
    '            # Standing charges (same for all modes — Octopus Agile import contract)\n'
    '            days = r.get("days", months * 30.5)\n'
    '            sc_import = float(cfg.get("standing_charge_import_p_day", 58.9))\n'
    '            sc_export = float(cfg.get("standing_charge_export_p_day", 0.0))\n'
    '            sc_total  = (sc_import + sc_export) * days / 100.0\n'
    '            results[mode] = {\n'
    '                "gross_gbp":            round(r["total"], 2),\n'
    '                "standing_charge_gbp":  round(sc_total, 2),\n'
    '                "net_gbp":              round(r["total"] - sc_total, 2),\n'
    '                "annualised_gross_gbp": round(r["total"] * 365 / max(1, days), 2),\n'
    '                "annualised_net_gbp":   round((r["total"] - sc_total) * 365 / max(1, days), 2),\n'
    '                "days":                 round(days, 1),\n'
    '                "avg_buy_p":            r.get("avgBuyThr", 0),\n'
    '                "avg_sell_p":           r.get("avgSellThr", 0),\n'
    '                "total_charge_kwh":     r.get("totalChargeKwh", 0),\n'
    '                "total_discharge_kwh":  r.get("totalDischargeKwh", 0),\n'
    '            }\n'
    '        except Exception as e:\n'
    '            results[mode] = {"error": str(e)}\n'
    '    # Add delta vs agile\n'
    '    if "agile" in results and "net_gbp" in results["agile"]:\n'
    '        base = results["agile"]["net_gbp"]\n'
    '        for mode in ("split", "optimise"):\n'
    '            if mode in results and "net_gbp" in results[mode]:\n'
    '                results[mode]["vs_agile_net_gbp"] = round(results[mode]["net_gbp"] - base, 2)\n'
    '    payload = {"modes": results, "months": months, "founder": founder,\n'
    '               "imp_mod_p": imp_mod, "exp_mod_p": exp_mod, "_ts": time.time()}\n'
    '    try:\n'
    '        with open(cache_p, "w") as _f:\n'
    '            json.dump(payload, _f, indent=2)\n'
    '    except Exception:\n'
    '        pass\n'
    '    return jsonify(payload)\n'
    '\n'
    '\n'
)

patch(srv,
    '@app.route("/api/backtest")\n'
    'def api_backtest():',
    COMPARE_ENDPOINT +
    '@app.route("/api/backtest")\n'
    'def api_backtest():',
    'server: add /api/backtest-compare endpoint')


print()
print("=" * 60)
print("deploy_backtest_compare.py COMPLETE")
print()
print("Test:")
print("  curl http://192.168.1.157:5000/api/backtest-compare?force=1")
print()
print("Returns: {modes: {agile: {...}, split: {...}, optimise: {...}}}")
print("Key fields per mode:")
print("  gross_gbp, net_gbp (after standing charges),")
print("  annualised_net_gbp, vs_agile_net_gbp (split/optimise only)")
print()
print("Restart docker: docker restart node3-portal")
print("=" * 60)
