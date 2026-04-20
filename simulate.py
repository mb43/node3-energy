#!/usr/bin/env python3
"""
NODE-3 Energy Arbitrage Simulation Engine
Fetches live Octopus Agile prices + Open-Meteo solar data,
runs arbitrage strategy for the Node-3 installation (single home),
and appends results to history.csv.

Run manually:   python simulate.py
Backfill 48h:   python simulate.py --backfill
GitHub Actions: runs every 30 mins via cron

Algorithm: full lookahead optimizer across all available slots.
No hardcoded time-of-day restrictions on charge or discharge.
Charges in globally cheapest slots, discharges in globally most expensive,
respecting SOC constraints throughout the window.
"""

import os
import json
import csv
import sys
import math
import argparse
import requests
from datetime import datetime, timedelta, timezone

# ---------------------------------------------
# CONFIGURATION
# ---------------------------------------------
BATTERY_KWH        = 72.0    # 3x Nissan e-NV200 packs = 72kWh nominal
MIN_SOC_KWH        = 7.2     # 10% reserve (never discharge below this)
INITIAL_SOC_KWH    = 36.0    # starting SOC (50%)
CHARGE_RATE_KW     = 10.5    # FoxESS 10.5kW HV inverter
DAILY_LOAD_KWH     = 12.0    # household consumption per day
SOLAR_KWP          = 0.0     # no solar modelled (pure arbitrage)
SOLAR_EFFICIENCY   = 0.18    # panel efficiency
BUY_PERCENTILE     = 35      # charge when price < 35th percentile of window
SELL_PERCENTILE    = 60      # discharge when price > 60th percentile of window
ROUND_TRIP_EFF     = 0.88    # FoxESS + Nissan cell round-trip efficiency
EXPORT_KWH         = 3.68    # 32A x 230V x 0.5h = G98 single-phase DNO export cap
                              # G99 50A upgrade -> 5.75 kWh/slot (apply via SSEN fast-track)
EXPORT_RATE_P_DEF  = 15.0    # Conservative Octopus Outgoing default (p/kWh) when live
                              # export prices unavailable; live prices preferred
VLP_PRICE_P        = 40.0    # VLP activation threshold: serve house first when >= 40p

# NO peak window restriction. Algorithm optimises across all 48 slots regardless
# of time of day. Midday solar dumps, overnight lows, morning spikes — all captured.

# UK region codes: A=Eastern, B=East Mids, C=London, D=North Wales/Merseyside,
# E=Midlands, F=NE England, G=NW England, H=Southern, J=SE England, K=SW England,
# L=Yorkshire, M=North Scotland, N=South Scotland, P=South Wales
REGION = os.environ.get("AGILE_REGION", "H")  # Default: Southern England (Hampshire)

# Coordinates for Open-Meteo (Southampton area)
LAT = float(os.environ.get("LATITUDE",  "50.9"))
LON = float(os.environ.get("LONGITUDE", "-1.4"))

# ---------------------------------------------
# FILE PATHS
# ---------------------------------------------
BASE_DIR            = os.path.dirname(os.path.abspath(__file__))
STATE_FILE          = os.path.join(BASE_DIR, "fleet_state.json")
PRICES_FILE         = os.path.join(BASE_DIR, "prices.json")
EXPORT_PRICES_FILE  = os.path.join(BASE_DIR, "export_prices.json")
WEATHER_FILE        = os.path.join(BASE_DIR, "weather.json")
HISTORY_FILE        = os.path.join(BASE_DIR, "history.csv")
DISPATCH_PLAN_FILE  = os.path.join(BASE_DIR, "dispatch_plan.json")


# ---------------------------------------------
# OCTOPUS AGILE IMPORT PRICES
# ---------------------------------------------
def discover_agile_product():
    """Dynamically find the current live Agile import product code."""
    try:
        resp = requests.get(
            "https://api.octopus.energy/v1/products/",
            params={'brand': "OCTOPUS_ENERGY", 'page_size': 100},
            timeout=15
        )
        resp.raise_for_status()
        products = resp.json().get("results", [])
        agile = [
            p for p in products
            if "agile" in p.get("display_name", "").lower()
            and p.get("is_available", True)
            and not p.get("is_export", False)
        ]
        if not agile:
            return None
        agile.sort(key=lambda p: p.get("available_from") or "", reverse=True)
        return agile[0]['code']
    except Exception as e:
        print("[WARN] Could not discover Agile product: " + str(e))
        return None


def fetch_agile_prices(product_code, region=REGION, from_dt=None, hours=48):
    """
    Fetch Agile half-hourly import prices from Octopus API.
    Returns list sorted ascending by valid_from.
    Fetches up to 48h ahead to enable lookahead planning.
    """
    if from_dt is None:
        from_dt = datetime.now(timezone.utc) - timedelta(hours=hours)

    tariff_code = "E-1R-" + product_code + "-" + region
    url = ("https://api.octopus.energy/v1/products/" + product_code
           + "/electricity-tariffs/" + tariff_code + "/standard-unit-rates/")
    try:
        resp = requests.get(
            url,
            params={
                'period_from': from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                'page_size': 200
            },
            timeout=15
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        results.sort(key=lambda x: x['valid_from'])
        return results
    except Exception as e:
        print("[WARN] Could not fetch prices for " + tariff_code + ": " + str(e))
        return []


def load_cached_prices():
    if os.path.exists(PRICES_FILE):
        try:
            with open(PRICES_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_prices(prices):
    with open(PRICES_FILE, "w") as f:
        json.dump(prices, f)


# ---------------------------------------------
# OCTOPUS AGILE OUTGOING (EXPORT) PRICES
# ---------------------------------------------
def fetch_agile_outgoing_prices(region=REGION, hours=48):
    """Fetch Agile Outgoing export prices. Falls back to EXPORT_RATE_P_DEF default."""
    try:
        resp = requests.get(
            "https://api.octopus.energy/v1/products/",
            params={'brand': "OCTOPUS_ENERGY", 'is_export': True, 'page_size': 100},
            timeout=15
        )
        resp.raise_for_status()
        products = resp.json().get("results", [])
        outgoing = [p for p in products if "agile" in p.get("display_name", "").lower()]
        if not outgoing:
            print("[WARN] No Agile Outgoing product found - using default export rate")
            return []
        outgoing.sort(key=lambda p: p.get("available_from") or "", reverse=True)
        product_code = outgoing[0]['code']
        tariff_code = "E-1R-" + product_code + "-" + region
        from_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
        url = ("https://api.octopus.energy/v1/products/" + product_code
               + "/electricity-tariffs/" + tariff_code + "/standard-unit-rates/")
        resp = requests.get(url, params={
            'period_from': from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            'page_size': 200
        }, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        results.sort(key=lambda x: x['valid_from'])
        print("[OK] Agile Outgoing export prices: " + str(len(results)) + " slots")
        return results
    except Exception as e:
        print("[WARN] Could not fetch Agile Outgoing prices: " + str(e)
              + " - using default " + str(EXPORT_RATE_P_DEF) + "p")
        return []


def load_cached_export_prices():
    if os.path.exists(EXPORT_PRICES_FILE):
        try:
            with open(EXPORT_PRICES_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_export_prices(prices):
    with open(EXPORT_PRICES_FILE, "w") as f:
        json.dump(prices, f)


def get_export_rate_p(export_prices, slot_dt):
    """Look up export rate (p/kWh) for a slot. Falls back to EXPORT_RATE_P_DEF."""
    target = slot_dt.strftime("%Y-%m-%dT%H:%M")
    for p in export_prices:
        if (p.get("valid_from") or "").startswith(target):
            return float(p['value_inc_vat'])
    return EXPORT_RATE_P_DEF


# ---------------------------------------------
# OPEN-METEO SOLAR DATA
# ---------------------------------------------
def fetch_solar_forecast(lat=LAT, lon=LON):
    """Fetch solar radiation + temperature from Open-Meteo (no API key needed)."""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                'latitude': lat,
                'longitude': lon,
                'hourly': "direct_radiation,diffuse_radiation,temperature_2m,cloud_cover",
                'timezone': "Europe/London",
                'past_days': 2,
                'forecast_days': 2
            },
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print("[WARN] Could not fetch solar forecast: " + str(e))
        return None


def load_cached_weather():
    if os.path.exists(WEATHER_FILE):
        try:
            with open(WEATHER_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_weather(weather):
    with open(WEATHER_FILE, "w") as f:
        json.dump(weather, f)


def get_solar_kwh_for_slot(weather, slot_dt, kwp=SOLAR_KWP, efficiency=SOLAR_EFFICIENCY):
    """
    Convert hourly solar radiation (W/m2) to kWh for a 30-min slot.
    Using STC approximation: Energy = Radiation x Area x Efficiency x Duration
    """
    if not weather or kwp == 0:
        return 0.0
    try:
        times   = weather['hourly']['time']
        direct  = weather['hourly']['direct_radiation']
        diffuse = weather['hourly']['diffuse_radiation']

        try:
            import pytz
            tz = pytz.timezone("Europe/London")
            local_dt = slot_dt.astimezone(tz)
        except Exception:
            local_dt = slot_dt

        hour_key = local_dt.strftime("%Y-%m-%dT%H:00")

        if hour_key not in times:
            return 0.0

        idx = times.index(hour_key)
        total_rad_wm2 = max(0, (direct[idx] or 0)) + 0.5 * max(0, (diffuse[idx] or 0))
        area_m2   = kwp * 6.0
        power_kw  = total_rad_wm2 * area_m2 * efficiency / 1000.0
        energy_kwh = power_kw * 0.5

        return max(0.0, energy_kwh)
    except Exception:
        return 0.0


# ---------------------------------------------
# LOOKAHEAD OPTIMIZER
# ---------------------------------------------
def percentile(values, pct):
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(len(s) * pct / 100)))
    return s[idx]


def plan_optimal_dispatch(price_slots, initial_soc_kwh, battery_kwh=BATTERY_KWH,
                          min_soc_kwh=MIN_SOC_KWH):
    """
    Lookahead optimizer: plan charge/discharge for all available price slots.
    No time-of-day restrictions. Works on any window — overnight, midday solar
    dumps, morning spikes, all treated equally.

    Algorithm:
      1. Compute buy/sell thresholds from the actual price distribution of this window
      2. Label each slot tentatively: charge (cheap) / discharge (expensive) / idle
      3. For discharge slots, only discharge if it's profitable after round-trip losses
         (i.e. sell_price * eff > buy_price of the cheapest available charge slot)
      4. Walk slots in time order, enforcing SOC constraints:
         - Can't discharge more than available above MIN_SOC
         - Can't charge above BATTERY_KWH
         - Skip action if SOC constraint would be violated
      5. VLP override: always discharge when price >= VLP_PRICE_P regardless of plan

    Returns: dict mapping valid_from string -> 'charge' | 'discharge' | 'idle'
    """
    if not price_slots:
        return {}

    charge_per_slot  = CHARGE_RATE_KW * 0.5   # 5.25 kWh max
    discharge_per_slot = EXPORT_KWH            # 3.68 kWh (G98 cap)
    load_per_slot    = DAILY_LOAD_KWH / 48.0   # ~0.25 kWh/slot

    prices_vals = [s['value_inc_vat'] for s in price_slots]
    buy_thr  = percentile(prices_vals, BUY_PERCENTILE)
    sell_thr = percentile(prices_vals, SELL_PERCENTILE)
    min_buy  = min(prices_vals) if prices_vals else 0.0

    print("[PLAN] Window: " + str(len(price_slots)) + " slots  "
          + "buy<" + str(round(buy_thr, 2)) + "p  "
          + "sell>" + str(round(sell_thr, 2)) + "p  "
          + "min=" + str(round(min_buy, 2)) + "p")

    # Phase 1: tentative labels based purely on price
    tentative = []
    for s in price_slots:
        p = s['value_inc_vat']
        if p <= buy_thr:
            tentative.append('charge')
        elif p >= sell_thr:
            # Only worth discharging if: sell_price * eff > cheapest_buy_price
            # This filters out cases where the spread doesn't cover round-trip losses
            if p * ROUND_TRIP_EFF > min_buy:
                tentative.append('discharge')
            else:
                tentative.append('idle')
        else:
            tentative.append('idle')

    # Phase 2: walk in time order, enforce SOC constraints
    soc = initial_soc_kwh
    plan = {}

    for i, slot in enumerate(price_slots):
        ts    = slot['valid_from']
        label = tentative[i]
        price = slot['value_inc_vat']

        # Household load every slot
        soc = max(0.0, soc - load_per_slot)

        # VLP override: always discharge when price is very high
        if price >= VLP_PRICE_P and soc > min_soc_kwh + 0.1:
            available = soc - min_soc_kwh
            discharge = min(discharge_per_slot, available)
            if discharge > 0.01:
                soc -= discharge
                plan[ts] = 'discharge'
            else:
                plan[ts] = 'idle'

        elif label == 'charge':
            headroom = battery_kwh - soc
            if headroom > 0.01:
                charge = min(charge_per_slot, headroom)
                soc += charge
                plan[ts] = 'charge'
            else:
                plan[ts] = 'idle'  # battery full

        elif label == 'discharge':
            available = soc - min_soc_kwh
            if available >= discharge_per_slot * 0.5:
                discharge = min(discharge_per_slot, available)
                soc -= discharge
                plan[ts] = 'discharge'
            else:
                plan[ts] = 'idle'  # not enough charge to discharge

        else:
            plan[ts] = 'idle'

        soc = max(min_soc_kwh, min(battery_kwh, soc))

    charged    = sum(1 for v in plan.values() if v == 'charge')
    discharged = sum(1 for v in plan.values() if v == 'discharge')
    idle       = sum(1 for v in plan.values() if v == 'idle')
    total      = len(plan)
    print("[PLAN] charge=" + str(charged) + " (" + str(round(100*charged/total)) + "%)"
          + "  discharge=" + str(discharged) + " (" + str(round(100*discharged/total)) + "%)"
          + "  idle=" + str(idle) + " (" + str(round(100*idle/total)) + "%)")

    return plan


def save_dispatch_plan(plan):
    with open(DISPATCH_PLAN_FILE, "w") as f:
        json.dump(plan, f)


def load_dispatch_plan():
    if os.path.exists(DISPATCH_PLAN_FILE):
        try:
            with open(DISPATCH_PLAN_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ---------------------------------------------
# NODE-3 STATE
# ---------------------------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            if data and "soc_kwh" in data:
                return data
            if data and "homes" in data and data['homes']:
                h = data['homes'][0]
                return {
                    'soc_kwh':          h.get("soc_kwh", INITIAL_SOC_KWH),
                    'profit_gbp':       data.get("fleet_profit_gbp", h.get("total_profit_gbp", 0.0)),
                    'charged_kwh':      h.get("charged_kwh", 0.0),
                    'discharged_kwh':   h.get("discharged_kwh", 0.0),
                    'last_action':      h.get("last_action", "idle"),
                    'last_price_p':     h.get("last_price_p", 0.0),
                    'buy_threshold_p':  data.get("buy_threshold_p", 0.0),
                    'sell_threshold_p': data.get("sell_threshold_p", 0.0),
                    'last_updated':     data.get("last_updated"),
                    'slots_simulated':  data.get("slots_simulated", 0),
                    'battery_kwh':      h.get("battery_kwh", BATTERY_KWH),
                    'solar_kwp':        h.get("solar_kwp", SOLAR_KWP),
                    'daily_load_kwh':   h.get("daily_load_kwh", DAILY_LOAD_KWH),
                }
        except Exception:
            pass
    return _fresh_state()


def _fresh_state():
    return {
        'soc_kwh':          INITIAL_SOC_KWH,
        'profit_gbp':       0.0,
        'charged_kwh':      0.0,
        'discharged_kwh':   0.0,
        'last_action':      "idle",
        'last_price_p':     0.0,
        'buy_threshold_p':  0.0,
        'sell_threshold_p': 0.0,
        'last_updated':     None,
        'slots_simulated':  0,
        'battery_kwh':      BATTERY_KWH,
        'solar_kwp':        SOLAR_KWP,
        'daily_load_kwh':   DAILY_LOAD_KWH,
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------
# SIMULATION CORE
# ---------------------------------------------
def simulate_slot(state, price_p, slot_dt, weather, buy_thr, sell_thr,
                  export_prices=None, planned_action=None):
    """
    Run one 30-min slot for Node-3 following the pre-computed dispatch plan.
    Falls back to threshold heuristic when no plan is available.

    No time-of-day restrictions. The plan (or threshold logic) decides
    charge/discharge based on price rank within the full window.
    """
    charge_kwh_max = CHARGE_RATE_KW * 0.5    # 5.25 kWh max charge/slot

    bat_kwh      = state.get("battery_kwh",    BATTERY_KWH)
    solar_kwp    = state.get("solar_kwp",      SOLAR_KWP)
    load_kwh_day = state.get("daily_load_kwh", DAILY_LOAD_KWH)
    min_soc      = bat_kwh * (MIN_SOC_KWH / BATTERY_KWH)

    slot_load_kwh = load_kwh_day / 48.0
    solar_kwh     = get_solar_kwh_for_slot(weather, slot_dt, kwp=solar_kwp)
    soc = state['soc_kwh']

    # Apply solar generation and household load
    soc = soc + solar_kwh - slot_load_kwh
    soc = max(0.0, min(bat_kwh, soc))

    action      = "idle"
    slot_profit = 0.0

    # VLP override always takes priority: very high price -> serve house + export
    if price_p >= VLP_PRICE_P and soc > min_soc + 0.1:
        available      = soc - min_soc
        house_served   = min(slot_load_kwh, available)
        export_avail   = max(0.0, available - house_served)
        grid_discharge = min(EXPORT_KWH - house_served, max(0.0, export_avail))
        grid_discharge = max(0.0, grid_discharge)

        total_moved = house_served + grid_discharge
        if total_moved > 0.01:
            soc -= total_moved
            if house_served > 0.01:
                slot_profit += house_served * price_p / 100.0
            if grid_discharge > 0.01:
                export_rate  = get_export_rate_p(export_prices or [], slot_dt)
                slot_profit += grid_discharge * ROUND_TRIP_EFF * export_rate / 100.0
                state['discharged_kwh'] += grid_discharge
            action = "discharging"

    # Follow the pre-computed plan if available
    elif planned_action == 'charge':
        headroom = bat_kwh - soc
        charge   = min(charge_kwh_max, headroom)
        if charge > 0.01:
            soc         += charge
            cost         = charge * price_p / 100.0
            slot_profit -= cost
            state['charged_kwh'] += charge
            action = "charging"

    elif planned_action == 'discharge':
        available  = soc - min_soc
        discharge  = min(EXPORT_KWH, available)
        if discharge > 0.01:
            soc         -= discharge
            export_rate  = get_export_rate_p(export_prices or [], slot_dt)
            revenue      = discharge * ROUND_TRIP_EFF * export_rate / 100.0
            slot_profit += revenue
            state['discharged_kwh'] += discharge
            action = "discharging"

    # Fallback heuristic (no plan available) — no time-of-day restriction
    elif price_p < buy_thr:
        headroom = bat_kwh - soc
        charge   = min(charge_kwh_max, headroom)
        if charge > 0.01:
            soc         += charge
            cost         = charge * price_p / 100.0
            slot_profit -= cost
            state['charged_kwh'] += charge
            action = "charging"

    elif price_p > sell_thr and soc > min_soc + 0.1:
        # No peak window restriction — discharge whenever price > sell threshold
        available  = soc - min_soc
        discharge  = min(EXPORT_KWH, available)
        if discharge > 0.01:
            soc         -= discharge
            export_rate  = get_export_rate_p(export_prices or [], slot_dt)
            revenue      = discharge * ROUND_TRIP_EFF * export_rate / 100.0
            slot_profit += revenue
            state['discharged_kwh'] += discharge
            action = "discharging"

    state['soc_kwh']          = max(min_soc, min(bat_kwh, soc))
    state['profit_gbp']      += slot_profit
    state['last_action']      = action
    state['last_price_p']     = price_p
    state['buy_threshold_p']  = buy_thr
    state['sell_threshold_p'] = sell_thr
    state['last_updated']     = slot_dt.isoformat()
    state['slots_simulated']  = state.get("slots_simulated", 0) + 1

    return slot_profit


def append_history(ts, profit_gbp, slot_profit, price_p, soc_kwh, action):
    """Append one row to history.csv (read-modify-write for VirtioFS compat)."""
    fieldnames = ["timestamp", "profit_gbp", "slot_profit_gbp", "price_p", "soc_kwh", "action"]
    rows = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
        except Exception:
            pass
    nr = {
        'timestamp':       ts,
        'profit_gbp':      round(profit_gbp, 6),
        'slot_profit_gbp': round(slot_profit, 6),
        'price_p':         round(price_p, 4),
        'soc_kwh':         round(soc_kwh, 3),
        'action':          action,
    }
    rows.append(nr)
    rows = rows[-200:]
    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_history_batch(history_rows):
    """Write a full list of history rows at once (used by backfill)."""
    fieldnames = ["timestamp", "profit_gbp", "slot_profit_gbp", "price_p", "soc_kwh", "action"]
    rows = history_rows[-200:]
    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------
# MAIN ENTRY POINTS
# ---------------------------------------------
def run_backfill():
    """
    Simulate the last 48 hours of real Agile prices.
    Uses full lookahead optimizer across all 48 slots — no time restrictions.
    Resets state and replays all slots in order.
    """
    print("[NODE-3] BACKFILL mode - optimising last 48 hours")

    product_code = discover_agile_product()
    if not product_code:
        print("[ERROR] Cannot discover Agile product. Aborting backfill.")
        sys.exit(1)
    print("[OK] Agile import product: " + product_code)

    prices = fetch_agile_prices(product_code, hours=48)
    if not prices:
        print("[ERROR] No price data returned. Aborting.")
        sys.exit(1)
    print("[OK] Fetched " + str(len(prices)) + " import price slots")
    save_prices(prices)

    weather = fetch_solar_forecast()
    if weather:
        save_weather(weather)
        print("[OK] Solar forecast fetched")
    else:
        weather = load_cached_weather()
        if weather:
            print("[WARN] Using cached weather data")
        else:
            print("[WARN] No weather data available - solar ignored")

    export_prices = fetch_agile_outgoing_prices(hours=48)
    if export_prices:
        save_export_prices(export_prices)
    else:
        export_prices = load_cached_export_prices()
        if export_prices:
            print("[WARN] Using cached export prices (" + str(len(export_prices)) + " slots)")
        else:
            print("[WARN] No export prices available - using flat " + str(EXPORT_RATE_P_DEF) + "p default")

    # Run the lookahead optimizer across the full 48-slot window
    dispatch_plan = plan_optimal_dispatch(prices, INITIAL_SOC_KWH)
    save_dispatch_plan(dispatch_plan)

    vals = [p['value_inc_vat'] for p in prices]
    buy_thr  = percentile(vals, BUY_PERCENTILE)
    sell_thr = percentile(vals, SELL_PERCENTILE)

    state = _fresh_state()
    history_rows = []

    for price_slot in prices:
        slot_dt     = datetime.fromisoformat(price_slot['valid_from'].replace('Z', '+00:00'))
        price_p     = price_slot['value_inc_vat']
        planned     = dispatch_plan.get(price_slot['valid_from'], None)
        slot_profit = simulate_slot(state, price_p, slot_dt, weather,
                                    buy_thr, sell_thr,
                                    export_prices=export_prices,
                                    planned_action=planned)
        r = {
            'timestamp':       slot_dt.isoformat(),
            'profit_gbp':      round(state['profit_gbp'], 6),
            'slot_profit_gbp': round(slot_profit, 6),
            'price_p':         round(price_p, 4),
            'soc_kwh':         round(state['soc_kwh'], 3),
            'action':          state['last_action'],
        }
        history_rows.append(r)

    save_state(state)
    write_history_batch(history_rows)

    charged    = sum(1 for r in history_rows if r['action'] == 'charging')
    discharged = sum(1 for r in history_rows if r['action'] == 'discharging')
    total      = len(history_rows)

    print("[DONE] Backfill complete.")
    print("       Profit:     GBP " + str(round(state['profit_gbp'], 4)))
    print("       Slots:      " + str(state['slots_simulated']))
    print("       Charged:    " + str(charged) + "/" + str(total)
          + " slots (" + str(round(100*charged/total)) + "%)")
    print("       Discharged: " + str(discharged) + "/" + str(total)
          + " slots (" + str(round(100*discharged/total)) + "%)")
    print("       SOC:        " + str(round(state['soc_kwh'], 1)) + " kWh")


def run_single():
    """
    Run a single incremental 30-min slot update.
    Fetches up to 24h of forward prices to (re)generate the dispatch plan.
    Follows the plan for the current slot.
    Auto-promotes to full backfill if history.csv is empty or missing.
    """
    history_empty = True
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', newline='') as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
                if len(rows) > 0:
                    history_empty = False
        except Exception:
            pass
    if history_empty:
        print('[NODE-3] History empty - running full 48h backfill...')
        run_backfill()
        return

    print('[NODE-3] SINGLE mode - fetching prices and refreshing plan')
    product_code = discover_agile_product()
    if not product_code:
        print('[ERROR] Cannot discover Agile product. Aborting.')
        sys.exit(1)

    # Fetch from 2h ago to cover current slot + all future published prices (up to 24h ahead)
    from_dt = datetime.now(timezone.utc) - timedelta(hours=2)
    prices = fetch_agile_prices(product_code, from_dt=from_dt, hours=26)
    if not prices:
        print('[ERROR] No price data returned. Aborting.')
        sys.exit(1)
    print('[OK] Fetched ' + str(len(prices)) + ' slots for lookahead planning')

    weather = fetch_solar_forecast()
    if not weather:
        weather = load_cached_weather()

    export_prices = fetch_agile_outgoing_prices(hours=26)
    if not export_prices:
        export_prices = load_cached_export_prices()

    state = load_state()
    if state is None:
        state = _fresh_state()

    # Regenerate the dispatch plan from current SOC across all available future slots
    dispatch_plan = plan_optimal_dispatch(prices, state['soc_kwh'])
    save_dispatch_plan(dispatch_plan)

    vals = [p['value_inc_vat'] for p in prices]
    buy_thr  = percentile(vals, BUY_PERCENTILE)
    sell_thr = percentile(vals, SELL_PERCENTILE)

    last_updated = state.get('last_updated')
    new_prices = []
    for ps in prices:
        slot_from = ps['valid_from'].replace('Z', '+00:00')
        if last_updated is None or slot_from > last_updated:
            new_prices.append(ps)

    if not new_prices:
        print('[NODE-3] No new slots since last run. Nothing to do.')
        return

    for price_slot in new_prices:
        slot_dt     = datetime.fromisoformat(price_slot['valid_from'].replace('Z', '+00:00'))
        price_p     = price_slot['value_inc_vat']
        planned     = dispatch_plan.get(price_slot['valid_from'], None)
        slot_profit = simulate_slot(state, price_p, slot_dt, weather,
                                    buy_thr, sell_thr,
                                    export_prices=export_prices,
                                    planned_action=planned)
        append_history(slot_dt.isoformat(), state['profit_gbp'], slot_profit,
                       price_p, state['soc_kwh'], state['last_action'])

    save_state(state)
    print('[DONE] Single update. Action: ' + state['last_action']
          + '  Price: ' + str(round(state['last_price_p'], 2)) + 'p'
          + '  SOC: ' + str(round(state['soc_kwh'], 1)) + 'kWh'
          + '  Profit: GBP ' + str(round(state['profit_gbp'], 4)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="NODE-3 Arbitrage Simulation Engine")
    parser.add_argument("--backfill", action="store_true",
                        help="Replay last 48h of real prices to populate history")
    args = parser.parse_args()

    if args.backfill:
        run_backfill()
    else:
        run_single()
