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
    "battery_kwh":  72.0,   # usable pack capacity (3x Nissan e-NV200)
    "import_kw":    10.0,   # charge rate — inverter/import limit
    "export_kw":     6.0,   # discharge rate — export limit (self-imposed; must not exceed
                             # the real DNO cap for whichever connection is active — 7.36kW
                             # for G98/32A, 11.5kW for G99/50A)
    "min_soc_pct":  10.0,   # absolute floor, % of battery_kwh
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
                        cfg[k] = float(saved[k])
        except Exception:
            pass
    return cfg


def save_config(updates):
    """Merge `updates` onto the current saved config and persist. Returns the
    full merged config. Silently ignores unknown keys and non-numeric values."""
    cfg = load_config()
    for k in DEFAULTS:
        if k in updates:
            try:
                v = float(updates[k])
                if v > 0:
                    cfg[k] = v
            except (TypeError, ValueError):
                pass
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    return cfg
