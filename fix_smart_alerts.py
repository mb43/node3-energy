#!/usr/bin/env python3
"""fix_smart_alerts.py — Make SOC/expensive-import alerts LP-aware.

The alerts currently fire any time battery is low + price is high, even
when the LP has deliberately depleted the battery ahead of a cheap overnight
charge window (e.g. at 22:30 before midnight cheap slot). This creates false
alarms that cry wolf when the system is actually working correctly.

Fix: before raising SOC_CRITICAL, SOC_LOW or EXPENSIVE_IMPORT alerts, check
dispatch_plan.json for an upcoming 'charge' slot within the next 3 hours.
If one exists, downgrade/suppress the alert with a "planned charge at HH:MM"
context message instead.

Run on Pi: python3 /tmp/fix_smart_alerts.py
"""
from pathlib import Path

SRV = Path('/home/pi/node3/server.py')
text = SRV.read_text('utf-8')

# ── Helper to look ahead in dispatch plan ────────────────────────────────────
# Inserted once near the top of the alert block (before the SOC check).

OLD_SOC_ANCHOR = (
    '        # ── Alert: SOC approaching floor ─────────────────────────────────────\n'
    '        if soc_kwh is not None and total_load_kw > 0:\n'
)

NEW_SOC_ANCHOR = (
    '        # ── Alert: SOC approaching floor ─────────────────────────────────────\n'
    '        # Check dispatch plan for upcoming charge within 3h — if one exists,\n'
    '        # the LP has deliberately depleted the battery ahead of a cheap window;\n'
    '        # suppress or downgrade the alert so we don\'t cry wolf.\n'
    '        def _next_charge_slot_dt(lookahead_hours=3):\n'
    '            """Return datetime of next planned charge slot, or None."""\n'
    '            try:\n'
    '                import json as _j\n'
    '                _plan_path = os.path.join(BASE_DIR, "dispatch_plan.json")\n'
    '                if not os.path.exists(_plan_path):\n'
    '                    return None\n'
    '                _plan = _j.loads(open(_plan_path).read())\n'
    '                _cutoff = datetime.now(timezone.utc) + timedelta(hours=lookahead_hours)\n'
    '                _charge_slots = []\n'
    '                for _vf, _action in _plan.items():\n'
    '                    if _action != "charge":\n'
    '                        continue\n'
    '                    try:\n'
    '                        _dt = datetime.fromisoformat(_vf.replace("Z", "+00:00"))\n'
    '                        if datetime.now(timezone.utc) < _dt <= _cutoff:\n'
    '                            _charge_slots.append(_dt)\n'
    '                    except Exception:\n'
    '                        pass\n'
    '                return min(_charge_slots) if _charge_slots else None\n'
    '            except Exception:\n'
    '                return None\n'
    '\n'
    '        if soc_kwh is not None and total_load_kw > 0:\n'
)

if OLD_SOC_ANCHOR in text:
    text = text.replace(OLD_SOC_ANCHOR, NEW_SOC_ANCHOR, 1)
    print('[OK]   server.py: _next_charge_slot_dt() helper injected before SOC alert block')
elif '_next_charge_slot_dt' in text:
    print('[SKIP] server.py: smart alert helper already present')
else:
    print('[WARN] server.py: SOC alert anchor not found — check manually')

# ── Patch SOC_CRITICAL: add charge-window context ────────────────────────────
OLD_CRITICAL = (
            '            if hours_left < 1.0:\n'
            '                alerts.append({\n'
            '                    "level": "critical",\n'
            '                    "code":  "SOC_CRITICAL",\n'
            '                    "message": (\n'
            '                        f"Battery at {soc_kwh:.1f} kWh — LESS THAN 1 HOUR of load remaining "\n'
            '                        f"at {total_load_kw:.1f} kW average. Grid import imminent."\n'
            '                    )\n'
            '                })\n'
)
NEW_CRITICAL = (
            '            if hours_left < 1.0:\n'
            '                _nxt = _next_charge_slot_dt(lookahead_hours=3)\n'
            '                if _nxt:\n'
            '                    _nxt_local = _nxt.strftime("%H:%M")\n'
            '                    alerts.append({\n'
            '                        "level": "info",\n'
            '                        "code":  "SOC_PLANNED_LOW",\n'
            '                        "message": (\n'
            '                            f"Battery at {soc_kwh:.1f} kWh — LP planned low ahead of "\n'
            '                            f"cheap charge window at {_nxt_local}. Grid import expected."\n'
            '                        )\n'
            '                    })\n'
            '                else:\n'
            '                    alerts.append({\n'
            '                        "level": "critical",\n'
            '                        "code":  "SOC_CRITICAL",\n'
            '                        "message": (\n'
            '                            f"Battery at {soc_kwh:.1f} kWh — LESS THAN 1 HOUR of load remaining "\n'
            '                            f"at {total_load_kw:.1f} kW average. Grid import imminent."\n'
            '                        )\n'
            '                    })\n'
)
if OLD_CRITICAL in text:
    text = text.replace(OLD_CRITICAL, NEW_CRITICAL, 1)
    print('[OK]   server.py: SOC_CRITICAL alert now LP-aware')
elif 'SOC_PLANNED_LOW' in text:
    print('[SKIP] server.py: SOC_CRITICAL already patched')
else:
    print('[WARN] server.py: SOC_CRITICAL anchor not found')

# ── Patch SOC_LOW: same logic ────────────────────────────────────────────────
OLD_SOC_LOW = (
            '            elif hours_left < _ALERT_HOURS_TO_EMPTY:\n'
            '                alerts.append({\n'
            '                    "level": "warning",\n'
            '                    "code":  "SOC_LOW",\n'
            '                    "message": (\n'
            '                        f"Battery at {soc_kwh:.1f} kWh — ~{hours_left:.1f}h of load "\n'
            '                        f"remaining at {total_load_kw:.1f} kW. Check next charge window."\n'
            '                    )\n'
            '                })\n'
)
NEW_SOC_LOW = (
            '            elif hours_left < _ALERT_HOURS_TO_EMPTY:\n'
            '                _nxt = _next_charge_slot_dt(lookahead_hours=4)\n'
            '                if _nxt:\n'
            '                    _nxt_local = _nxt.strftime("%H:%M")\n'
            '                    alerts.append({\n'
            '                        "level": "info",\n'
            '                        "code":  "SOC_PLANNED_LOW",\n'
            '                        "message": (\n'
            '                            f"Battery at {soc_kwh:.1f} kWh — LP running battery down "\n'
            '                            f"ahead of planned charge at {_nxt_local}. Working as intended."\n'
            '                        )\n'
            '                    })\n'
            '                else:\n'
            '                    alerts.append({\n'
            '                        "level": "warning",\n'
            '                        "code":  "SOC_LOW",\n'
            '                        "message": (\n'
            '                            f"Battery at {soc_kwh:.1f} kWh — ~{hours_left:.1f}h of load "\n'
            '                            f"remaining at {total_load_kw:.1f} kW. No charge planned soon."\n'
            '                        )\n'
            '                    })\n'
)
if OLD_SOC_LOW in text:
    text = text.replace(OLD_SOC_LOW, NEW_SOC_LOW, 1)
    print('[OK]   server.py: SOC_LOW alert now LP-aware')
elif 'No charge planned soon' in text:
    print('[SKIP] server.py: SOC_LOW already patched')
else:
    print('[WARN] server.py: SOC_LOW anchor not found')

# ── Patch EXPENSIVE_IMPORT: suppress when charge coming ─────────────────────
OLD_EXP = (
            '            if cur_price is not None and cur_price >= _ALERT_GRID_IMPORT_P:\n'
            '                usable = max(0.0, float(soc_kwh) - min_soc_kwh)\n'
            '                if usable < total_load_kw * 0.5:  # less than 30 mins of load above floor\n'
            '                    alerts.append({\n'
            '                        "level": "warning",\n'
            '                        "code":  "EXPENSIVE_IMPORT",\n'
            '                        "message": (\n'
            '                            f"Grid price now {cur_price:.1f}p/kWh and battery nearly empty "\n'
            '                            f"({soc_kwh:.1f} kWh). Baseload ({baseload_kw:.1f} kW) likely "\n'
            '                            f"drawing from grid at expensive rate."\n'
            '                        )\n'
            '                    })\n'
)
NEW_EXP = (
            '            if cur_price is not None and cur_price >= _ALERT_GRID_IMPORT_P:\n'
            '                usable = max(0.0, float(soc_kwh) - min_soc_kwh)\n'
            '                if usable < total_load_kw * 0.5:  # less than 30 mins of load above floor\n'
            '                    _nxt = _next_charge_slot_dt(lookahead_hours=3)\n'
            '                    if _nxt:\n'
            '                        pass  # LP planned low — suppress EXPENSIVE_IMPORT noise\n'
            '                    else:\n'
            '                        alerts.append({\n'
            '                            "level": "warning",\n'
            '                            "code":  "EXPENSIVE_IMPORT",\n'
            '                            "message": (\n'
            '                                f"Grid price now {cur_price:.1f}p/kWh and battery nearly empty "\n'
            '                                f"({soc_kwh:.1f} kWh). Baseload ({baseload_kw:.1f} kW) likely "\n'
            '                                f"drawing from grid at expensive rate."\n'
            '                            )\n'
            '                        })\n'
)
if OLD_EXP in text:
    text = text.replace(OLD_EXP, NEW_EXP, 1)
    print('[OK]   server.py: EXPENSIVE_IMPORT alert suppressed when charge is planned')
elif 'suppress EXPENSIVE_IMPORT noise' in text:
    print('[SKIP] server.py: EXPENSIVE_IMPORT already patched')
else:
    print('[WARN] server.py: EXPENSIVE_IMPORT anchor not found')

SRV.write_text(text, 'utf-8')
print('\n[DONE] Smart alerts applied. Restart: docker restart node3-portal')
