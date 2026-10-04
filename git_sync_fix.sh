#!/usr/bin/env bash
# git_sync_fix.sh — commit health-check syntax fix, pull remote, rebase, push
set -euo pipefail

NODE3_REPO="/Users/mattbrander/Documents/Claude/Projects/Dovecote Node3"
cd "$NODE3_REPO"

echo "══════════════════════════════════════════"
echo "  Node-3 Git Sync Fix"
echo "══════════════════════════════════════════"
echo

# ── 1. Stage the health-check syntax fix ─────────────────────────────────────
echo "[1/3] Staging master_deploy.sh syntax fix…"
git add master_deploy.sh
if git diff --cached --quiet; then
    echo "  (nothing to commit — already clean)"
else
    git commit -m "$(cat <<'EOF'
fix(deploy): fix health-check SSH syntax error in master_deploy.sh

Replace inline escaped f-string with heredoc to avoid shell quoting issues.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
    echo "  ✓ committed"
fi

# ── 2. Pull remote changes (rebase) ──────────────────────────────────────────
echo
echo "[2/3] Pulling remote changes (rebase)…"
git pull --rebase origin main

# ── 3. Push ──────────────────────────────────────────────────────────────────
echo
echo "[3/3] Pushing…"
git push

echo
echo "══════════════════════════════════════════"
echo "  Done. Pi → Mac → GitHub all in sync."
echo
git log --oneline -3
echo "══════════════════════════════════════════"
