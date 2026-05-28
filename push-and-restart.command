#!/bin/bash
cd "$(dirname "$0")"
echo "=== Pushing to GitHub ==="
git push origin HEAD:main
echo ""
echo "=== Restarting Docker ==="
docker-compose down && docker-compose up -d
echo ""
echo "=== Done ==="
