#!/usr/bin/env python3
"""fix_server_routes.py — fix duplicate fuse-status route + add missing endpoints
Run on Pi: python3 /tmp/fix_server_routes.py
"""
from pathlib import Path
import re

SRV = Path('/home/pi/node3/server.py')
SIM = Path('/home/pi/node3/simulate.py')

# ── 1. Fix duplicate /api/fuse-status in server.py ───────────────────────────
text = SRV.read_text('utf-8')

FUSE_ROUTE = '@app.route("/api/fuse-status")'
count = text.count(FUSE_ROUTE)

if count > 1:
    # Remove all but the last occurrence (with its full function body)
    # Find positions of all occurrences
    positions = [m.start() for m in re.finditer(re.escape(FUSE_ROUTE), text)]
    print(f'[FIX] {count} occurrences of /api/fuse-status — removing {count-1}')
    # Remove all but last — work backwards
    for pos in reversed(positions[:-1]):
        # Find end of this function block = start of next @app.route or top-level def
        rest = text[pos+1:]
        m = re.search(r'\n(?=@app\.|^def |^class |\nif __name__)', rest, re.MULTILINE)
        end = pos + 1 + (m.start() + 1 if m else len(rest))
        text = text[:pos] + text[end:]
        print(f'  Removed duplicate at offset {pos}')
    SRV.write_text(text, 'utf-8')
    print('[OK]   Duplicate /api/fuse-status removed')
else:
    print(f'[OK]   /api/fuse-status count={count} — no duplicates')

# Re-read after dedup
text = SRV.read_text('utf-8')

# ── 2. Add /api/house-profile + /api/grid-history before /api/fuse-status ────
NEW_ENDPOINTS = '''@app.route("/api/house-profile")
def api_house_profile():
    """Return learned 48-slot house load profile + meta."""
    import json as _json
    profile_path = os.path.join(BASE_DIR, "house_profile.json")
    meta_path    = os.path.join(BASE_DIR, "house_profile_meta.json")
    profile, meta = [], {}
    try:
        if os.path.exists(profile_path):
            profile = _json.loads(open(profile_path).read())
    except Exception:
        pass
    try:
        if os.path.exists(meta_path):
            meta = _json.loads(open(meta_path).read())
    except Exception:
        pass
    return jsonify({"profile": profile, "meta": meta, "ready": len(profile) == 48})


@app.route("/api/grid-history")
def api_grid_history():
    """Return last N rows from grid_history.csv as JSON."""
    import csv as _csv
    rows_param = max(1, min(int(request.args.get("rows", 288)), 10000))
    csv_path = os.path.join(BASE_DIR, "grid_history.csv")
    rows = []
    try:
        if os.path.exists(csv_path):
            with open(csv_path, newline="") as f:
                for row in _csv.DictReader(f):
                    rows.append(row)
            rows = rows[-rows_param:]
    except Exception as e:
        return jsonify({"error": str(e), "rows": []}), 500
    return jsonify({"rows": rows, "count": len(rows)})


'''

if 'def api_house_profile' in text:
    print('[SKIP] /api/house-profile already in server.py')
else:
    anchor = '@app.route("/api/fuse-status")'
    if anchor in text:
        text = text.replace(anchor, NEW_ENDPOINTS + anchor, 1)
        SRV.write_text(text, 'utf-8')
        print('[OK]   /api/house-profile + /api/grid-history added')
    else:
        print('[WARN] Could not find /api/fuse-status anchor — add endpoints manually')

# ── 3. Add _rebuild_house_profile() to simulate.py ───────────────────────────
sim_text = SIM.read_text('utf-8')

REBUILD_FN = '''

# ── Rebuild house load profile before each simulate run ──────────────────────
def _rebuild_house_profile():
    """Silently rebuild house_profile.json from grid_history.csv.
    No-ops when less than 3 days of data collected.
    """
    try:
        import house_profile as _hp
        _hp.run()
    except Exception:
        pass

'''

if '_rebuild_house_profile' in sim_text:
    print('[SKIP] _rebuild_house_profile already in simulate.py')
else:
    # Find __main__ block — try with and without leading newline
    for anchor in ['\nif __name__ == "__main__":', 'if __name__ == "__main__":']:
        if anchor in sim_text:
            sim_text = sim_text.replace(anchor, REBUILD_FN + anchor, 1)
            SIM.write_text(sim_text, 'utf-8')
            print('[OK]   _rebuild_house_profile() added to simulate.py')
            break
    else:
        # Append to end of file
        SIM.write_text(sim_text + REBUILD_FN, 'utf-8')
        print('[OK]   _rebuild_house_profile() appended to simulate.py (no __main__ found)')

print('\nDone. Restart: docker restart node3-portal')
