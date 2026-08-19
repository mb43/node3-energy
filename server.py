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
import node3_config as _cfg

app = Flask(__name__)
CORS(app)

# Shared runtime settings (battery capacity, import/export rates) — single
# source of truth, see node3_config.py. Loaded once at import; each request
# that needs current values re-reads via _cfg.load_config() so /api/settings
# updates take effect without a restart.

# ─────────────────────────────────────────────
# BATTERY-EMULATOR MQTT — real SOC feed
# Subscribes to Battery-Emulator ESP32 telemetry and writes real SOC
# into fleet_state.json so LP dispatch uses actual hardware state.
# ─────────────────────────────────────────────
_MQTT_HOST  = os.environ.get("MQTT_HOST", "")
_MQTT_PORT  = int(os.environ.get("MQTT_PORT", "1883"))
_BATT_TOPIC = os.environ.get("BATTERY_EMULATOR_MQTT_TOPIC", "battery-emulator")
_real_soc_lock = threading.Lock()


def _on_battery_message(client, userdata, msg):
    """
    Called when Battery-Emulator publishes telemetry.
    Payload keys (Battery-Emulator project):
      SOC (%), StateOfHealth (%), voltage (V), current (A), temperature (°C)
    Writes real SOC into fleet_state.json immediately.
    """
    try:
        payload = json.loads(msg.payload.decode())
        soc_pct = payload.get("SOC") or payload.get("soc")
        if soc_pct is None:
            return
        # Convert % to kWh using the configured battery capacity (node3_config)
        battery_kwh = _cfg.load_config()["battery_kwh"]
        soc_kwh = round(float(soc_pct) / 100.0 * battery_kwh, 2)

        state_path = os.path.join(BASE_DIR, "fleet_state.json")
        with _real_soc_lock:
            try:
                with open(state_path) as f:
                    state = json.load(f)
            except Exception:
                state = {}
            state["soc_kwh"]          = soc_kwh
            state["soc_pct"]          = round(float(soc_pct), 1)
            state["soc_source"]       = "hardware"
            state["soc_updated"]      = datetime.now(timezone.utc).isoformat()
            state["batt_voltage_v"]   = payload.get("voltage")
            state["batt_current_a"]   = payload.get("current")
            state["batt_temp_c"]      = payload.get("temperature")
            state["batt_soh_pct"]     = payload.get("StateOfHealth")
            with open(state_path, "w") as f:
                json.dump(state, f, indent=2)

        print(f"[MQTT-SOC] Real SOC: {soc_pct:.1f}% = {soc_kwh} kWh  "
              f"V={payload.get('voltage','?')}  I={payload.get('current','?')}A",
              flush=True)
    except Exception as e:
        print(f"[MQTT-SOC] Parse error: {e}", flush=True)


def _start_mqtt_soc_listener():
    """
    Background thread: connect to MQTT broker and subscribe to
    Battery-Emulator telemetry topic. Reconnects automatically.
    Does nothing if MQTT_HOST is not set.
    """
    if not _MQTT_HOST:
        print("[MQTT-SOC] MQTT_HOST not set — real SOC feed disabled (using simulated SOC)", flush=True)
        return

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("[MQTT-SOC] paho-mqtt not installed — run: pip install paho-mqtt", flush=True)
        return

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(_BATT_TOPIC)
            print(f"[MQTT-SOC] Connected to {_MQTT_HOST}:{_MQTT_PORT} — subscribed to '{_BATT_TOPIC}'", flush=True)
        else:
            print(f"[MQTT-SOC] Connect failed rc={rc}", flush=True)

    def on_disconnect(client, userdata, rc):
        print(f"[MQTT-SOC] Disconnected (rc={rc}) — will reconnect", flush=True)

    while True:
        try:
            client = mqtt.Client(client_id="node3-server", clean_session=True)
            client.on_connect    = on_connect
            client.on_disconnect = on_disconnect
            client.on_message    = _on_battery_message
            client.connect(_MQTT_HOST, _MQTT_PORT, keepalive=60)
            client.loop_forever()
        except Exception as e:
            print(f"[MQTT-SOC] Exception: {e} — retrying in 30s", flush=True)
            time.sleep(30)

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
# Actually uses simulate.py's LP-optimal plan_optimal_dispatch() now (fixed 19
# Aug 2026) — it previously claimed to be "the same logic as simulate.py" but
# was in fact a pure percentile-threshold heuristic with no LP/scipy
# involvement whatsoever, directly violating Matt's standing "LP dispatch is
# permanent, never revert to greedy/percentile" rule for the headline
# "12-month backtest" figure the dashboard shows next to the live 24hr number.
# Called by /api/backtest; result cached 24h in backtest_cache.json.
# ─────────────────────────────────────────────
import simulate as _sim   # reuse the real LP dispatch engine — do not re-implement it here

# Battery/rate constants now sourced from node3_config (single source of
# truth, see node3_config.py) instead of a hand-typed, drifted-out-of-sync
# copy. _BT_CHARGE_KWH_SLOT/_BT_EXPORT_KWH are re-read fresh at the top of
# _run_backtest() each call so a settings change takes effect without a
# restart.
_BT_RTE              = 0.88          # round-trip efficiency
_BT_VLP_P            = 40.0          # Very Large Price threshold
_BT_EXPORT_DEF_P     = 15.0          # flat fallback when live export prices absent
_BT_DAILY_LOAD_KWH   = 12.0
_BT_SVT_REF_P        = 25.0          # Ofgem Standard Variable Tariff reference
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
    Fetch 12 months of Octopus Agile import + export prices and replay them
    through simulate.py's real LP-optimal plan_optimal_dispatch() (fixed 19
    Aug 2026 — this used to be a hand-rolled percentile-threshold heuristic
    that never touched scipy at all, despite the comment here previously
    claiming otherwise). Replans every 96 slots (48h) with a 96-slot lookahead,
    using the real running SOC — the same cadence and inputs the live system
    uses when fresh Agile prices are published once daily.

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

    # ── LP-optimal simulation ──────────────────────────────────
    # Replans with simulate.py's real plan_optimal_dispatch() every time the
    # plan runs out (every 96 slots / 48h, since each replan covers a 96-slot
    # lookahead window), using the actual running SOC as the starting point —
    # not a per-slot percentile threshold.
    _bt_cfg           = _cfg.load_config()
    _BT_BATTERY_KWH   = _bt_cfg["battery_kwh"]
    _BT_MIN_SOC_KWH   = _BT_BATTERY_KWH * (_bt_cfg["min_soc_pct"] / 100.0)
    _BT_EXPORT_KWH    = _bt_cfg["export_kw"] * 0.5
    _BT_CHARGE_KWH_SLOT = _bt_cfg["import_kw"] * 0.5

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

    dispatch_plan = {}   # valid_from -> 'charge' | 'discharge' | 'idle', filled as we go

    for idx in range(n):
        slot  = import_prices[idx]
        price = float(slot['value_inc_vat'])
        vf    = slot['valid_from'].replace('Z', '+00:00')
        dt    = datetime.fromisoformat(vf)
        key   = dt.strftime('%Y-%m')

        # Replan (real LP, not a heuristic) whenever we've run off the end of
        # the current plan — happens every 96 slots by construction (the window
        # requested below is 96 slots wide).
        if slot['valid_from'] not in dispatch_plan:
            window = import_prices[idx: idx + 96]
            dispatch_plan.update(
                _sim.plan_optimal_dispatch(window, soc, battery_kwh=_BT_BATTERY_KWH,
                                            min_soc_kwh=_BT_MIN_SOC_KWH,
                                            export_kwh_cap=_BT_EXPORT_KWH)
            )
        planned = dispatch_plan.get(slot['valid_from'])

        # Initialise month bucket
        if key not in monthly:
            monthly[key] = {
                'profit': 0.0, 'chargeCost': 0.0, 'exportIncome': 0.0,
                'chargeSlots': 0, 'sellSlots': 0, 'slots': 0,
                'priceSum': 0.0, 'buyPriceSum': 0.0, 'sellPriceSum': 0.0,
                'chargeKwh': 0.0, 'dischargeKwh': 0.0,
                'homeEnergySaved': 0.0, 'homeEnergyAccum': 0.0, 'homeKwh': 0.0,
                'socMin': float('inf'), 'socMax': float('-inf'),
            }

        mo             = monthly[key]
        mo['slots']   += 1
        mo['priceSum'] += price

        slot_profit   = 0.0
        is_vlp        = price >= _BT_VLP_P
        home_load     = _bt_home_load(dt)

        # Home load ALWAYS drains SOC, every slot — matching simulate.py's
        # simulate_slot() exactly (see its comment: "home load already
        # deducted from SOC above. Do NOT re-deduct house_served here — that
        # was the previous double-deduction bug"). Previously this backtest
        # only drained SOC for home load during VLP slots and separately
        # "sold" the avoided import as revenue — a different, inconsistent
        # physical model from the live system, found + fixed 19 Aug 2026 so
        # the 12-month backtest's SOC trajectory (and therefore its
        # charge/discharge decisions) genuinely matches live behaviour. The
        # separate 'homeEnergySaved' stat below (Agile vs SVT) is unaffected
        # — that's an independent informational figure, not part of the SOC/
        # dispatch mechanics.
        soc = max(0.0, soc - home_load)

        if is_vlp and soc > _BT_MIN_SOC_KWH + 0.1:
            # VLP: export whatever's available above the reserve floor.
            avail     = soc - _BT_MIN_SOC_KWH
            grid_disc = min(_BT_EXPORT_KWH, avail)
            if grid_disc > 0.01:
                exp_p = get_exp(slot)
                income = grid_disc * _BT_RTE * exp_p / 100.0
                soc                   -= grid_disc
                slot_profit           += income
                mo['exportIncome']    += income
                mo['sellSlots']       += 1
                mo['sellPriceSum']    += exp_p
                mo['dischargeKwh']    += grid_disc
                total_export_income   += income
                total_discharge_kwh   += grid_disc
                total_sell_price_sum  += exp_p
                total_sell_slots      += 1

        elif planned == 'charge':
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

        elif planned == 'discharge' and soc > _BT_MIN_SOC_KWH + 0.1:
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
    # buyThr/sellThr previously meant "percentile threshold" under the old
    # heuristic; under LP dispatch there's no fixed threshold, so these now
    # report the actual average price paid/received on executed charge/sell
    # slots that month instead — more meaningful for the chart that plots them.
    for m in monthly.values():
        m['buyThr']  = m['buyPriceSum']  / m['chargeSlots'] if m['chargeSlots'] > 0 else 0.0
        m['sellThr'] = m['sellPriceSum'] / m['sellSlots']   if m['sellSlots']   > 0 else 0.0
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
    # Explicit no-store — dashboard.html is edited/live-mounted frequently and
    # Matt has been bitten by a stale browser copy hiding new features (e.g.
    # the ⚙ SETTINGS button) that were already live on disk. Flask's default
    # send_file() relies on conditional GET (Last-Modified/ETag), which is
    # usually fine but gives the browser room to serve straight from disk
    # cache on a plain reload — force it to always re-fetch.
    resp = send_file(os.path.join(BASE_DIR, "dashboard.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


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


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    """
    Operator-configurable physical parameters — battery capacity, import
    (charge) rate, export (discharge) rate, min SOC floor. Single source of
    truth (node3_config.py / node3_config.json) read by simulate.py and every
    dispatch/backtest engine in this file. Defaults: 72kWh / 10kW / 6kW.

    GET  -> current settings
    POST -> JSON body with any subset of {battery_kwh, import_kw, export_kw,
            min_soc_pct}; merges onto existing settings and persists. Takes
            effect on the NEXT simulate.py run (it reads config at import
            time) and immediately for server.py's own endpoints (which
            re-read config per request).
    """
    if request.method == "GET":
        return jsonify(_cfg.load_config())

    if not _check_api_key():
        return jsonify({"error": "invalid or missing API key"}), 401

    body = request.get_json(silent=True) or {}
    updates = {}
    for key in ("battery_kwh", "import_kw", "export_kw", "min_soc_pct"):
        if key in body:
            try:
                v = float(body[key])
            except (TypeError, ValueError):
                return jsonify({"error": f"{key} must be numeric"}), 400
            if v <= 0:
                return jsonify({"error": f"{key} must be > 0"}), 400
            updates[key] = v
    if not updates:
        return jsonify({"error": "no valid settings fields in request body"}), 400

    merged = _cfg.save_config(updates)
    print(f"[SETTINGS] Updated: {updates} -> {merged}")
    return jsonify(merged)


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

    # Annotate with forward SoC simulation. Rates now sourced from node3_config
    # (single source of truth — see node3_config.py) instead of a hardcoded
    # copy that had drifted to CHARGE_KWH=5.25 regardless of the active export
    # cap, a repeat of a bug Matt had already ordered fixed once before.
    # G98 (Matt's actual live connection) uses the configurable import/export
    # settings. G99 stays a fixed, real DNO-defined figure (50A/5.75kWh per
    # slot) for the comparison scenario — it's a different physical grid
    # connection, not a tunable operating choice.
    _plan_cfg       = _cfg.load_config()
    BAT_KWH         = _plan_cfg["battery_kwh"]
    MIN_SOC         = BAT_KWH * (_plan_cfg["min_soc_pct"] / 100.0)
    CHARGE_KWH      = _plan_cfg["import_kw"] * 0.5    # configurable charge rate
    EXPORT_KWH_G98  = _plan_cfg["export_kw"] * 0.5    # configurable export rate
    EXPORT_KWH_G99  = 5.75   # fixed — G99 DNO export cap (pending ref 260420-000198)
    RTE             = 0.88
    # DAILY_LOAD_KWH is the assumed PHYSICAL home consumption (drains the
    # battery every slot in the SOC trace below) — separate from the BILLING
    # free allowance (FREE_ALLOWANCE_KWH). These used to be the same number
    # (12.0) by coincidence, which meant excess_kwh below was ALWAYS zero —
    # the free allowance exactly matched modelled consumption, so nothing
    # ever fell into the "billed at cost" bracket. Matt's tariff design
    # (19 Aug): homeowner gets 10 kWh/day free from the battery; anything
    # the house draws above that, Dovecote bills back at avg buy price +10%.
    DAILY_LOAD_KWH      = 12.0   # modelled physical home consumption (kWh/day)
    FREE_ALLOWANCE_KWH  = 10.0   # homeowner's free-from-battery allowance (kWh/day)
    EXCESS_MARKUP        = 1.10  # excess billed at avg buy price × this (10% margin)
    LOAD_PER_SLOT   = DAILY_LOAD_KWH / 48.0

    raw   = load_json("fleet_state.json") or {}
    state = normalize_state(raw) or {}
    soc   = float(state.get("soc_kwh", BAT_KWH * 0.5))

    ch_slots = [s for s in slots if s["action"] == "charge"]
    ex_slots = [s for s in slots if s["action"] == "discharge"]
    n_slots  = len(slots)

    # ── G98 SOC trace + P&L ───────────────────────────────────────────────────
    # SOC simulation mirrors simulate.py exactly: house load drawn every slot.
    # P&L is split into:
    #   arbitrage_cost  = electricity bought to fuel exports (what Dovecote spends to earn)
    #   hosting_cost    = electricity consumed by house, given free up to 12 kWh/day
    #                     (homeowner pays back excess above allowance at 0% uplift)
    total_revenue_g98 = 0.0
    total_charge_cost = 0.0   # all charge electricity paid by Dovecote
    house_load_cost   = 0.0   # portion of charge cost attributed to house supply

    for s in slots:
        # House load drawn every slot regardless of action (always-on load)
        soc = max(MIN_SOC, soc - LOAD_PER_SLOT)
        # Track house supply cost at the slot import price (what Dovecote pays for it)
        house_load_cost += LOAD_PER_SLOT * s["importP"] / 100

        if s["action"] == "charge":
            ch  = min(CHARGE_KWH, BAT_KWH - soc)
            soc = min(BAT_KWH, soc + ch)
            total_charge_cost += ch * s["importP"] / 100
        elif s["action"] == "discharge":
            dc  = min(EXPORT_KWH_G98, soc - MIN_SOC)
            dc  = max(0.0, dc)
            soc = max(MIN_SOC, soc - dc)
            total_revenue_g98 += dc * RTE * s["exportP"] / 100

        s["planSoc"] = round(soc, 2)

    # House load within the free 10 kWh/day allowance → Dovecote absorbs it.
    # Anything the house draws above that allowance → homeowner pays it back
    # at avg buy price + 10% (Dovecote's margin on the excess), not at cost.
    house_load_kwh_total  = LOAD_PER_SLOT * n_slots
    house_days            = n_slots / 48.0
    free_allowance_kwh    = FREE_ALLOWANCE_KWH * house_days      # e.g. 1.3125 days = 13.125 kWh
    excess_kwh            = max(0.0, house_load_kwh_total - free_allowance_kwh)
    # Modelled consumption (DAILY_LOAD_KWH=12) now sits above the free
    # allowance (FREE_ALLOWANCE_KWH=10) by design, so excess_kwh is
    # genuinely >0 (≈2kWh/day) rather than always zero as it was when both
    # constants were the same number.
    avg_import_p          = (total_charge_cost / (len(ch_slots) * CHARGE_KWH)
                             if ch_slots else sum(s["importP"] for s in slots) / n_slots)
    house_recovery         = excess_kwh * avg_import_p * EXCESS_MARKUP / 100  # homeowner pays this back, +10% margin
    # hosting_cost = net electricity value given free to homeowner (their grid import savings)
    # Capped at 0 (can't be negative) and at total_charge_cost when no trades.
    hosting_cost_absorbed = max(0.0, min(house_load_cost - house_recovery, total_charge_cost))

    # net_g98        = what Dovecote actually earned in cash from battery trading
    # arbitrage_net  = what Dovecote keeps after giving homeowner their free-electricity benefit
    # hosting_cost   = the portion of battery value passed to the homeowner (non-cash)
    net_g98        = total_revenue_g98 - total_charge_cost       # total Dovecote cash P&L
    arbitrage_net  = net_g98 - hosting_cost_absorbed             # Dovecote's share after hosting

    # ── G99 net — independent SOC simulation with G99 export cap, same charge rate ──
    # Charge rate is unchanged (configurable import rate, default 5.0 kWh/slot).
    # Only export cap increases: configurable G98 export → fixed 5.75 kWh/slot (G99).
    soc_g99        = float(state.get("soc_kwh", BAT_KWH * 0.5))
    total_rev_g99  = 0.0
    total_cost_g99 = 0.0
    for s in slots:
        soc_g99 = max(MIN_SOC, soc_g99 - LOAD_PER_SLOT)
        if s["action"] == "charge":
            ch       = min(CHARGE_KWH, BAT_KWH - soc_g99)   # same charge rate as G98
            soc_g99  = min(BAT_KWH, soc_g99 + ch)
            total_cost_g99 += ch * s["importP"] / 100
        elif s["action"] == "discharge":
            dc       = min(EXPORT_KWH_G99, soc_g99 - MIN_SOC)   # larger export cap
            dc       = max(0.0, dc)
            soc_g99  = max(MIN_SOC, soc_g99 - dc)
            total_rev_g99 += dc * RTE * s["exportP"] / 100
    net_g99 = total_rev_g99 - total_cost_g99

    # ── Annualised projections based on this planning window ─────────────────
    plan_days      = n_slots / 48.0 if n_slots > 0 else 1.0
    annual_g98     = round(net_g98 / plan_days * 365, 2) if plan_days > 0 else 0
    annual_g99     = round(net_g99 / plan_days * 365, 2) if plan_days > 0 else 0
    annual_delta   = round(annual_g99 - annual_g98, 2)

    return jsonify({
        "slots":    slots,
        "summary": {
            "charge_slots":          len(ch_slots),
            "export_slots":          len(ex_slots),
            # Total Dovecote cash position (export revenue minus all charge costs)
            "net_g98":               round(net_g98, 4),
            "net_g99":               round(net_g99, 4),
            # Annualised projections (scale this planning window × 365/plan_days)
            "annual_g98":            annual_g98,
            "annual_g99":            annual_g99,
            "annual_delta":          annual_delta,
            # P&L breakdown
            "total_rev_g98":         round(total_revenue_g98, 4),
            "total_rev_g99":         round(total_rev_g99, 4),
            "total_charge_cost":     round(total_charge_cost, 4),
            # House load split
            "house_load_kwh":        round(house_load_kwh_total, 3),
            "house_load_cost":       round(house_load_cost, 4),    # what Dovecote pays for house supply
            "house_recovery":        round(house_recovery, 4),     # recovered from homeowner (excess)
            "hosting_cost":          round(hosting_cost_absorbed, 4), # Dovecote's free-allowance cost
            # Pure arbitrage profit (hosting cost separated out)
            "arbitrage_net_g98":     round(arbitrage_net, 4),
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
            cached_at = cached.get('_cached_at', 0)
            age_h = (time.time() - cached_at) / 3600
            if age_h < 24:
                print(f'[BACKTEST] Cache hit ({age_h:.1f}h old)')
                out = dict(cached['data'])
                # Surface generation time in the payload itself — not just the
                # server-side cache wrapper — so the dashboard can show the user
                # exactly how fresh these numbers are instead of presenting them
                # as unconditionally live. See stale-data watchdog, 19 Aug 2026.
                out['_generated_at'] = datetime.fromtimestamp(cached_at, tz=timezone.utc).isoformat()
                return jsonify(out)
        except Exception as e:
            print(f'[BACKTEST] Cache read error: {e}')

    try:
        data = _run_backtest()
        now_ts = time.time()
        try:
            with open(cache_path, 'w') as f:
                json.dump({'_cached_at': now_ts, 'data': data}, f)
        except Exception as e:
            print(f'[BACKTEST] Cache write error: {e}')
        data['_generated_at'] = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()
        return jsonify(data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route("/api/backtest-lp")
def api_backtest_lp():
    """
    12-month LP-optimal backtest vs greedy, day-by-day.

    Fetches 12 months of real Octopus Agile import prices, groups by UTC calendar
    day, and for each day runs:
      - LP:    scipy HiGHS linear programme — globally optimal for the known 48-slot window
      - Greedy: percentile-threshold heuristic — matches the old algorithm

    Rates sourced from node3_config (single source of truth) — default 72kWh /
    10kW import / 6kW export for G98; G99 export stays fixed at the real DNO
    figure (50A/5.75kWh per slot) since it models a different grid connection.
    Results cached 24h in backtest_lp_cache.json.  Add ?force=1 to rerun.
    """
    cache_path = os.path.join(BASE_DIR, "backtest_lp_cache.json")
    force      = request.args.get('force', '').lower() in ('1', 'true', 'yes')

    if not force and os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            age_h = (time.time() - cached.get('_cached_at', 0)) / 3600
            if age_h < 24:
                print(f'[BT-LP] Cache hit ({age_h:.1f}h old)')
                return jsonify(cached['data'])
        except Exception as e:
            print(f'[BT-LP] Cache read error: {e}')

    try:
        import numpy as np
        from scipy.optimize import linprog
    except ImportError:
        return jsonify({'error': 'scipy not installed — run docker compose build --no-cache'}), 500

    # ── Constants ────────────────────────────────────────────────────────────
    # Sourced from node3_config (single source of truth) instead of a
    # hardcoded 5.25-vs-3.68 mismatch — see node3_config.py.
    _lp_cfg        = _cfg.load_config()
    BATTERY        = _lp_cfg["battery_kwh"]
    MIN_SOC        = BATTERY * (_lp_cfg["min_soc_pct"] / 100.0)
    CHARGE_KWH     = _lp_cfg["import_kw"] * 0.5   # configurable, both G98 & G99 (same inverter)
    EXPORT_G98     = _lp_cfg["export_kw"] * 0.5   # configurable G98 export rate
    EXPORT_G99     = 5.75    # fixed — G99 DNO export cap: 50A × 230V × 0.5h (pending)
    RTE            = 0.88
    VLP_P          = 40.0
    LOAD_DAY       = 12.0
    LOAD_SLOT      = LOAD_DAY / 48.0

    # ── Fetch 12 months of import prices ─────────────────────────────────────
    print('[BT-LP] Fetching 12-month Agile import prices…')
    imp_code = _bt_discover(is_export=False)
    from_dt  = (datetime.now(timezone.utc) - timedelta(days=366)).strftime("%Y-%m-%dT%H:%M:%SZ")
    imp_url  = (f'https://api.octopus.energy/v1/products/{imp_code}'
                f'/electricity-tariffs/E-1R-{imp_code}-{_BT_REGION}/standard-unit-rates/'
                f'?period_from={from_dt}&page_size=1500')
    import_prices = _bt_fetch_all(imp_url)
    print(f'[BT-LP] {len(import_prices)} import slots fetched')

    # ── Group by UTC calendar day ─────────────────────────────────────────────
    from collections import defaultdict
    by_day = defaultdict(list)
    for slot in import_prices:
        day = slot['valid_from'][:10]   # 'YYYY-MM-DD'
        by_day[day].append(slot)
    # Sort slots within each day
    for day in by_day:
        by_day[day].sort(key=lambda s: s['valid_from'])

    # ── Per-day LP and greedy functions ───────────────────────────────────────
    def lp_day(prices_p, init_soc, charge_kwh=CHARGE_KWH, export_kwh=EXPORT_G98):
        n = len(prices_p)
        if n < 10:
            return 0.0, init_soc
        p       = np.array(prices_p, dtype=float)
        c_obj   = np.concatenate([p, -p * RTE])
        A_ub    = np.zeros((2 * n, 2 * n))
        b_ub    = np.zeros(2 * n)
        for t in range(1, n + 1):
            rl = t - 1; ru = n + (t - 1)
            A_ub[rl, :t] = -1;  A_ub[rl, n:n+t] =  1
            b_ub[rl]     = init_soc - t * LOAD_SLOT - MIN_SOC
            A_ub[ru, :t] =  1;  A_ub[ru, n:n+t] = -1
            b_ub[ru]     = BATTERY - init_soc + t * LOAD_SLOT
        bounds = [(0, charge_kwh)] * n + [(0, export_kwh)] * n
        res    = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method='highs')
        if res.status != 0:
            return 0.0, init_soc
        c_v = res.x[:n]; d_v = res.x[n:]
        rev_p = sum(d_v[i]*prices_p[i]*RTE - c_v[i]*prices_p[i] for i in range(n))
        # Walk SOC to get end state
        soc = init_soc
        for i in range(n):
            soc = max(0.0, soc - LOAD_SLOT)
            if d_v[i] > export_kwh * 0.1:
                soc = max(MIN_SOC, soc - min(export_kwh, soc - MIN_SOC))
            elif c_v[i] > charge_kwh * 0.1:
                soc = min(BATTERY, soc + min(charge_kwh, BATTERY - soc))
            soc = max(MIN_SOC, min(BATTERY, soc))
        return rev_p / 100.0, soc   # return £ and end SOC

    def greedy_day(prices_p, init_soc):
        n = len(prices_p)
        if n < 10:
            return 0.0, init_soc
        sorted_asc  = sorted(range(n), key=lambda i: prices_p[i])
        sorted_desc = sorted(range(n), key=lambda i: prices_p[i], reverse=True)
        usable      = BATTERY - MIN_SOC
        max_cs      = max(1, int(usable / EXPORT_G98) + 1)
        cands       = [i for i in sorted_asc if prices_p[i] < VLP_P][:max_cs]
        avg_cp      = sum(prices_p[i] for i in cands) / len(cands) if cands else min(prices_p)
        be_p        = (CHARGE_KWH * avg_cp) / (EXPORT_G98 * RTE)
        tentative   = ['idle'] * n
        dbud        = usable
        for i in sorted_desc:
            if prices_p[i] >= VLP_P:
                tentative[i] = 'discharge'; dbud -= EXPORT_G98; continue
            if dbud <= 0 or prices_p[i] <= be_p: break
            tentative[i] = 'discharge'; dbud -= EXPORT_G98
        for i in sorted_asc:
            if prices_p[i] > be_p: break
            if tentative[i] != 'idle': continue
            tentative[i] = 'charge'
        soc = init_soc; rev_p = 0.0
        for i in range(n):
            soc = max(0.0, soc - LOAD_SLOT)
            p   = prices_p[i]
            if prices_p[i] >= VLP_P and soc > MIN_SOC + 0.1:
                di = min(EXPORT_G98, soc - MIN_SOC); soc -= di; rev_p += di * p * RTE
            elif tentative[i] == 'charge':
                ch = min(CHARGE_KWH, BATTERY - soc)
                if ch > 0.01: soc += ch; rev_p -= ch * p
            elif tentative[i] == 'discharge':
                av = soc - MIN_SOC
                if av >= EXPORT_G98 * 0.5:
                    di = min(EXPORT_G98, av); soc -= di; rev_p += di * p * RTE
            soc = max(MIN_SOC, min(BATTERY, soc))
        return rev_p / 100.0, soc

    # ── Run all algorithms across all days ────────────────────────────────────
    days_sorted  = sorted(by_day.keys())
    lp_monthly   = defaultdict(float)
    g99_monthly  = defaultdict(float)
    gr_monthly   = defaultdict(float)
    lp_daily     = {}
    g99_daily    = {}
    gr_daily     = {}
    lp_soc  = BATTERY * 0.5    # start at 50%
    g99_soc = BATTERY * 0.5
    gr_soc  = BATTERY * 0.5

    print(f'[BT-LP] Running LP(G98) + LP(G99) + greedy across {len(days_sorted)} days…')
    for day in days_sorted:
        slots    = by_day[day]
        prices_p = [float(s['value_inc_vat']) for s in slots]
        month    = day[:7]

        lp_rev,  lp_soc  = lp_day(prices_p, lp_soc,  charge_kwh=CHARGE_KWH, export_kwh=EXPORT_G98)
        g99_rev, g99_soc = lp_day(prices_p, g99_soc, charge_kwh=CHARGE_KWH, export_kwh=EXPORT_G99)
        gr_rev,  gr_soc  = greedy_day(prices_p, gr_soc)

        lp_monthly[month]  += lp_rev
        g99_monthly[month] += g99_rev
        gr_monthly[month]  += gr_rev
        lp_daily[day]       = round(lp_rev, 4)
        g99_daily[day]      = round(g99_rev, 4)
        gr_daily[day]       = round(gr_rev, 4)

    lp_total  = sum(lp_monthly.values())
    g99_total = sum(g99_monthly.values())
    gr_total  = sum(gr_monthly.values())
    uplift    = lp_total - gr_total
    uplift_pct = (uplift / abs(gr_total) * 100) if gr_total else 0
    g99_uplift = g99_total - lp_total
    g99_uplift_pct = (g99_uplift / abs(lp_total) * 100) if lp_total else 0

    print(f'[BT-LP] G98 LP=£{lp_total:.2f}  G99 LP=£{g99_total:.2f}  '
          f'Greedy=£{gr_total:.2f}  LP/Greedy uplift=+£{uplift:.2f} ({uplift_pct:.1f}%)')
    print(f'[BT-LP] G99 vs G98 uplift: +£{g99_uplift:.2f} ({g99_uplift_pct:.1f}%)')

    # Build monthly comparison list
    all_months = sorted(set(list(lp_monthly.keys()) + list(gr_monthly.keys())))
    monthly_compare = [
        {
            'month':      m,
            'lp':         round(lp_monthly.get(m, 0), 2),
            'lp_g99':     round(g99_monthly.get(m, 0), 2),
            'greedy':     round(gr_monthly.get(m, 0), 2),
            'uplift':     round(lp_monthly.get(m, 0) - gr_monthly.get(m, 0), 2),
            'g99_uplift': round(g99_monthly.get(m, 0) - lp_monthly.get(m, 0), 2),
        }
        for m in all_months
    ]

    result = {
        'lp_total_gbp':        round(lp_total, 2),
        'lp_g99_total_gbp':    round(g99_total, 2),
        'greedy_total_gbp':    round(gr_total, 2),
        'uplift_gbp':          round(uplift, 2),
        'uplift_pct':          round(uplift_pct, 1),
        'g99_uplift_gbp':      round(g99_uplift, 2),
        'g99_uplift_pct':      round(g99_uplift_pct, 1),
        'days_analysed':       len(days_sorted),
        'monthly':             monthly_compare,
        'lp_daily':            lp_daily,
        'lp_g99_daily':        g99_daily,
        'greedy_daily':        gr_daily,
        'algorithm':           'scipy HiGHS LP  vs  percentile-greedy',
        'rates':               f'G98: charge={CHARGE_KWH}kWh/slot export={EXPORT_G98}kWh/slot | G99: export={EXPORT_G99}kWh/slot',
        'rte':                 RTE,
        'battery_kwh':         BATTERY,
        'run_at':              datetime.now(timezone.utc).isoformat(),
    }

    try:
        with open(cache_path, 'w') as f:
            json.dump({'_cached_at': time.time(), 'data': result}, f)
    except Exception as e:
        print(f'[BT-LP] Cache write error: {e}')

    return jsonify(result)


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
        hw_result = None
        if result.returncode == 0 and mode == "single":
            hw_result = _run_hardware_bridge()
        return jsonify({
            "status":    "ok" if result.returncode == 0 else "error",
            "mode":      mode,
            "stdout":    result.stdout[-3000:],
            "stderr":    result.stderr[-2000:],
            "exit_code": result.returncode,
            "hardware":  "bridge_called" if hw_result is not None else "skipped"
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


def _run_hardware_bridge():
    """
    Run hardware_bridge.py as a subprocess — same pattern as simulate.py.
    Avoids importlib/volume-mount locking issues on macOS Docker.
    """
    try:
        bridge_path = os.path.join(BASE_DIR, "hardware_bridge.py")
        if not os.path.exists(bridge_path):
            print("[HW-BRIDGE] hardware_bridge.py not found — skipping", flush=True)
            return None
        result = subprocess.run(
            [sys.executable, bridge_path],
            timeout=30, capture_output=True, text=True
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode == 0:
            try:
                data   = json.loads(stdout)
                mode   = data.get("mode", "?")
                sent   = data.get("sent", False)
                path   = data.get("path", "none")
                action = data.get("lp_action", "?")
                wm     = data.get("work_mode", "?")
                if sent:
                    print(f"[HW-BRIDGE] OK — mode={mode} action={action} → {wm} via {path}", flush=True)
                else:
                    reason = data.get("reason") or data.get("error", "no control path configured")
                    print(f"[HW-BRIDGE] {reason}", flush=True)
            except Exception:
                print(f"[HW-BRIDGE] OK — {stdout[:120] or '(no output)'}", flush=True)
        else:
            print(f"[HW-BRIDGE] Error (rc={result.returncode}): {stderr[:200]}", flush=True)
        return result
    except Exception as exc:
        print(f"[HW-BRIDGE] Exception: {exc}", flush=True)
        return None


def _simulation_loop():
    """
    Background thread: run simulate.py immediately on startup, then again
    at each 30-minute Agile slot boundary (HH:00 / HH:30).
    After each successful simulate run, calls hardware_bridge to send
    the current slot command to the FoxESS inverter.
    """
    # Run immediately on startup so prices.json is fresh from the first request.
    print("[NODE-3 scheduler] Startup run — fetching fresh prices…", flush=True)
    try:
        rc, err = _run_simulate()
        if rc == 0:
            print("[NODE-3 scheduler] Startup simulate.py OK", flush=True)
            _run_hardware_bridge()
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
                _run_hardware_bridge()
            else:
                print(f"[NODE-3 scheduler] simulate.py error: {err[:200]}", flush=True)
        except Exception as exc:
            print(f"[NODE-3 scheduler] Exception: {exc}", flush=True)


# ─────────────────────────────────────────────
# HARDWARE STATUS + MODE API
# ─────────────────────────────────────────────
@app.route("/api/hardware-status")
def api_hardware_status():
    """Current hardware bridge status: mode, last command, control paths."""
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(BASE_DIR, "hardware_bridge.py"), "--status"],
            timeout=10, capture_output=True, text=True
        )
        return jsonify(json.loads(result.stdout))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/set-mode", methods=["POST"])
def api_set_mode():
    """
    Change operational mode. Body: {"mode": "pre_commissioning|self_consumption|full_export",
                                     "g99_active": true|false}
    Requires NODE3_API_KEY header if key is set.
    """
    if not _check_api_key():
        return jsonify({"error": "Unauthorised"}), 401
    try:
        body = request.get_json(force=True) or {}
        mode = body.get("mode", "")
        g99  = body.get("g99_active", None)
        cmd  = [sys.executable, os.path.join(BASE_DIR, "hardware_bridge.py"), "--set-mode", mode]
        if g99:
            cmd.append("--g99")
        result = subprocess.run(cmd, timeout=10, capture_output=True, text=True)
        if result.returncode == 0:
            return jsonify({"ok": True, "output": result.stdout.strip()})
        return jsonify({"error": result.stderr.strip()}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

    # Start Battery-Emulator MQTT SOC listener (daemon — dies with server)
    mqtt_thread = threading.Thread(target=_start_mqtt_soc_listener, daemon=True, name="mqtt-soc")
    mqtt_thread.start()

    app.run(host=args.host, port=args.port, debug=False, threaded=True)
