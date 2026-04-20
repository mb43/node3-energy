#!/bin/bash
cd "$(dirname "$0")"
echo "=== NODE-3 Backfill ==="
python3 simulate.py --backfill
echo ""
echo "=== Done. Press any key to close ==="
read -n 1
