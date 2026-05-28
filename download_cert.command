#!/bin/bash
# Download FoxESS G99 cert to Downloads
curl -L -o "$HOME/Downloads/KH105-G99_Amd-9_A23-test-report-20230424.pdf" \
  "https://fox-ess.tech/wp-content/uploads/2025/06/KH105-G99_Amd-9_A23-test-report-20230424.pdf" \
  --user-agent "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  --referer "https://fox-ess.tech/" \
  -v
echo ""
echo "Done. Press any key to close."
read -n1
