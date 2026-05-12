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
MIN_SOC_KWH        = 7.2     # 10% absolute floor (protection — hardware limit)
RESERVE_SOC_KWH    = 36.0    # 50% operational reserve — maintain this between sessions
                              # Regular trades only use capacity ABOVE this floor.
                              # VLP events (>=40p) may draw into the reserve down to MIN_SOC.
                              # Purpose: 72kWh battery must always be ready to capitalise on
                              # price spikes; starting depleted destroys arbitrage capacity.
INITIAL_SOC_KWH    = 36.0    # starting SOC assumption when real state unavailable (50%)
INVERTER_KW        = 10.5    # FoxESS KH10.5 hard inverter limit — never exceeded
DAILY_LOAD_KWH     = 12.0    # household consumption per day
SOLAR_KWP          = 0.0     # no solar modelled (pure arbitrage)
SOLAR_EFFICIENCY   = 0.18    # panel efficiency
ROUND_TRIP_EFF     = 0.88    # FoxESS + Nissan cell round-trip efficiency

# ── DNO export caps ──────────────────────────────────────────────────────────
# CHARGE RATE ALWAYS EQUALS EXPORT CAP (symmetric operation).
# Running asymmetric (charge faster than you can export) is guaranteed loss —
# you pay for energy you cannot profitably discharge. Never do this.
EXPORT_KWH_G98     = 3.68    # 32A × 230V × 0.5h  — G98 DNO cap (active)
EXPORT_KWH_G99     = 5.75    # 50A × 230V × 0.5h  — G99 target (ref 260420-000198)

# ── Active mode — change BOTH lines together when SSEN approves G99 ──────────
EXPORT_KWH         = EXPORT_KWH_G98
CHARGE_RATE_KW     = min(EXPORT_KWH * 2, INVERTER_KW)  # symmetric: kWh/slot × 2 = kW
#                                                         G98 → 7.36 kW / G99 → 10.5 kW

EXPORT_RATE_P_DEF  = 15.0    # Conservative Octopus Outgoing default (p/kWh) when live
                              # export prices unavailable; live prices preferred
VLP_PRICE_P        = 40.0    # VLP threshold: always discharge when price >= 40p

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
DISPATCH_PLAN_FILE       = os.path.join(BASE_DIR, "dispatch_plan.json")
HISTORICAL_STATS_FILE    = os.path.join(BASE_DIR, "historical_stats.json")
HISTORICAL_REFRESH_DAYS  = 7   # Re-fetch 12 months of history weekly


# ---------------------------------------------
# HISTORICAL PRICE INTELLIGENCE
# ---------------------------------------------
def fetch_historical_prices(product_code, region=REGION):
    """
    Fetch 12 months of historical Agile prices from Octopus API in monthly chunks.
    Returns flat list of price records.
    """
    end_dt   = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365)
    tariff_code = "E-1R-" + product_code + "-" + region
    url = ("https://api.octopus.energy/v1/products/" + product_code
           + "/electricity-tariffs/" + tariff_code + "/standard-unit-rates/")
    all_prices = []
    from_dt = start_dt
    while from_dt < end_dt:
        to_dt = min(from_dt + timedelta(days=31), end_dt)
        try:
            resp = requests.get(url, params={
                'period_from': from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                'period_to':   to_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                'page_size':   1500,
            }, timeout=30)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            all_prices.extend(results)
            print("[HIST] " + from_dt.strftime("%Y-%m") + ": " + str(len(results)) + " slots")
        except Exception as e:
            print("[WARN] Historical fetch failed for "
                  + from_dt.strftime("%Y-%m") + ": " + str(e))
        from_dt = to_dt
    return all_prices


def build_historical_stats(prices):
    """
    Build percentile tables from 12 months of prices.
    Indexed by: overall | month-of-year | hour-of-day | month+hour (most specific).
    This gives the engine genuine seasonal + time-of-day context.
    """
    from collections import defaultdict
    overall        = []
    by_month       = defaultdict(list)
    by_hour        = defaultdict(list)
    by_month_hour  = defaultdict(list)

    for p in prices:
        val = p.get('value_inc_vat')
        if val is None:
            continue
        val = float(val)
        if val < -20 or val > 100:   # exclude extreme outliers / plunge pricing
            continue
        ts = p.get('valid_from', '')
        try:
            dt    = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            month = dt.month
            hour  = dt.hour
        except Exception:
            continue
        overall.append(val)
        by_month[month].append(val)
        by_hour[hour].append(val)
        by_month_hour[(month, hour)].append(val)

    def pcts(values):
        if not values:
            return None
        s = sorted(values)
        n = len(s)
        return {
            'p5':  s[max(0, int(n * 0.05))],
            'p15': s[max(0, int(n * 0.15))],
            'p25': s[max(0, int(n * 0.25))],
            'p35': s[max(0, int(n * 0.35))],
            'p50': s[max(0, int(n * 0.50))],
            'p65': s[max(0, int(n * 0.65))],
            'p75': s[max(0, int(n * 0.75))],
            'p85': s[max(0, int(n * 0.85))],
            'p95': s[max(0, int(n * 0.95))],
            'n':   n,
        }

    return {
        'cached_at':     datetime.now(timezone.utc).isoformat(),
        'total_slots':   len(overall),
        'region':        REGION,
        'overall':       pcts(overall),
        'by_month':      {str(m): pcts(v) for m, v in by_month.items()},
        'by_hour':       {str(h): pcts(v) for h, v in by_hour.items()},
        'by_month_hour': {
            str(m) + '_' + str(h): pcts(v)
            for (m, h), v in by_month_hour.items()
        },
    }


def load_historical_stats():
    """Return cached stats if fresh (< HISTORICAL_REFRESH_DAYS old), else None."""
    if not os.path.exists(HISTORICAL_STATS_FILE):
        return None
    try:
        with open(HISTORICAL_STATS_FILE) as f:
            stats = json.load(f)
        cached_at = datetime.fromisoformat(stats['cached_at'])
        if (datetime.now(timezone.utc) - cached_at).days >= HISTORICAL_REFRESH_DAYS:
            return None
        return stats
    except Exception:
        return None


def save_historical_stats(stats):
    with open(HISTORICAL_STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)


def get_or_refresh_historical_stats(product_code):
    """
    Return historical stats, refreshing from API if stale or missing.
    Returns None if API unavailable and no cache exists.
    """
    stats = load_historical_stats()
    if stats:
        print("[HIST] Cached stats: " + str(stats.get('total_slots', '?'))
              + " slots, age < " + str(HISTORICAL_REFRESH_DAYS) + " days")
        return stats
    if not product_code:
        return None
    print("[HIST] Fetching 12-month historical Agile prices (region " + REGION + ")…")
    prices = fetch_historical_prices(product_code)
    if not prices:
        print("[WARN] No historical prices retrieved — using window-only thresholds")
        return None
    stats = build_historical_stats(prices)
    save_historical_stats(stats)
    print("[HIST] Built stats from " + str(stats['total_slots']) + " slots  "
          + "overall p25=" + str(round(stats['overall']['p25'], 2)) + "p  "
          + "p75=" + str(round(stats['overall']['p75'], 2)) + "p")
    return stats


def score_price_vs_history(price_p, slot_dt, stats):
    """
    Score a price 0–100 against 12 months of history for the same month+hour.
    0  = historically cheapest (strong buy signal)
    100 = historically most expensive (strong sell signal)
    Uses month+hour context first, falls back to month, then overall.
    """
    if not stats:
        return 50

    month = str(slot_dt.month)
    hour  = str(slot_dt.hour)
    ctx   = (stats.get('by_month_hour', {}).get(month + '_' + hour)
             or stats.get('by_month',      {}).get(month)
             or stats.get('overall'))
    if not ctx:
        return 50

    ladder = [
        (ctx.get('p5',  -999),  5),
        (ctx.get('p15', -999), 15),
        (ctx.get('p25', -999), 25),
        (ctx.get('p35', -999), 35),
        (ctx.get('p50', -999), 50),
        (ctx.get('p65', -999), 65),
        (ctx.get('p75', -999), 75),
        (ctx.get('p85', -999), 85),
        (ctx.get('p95', -999), 95),
    ]
    if price_p <= ladder[0][0]:
        return 0
    if price_p >= ladder[-1][0]:
        return 100
    for i in range(len(ladder) - 1):
        lo_p, lo_s = ladder[i]
        hi_p, hi_s = ladder[i + 1]
        if lo_p <= price_p <= hi_p:
            if hi_p == lo_p:
                return lo_s
            frac = (price_p - lo_p) / (hi_p - lo_p)
            return lo_s + frac * (hi_s - lo_s)
    return 50


def price_rank_in_window(price_p, all_prices_vals):
    """Percentile rank of price within the current window (0–100)."""
    if not all_prices_vals:
        return 50
    below = sum(1 for v in all_prices_vals if v < price_p)
    return (below / len(all_prices_vals)) * 100


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
                          min_soc_kwh=MIN_SOC_KWH, historical_stats=None,
                          export_kwh_cap=None):
    """
    True greedy optimiser over the known 48-slot Agile price window.

    Octopus Agile publishes the next day's 48 half-hourly prices at ~16:00 each day.
    run_single() fetches from now-2h to now+26h, so:
      - Before 16:00: window = remaining slots of today (known since yesterday's 16:00 publish)
      - After  16:00: window = remaining today + full tomorrow (both now published)
    In either case, all prices in the returned window are REAL published values.
    Historical scoring is not needed and actively harms results (e.g. labelling a 34p
    slot 'idle' because it is historically normal, while labelling 22p 'discharge'
    because it is unusually high for that hour of day). With known prices the correct
    strategy is simple:

    Algorithm:
      1. Sort all slots by import price ascending → cheapest M slots = charge candidates
      2. Calculate actual average charge cost from those M slots (accurate break-even)
      3. Sort all slots by price descending → label as 'discharge' from highest down,
         stopping when price falls below break-even. Higher prices ALWAYS selected
         before lower ones — never discharge at 22p when 34p is in the same window.
      4. VLP override (≥ VLP_PRICE_P): flagged as discharge regardless of ranking.
      5. Walk in time order enforcing SOC constraints. Slots labelled 'idle' hold
         charge in reserve for higher-value slots later in the day.

    Break-even: export_p > (charge_kwh_per_slot × avg_charge_p) / (discharge_kwh_per_slot × RTE)
      G98 example (symmetric 3.68/3.68): 3.68 × 17p / (3.68 × 0.88) = 19.3p  →  discharge above ~19p
      G99 example (symmetric 5.75/5.75): 5.75 × 17p / (5.75 × 0.88) = 19.3p  →  same break-even

    historical_stats param retained for API compatibility but no longer used.
    Returns: dict mapping valid_from string -> 'charge' | 'discharge' | 'idle'
    """
    if not price_slots:
        return {}

    discharge_per_slot = export_kwh_cap if export_kwh_cap is not None else EXPORT_KWH
    charge_per_slot    = discharge_per_slot              # ALWAYS symmetric — charge == export cap
    load_per_slot      = DAILY_LOAD_KWH / 48.0          # 0.25 kWh

    n              = len(price_slots)
    prices_vals    = [s['value_inc_vat'] for s in price_slots]

    print("[PLAN] True greedy optimiser | window=" + str(n) + " slots"
          + "  min=" + str(round(min(prices_vals), 2)) + "p"
          + "  max=" + str(round(max(prices_vals), 2)) + "p"
          + "  avg=" + str(round(sum(prices_vals)/n, 2)) + "p")

    # ── Step 1: estimate how much energy we can usefully cycle ──────────────
    usable_kwh = battery_kwh - min_soc_kwh          # 72 - 7.2 = 64.8 kWh

    # ── Step 2: identify the cheapest charge slots ───────────────────────────
    # Sort indices by price ascending; exclude slots that will be VLP-discharged
    sorted_asc  = sorted(range(n), key=lambda i: prices_vals[i])
    sorted_desc = sorted(range(n), key=lambda i: prices_vals[i], reverse=True)

    vlp_indices = {i for i in range(n) if prices_vals[i] >= VLP_PRICE_P}

    # Take cheapest slots (excluding VLP) up to battery capacity
    max_charge_slots = max(1, int(usable_kwh / charge_per_slot) + 1)
    charge_candidates = [i for i in sorted_asc if i not in vlp_indices][:max_charge_slots]

    # ── Step 3: break-even based on ACTUAL planned charge prices ────────────
    if charge_candidates:
        avg_charge_p = sum(prices_vals[i] for i in charge_candidates) / len(charge_candidates)
    else:
        avg_charge_p = min(prices_vals) if prices_vals else 0.0

    # Export price needed to cover the round-trip cost of one charge-discharge pair
    # charge_cost = charge_per_slot × avg_charge_p
    # revenue     = discharge_per_slot × RTE × export_p
    # break-even: charge_cost = revenue  →  export_p = charge_cost / (discharge_per_slot × RTE)
    breakeven_p = (charge_per_slot * avg_charge_p) / (discharge_per_slot * ROUND_TRIP_EFF)

    print("[PLAN] avg_charge_p=" + str(round(avg_charge_p, 2)) + "p"
          + "  breakeven_export_p=" + str(round(breakeven_p, 2)) + "p"
          + "  discharge_per_slot=" + str(discharge_per_slot) + "kWh")

    # ── Step 4: label slots ──────────────────────────────────────────────────
    tentative = ['idle'] * n

    # Mark discharge slots: highest price first, stop below break-even
    discharge_budget = usable_kwh
    for i in sorted_desc:
        if prices_vals[i] >= VLP_PRICE_P:
            # VLP handled separately in time-walk; mark here so charge slots avoid it
            tentative[i] = 'discharge'
            discharge_budget -= discharge_per_slot
            continue
        if discharge_budget <= 0:
            break
        if prices_vals[i] <= breakeven_p:
            break   # sorted descending — all remaining prices are also below break-even
        tentative[i] = 'discharge'
        discharge_budget -= discharge_per_slot

    # ── Negative price slots: ALWAYS charge (Octopus pays YOU to consume) ───────
    # These are unconditional — free or paid energy, fill regardless of export plan.
    # The SOC walk (Step 5) will skip if battery is already full.
    for i in range(n):
        if prices_vals[i] <= 0 and tentative[i] != 'discharge':
            tentative[i] = 'charge'

    # ── Unified charge allocation (export fuel + reserve restoration) ─────────────
    # Two separate passes previously caused under-counting due to mid-path SOC
    # capping (the linear projection assumed all charge energy was absorbed, but
    # the time walk caps at battery_kwh, so fewer kWh actually enter the battery).
    #
    # Replaced with a single iterative approach: simulate the forward SOC after each
    # slot addition and stop when the reserve floor is met.  This is O(n²) but n≤63
    # so trivially fast.  Negative-price slots (already assigned above) are kept.
    #
    # Phase 1: sub-break-even slots only — these are profitable for export.
    # Phase 2: above-break-even slots if reserve still not met — operational priority.
    #          (Reserve maintenance matters more than marginal charge cost above BE.)

    def _soc_walk(labels):
        """Forward SOC simulation matching Step 5 exactly (no VLP — handled in Step 5)."""
        s = initial_soc_kwh
        for i in range(n):
            s = max(min_soc_kwh, s - load_per_slot)
            if labels[i] == 'charge':
                headroom = battery_kwh - s
                if headroom > 0.01:
                    s = min(battery_kwh, s + min(charge_per_slot, headroom))
            elif labels[i] == 'discharge':
                avail = s - min_soc_kwh
                if avail >= discharge_per_slot * 0.5:
                    s = max(min_soc_kwh, s - min(discharge_per_slot, avail))
            s = max(min_soc_kwh, min(battery_kwh, s))
        return s

    # Phase 1: add profitable charge slots (≤ break-even price) until reserve met
    for i in sorted_asc:
        if prices_vals[i] > breakeven_p:
            break   # sorted ascending — all remaining are above break-even too
        if tentative[i] in ('discharge', 'charge'):
            continue
        if _soc_walk(tentative) >= RESERVE_SOC_KWH:
            break   # reserve already met — stop adding
        tentative[i] = 'charge'

    # Phase 2: if reserve still short, add cheapest remaining idle slots
    # (above break-even is acceptable here — this is reserve maintenance, not trading)
    reserve_added = 0
    for i in sorted_asc:
        if _soc_walk(tentative) >= RESERVE_SOC_KWH:
            break
        if tentative[i] in ('discharge', 'charge'):
            continue
        tentative[i] = 'charge'
        reserve_added += 1

    final_proj = _soc_walk(tentative)
    if reserve_added:
        print("[PLAN] Reserve top-up (phase 2): +" + str(reserve_added) + " above-BE slots"
              + "  projected_end=" + str(round(final_proj, 1)) + "kWh")
    else:
        print("[PLAN] Reserve met by phase-1 charges"
              + "  projected_end=" + str(round(final_proj, 1)) + "kWh")

    # ── Step 5: walk in time order enforcing SOC ─────────────────────────────
    soc  = initial_soc_kwh
    plan = {}

    for i, slot in enumerate(price_slots):
        ts    = slot['valid_from']
        label = tentative[i]
        price = slot['value_inc_vat']

        # Household load every slot (behind-the-meter, not exported)
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
                # SOC insufficient — hold idle, preserving charge for next high slot
                plan[ts] = 'idle'

        else:
            plan[ts] = 'idle'

        soc = max(min_soc_kwh, min(battery_kwh, soc))

    charged    = sum(1 for v in plan.values() if v == 'charge')
    discharged = sum(1 for v in plan.values() if v == 'discharge')
    idle_ct    = sum(1 for v in plan.values() if v == 'idle')
    total      = len(plan)
    print("[PLAN] charge=" + str(charged) + " (" + str(round(100*charged/total)) + "%)"
          + "  discharge=" + str(discharged) + " (" + str(round(100*discharged/total)) + "%)"
          + "  idle=" + str(idle_ct) + " (" + str(round(100*idle_ct/total)) + "%)")

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
                  export_prices=None, planned_action=None, export_kwh_cap=None):
    """
    Run one 30-min slot for Node-3 following the pre-computed dispatch plan.
    Falls back to threshold heuristic when no plan is available.

    No time-of-day restrictions. The plan (or threshold logic) decides
    charge/discharge based on price rank within the full window.
    """
    charge_kwh_max  = CHARGE_RATE_KW * 0.5    # 5.25 kWh max charge/slot
    export_kwh_slot = export_kwh_cap if export_kwh_cap is not None else EXPORT_KWH

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

    # VLP override always takes priority: very high price -> export to grid.
    # NOTE: home load already deducted from SOC at line 720 above. Do NOT
    # re-deduct house_served here — that was the previous double-deduction bug.
    # Just export whatever battery capacity is available above the reserve floor.
    if price_p >= VLP_PRICE_P and soc > min_soc + 0.1:
        available      = soc - min_soc
        grid_discharge = min(export_kwh_slot, available)
        grid_discharge = max(0.0, grid_discharge)

        if grid_discharge > 0.01:
            soc             -= grid_discharge
            export_rate      = get_export_rate_p(export_prices or [], slot_dt)
            slot_profit     += grid_discharge * ROUND_TRIP_EFF * export_rate / 100.0
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
        discharge  = min(export_kwh_slot, available)
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
        available  = soc - min_soc
        discharge  = min(export_kwh_slot, available)
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


HISTORY_FIELDS = [
    "timestamp", "profit_gbp", "slot_profit_gbp", "price_p", "soc_kwh", "action",
    "g99_profit_gbp", "g99_slot_profit_gbp", "g99_soc_kwh", "g99_action",
]


def append_history(ts, profit_gbp, slot_profit, price_p, soc_kwh, action,
                   g99_profit=None, g99_slot_profit=None, g99_soc=None, g99_action=None):
    """Append one row to history.csv including G98 and G99 parallel values."""
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
        'timestamp':            ts,
        'profit_gbp':           round(profit_gbp, 6),
        'slot_profit_gbp':      round(slot_profit, 6),
        'price_p':              round(price_p, 4),
        'soc_kwh':              round(soc_kwh, 3),
        'action':               action,
        'g99_profit_gbp':       round(g99_profit, 6)       if g99_profit      is not None else '',
        'g99_slot_profit_gbp':  round(g99_slot_profit, 6)  if g99_slot_profit is not None else '',
        'g99_soc_kwh':          round(g99_soc, 3)           if g99_soc         is not None else '',
        'g99_action':           g99_action or '',
    }
    rows.append(nr)
    rows = rows[-200:]
    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def write_history_batch(history_rows):
    """Write a full list of history rows at once (used by backfill)."""
    rows = history_rows[-200:]
    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction='ignore')
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
    Falls back to cached prices when the API is unreachable.
    """
    print("[NODE-3] BACKFILL mode - optimising last 48 hours")

    product_code = discover_agile_product()
    if not product_code:
        print("[WARN] API unavailable. Trying cached prices for backfill.")
        prices = load_cached_prices()
        if not prices:
            print("[ERROR] No cached prices available. Aborting backfill.")
            sys.exit(1)
        print("[OK] Using " + str(len(prices)) + " cached import price slots (offline mode)")
    else:
        print("[OK] Agile import product: " + product_code)
        prices = fetch_agile_prices(product_code, hours=48)
        if not prices:
            print("[WARN] API returned no data. Trying cached prices.")
            prices = load_cached_prices()
            if not prices:
                print("[ERROR] No price data available. Aborting.")
                sys.exit(1)
            print("[OK] Using " + str(len(prices)) + " cached import price slots")
        else:
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

    # Fetch 12-month historical stats for intelligent thresholds
    hist_stats = get_or_refresh_historical_stats(product_code)

    # Run dual dispatch plans: G98 (32A current) and G99 (50A target)
    print("[PLAN] --- G98 (32A, 3.68kWh/slot) ---")
    dispatch_plan = plan_optimal_dispatch(prices, INITIAL_SOC_KWH,
                                          historical_stats=hist_stats,
                                          export_kwh_cap=EXPORT_KWH_G98)
    save_dispatch_plan(dispatch_plan)
    print("[PLAN] --- G99 (50A, 5.75kWh/slot) ---")
    dispatch_plan_g99 = plan_optimal_dispatch(prices, INITIAL_SOC_KWH,
                                              historical_stats=hist_stats,
                                              export_kwh_cap=EXPORT_KWH_G99)

    vals = [p['value_inc_vat'] for p in prices]
    buy_thr  = percentile(vals, BUY_PERCENTILE)
    sell_thr = percentile(vals, SELL_PERCENTILE)

    state      = _fresh_state()
    state_g99  = _fresh_state()
    history_rows = []

    for price_slot in prices:
        slot_dt     = datetime.fromisoformat(price_slot['valid_from'].replace('Z', '+00:00'))
        price_p       = price_slot['value_inc_vat']
        planned       = dispatch_plan.get(price_slot['valid_from'], None)
        planned_g99   = dispatch_plan_g99.get(price_slot['valid_from'], None)

        # G98 simulation (current, 32A cap)
        slot_profit = simulate_slot(state, price_p, slot_dt, weather,
                                    buy_thr, sell_thr,
                                    export_prices=export_prices,
                                    planned_action=planned,
                                    export_kwh_cap=EXPORT_KWH_G98)
        # G99 simulation (target, 50A cap)
        g99_profit = simulate_slot(state_g99, price_p, slot_dt, weather,
                                   buy_thr, sell_thr,
                                   export_prices=export_prices,
                                   planned_action=planned_g99,
                                   export_kwh_cap=EXPORT_KWH_G99)
        r = {
            'timestamp':           slot_dt.isoformat(),
            'profit_gbp':          round(state['profit_gbp'], 6),
            'slot_profit_gbp':     round(slot_profit, 6),
            'price_p':             round(price_p, 4),
            'soc_kwh':             round(state['soc_kwh'], 3),
            'action':              state['last_action'],
            'g99_profit_gbp':      round(state_g99['profit_gbp'], 6),
            'g99_slot_profit_gbp': round(g99_profit, 6),
            'g99_soc_kwh':         round(state_g99['soc_kwh'], 3),
            'g99_action':          state_g99['last_action'],
        }
        history_rows.append(r)

    save_state(state)
    write_history_batch(history_rows)

    charged    = sum(1 for r in history_rows if r['action'] == 'charging')
    discharged = sum(1 for r in history_rows if r['action'] == 'discharging')
    total      = len(history_rows)
    g99_final  = history_rows[-1]['g99_profit_gbp'] if history_rows else 0
    g98_final  = history_rows[-1]['profit_gbp']     if history_rows else 0

    print("[DONE] Backfill complete.")
    print("       G98 Profit: GBP " + str(round(state['profit_gbp'], 4))
          + "  (32A current)")
    print("       G99 Profit: GBP " + str(round(state_g99['profit_gbp'], 4))
          + "  (50A upgrade)  +" + str(round(state_g99['profit_gbp'] - state['profit_gbp'], 4)) + " delta")
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
    Falls back to cached prices when the API is unreachable.
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
    offline_mode = False

    if not product_code:
        print('[WARN] API unavailable. Falling back to cached prices (offline mode).')
        prices = load_cached_prices()
        if not prices:
            print('[ERROR] No cached prices available. Aborting.')
            sys.exit(1)
        print('[OK] Using ' + str(len(prices)) + ' cached price slots')
        offline_mode = True
    else:
        # Fetch from 2h ago to cover current slot + all future published prices (up to 24h ahead)
        from_dt = datetime.now(timezone.utc) - timedelta(hours=2)
        prices = fetch_agile_prices(product_code, from_dt=from_dt, hours=26)
        if not prices:
            print('[WARN] API returned no data. Falling back to cached prices.')
            prices = load_cached_prices()
            if not prices:
                print('[ERROR] No price data available. Aborting.')
                sys.exit(1)
            print('[OK] Using ' + str(len(prices)) + ' cached price slots')
            offline_mode = True
        else:
            print('[OK] Fetched ' + str(len(prices)) + ' slots for lookahead planning')

    weather = fetch_solar_forecast()
    if not weather:
        weather = load_cached_weather()

    export_prices = fetch_agile_outgoing_prices(hours=26)
    if export_prices:
        save_export_prices(export_prices)
    else:
        export_prices = load_cached_export_prices()

    # CRITICAL: persist fresh prices so /api/prices returns current + future slots
    save_prices(prices)

    state = load_state()
    if state is None:
        state = _fresh_state()
    state_g99 = load_state()
    if state_g99 is None:
        state_g99 = _fresh_state()

    # ── STARTUP SEQUENCE ─────────────────────────────────────────────────────────
    # If battery SOC is below the reserve floor (default first-boot or after a deep
    # drain), skip arbitrage and just charge continuously at any price until the
    # reserve is reached.  This prevents the algorithm from planning large export
    # windows it can't complete and ending each day progressively more depleted.
    #
    # Target: RESERVE_SOC_KWH (36 kWh, 50%).  Once reached, normal arbitrage begins.
    # Override flag in fleet_state.json: "startup_complete": true to skip this check.
    startup_done = state.get('startup_complete', False)
    soc_now = state['soc_kwh']
    if not startup_done and soc_now < RESERVE_SOC_KWH:
        print("[STARTUP] SOC=" + str(round(soc_now, 1)) + "kWh < reserve floor "
              + str(RESERVE_SOC_KWH) + "kWh — CHARGE-ONLY mode until reserve met.")
        print("[STARTUP] Arbitrage suspended. Battery will charge at current price regardless.")
        # Force all new slots to charge regardless of plan
        for price_slot in (load_cached_prices() or prices)[-48:]:
            slot_dt = datetime.fromisoformat(price_slot['valid_from'].replace('Z', '+00:00'))
            price_p = price_slot['value_inc_vat']
            slot_profit = simulate_slot(state, price_p, slot_dt, weather,
                                        buy_thr=999.0, sell_thr=999.0,
                                        export_prices=export_prices,
                                        planned_action='charge',
                                        export_kwh_cap=EXPORT_KWH_G98)
            if state['soc_kwh'] >= RESERVE_SOC_KWH:
                state['startup_complete'] = True
                print("[STARTUP] Reserve reached: " + str(round(state['soc_kwh'], 1))
                      + "kWh — resuming normal arbitrage next slot.")
                break
        save_state(state)
        return

    # ── Fetch 12-month historical stats for intelligent thresholds ────────────
    hist_stats = get_or_refresh_historical_stats(product_code if not offline_mode else None)

    # Dual dispatch plans: G98 and G99
    dispatch_plan     = plan_optimal_dispatch(prices, state['soc_kwh'],
                                              historical_stats=hist_stats,
                                              export_kwh_cap=EXPORT_KWH_G98)
    dispatch_plan_g99 = plan_optimal_dispatch(prices, state_g99['soc_kwh'],
                                              historical_stats=hist_stats,
                                              export_kwh_cap=EXPORT_KWH_G99)
    save_dispatch_plan(dispatch_plan)

    vals = [p['value_inc_vat'] for p in prices]
    buy_thr  = percentile(vals, BUY_PERCENTILE)
    sell_thr = percentile(vals, SELL_PERCENTILE)

    last_updated = None if offline_mode else state.get('last_updated')
    now_utc = datetime.now(timezone.utc).isoformat()
    new_prices = []
    for ps in prices:
        slot_from = ps['valid_from'].replace('Z', '+00:00')
        # Only process slots that have already started (no future slots)
        if slot_from > now_utc:
            continue
        if last_updated is None or slot_from > last_updated:
            new_prices.append(ps)

    if not new_prices:
        print('[NODE-3] No new slots since last run. Nothing to do.')
        return

    for price_slot in new_prices:
        slot_dt   = datetime.fromisoformat(price_slot['valid_from'].replace('Z', '+00:00'))
        price_p   = price_slot['value_inc_vat']
        planned     = dispatch_plan.get(price_slot['valid_from'], None)
        planned_g99 = dispatch_plan_g99.get(price_slot['valid_from'], None)

        slot_profit = simulate_slot(state, price_p, slot_dt, weather,
                                    buy_thr, sell_thr,
                                    export_prices=export_prices,
                                    planned_action=planned,
                                    export_kwh_cap=EXPORT_KWH_G98)
        g99_profit = simulate_slot(state_g99, price_p, slot_dt, weather,
                                   buy_thr, sell_thr,
                                   export_prices=export_prices,
                                   planned_action=planned_g99,
                                   export_kwh_cap=EXPORT_KWH_G99)
        append_history(slot_dt.isoformat(), state['profit_gbp'], slot_profit,
                       price_p, state['soc_kwh'], state['last_action'],
                       g99_profit=state_g99['profit_gbp'],
                       g99_slot_profit=g99_profit,
                       g99_soc=state_g99['soc_kwh'],
                       g99_action=state_g99['last_action'])

    save_state(state)
    delta = state_g99['profit_gbp'] - state['profit_gbp']
    print('[DONE] G98: ' + state['last_action']
          + '  ' + str(round(state['last_price_p'], 2)) + 'p'
          + '  SOC ' + str(round(state['soc_kwh'], 1)) + 'kWh'
          + '  £' + str(round(state['profit_gbp'], 4)))
    print('       G99: ' + state_g99['last_action']
          + '  SOC ' + str(round(state_g99['soc_kwh'], 1)) + 'kWh'
          + '  £' + str(round(state_g99['profit_gbp'], 4))
          + '  (delta +£' + str(round(delta, 4)) + ')')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="NODE-3 Arbitrage Simulation Engine")
    parser.add_argument("--backfill", action="store_true",
                        help="Replay last 48h of real prices to populate history")
    args = parser.parse_args()

    if args.backfill:
        run_backfill()
    else:
        run_single()
