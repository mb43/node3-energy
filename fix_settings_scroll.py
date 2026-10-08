#!/usr/bin/env python3
"""Make settings modal scrollable so Save button is always reachable."""
from pathlib import Path

DASH = Path('/home/pi/node3/dashboard.html')

def patch(old, new, label):
    text = DASH.read_text('utf-8')
    if old not in text:
        if new.split('\n')[0].strip() in text:
            print(f'[SKIP] {label}')
        else:
            print(f'[WARN] {label} — anchor not found')
        return
    DASH.write_text(text.replace(old, new, 1), 'utf-8')
    print(f'[OK]   {label}')

patch(
    '<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:24px 28px;width:360px;max-width:90vw">',
    '<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:24px 28px;width:360px;max-width:90vw;max-height:90vh;overflow-y:auto">',
    'Settings modal: make inner div scrollable'
)

print('Done. docker restart node3-portal')
