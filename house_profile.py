#!/usr/bin/env python3
"""
house_profile.py — NODE-3 House Load Profile Learner
=====================================================
Reads the grid power time-series from grid_history.csv (logged by
fox_modbus_loop.py), calculates actual house load per half-hour slot
(grid_import − battery_charging), and builds a learned 48-slot daily
load profile used by simulate.py instead of the fixed Elexon PC1 shape.

WHAT IT LEARNS
--------------
For each 30-minute Agile slot (00:00, 00:30, … 23:30):
  house_load_w = grid_power_w - bat_charge_w
               (grid import minus what's going to battery = actual house)

Averaging over recent days (default: last 14 days) gives a repeatable
profile that reflects actual consumption at this specific site.

OUTPUT
------
  house_profile.json  — 48-element list of average house_kwh per half-hour slot
                       [slot_0_kwh, slot_1_kwh, ... slot_47_kwh]
  Also writes:
  house_profile_meta.json — stats: days of data, total daily kWh, slot σ, last updated

USAGE
-----
  python3 house_profile.py               # build profile from all available data
  python3 house_profile.py --days 7      # use last 7 days only
  python3 house_profile.py --min-days 3  # require at least N days before overwriting
  python3 house_profile.py --stats       # print profile summary and exit

HOW simulate.py USES IT
-----------------------
If house_profile.json exists and has >= min_days of data, simulate.py reads
the 48-slot kWh list and uses it as the load shape instead of
house_kwh_day × PC1_PROFILE[slot]. The total daily kWh from the learned
profile replaces house_kwh_day for LP dispatch decisions.
"""

import csv, json, os, sys, math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

BASE_DIR        = Path(__file__).parent
GRID_HISTORY    = BASE_DIR / "grid_history.csv"
PROFILE_FILE    = BASE_DIR / "house_profile.json"
META_FILE       = BASE_DIR / "house_profile_meta.json"
DEFAULT_DAYS    = 14   # rolling window
MIN_SLOTS_PER_BUCKET = 3  # need at least this many readings per slot to trust it


def _slot_index(dt):
    """Return 0..47 slot index for a datetime."""
    return dt.hour * 2 + (1 if dt.minute >= 30 else 0)


def load_grid_history(days=DEFAULT_DAYS):
    """Read grid_history.csv, filter to last `days` days.
    Returns list of dicts: {ts, grid_power_w, bat_charge_w, soc_pct}
    """
    if not GRID_HISTORY.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = []
    with open(GRID_HISTORY, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = datetime.fromisoformat(row['ts'].replace('Z', '+00:00'))
                if ts < cutoff:
                    continue
                rows.append({
                    'ts':           ts,
                    'grid_power_w': float(row['grid_power_w']),
                    'bat_charge_w': float(row.get('bat_charge_w', 0) or 0),
                    'soc_pct':      float(row.get('soc_pct', 0) or 0),
                })
            except (ValueError, KeyError):
                continue
    return rows


def build_profile(rows):
    """Build 48-slot average house load profile from grid history rows.

    house_load_w = max(0, grid_power_w - bat_charge_w)

    Returns (profile_kwh_48, meta_dict).
    profile_kwh_48: list of 48 floats — average house kWh per half-hour slot.
    """
    # Aggregate by slot index
    slot_sums  = defaultdict(float)   # total house_load_w readings per slot
    slot_counts = defaultdict(int)

    # Also track per-day slot totals for σ calculation
    day_slot = defaultdict(lambda: defaultdict(list))  # day_str → slot → [kwh]

    for row in rows:
        ts   = row['ts'].astimezone(timezone.utc)
        slot = _slot_index(ts)
        house_w = max(0.0, row['grid_power_w'] - row['bat_charge_w'])
        house_kwh_halfhour = house_w * 0.5 / 1000.0   # W × 0.5h → kWh

        slot_sums[slot]   += house_kwh_halfhour
        slot_counts[slot] += 1
        day_str = ts.strftime('%Y-%m-%d')
        day_slot[day_str][slot].append(house_kwh_halfhour)

    # Build 48-slot profile
    profile = []
    for s in range(48):
        count = slot_counts.get(s, 0)
        if count >= MIN_SLOTS_PER_BUCKET:
            profile.append(round(slot_sums[s] / count, 4))
        else:
            # Insufficient data for this slot — use interpolated neighbour or default
            prev_slot = (s - 1) % 48
            next_slot = (s + 1) % 48
            neighbours = [slot_sums.get(n, 0) / max(slot_counts.get(n, 1), 1)
                          for n in [prev_slot, next_slot] if slot_counts.get(n, 0) >= MIN_SLOTS_PER_BUCKET]
            if neighbours:
                profile.append(round(sum(neighbours) / len(neighbours), 4))
            else:
                profile.append(round(0.125, 4))  # 0.25kWh/h default (flat 250W)

    total_daily_kwh = sum(profile)
    days_of_data    = len(day_slot)

    # Per-slot standard deviation across days
    slot_stdevs = []
    for s in range(48):
        day_values = [v for day in day_slot.values() for v in day.get(s, [])]
        if len(day_values) >= 2:
            mean = sum(day_values) / len(day_values)
            stdev = math.sqrt(sum((x - mean)**2 for x in day_values) / len(day_values))
            slot_stdevs.append(round(stdev, 4))
        else:
            slot_stdevs.append(0.0)

    meta = {
        'updated':          datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'days_of_data':     days_of_data,
        'total_rows':       len(rows),
        'total_daily_kwh':  round(total_daily_kwh, 2),
        'peak_slot':        profile.index(max(profile)),
        'peak_kwh':         round(max(profile), 3),
        'slot_stdevs':      slot_stdevs,
        'data_window_days': DEFAULT_DAYS,
    }
    return profile, meta


def slot_label(i):
    h = i // 2
    m = '30' if i % 2 else '00'
    return f'{h:02d}:{m}'


def print_stats(profile, meta):
    print(f"\nHouse Load Profile — {meta['days_of_data']} days of data")
    print(f"Total daily kWh: {meta['total_daily_kwh']:.2f}  Peak: {slot_label(meta['peak_slot'])} ({meta['peak_kwh']:.3f} kWh/slot)")
    print(f"Updated: {meta['updated']}\n")
    print(f"{'Slot':>8}  {'kWh/slot':>10}  {'σ':>8}")
    for i, (kwh, sd) in enumerate(zip(profile, meta['slot_stdevs'])):
        bar = '█' * int(kwh / max(profile) * 20)
        print(f"  {slot_label(i):>5}   {kwh:>8.3f}  {sd:>8.4f}  {bar}")


def run(days=DEFAULT_DAYS, min_days=3, stats_only=False):
    rows = load_grid_history(days=days)
    if not rows:
        print(f"No data in {GRID_HISTORY} — fox_modbus_loop.py must be running to collect data.")
        return None, None

    profile, meta = build_profile(rows)

    if stats_only:
        print_stats(profile, meta)
        return profile, meta

    if meta['days_of_data'] < min_days:
        print(f"Only {meta['days_of_data']} days of data (need {min_days}) — profile not saved yet.")
        print("Keep fox_modbus_loop.py running to accumulate more data.")
        return profile, meta

    PROFILE_FILE.write_text(json.dumps(profile, indent=2))
    META_FILE.write_text(json.dumps(meta, indent=2))
    print(f"[OK] Profile saved: {meta['days_of_data']} days, {meta['total_daily_kwh']:.2f} kWh/day")
    return profile, meta


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--days',     type=int, default=DEFAULT_DAYS, help='Rolling window in days')
    p.add_argument('--min-days', type=int, default=3,            help='Min days before saving profile')
    p.add_argument('--stats',    action='store_true',            help='Print profile and exit')
    a = p.parse_args()
    run(days=a.days, min_days=a.min_days, stats_only=a.stats)
