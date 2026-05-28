#!/bin/bash
# Copy filled G99 A1-1 PDF to Downloads AND /tmp (for upload tool)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/G99_A1-1_Form_Filled.pdf" "$HOME/Downloads/G99_A1-1_Form_Filled.pdf"
cp "$SCRIPT_DIR/G99_A1-1_Form_Filled.pdf" "/tmp/G99_A1-1_Form_Filled.pdf"
echo ""
echo "Copied to: $HOME/Downloads/G99_A1-1_Form_Filled.pdf"
echo "Copied to: /tmp/G99_A1-1_Form_Filled.pdf"
ls -lh "$HOME/Downloads/G99_A1-1_Form_Filled.pdf" "/tmp/G99_A1-1_Form_Filled.pdf"
echo ""
echo "Done. Press any key to close."
read -n1
