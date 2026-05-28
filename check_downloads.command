#!/bin/bash
echo "=== Downloads: G99 files ==="
ls -lh "$HOME/Downloads/"*G99* "$HOME/Downloads/"*g99* 2>/dev/null
echo "=== Done. Press any key ==="
read -n1
