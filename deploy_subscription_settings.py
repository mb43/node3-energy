#!/usr/bin/env python3
"""
deploy_subscription_settings.py
Adds subscription_pcm + E.ON SC field to settings modal, openSettings(), saveSettings().
Run on Pi: python3 /tmp/deploy_subscription_settings.py
"""
import sys
from pathlib import Path

BASE = Path('/home/pi/node3')
DASH = BASE / 'dashboard.html'

def patch(path, old, new, label):
    text = path.read_text('utf-8')
    if old not in text:
        if new.split('\n')[0].strip() in text:
            print(f'[SKIP] {label} — already applied')
        else:
            print(f'[WARN] {label} — anchor not found')
        return False
    assert text.count(old) == 1, f'Ambiguous anchor for {label}'
    path.write_text(text.replace(old, new, 1), 'utf-8')
    print(f'[OK]   {label}')
    return True

# ── 1. Settings modal HTML: add subscription + E.ON SC fields ────────────────
patch(DASH,
    '      <label style="display:block;font-size:11px;color:#8b949e;margin-bottom:3px">Export standing charge (p/day)</label>\n'
    '      <input type="number" id="set-standing-export" step="0.1" min="0" style="width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;padding:7px 10px;margin-bottom:4px;font-size:13px">\n'
    '      <div style="font-size:10px;color:#8b949e;margin-bottom:16px">Deducted from backtest P&amp;L. Agile import ≈ 58.9p/day; Agile Outgoing = 0p/day.</div>\n'
    '\n'
    '      <div id="settings-msg"',

    '      <label style="display:block;font-size:11px;color:#8b949e;margin-bottom:3px">Export standing charge (p/day)</label>\n'
    '      <input type="number" id="set-standing-export" step="0.1" min="0" style="width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;padding:7px 10px;margin-bottom:4px;font-size:13px">\n'
    '      <div style="font-size:10px;color:#8b949e;margin-bottom:16px">Deducted from backtest P&amp;L. Agile import ≈ 62.22p/day · Agile Outgoing = 0p/day.</div>\n'
    '\n'
    '      <label style="display:block;font-size:11px;color:#8b949e;margin-bottom:3px">E.ON Next Optimise standing charge (p/day)</label>\n'
    '      <input type="number" id="set-standing-eon" step="0.1" min="0" style="width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;padding:7px 10px;margin-bottom:4px;font-size:13px">\n'
    '      <div style="font-size:10px;color:#8b949e;margin-bottom:16px">Used for SPLIT &amp; OPTIMISE tariff modes. Update once E.ON quote confirmed.</div>\n'
    '\n'
    '      <div style="font-size:11px;font-weight:bold;color:#8b949e;margin-bottom:8px;border-top:1px solid #21262d;padding-top:12px">Financial model</div>\n'
    '\n'
    '      <label style="display:block;font-size:11px;color:#8b949e;margin-bottom:3px">Dovecote subscription (£/month)</label>\n'
    '      <input type="number" id="set-subscription-pcm" step="0.01" min="0" style="width:100%;box-sizing:border-box;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;padding:7px 10px;margin-bottom:4px;font-size:13px">\n'
    '      <div style="font-size:10px;color:#8b949e;margin-bottom:16px">Monthly fee charged to homeowner. Set 0 for pure arbitrage scenario.</div>\n'
    '\n'
    '      <div id="settings-msg"',
    'Settings modal: add E.ON SC + subscription_pcm fields')

# ── 2. openSettings(): load new fields ───────────────────────────────────────
patch(DASH,
    "    document.getElementById('set-standing-export').value = cfg.standing_charge_export_p_day ?? 0;\n"
    "    _updateBaseloadHint(cfg);",
    "    document.getElementById('set-standing-export').value = cfg.standing_charge_export_p_day ?? 0;\n"
    "    document.getElementById('set-standing-eon').value     = cfg.standing_charge_eon_p_day ?? 62.22;\n"
    "    document.getElementById('set-subscription-pcm').value = cfg.subscription_pcm ?? 29;\n"
    "    _updateBaseloadHint(cfg);",
    'openSettings: load E.ON SC + subscription_pcm')

# ── 3. saveSettings() body: add new fields ───────────────────────────────────
patch(DASH,
    "    standing_charge_import_p_day: parseFloat(document.getElementById('set-standing-import').value),\n"
    "    standing_charge_export_p_day: parseFloat(document.getElementById('set-standing-export').value),",
    "    standing_charge_import_p_day:  parseFloat(document.getElementById('set-standing-import').value),\n"
    "    standing_charge_export_p_day:  parseFloat(document.getElementById('set-standing-export').value),\n"
    "    standing_charge_eon_p_day:     parseFloat(document.getElementById('set-standing-eon').value),\n"
    "    subscription_pcm:              parseFloat(document.getElementById('set-subscription-pcm').value),",
    'saveSettings body: add E.ON SC + subscription_pcm')

# ── 4. saveSettings(): validate new fields ───────────────────────────────────
patch(DASH,
    "  if (!isFinite(body.baseload_kw) || body.baseload_kw < 0) {\n"
    "    msg.textContent = 'baseload_kw must be 0 or positive.'; return;\n"
    "  }\n"
    "  try {",
    "  if (!isFinite(body.baseload_kw) || body.baseload_kw < 0) {\n"
    "    msg.textContent = 'baseload_kw must be 0 or positive.'; return;\n"
    "  }\n"
    "  if (!isFinite(body.subscription_pcm) || body.subscription_pcm < 0) {\n"
    "    msg.textContent = 'subscription_pcm must be 0 or positive.'; return;\n"
    "  }\n"
    "  for (const k of ['standing_charge_import_p_day','standing_charge_export_p_day','standing_charge_eon_p_day']) {\n"
    "    if (!isFinite(body[k]) || body[k] < 0) { msg.textContent = `${k} must be >= 0.`; return; }\n"
    "  }\n"
    "  try {",
    'saveSettings: validate subscription_pcm + SC fields')

print('\nDone. Restart docker:')
print('  docker restart node3-portal')
