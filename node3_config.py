#!/usr/bin/env python3
"""
NODE-3 shared runtime settings.

Single source of truth for the operator-configurable physical parameters:
battery capacity, import (charge) rate, and export (discharge) rate. Both
simulate.py and server.py import this module instead of hardcoding their own
copies — previously BATTERY_KWH/CHARGE_KWH/EXPORT_KWH constants were
independently hand-typed in at least SIX different places across simulate.py
and server.py (plan_optimal_dispatch, simulate_slot, _run_backtest, /api/plan,
/api/backtest-lp), several of which had drifted out of sync with each other
and with Matt's explicit standing instructions. This file exists so there is
exactly ONE place these numbers live, editable via /api/settings + the
dashboard's SETTINGS panel, persisted to node3_config.json.

Defaults set 19 Aug 2026 per Matt's explicit instruction: 72 kWh battery,
10 kW import (charge), 6 kW export (discharge). These apply to the LIVE /
"current operation" dispatch (what's labelled G98 throughout the codebase,
since that's Matt's actual current DNO connection). The G99 scenario used in
the G98-vs-G99 comparison tabs is a separate, fixed, real DNO-defined figure
(50A / 5.75 kWh per slot) representing a hypothetical upgraded connection —
it is NOT affected by these settings, since it models a different physical
grid connection, not a configurable operating choice.
"""

import os
import json

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "node3_config.json")

DEFAULTS = {
    "battery_kwh":   72.0,  # usable pack capacity (3x Nissan e-NV200)
    "import_kw":      9.0,  # charge rate — Fox ESS KH10.5 (10.5 kW) minus Z15 miner
                             # constant baseload 1.5 kW on inverter AC output = 9.0 kW effective
    "export_kw":      5.5,  # discharge rate — SSEN G99 confirmed at 5.5 kW
                             # (approval ref 260420-000198/FJJ907/1).
                             # Override in settings if wiring changes.
    "min_soc_pct":   10.0,  # absolute floor, % of battery_kwh
    "baseload_kw":    0.0,  # constant background load (kW) added to the 12kWh/day house
                             # profile — e.g. 1.5 for a 36kWh/day ASIC miner running 24/7.
                             # Affects LP planning and SOC drain every slot.
                             # Matt's site: 1.5 (Z15 draws ~1510W constant).
    "house_kwh_day": 12.0,  # profiled household consumption per day (Elexon PC1 shape)
    "svt_ref_p":     25.0,  # Ofgem SVT reference (p/kWh)
    "subscription_pcm": 29.0,  # monthly subscription per consumer site (£)
    # ── Tariff mode (added Oct 2026) ──────────────────────────────────────────
    "tariff_mode":           "agile",  # active tariff: 'agile' | 'split' | 'optimise'
    "optimise_import_mod_p": 3.0,      # p/kWh import discount 00:00-06:00 (E.ON Optimise early-bird)
    "optimise_export_mod_p": 3.0,      # p/kWh export bonus 16:00-19:00   (E.ON Optimise early-bird)
    # ── Standing charges (added Oct 2026) ────────────────────────────────────
    "standing_charge_import_p_day": 58.9,  # daily standing charge on import tariff (p/day)
                                            # Octopus Agile H region ≈ 58.9p/day incl VAT
    "standing_charge_export_p_day":  0.0,  # daily standing charge on export contract (p/day)
                                            # Octopus Agile Outgoing = 0p/day
}


def load_config():
    """Return the current settings, merging any saved overrides onto DEFAULTS."""
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k in DEFAULTS:
                    if k in saved:
                        if isinstance(DEFAULTS[k], str):
                            cfg[k] = str(saved[k])
                        else:
                            cfg[k] = float(saved[k])
        except Exception:
            pass
    return cfg


def save_config(updates):
    """Merge `updates` onto the current saved config and persist. Returns the
    full merged config. Silently ignores unknown keys and non-numeric values.
    baseload_kw and house_kwh_day allow zero (>= 0); others require > 0."""
    NON_NEGATIVE = {"baseload_kw", "house_kwh_day",
                    "standing_charge_import_p_day", "standing_charge_export_p_day"}
    STRING_KEYS  = {"tariff_mode"}
    VALID_MODES  = {"agile", "split", "optimise"}
    cfg = load_config()
    for k in DEFAULTS:
        if k in updates:
            if k in STRING_KEYS:
                v = str(updates[k]).lower().strip()
                if v in VALID_MODES:
                    cfg[k] = v
            else:
                try:
                    v = float(updates[k])
                    if k in NON_NEGATIVE and v >= 0:
                        cfg[k] = v
                    elif k not in NON_NEGATIVE and v > 0:
                        cfg[k] = v
                except (TypeError, ValueError):
                    pass
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    return cfg
