#!/usr/bin/env python3
"""fix_fuse_card.py — insert fuse status card into dashboard.html.
Run on Pi: python3 /tmp/fix_fuse_card.py
"""
from pathlib import Path
DASH = Path('/home/pi/node3/dashboard.html')

FUSE_CARD = '''
    <div class="chart-card" style="margin-bottom:16px" id="fuse-card">
      <div class="chart-title" style="margin-bottom:10px;display:flex;align-items:center;gap:8px">
        FUSE PROTECTION
        <span id="fuse-health-dot" style="width:8px;height:8px;border-radius:50%;background:#6e7681;flex-shrink:0;display:inline-block"></span>
        <span id="fuse-health-label" style="font-size:11px;color:var(--muted);font-weight:400;margin-left:2px">—</span>
      </div>
      <div class="homeowner-savings-grid">
        <div class="stat-card">
          <div class="stat-label">Grid Import</div>
          <div class="stat-value" id="fuse-grid">—</div>
          <div class="stat-sub">Site total from meter</div>
        </div>
        <div class="stat-card amber">
          <div class="stat-label">Bat Charging</div>
          <div class="stat-value amber" id="fuse-bat">—</div>
          <div class="stat-sub">From bms_monitor packs</div>
        </div>
        <div class="stat-card green">
          <div class="stat-label">Charge Headroom</div>
          <div class="stat-value green" id="fuse-headroom">—</div>
          <div class="stat-sub">Before 18.4 kW fuse</div>
        </div>
      </div>
      <div style="margin-top:12px">
        <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-bottom:4px">
          <span>0 kW</span><span id="fuse-bar-label">Safe limit: 16.4 kW</span><span>18.4 kW</span>
        </div>
        <div style="height:8px;background:#21262d;border-radius:4px;overflow:hidden">
          <div id="fuse-bar" style="height:100%;width:0%;background:#3fb950;border-radius:4px;transition:width 0.6s,background 0.6s"></div>
        </div>
      </div>
    </div>
'''

text = DASH.read_text('utf-8')
if 'id="fuse-card"' in text:
    print('[SKIP] fuse card already in dashboard')
else:
    anchor = '<div class="chart-card" style="margin-bottom:16px">\n      <div class="chart-title" style="margin-bottom:10px">LIVE PACK TELEMETRY</div>'
    if anchor in text:
        text = text.replace(anchor, FUSE_CARD + '\n    ' + anchor, 1)
        DASH.write_text(text, 'utf-8')
        print('[OK]   fuse card inserted before LIVE PACK TELEMETRY')
    else:
        # fallback: before hw-source-card
        anchor2 = '<div class="stat-card" id="hw-source-card">'
        if anchor2 in text:
            idx = text.find(anchor2)
            # Walk back to find containing chart-card
            back = text.rfind('<div class="chart-card"', 0, idx)
            insert_before = text[back:back+35]
            text = text.replace(insert_before, FUSE_CARD + '\n    ' + insert_before, 1)
            DASH.write_text(text, 'utf-8')
            print('[OK]   fuse card inserted before hw-source-card section')
        else:
            print('[WARN] anchor not found — fuse card NOT inserted, manual add needed')

print('Done.')
