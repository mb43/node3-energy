#!/usr/bin/env python3
"""fix_duplicate_route.py — remove duplicate @app.route blocks from server.py
Run on Pi: python3 /tmp/fix_duplicate_route.py
"""
import re
from pathlib import Path

SRV = Path('/home/pi/node3/server.py')
text = SRV.read_text('utf-8')

# Find all @app.route decorator occurrences and their function names
# Strategy: find duplicate route+function pairs and keep only the last one
# (the last one is usually the most recent/correct version)

route_pattern = re.compile(
    r'(@app\.route\("([^"]+)"\)[^\n]*\ndef (\w+)\()',
    re.MULTILINE
)

matches = list(route_pattern.finditer(text))

# Find duplicates by route path
from collections import defaultdict
by_route = defaultdict(list)
for m in matches:
    by_route[m.group(2)].append(m)

duplicates_found = False
for route, hits in by_route.items():
    if len(hits) > 1:
        print(f'[DUP] {route} — {len(hits)} definitions, keeping last')
        duplicates_found = True

if not duplicates_found:
    print('[OK] No duplicate routes found — server.py is clean')
    exit(0)

# For each duplicated route, remove all but the LAST definition.
# We do this by finding the full function body for each duplicate and removing
# all but the last occurrence.

def find_function_block(text, start_pos):
    """Find the complete function block starting at start_pos (the @app.route line).
    Returns (block_start, block_end) indices.
    Ends when we hit the next @app.route, @app.errorhandler, or top-level def/class.
    """
    # Find end: next top-level @app.route or def at column 0 (not indented)
    next_top = re.search(
        r'\n(?=@app\.|^def |^class |\nif __name__)',
        text[start_pos + 1:],
        re.MULTILINE
    )
    if next_top:
        end = start_pos + 1 + next_top.start() + 1  # +1 to include the \n
    else:
        end = len(text)
    return start_pos, end

# Build removal list: for duplicate routes, mark all but last for removal
to_remove = []  # list of (start, end) spans to delete

for route, hits in by_route.items():
    if len(hits) <= 1:
        continue
    # Keep only the last hit; remove all earlier ones
    for hit in hits[:-1]:
        block_start, block_end = find_function_block(text, hit.start())
        to_remove.append((block_start, block_end))
        print(f'  Removing earlier definition of {route} at offset {block_start}')

# Sort removals in reverse order so indices stay valid
to_remove.sort(key=lambda x: x[0], reverse=True)

for start, end in to_remove:
    text = text[:start] + text[end:]

SRV.write_text(text, 'utf-8')
print(f'\n[OK] Fixed — removed {len(to_remove)} duplicate route block(s)')
print('     Restart docker: docker restart node3-portal')
