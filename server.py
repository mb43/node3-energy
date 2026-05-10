#!/usr/bin/env python3
"""
NODE-3 Arbitrage Portal — Flask Backend
Serves the dashboard and exposes REST API endpoints.

Run:  python server.py
      python server.py --port 8585
"""

import os
import json
import csv
import math
import time
import argparse
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, send_file, Response, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# API key authentication for mutating endpoints.
# Set NODE3_API_KEY env var to require key on trigger/reset.
_API_KEY = os.environ.get("NODE3_API_KEY", "")

def _check_api_key():
    if not _API_KEY:
        return True
    return request.headers.get("X-API-Key", "") == _API_KEY


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────
def load_json(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def load_history(max_rows=200):
    path = os.path.join(BASE_DIR, "history.csv")
    if not os.path.exists(path):
        return []
    records = []
    try:
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Support both new flat columns and legacy fleet columns
                profit = float(row.get("profit_gbp") or row.get("fleet_profit_gbp") or 0)
                soc    = float(row.get("soc_kwh")    or row.get("avg_soc_kwh")      or 0)
                price  = float(row.get("price_p")    or row.get("avg_price_p")      or 0)
                action = row.get("action", "idle")
                g99_profit = row.get("g99_profit_gbp", "")
                g99_soc    = row.get("g99_soc_kwh", "")
                records.append({
                    "timestamp":          row["timestamp"],
                    "profit_gbp":         profit,
                    "slot_profit_gbp":    float(row.get("slot_profit_gbp", 0)),
                    "price_p":            price,
                    "soc_kwh":            soc,
                    "action":             action,
                    "g99_profit_gbp":     float(g99_profit) if g99_profit else None,
                    "g99_slot_profit_gbp": float(row.get("g99_slot_profit_gbp", 0) or 0),
                    "g99_soc_kwh":        float(g99_soc) if g99_soc else None,
                    "g99_action":         row.get("g99_action", ""),
                })
    except Exception as e:
        print("[WARN] history.csv read error: " + str(e))
    return records[-max_rows:]


def normalize_state(state):
    """
    Accept either new flat state or legacy {homes:[...]} structure
    and always return a flat state dict.
    """
    if not state:
        return None
    if "soc_kwh" in state:
        return state  # already flat
    # Legacy migration
    if "homes" in state and state["homes"]:
        h = state["homes"][0]
        return {
            "soc_kwh":          h.get("soc_kwh", 0),
            "profit_gbp":       state.get("fleet_profit_gbp", h.get("total_profit_gbp", 0)),
            "charged_kwh":      h.get("charged_kwh", 0),
            "discharged_kwh":   h.get("discharged_kwh", 0),
            "last_action":      h.get("last_action", "idle"),
            "last_price_p":     h.get("last_price_p", 0),
            "buy_threshold_p":  state.get("buy_threshold_p", 0),
            "sell_threshold_p": state.get("sell_threshold_p", 0),
            "last_updated":     state.get("last_updated"),
            "slots_simulated":  state.get("slots_simulated", 0),
            "battery_kwh":      h.get("battery_kwh", 72.0),
            "solar_kwp":        h.get("solar_kwp", 0.0),
            "daily_load_kwh":   h.get("daily_load_kwh", 12.0),
        }
    return None


# ─────────────────────────────────────────────
# BACKTEST ENGINE
# Single-source-of-truth algorithm — same logic as simulate.py.
# Called by /api/backtest; result cached 24h in backtest_cache.json.
# ─────────────────────────────────────────────

# Constants must match simulate.py
_BT_BATTERY_KWH      = 72.0
_BT_MIN_SOC_KWH      = 7.2
_BT_CHARGE_KWH_SLOT  = 10.5 * 0.5   # 5.25 kWh/slot
_BT_EXPORT_KWH       = 3.68          # G98 single-phase export cap per slot
_BT_RTE              = 0.88          # round-trip efficiency
_BT_BUY_PCT          = 35
_BT_SELL_PCT         = 60
_BT_VLP_P            = 40.0          # Very Large Price threshold
_BT_EXPORT_DEF_P     = 15.0          # flat fallback when live export prices absent
_BT_DAILY_LOAD_KWH   = 12.0
_BT_SVT_REF_P        = 25.0          # Ofgem Standard Variable Tariff reference
_BT_MIN_PROFIT_P     = 3.0           # min net p/kWh after RTE before charging
_BT_REGION           = os.environ.get("AGILE_REGION", "H")  # Southern England

# Elexon PC1 half-hourly load profile — identical to JavaScript HOME_LOAD_PROFILE
_PC1_RAW = [
    0.40, 0.32, 0.27, 0.24, 0.21, 0.20, 0.20, 0.21,  # 00:00–04:00
    0.24, 0.32, 0.45, 0.62, 0.90, 1.50, 1.90, 2.10,  # 04:00–08:00
    2.00, 1.75, 1.45, 1.20, 1.05, 0.95, 0.88, 0.85,  # 08:00–12:00
    0.85, 0.85, 0.90, 0.95, 1.00, 1.08, 1.20, 1.35,  # 12:00–16:00
    1.55, 1.85, 2.10, 2.30, 2.25, 2.10, 1.90, 1.65,  # 16:00–20:00
    1.45, 1.22, 1.00, 0.80, 0.65, 0.55, 0.47, 0.42,  # 20:00–00:00
]
_PC1_SUM     = sum(_PC1_RAW)
_PC1_PROFILE = [v / _PC1_SUM for v in _PC1_RAW]


def _bt_percentile(values, pct):
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(len(s) * pct / 100)))
    return s[idx]


def _bt_home_load(dt_utc):
    """kWh home draws this 30-min slot (PC1-weighted, UTC time index)."""
    si = dt_utc.hour * 2 + (1 if dt_utc.minute >= 30 else 0)
    return _BT_DAILY_LOAD_KWH * _PC1_PROFILE[si % 48]


def _bt_fetch_all(url, max_pages=20):
    """Paginate through Octopus API price endpoint. Returns all results sorted by valid_from."""
    import requests as _req
    all_results = []
    page = 0
    while url and page < max_pages:
        page += 1
        resp = _req.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get('results', []))
        url = data.get('next')
    all_results.sort(key=lambda x: x['valid_from'])
    return all_results


def _bt_discover(is_export=False):
    """Find the current live Agile import or export product code."""
    import requests as _req
    params = {'brand': 'OCTOPUS_ENERGY', 'page_size': 100}
    if is_export:
        params['is_export'] = True
    resp = _req.get('https://api.octopus.energy/v1/products/', params=params, timeout=15)
    resp.raise_for_status()
    products = [p for p in resp.json().get('results', [])
                if 'agile' in p.get('display_name', '').lower()]
    if not products:
        raise ValueError('No Agile product found')
    products.sort(key=lambda p: p.get('available_from') or '', reverse=True)
    return products[0]['code']


def _run_backtest(months=12):
    """
    Fetch 12 months of Octopus Agile import + export prices and run the
    rolling-window arbitrage simulation.  This is the ONLY implementation
    of the algorithm — simulate.py, the live forward schedule, and this
    backtest all share the same constants and logic.

    Returns a dict matching the format expected by dashboard.html's
    renderHistoricalResults() function.
    """
    from_dt = datetime.now(timezone.utc) - timedelta(days=months * 31)
    period_from = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Fetch import prices ───────────────────────────────────
    imp_code    = _bt_discover(is_export=False)
    imp_tariff  = f'E-1R-{imp_code}-{_BT_REGION}'
    imp_url     = (f'https://api.octopus.energy/v1/products/{imp_code}'
                   f'/electricity-tariffs/{imp_tariff}/standard-unit-rates/'
                   f'?period_from={period_from}&page_size=1500')
    print(f'[BACKTEST] Fetching import prices (product={imp_code})…')
    import_prices = _bt_fetch_all(imp_url)
    print(f'[BACKTEST] {len(import_prices)} import slots')

    # ── Fetch export prices (non-fatal) ──────────────────────
    export_prices = []
    has_export    = False
    try:
        exp_code   = _bt_discover(is_export=True)
        exp_tariff = f'E-1R-{exp_code}-{_BT_REGION}'
        exp_url    = (f'https://api.octopus.energy/v1/products/{exp_code}'
                      f'/electricity-tariffs/{exp_tariff}/standard-unit-rates/'
                      f'?period_from={period_from}&page_size=1500')
        print(f'[BACKTEST] Fetching export prices (product={exp_code})…')
        export_prices = _bt_fetch_all(exp_url)
        has_export    = len(export_prices) > 100
        print(f'[BACKTEST] {len(export_prices)} export slots, has_export={has_export}')
    except Exception as e:
        print(f'[BACKTEST] Export fetch failed ({e}) — using flat {_BT_EXPORT_DEF_P}p default')

    # ── Build O(1) export price lookup ───────────────────────
    # Key: first 16 chars of valid_from ISO string "YYYY-MM-DDTHH:MM"
    ep_map = {ep['valid_from'][:16]: float(ep['value_inc_vat']) for ep in export_prices}

    def get_exp(slot):
        return ep_map.get(slot['valid_from'][:16], _BT_EXPORT_DEF_P)

    # ── Rolling-window simulation ─────────────────────────────
    n   = len(import_prices)
    soc = _BT_BATTERY_KWH * 0.5   # start at 50% SOC

    total_charge_cost    = 0.0
    total_export_income  = 0.0
    total_charge_kwh     = 0.0
    total_discharge_kwh  = 0.0
    total_home_saved     = 0.0
    total_sell_price_sum = 0.0
    total_sell_slots     = 0
    monthly              = {}

    for idx in range(n):
        slot  = import_prices[idx]
        price = float(slot['value_inc_vat'])
        vf    = slot['valid_from'].replace('Z', '+00:00')
        dt    = datetime.fromisoformat(vf)
        key   = dt.strftime('%Y-%m')

        # Rolling 48-slot lookahead window
        w_end   = min(idx + 48, n)
        window  = import_prices[idx:w_end]
        w_vals  = [float(s['value_inc_vat']) for s in window]

        buy_pct_thr  = _bt_percentile(w_vals, _BT_BUY_PCT)
        sell_pct_thr = _bt_percentile(w_vals, _BT_SELL_PCT)

        # Dynamic buy ceiling: best export in window × RTE − min_profit
        # Prevents charging when no profitable export opportunity exists.
        best_exp  = max((get_exp(s) for s in window), default=_BT_EXPORT_DEF_P)
        dyn_ceil  = best_exp * _BT_RTE - _BT_MIN_PROFIT_P
        fwd_buy   = min(buy_pct_thr, dyn_ceil) if dyn_ceil > 0 else -math.inf
        fwd_sell  = sell_pct_thr

        # Initialise month bucket
        if key not in monthly:
            monthly[key] = {
                'profit': 0.0, 'chargeCost': 0.0, 'exportIncome': 0.0,
                'chargeSlots': 0, 'sellSlots': 0, 'slots': 0,
                'priceSum': 0.0, 'buyPriceSum': 0.0, 'sellPriceSum': 0.0,
                'chargeKwh': 0.0, 'dischargeKwh': 0.0,
                'homeEnergySaved': 0.0, 'homeEnergyAccum': 0.0, 'homeKwh': 0.0,
                'buyThrSum': 0.0, 'sellThrSum': 0.0,
                'socMin': float('inf'), 'socMax': float('-inf'),
            }

        mo             = monthly[key]
        mo['slots']   += 1
        mo['priceSum'] += price
        if math.isfinite(fwd_buy):
            mo['buyThrSum'] += fwd_buy
        mo['sellThrSum'] += fwd_sell

        slot_profit   = 0.0
        always_charge = price < 0
        is_vlp        = price >= _BT_VLP_P
        home_load     = _bt_home_load(dt)

        if is_vlp and soc > _BT_MIN_SOC_KWH + 0.1:
            # VLP: serve house first, then export remainder
            avail     = soc - _BT_MIN_SOC_KWH
            house     = min(home_load, avail)
            grid_disc = min(_BT_EXPORT_KWH - house, max(0.0, avail - house))
            moved     = house + grid_disc
            if moved > 0.01:
                soc -= moved
                if house > 0.01:
                    slot_profit += house * price / 100.0
                if grid_disc > 0.01:
                    exp_p = get_exp(slot)
                    income = grid_disc * _BT_RTE * exp_p / 100.0
                    slot_profit           += income
                    mo['exportIncome']    += income
                    mo['sellSlots']       += 1
                    mo['sellPriceSum']    += exp_p
                    mo['dischargeKwh']    += grid_disc
                    total_export_income   += income
                    total_discharge_kwh   += grid_disc
                    total_sell_price_sum  += exp_p
                    total_sell_slots      += 1

        elif always_charge or price <= fwd_buy:
            charge = min(_BT_CHARGE_KWH_SLOT, _BT_BATTERY_KWH - soc)
            if charge > 0.01:
                soc               += charge
                cost               = charge * price / 100.0
                slot_profit       -= cost
                mo['chargeCost']  += cost
                mo['chargeSlots'] += 1
                mo['buyPriceSum'] += price
                mo['chargeKwh']   += charge
                total_charge_cost += cost
                total_charge_kwh  += charge

        elif price >= fwd_sell and soc > _BT_MIN_SOC_KWH + 0.1:
            avail = soc - _BT_MIN_SOC_KWH
            disc  = min(_BT_EXPORT_KWH, avail)
            if disc > 0.01:
                exp_p = get_exp(slot)
                income = disc * _BT_RTE * exp_p / 100.0
                soc                  -= disc
                slot_profit          += income
                mo['exportIncome']   += income
                mo['sellSlots']      += 1
                mo['sellPriceSum']   += exp_p
                mo['dischargeKwh']   += disc
                total_export_income  += income
                total_discharge_kwh  += disc
                total_sell_price_sum += exp_p
                total_sell_slots     += 1

        soc = max(_BT_MIN_SOC_KWH, min(_BT_BATTERY_KWH, soc))
        mo['socMin'] = min(mo['socMin'], soc)
        mo['socMax'] = max(mo['socMax'], soc)
        mo['profit'] += slot_profit

        # Home energy: Agile saving vs SVT (PC1-weighted per-slot)
        home_val            = home_load * max(0.0, _BT_SVT_REF_P - price) / 100.0
        mo['homeEnergySaved']  += home_val
        mo['homeEnergyAccum']  += home_val
        mo['homeKwh']          += home_load
        total_home_saved       += home_val

    # ── Post-process monthly averages ────────────────────────
    for m in monthly.values():
        m['buyThr']  = m['buyThrSum']  / m['slots'] if m['slots'] > 0 else 0.0
        m['sellThr'] = m['sellThrSum'] / m['slots'] if m['slots'] > 0 else 0.0
        if not math.isfinite(m['socMin']): m['socMin'] = 0.0
        if not math.isfinite(m['socMax']): m['socMax'] = 0.0

    all_mo       = list(monthly.values())
    avg_buy_thr  = sum(m['buyThr']  for m in all_mo) / len(all_mo) if all_mo else 0.0
    avg_sell_thr = sum(m['sellThr'] for m in all_mo) / len(all_mo) if all_mo else 0.0
    avg_exp_rate = (total_sell_price_sum / total_sell_slots
                   if total_sell_slots > 0 else _BT_EXPORT_DEF_P)

    net = total_export_income - total_charge_cost
    print(f'[BACKTEST] Done. Net={net:.2f} Export={total_export_income:.2f} Charge={total_charge_cost:.2f} Slots={n}')

    return {
        'total':                round(net, 4),
        'monthly':              monthly,
        'totalSlots':           n,
        'buyThr':               round(avg_buy_thr,  4),
        'sellThr':              round(avg_sell_thr, 4),
        'totalHomeEnergySaved': round(total_home_saved, 4),
        'totalChargeCost':      round(total_charge_cost, 4),
        'totalExportIncome':    round(total_export_income, 4),
        'totalChargeKwh':       round(total_charge_kwh, 4),
        'totalDischargeKwh':    round(total_discharge_kwh, 4),
        'avgExportRateP':       round(avg_exp_rate, 4),
        'hasExportData':        has_export,
    }


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────
@app.route("/")
def index():
    return send_file(os.path.join(BASE_DIR, "dashboard.html"))


@app.route("/NODE3_Schematic.html")
def schematic():
    return send_file(os.path.join(BASE_DIR, "NODE3_Schematic.html"))


@app.route("/api/node")
@app.route("/api/fleet")   # keep old path for compat
def api_node():
    """Current Node-3 state — SOC, profit, last action."""
    raw = load_json("fleet_state.json")
    state = normalize_state(raw)
    if not state:
        return jsonify({"error": "Node-3 state not yet available. Run simulate.py first."}), 503
    return jsonify(state)


@app.route("/api/prices")
def api_prices():
    """Last 96 Agile price slots (48 hours)."""
    prices = load_json("prices.json")
    if not prices:
        return jsonify([])
    return jsonify(prices[-96:])


@app.route("/api/history")
def api_history():
    """Historical simulation results — up to 200 rows."""
    limit = request.args.get("limit", 200, type=int)
    return jsonify(load_history(max_rows=limit))


@app.route("/api/status")
def api_status():
    """Server health + data freshness."""
    raw   = load_json("fleet_state.json")
    state = normalize_state(raw)
    prices = load_json("prices.json")

    history_rows = 0
    history_path = os.path.join(BASE_DIR, "history.csv")
    if os.path.exists(history_path):
        try:
            history_rows = max(0, sum(1 for _ in open(history_path)) - 1)
        except Exception:
            pass

    return jsonify({
        "server_time":      datetime.now(timezone.utc).isoformat(),
        "fleet_ready":      state is not None,       # kept for dashboard compat
        "node_ready":       state is not None,
        "prices_available": bool(prices),
        "history_rows":     history_rows,
        "last_simulated":   state.get("last_updated") if state else None,
        "profit_gbp":       state.get("profit_gbp") if state else None,
        "slots_simulated":  state.get("slots_simulated") if state else None,
    })


@app.route("/api/run-now", methods=["POST"])
def api_run_now():
    """Trigger simulate.py immediately (useful after a restart or when prices go stale)."""
    try:
        rc, err = _run_simulate()
        if rc == 0:
            return jsonify({"status": "ok", "message": "simulate.py completed successfully"})
        else:
            return jsonify({"status": "error", "message": err[:500]}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/plan")
def api_plan():
    """
    Forward dispatch plan — Python-computed optimal schedule for all future price slots.
    Returns array of slot objects: {time, action, importP, exportP, planSoc}
    Single source of truth: generated by simulate.py plan_optimal_dispatch().
    """
    plan   = load_json("dispatch_plan.json") or {}
    prices = load_json("prices.json") or []
    export = load_json("export_prices.json") or []

    # Build export price lookup by slot start
    exp_lookup = {}
    for e in export:
        vf = e.get("valid_from") or e.get("time")
        if vf:
            exp_lookup[vf[:19]] = e.get("value_inc_vat", e.get("priceP", 0))

    now_utc = datetime.now(timezone.utc)
    midnight_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    slots = []
    for p in prices:
        vf = p.get("valid_from") or p.get("time")
        if not vf:
            continue
        try:
            slot_dt = datetime.fromisoformat(vf.replace("Z", "+00:00"))
        except Exception:
            continue
        if slot_dt < midnight_utc:
            continue
        imp = p.get("value_inc_vat", p.get("priceP", 0))
        exp = exp_lookup.get(vf[:19], imp * 0.6)   # fallback: 60% of import
        action = plan.get(vf, plan.get(vf[:19], "idle"))
        slots.append({
            "time":    vf,
            "action":  action,
            "importP": round(imp, 4),
            "exportP": round(exp, 4),
        })

    # Annotate with forward SoC simulation (Python constants)
    CHARGE_KWH = 5.25
    EXPORT_KWH = 3.68   # G98; update to 5.75 post-G99
    RTE        = 0.88
    BAT_KWH    = 72.0
    MIN_SOC    = 7.2

    raw = load_json("fleet_state.json") or {}
    state = normalize_state(raw) or {}
    soc = float(state.get("soc_kwh", BAT_KWH * 0.5))

    # Annualised figures (G98 and G99)
    total_revenue_g98 = 0.0
    total_cost        = 0.0
    ch_slots = [s for s in slots if s["action"] == "charge"]
    ex_slots = [s for s in slots if s["action"] == "discharge"]

    for s in slots:
        if s["action"] == "charge":
            ch = min(CHARGE_KWH, BAT_KWH - soc)
            soc = min(BAT_KWH, soc + ch)
            s["planSoc"] = round(soc, 2)
            total_cost += ch * s["importP"] / 100
        elif s["action"] == "discharge":
            dc = min(EXPORT_KWH, soc - MIN_SOC)
            dc = max(0, dc)
            soc = max(MIN_SOC, soc - dc)
            s["planSoc"] = round(soc, 2)
            total_revenue_g98 += dc * RTE * s["exportP"] / 100
        else:
            s["planSoc"] = round(soc, 2)

    net_g98 = total_revenue_g98 - total_cost

    # G99 net (same cost, larger export cap)
    EXPORT_KWH_G99 = 5.75
    rev_g99 = sum(
        min(EXPORT_KWH_G99, BAT_KWH) * RTE * s["exportP"] / 100
        for s in ex_slots
    )
    net_g99 = rev_g99 - total_cost

    return jsonify({
        "slots":    slots,
        "summary": {
            "charge_slots":   len(ch_slots),
            "export_slots":   len(ex_slots),
            "net_g98":        round(net_g98, 4),
            "net_g99":        round(net_g99, 4),
            "total_cost":     round(total_cost, 4),
            "total_rev_g98":  round(total_revenue_g98, 4),
        }
    })


@app.route("/api/backtest")
def api_backtest():
    """
    12-month historical backtest using the Python algorithm (single source of truth).
    Results are cached in backtest_cache.json for 24 hours.
    Add ?force=1 to bypass cache and re-run.
    """
    cache_path = os.path.join(BASE_DIR, "backtest_cache.json")
    force      = request.args.get('force', '').lower() in ('1', 'true', 'yes')

    if not force and os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            age_h = (time.time() - cached.get('_cached_at', 0)) / 3600
            if age_h < 24:
                print(f'[BACKTEST] Cache hit ({age_h:.1f}h old)')
                return jsonify(cached['data'])
        except Exception as e:
            print(f'[BACKTEST] Cache read error: {e}')

    try:
        data = _run_backtest()
        try:
            with open(cache_path, 'w') as f:
                json.dump({'_cached_at': time.time(), 'data': data}, f)
        except Exception as e:
            print(f'[BACKTEST] Cache write error: {e}')
        return jsonify(data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route("/api/trigger", methods=["GET", "POST"])
def api_trigger():
    """
    Manually trigger a simulation slot.
    GET  -> single slot
    POST -> with ?mode=backfill to replay 48h
    """
    if not _check_api_key():
        return jsonify({"error": "Unauthorised — set X-API-Key header"}), 401

    mode = request.args.get("mode", "single")
    cmd  = [sys.executable, os.path.join(BASE_DIR, "simulate.py")]
    if mode == "backfill":
        cmd.append("--backfill")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=BASE_DIR,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        return jsonify({
            "status":    "ok" if result.returncode == 0 else "error",
            "mode":      mode,
            "stdout":    result.stdout[-3000:],
            "stderr":    result.stderr[-2000:],
            "exit_code": result.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({"status": "timeout"}), 504
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Reset Node-3 state (delete state + history files)."""
    if not _check_api_key():
        return jsonify({"error": "Unauthorised — set X-API-Key header"}), 401
    for fname in ("fleet_state.json", "history.csv"):
        path = os.path.join(BASE_DIR, fname)
        if os.path.exists(path):
            os.remove(path)
    return jsonify({"status": "reset", "message": "Node-3 state and history cleared."})


@app.route("/api/debug/compile")
def api_debug_compile():
    """Compile-check simulate.py and return any SyntaxError detail."""
    path = os.path.join(BASE_DIR, "simulate.py")
    try:
        with open(path, "rb") as f:
            src = f.read()
        compile(src, path, "exec")
        return jsonify({"status": "ok", "python": sys.version, "lines": src.count(b"\n")})
    except SyntaxError as e:
        return jsonify({"status": "error", "python": sys.version,
                        "lineno": e.lineno, "msg": str(e), "text": e.text})


# ─────────────────────────────────────────────
# BACKGROUND SIMULATION SCHEDULER
# Mirrors the GitHub Actions 30-min cron so the
# local portal stays live without manual triggers.
# ─────────────────────────────────────────────
_SIMULATE_INTERVAL_S = 1800  # 30 minutes

def _next_slot_delay() -> float:
    """Seconds until the next Agile half-hour slot boundary (HH:00 or HH:30)."""
    now = datetime.now(timezone.utc)
    minute = now.minute
    second = now.second
    if minute < 30:
        return (30 - minute) * 60 - second
    else:
        return (60 - minute) * 60 - second

def _run_simulate():
    """Run simulate.py once and return (returncode, stderr)."""
    cmd = [sys.executable, os.path.join(BASE_DIR, "simulate.py")]
    result = subprocess.run(cmd, timeout=120, capture_output=True, text=True)
    return result.returncode, result.stderr


def _simulation_loop():
    """
    Background thread: run simulate.py immediately on startup, then again
    at each 30-minute Agile slot boundary (HH:00 / HH:30).
    """
    # Run immediately on startup so prices.json is fresh from the first request.
    print("[NODE-3 scheduler] Startup run — fetching fresh prices…", flush=True)
    try:
        rc, err = _run_simulate()
        if rc == 0:
            print("[NODE-3 scheduler] Startup simulate.py OK", flush=True)
        else:
            print(f"[NODE-3 scheduler] Startup simulate.py error: {err[:200]}", flush=True)
    except Exception as exc:
        print(f"[NODE-3 scheduler] Startup exception: {exc}", flush=True)

    # Then align to slot boundaries for subsequent runs.
    while True:
        delay = _next_slot_delay()
        print(f"[NODE-3 scheduler] Next slot boundary in {delay:.0f}s", flush=True)
        time.sleep(max(5, delay))
        try:
            print("[NODE-3 scheduler] Running simulate.py …", flush=True)
            rc, err = _run_simulate()
            if rc == 0:
                print("[NODE-3 scheduler] simulate.py OK", flush=True)
            else:
                print(f"[NODE-3 scheduler] simulate.py error: {err[:200]}", flush=True)
        except Exception as exc:
            print(f"[NODE-3 scheduler] Exception: {exc}", flush=True)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NODE-3 Arbitrage Portal Server")
    parser.add_argument("--port", type=int, default=8585, help="Port to listen on (default: 8585)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    args = parser.parse_args()

    print("\n" + "="*55)
    print("  NODE-3 ARBITRAGE PORTAL")
    print("  http://localhost:" + str(args.port))
    print("="*55 + "\n")

    # Start background simulation scheduler (daemon so it dies with the server)
    sim_thread = threading.Thread(target=_simulation_loop, daemon=True, name="sim-scheduler")
    sim_thread.start()
    print("[NODE-3 scheduler] Started — will run simulate.py at each 30-min slot boundary", flush=True)

    app.run(host=args.host, port=args.port, debug=False, threaded=True)
