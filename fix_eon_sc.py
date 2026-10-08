#!/usr/bin/env python3
"""fix_eon_sc.py — Fix E.ON Optimise standing charge + LP tariff-mode bugs.

Run on Pi:  python3 /tmp/fix_eon_sc.py

What this fixes:
  1. Settings save endpoint: add standing_charge_eon_p_day to accepted keys
     so the user's 48.9p/day setting actually persists to node3_config.json.
  2. LP tariff-mode override: add tariff_mode param to plan_optimal_dispatch()
     so the backtest-compare LP uses the correct mode for each scenario, not
     whatever mode happens to be live in config.
  3. Backtest window pre-adjustment: remove the buy-price pre-adjustment in
     _run_backtest() (it caused double-application when LP also adjusts).
     LP now handles all price adjustments internally.
  4. Clean up tripled duplicate code blocks from repeated deploys.
"""
from pathlib import Path
import re

SRV = Path('/home/pi/node3/server.py')
SIM = Path('/home/pi/node3/simulate.py')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PART A — simulate.py: add tariff_mode override param to plan_optimal_dispatch
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

sim = SIM.read_text('utf-8')

# Patch 1: add tariff_mode=None to function signature
OLD_SIG = ('def plan_optimal_dispatch(price_slots, initial_soc_kwh, battery_kwh=BATTERY_KWH,\n'
           '                          min_soc_kwh=MIN_SOC_KWH, historical_stats=None,\n'
           '                          export_kwh_cap=None, daily_load_kwh=None,\n'
           '                          export_prices=None):')
NEW_SIG = ('def plan_optimal_dispatch(price_slots, initial_soc_kwh, battery_kwh=BATTERY_KWH,\n'
           '                          min_soc_kwh=MIN_SOC_KWH, historical_stats=None,\n'
           '                          export_kwh_cap=None, daily_load_kwh=None,\n'
           '                          export_prices=None, tariff_mode=None):')

if OLD_SIG in sim:
    sim = sim.replace(OLD_SIG, NEW_SIG, 1)
    print('[OK]   simulate.py: added tariff_mode=None to plan_optimal_dispatch signature')
elif 'tariff_mode=None' in sim and 'plan_optimal_dispatch' in sim:
    print('[SKIP] simulate.py: tariff_mode param already present')
else:
    print('[WARN] simulate.py: could not find plan_optimal_dispatch signature — check manually')

# Patch 2: use tariff_mode override instead of always reading from config
OLD_TARIFF = '        _tariff  = _t_cfg.get("tariff_mode", "agile")'
NEW_TARIFF = '        _tariff  = tariff_mode if tariff_mode is not None else _t_cfg.get("tariff_mode", "agile")'

if OLD_TARIFF in sim:
    sim = sim.replace(OLD_TARIFF, NEW_TARIFF, 1)
    print('[OK]   simulate.py: _tariff now uses tariff_mode override when provided')
elif NEW_TARIFF in sim:
    print('[SKIP] simulate.py: _tariff override already applied')
else:
    print('[WARN] simulate.py: could not find _tariff assignment — check manually')

SIM.write_text(sim, 'utf-8')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PART B — server.py patches
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

srv = SRV.read_text('utf-8')

# ── B1: Settings endpoint — add standing_charge_eon_p_day to accepted keys ──

OLD_NONNEG = ('    NON_NEGATIVE_KEYS = {"baseload_kw", "house_kwh_day",\n'
              '                         "standing_charge_import_p_day", "standing_charge_export_p_day"}')
NEW_NONNEG = ('    NON_NEGATIVE_KEYS = {"baseload_kw", "house_kwh_day",\n'
              '                         "standing_charge_import_p_day", "standing_charge_export_p_day",\n'
              '                         "standing_charge_eon_p_day"}')

if OLD_NONNEG in srv:
    srv = srv.replace(OLD_NONNEG, NEW_NONNEG, 1)
    print('[OK]   server.py: standing_charge_eon_p_day added to NON_NEGATIVE_KEYS')
elif 'standing_charge_eon_p_day' in srv.split('NON_NEGATIVE_KEYS')[0 if 'NON_NEGATIVE_KEYS' in srv else -1:] or NEW_NONNEG in srv:
    print('[SKIP] server.py: NON_NEGATIVE_KEYS already includes eon_sc')
else:
    print('[WARN] server.py: NON_NEGATIVE_KEYS anchor not found')

OLD_KEYS = ('    for key in ("battery_kwh", "import_kw", "export_kw", "min_soc_pct",\n'
            '                "baseload_kw", "house_kwh_day", "svt_ref_p", "subscription_pcm",\n'
            '                "standing_charge_import_p_day", "standing_charge_export_p_day"):')
NEW_KEYS = ('    for key in ("battery_kwh", "import_kw", "export_kw", "min_soc_pct",\n'
            '                "baseload_kw", "house_kwh_day", "svt_ref_p", "subscription_pcm",\n'
            '                "standing_charge_import_p_day", "standing_charge_export_p_day",\n'
            '                "standing_charge_eon_p_day"):')

if OLD_KEYS in srv:
    srv = srv.replace(OLD_KEYS, NEW_KEYS, 1)
    print('[OK]   server.py: standing_charge_eon_p_day added to settings save keys')
elif NEW_KEYS in srv:
    print('[SKIP] server.py: settings save keys already include eon_sc')
else:
    print('[WARN] server.py: settings save keys anchor not found')

# ── B2: Dedup tripled SC variable block ─────────────────────────────────────

SC_BLOCK = (
    '    # ── Standing charges ──────────────────────────────────────────────────\n'
    '    _SC_IMPORT_P    = float(_bt_cfg.get("standing_charge_import_p_day", 62.22))  # p/day\n'
    '    _SC_EXPORT_P    = float(_bt_cfg.get("standing_charge_export_p_day", 0.0))   # p/day\n'
    '    _SC_EON_P       = float(_bt_cfg.get("standing_charge_eon_p_day",   62.22))   # p/day\n'
    '    _SC_AGILE_TOTAL = _SC_IMPORT_P + _SC_EXPORT_P   # p/day (Agile import + Outgoing)\n'
)

count_sc = srv.count(SC_BLOCK)
if count_sc > 1:
    # Keep first, remove subsequent copies
    first_pos = srv.index(SC_BLOCK)
    rest = srv[first_pos + len(SC_BLOCK):]
    rest = rest.replace(SC_BLOCK, '', count_sc - 1)
    srv = srv[:first_pos + len(SC_BLOCK)] + rest
    print(f'[OK]   server.py: removed {count_sc - 1} duplicate SC variable block(s)')
elif count_sc == 1:
    print('[SKIP] server.py: SC variable block already unique')
else:
    print('[WARN] server.py: SC variable block not found')

# ── B3: Dedup tripled tariff_mode check ─────────────────────────────────────

TARIFF_BLOCK = (
    '    # ── Active tariff for this run ────────────────────────────────────────\n'
    '    if tariff_mode is None:\n'
    '        tariff_mode = _bt_cfg.get("tariff_mode", "agile")\n'
)

count_tm = srv.count(TARIFF_BLOCK)
if count_tm > 1:
    first_pos = srv.index(TARIFF_BLOCK)
    rest = srv[first_pos + len(TARIFF_BLOCK):]
    rest = rest.replace(TARIFF_BLOCK, '', count_tm - 1)
    srv = srv[:first_pos + len(TARIFF_BLOCK)] + rest
    print(f'[OK]   server.py: removed {count_tm - 1} duplicate tariff_mode block(s)')
elif count_tm == 1:
    print('[SKIP] server.py: tariff_mode block already unique')
else:
    print('[WARN] server.py: tariff_mode block not found')

# ── B4: Dedup tripled buy_p/sell_adj block ───────────────────────────────────

BUY_BLOCK = (
    '        # ── Effective buy/sell prices under active tariff ─────────────────\n'
    '        _h        = dt.hour\n'
    '        _buy_p    = price\n'
    '        _sell_adj = 0.0\n'
    '        if tariff_mode in (\'split\', \'optimise\') and 0 <= _h < 6:\n'
    '            _buy_p = max(0.0, price - imp_mod_p)\n'
    '        if tariff_mode == \'optimise\' and 16 <= _h < 19:\n'
    '            _sell_adj = exp_mod_p\n'
)

count_buy = srv.count(BUY_BLOCK)
if count_buy > 1:
    first_pos = srv.index(BUY_BLOCK)
    rest = srv[first_pos + len(BUY_BLOCK):]
    rest = rest.replace(BUY_BLOCK, '', count_buy - 1)
    srv = srv[:first_pos + len(BUY_BLOCK)] + rest
    print(f'[OK]   server.py: removed {count_buy - 1} duplicate buy_p/sell_adj block(s)')
elif count_buy == 1:
    print('[SKIP] server.py: buy_p/sell_adj block already unique')
else:
    print('[WARN] server.py: buy_p/sell_adj block not found (may already be deduped differently)')

# ── B5: Replace window pre-adjustment + LP call (pass tariff_mode, no pre-adjust) ──

OLD_WINDOW = (
    '        if slot[\'valid_from\'] not in dispatch_plan:\n'
    '            if tariff_mode != \'agile\':\n'
    '                # Buy-price-adjusted window so LP shifts charging to cheap 00-06 slots\n'
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
    '            )\n'
)
NEW_WINDOW = (
    '        if slot[\'valid_from\'] not in dispatch_plan:\n'
    '            # Pass raw (unadjusted) prices — plan_optimal_dispatch applies\n'
    '            # tariff-specific buy/sell adjustments internally when tariff_mode\n'
    '            # is supplied, avoiding double-application of the import discount.\n'
    '            window = import_prices[idx: idx + 96]\n'
    '            dispatch_plan.update(\n'
    '                _sim.plan_optimal_dispatch(window, soc, battery_kwh=_BT_BATTERY_KWH,\n'
    '                                            min_soc_kwh=_BT_MIN_SOC_KWH,\n'
    '                                            export_kwh_cap=_BT_EXPORT_KWH,\n'
    '                                            daily_load_kwh=_bt_total_load_day,\n'
    '                                            tariff_mode=tariff_mode)\n'
    '            )\n'
)

if OLD_WINDOW in srv:
    srv = srv.replace(OLD_WINDOW, NEW_WINDOW, 1)
    print('[OK]   server.py: LP window pre-adjustment removed; tariff_mode passed to LP')
elif 'tariff_mode=tariff_mode' in srv and 'dispatch_plan.update' in srv:
    print('[SKIP] server.py: LP window fix already applied')
else:
    print('[WARN] server.py: LP window anchor not found — check manually')

# ── B6: Force-clear the backtest-compare cache so changes take effect ─────────

import os, glob
cache_patterns = [
    '/home/pi/node3/backtest_compare_cache*.json',
    '/home/pi/node3/.cache/backtest_compare*.json',
]
cleared = 0
for pat in cache_patterns:
    for f in glob.glob(pat):
        try:
            os.remove(f)
            cleared += 1
        except Exception:
            pass
print(f'[OK]   Cache: cleared {cleared} backtest-compare cache file(s)')

SRV.write_text(srv, 'utf-8')
print('\n[DONE] All patches applied. Restart: docker restart node3-portal')
print('       Then: curl "http://localhost:5000/api/backtest-compare?force=1"')
print('       After restart, go to Settings and re-enter 48.9p for E.ON standing charge.')
