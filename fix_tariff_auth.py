#!/usr/bin/env python3
"""
fix_tariff_auth.py  — Dovecote Node-3
Removes the _check_api_key() guard from /api/tariff POST.
The tariff toggle is a dashboard-UI action (same pattern as /api/settings)
and must not require an API key.
"""
from pathlib import Path

srv = Path('/home/pi/node3/server.py')
text = srv.read_text('utf-8')

OLD = (
    '    if not _check_api_key():\n'
    '        return jsonify({"error": "invalid or missing API key"}), 401\n'
    '    body = request.get_json(silent=True) or {}\n'
    '    mode = str(body.get("mode", "")).lower().strip()\n'
    '    if mode not in ("agile", "split", "optimise"):\n'
    '        return jsonify({"error": "mode must be agile | split | optimise"}), 400\n'
    '    merged = _cfg.save_config({"tariff_mode": mode})\n'
    '    print(f"[TARIFF] Mode set to: {mode}")\n'
    '    return jsonify({"tariff_mode": merged.get("tariff_mode", mode), "ok": True})'
)

NEW = (
    '    body = request.get_json(silent=True) or {}\n'
    '    mode = str(body.get("mode", "")).lower().strip()\n'
    '    if mode not in ("agile", "split", "optimise"):\n'
    '        return jsonify({"error": "mode must be agile | split | optimise"}), 400\n'
    '    merged = _cfg.save_config({"tariff_mode": mode})\n'
    '    print(f"[TARIFF] Mode set to: {mode}")\n'
    '    return jsonify({"tariff_mode": merged.get("tariff_mode", mode), "ok": True})'
)

count = text.count(OLD)
assert count == 1, f"Expected 1 match, got {count}"

srv.write_text(text.replace(OLD, NEW, 1), 'utf-8')
print("[OK] /api/tariff POST: _check_api_key() guard removed")
print("Restart: docker restart node3-portal")
