#!/usr/bin/env python3
import re, shutil

fpath = '/home/pi/node3/dashboard.html'
shutil.copy(fpath, fpath + '.bak_fix5')

with open(fpath, 'r', encoding='utf-8') as f:
    html = f.read()

scripts = list(re.finditer(r'<script(?![^>]*src=)[^>]*>([\s\S]*?)</script>', html))
target = max(scripts, key=lambda m: len(m.group(1)))
script_start = target.start(1)
script_content = target.group(1)
lines = script_content.split('\n')

# Script line 2634 (0-indexed 2633): opens template ending with backtick
# Script line 2643 (0-indexed 2642): should close template with `; but has \`; (escaped backtick)
l2634 = lines[2633]
l2643 = lines[2642]

print(f"Line 2634: {repr(l2634)}")
print(f"Line 2643: {repr(l2643)}")

assert len(l2634) == 25 and l2634[-1] == '`', f"Unexpected line 2634: {repr(l2634)}"
assert len(l2643) == 7 and l2643 == '    \\`;', f"Unexpected line 2643: {repr(l2643)}"

# Fix: remove the backslash — change \`; to `;
lines[2642] = '    `;'
print(f"Fixed line 2643: {repr(lines[2642])}")

new_script = '\n'.join(lines)
new_html = html[:script_start] + new_script + html[script_start + len(script_content):]

with open(fpath, 'w', encoding='utf-8') as f:
    f.write(new_html)
print("Done.")
