#!/bin/bash
# NODE-3 GitHub publish script
# Run from inside the "Dovecote Node3" folder:
#   cd ~/Documents/Claude/Projects/Dovecote\ Node3
#   bash PUBLISH_TO_GITHUB.sh

set -e

echo ""
echo "══════════════════════════════════════════"
echo "  NODE-3 → GitHub Pages Publisher"
echo "══════════════════════════════════════════"
echo ""

# ── Require gh CLI ─────────────────────────────────────────────
if ! command -v gh &>/dev/null; then
  echo "⚠  GitHub CLI (gh) not found."
  echo "   Install:  brew install gh"
  echo "   Auth:     gh auth login"
  echo "   Then re-run this script."
  exit 1
fi

if ! gh auth status &>/dev/null; then
  echo "⚠  Not logged in to GitHub CLI."
  echo "   Run: gh auth login"
  exit 1
fi

REPO_NAME="node3-arbitrage"
GITHUB_USER=$(gh api user --jq .login)
REMOTE_URL="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

echo "→ GitHub user: ${GITHUB_USER}"
echo "→ Repo: ${REMOTE_URL}"

# ── Clean up any broken .git (from sandbox attempts) ───────────
if [ -d ".git" ]; then
  echo "→ Removing existing .git directory..."
  rm -rf .git
fi

# ── Create GitHub repo if it doesn't exist ─────────────────────
if ! gh repo view "${GITHUB_USER}/${REPO_NAME}" &>/dev/null; then
  echo "→ Creating new GitHub repo: ${REPO_NAME} ..."
  gh repo create "${REPO_NAME}" \
    --public \
    --description "NODE-3 Energy Arbitrage Portal — live Octopus Agile battery optimisation"
  echo "→ Repo created."
else
  echo "→ Repo already exists — will force-push latest version."
fi

# ── Init fresh git repo ────────────────────────────────────────
echo "→ Initialising fresh git repo..."
git init
git config user.name  "Matt Brander"
git config user.email "matt.brander@gmail.com"
git branch -M main
git remote add origin "${REMOTE_URL}"

# ── Stage and commit ───────────────────────────────────────────
echo "→ Staging files..."
git add \
  .gitignore \
  .dockerignore \
  dashboard.html \
  index.html \
  README.md \
  simulate.py \
  server.py \
  requirements.txt \
  Dockerfile \
  docker-compose.yml \
  run-portal-direct.command \
  run_backfill.command \
  fleet_state.json \
  prices.json \
  history.csv \
  .github/

git status --short

echo "→ Committing..."
git commit -m "feat: NODE-3 Arbitrage Portal — single-source Python algorithm, live Octopus Agile

Algorithm (single source of truth — Python only):
- Rolling 48-slot lookahead window, BUY_PCT=35, SELL_PCT=60, RTE=0.88
- dynamicBuyCeil = bestExportInWindow × 0.88 − 3p (prevents loss-making charges)
- No time-of-day restrictions — full window optimisation, all hours
- Live slot simulation: simulate.py → history.csv every 30 min via GitHub Actions
- 12-month historical backtest: server.py /api/backtest (Python, cached 24h)
- JS simulateHistorical() deleted — one algorithm, no duplicates

Portal features:
- Live Octopus Agile import + Agile Outgoing export prices (separate tariffs)
- Forward 48-slot schedule with dynamic buy/sell thresholds
- 12-month P&L: arbitrage cash + Agile tariff saving vs 25p SVT (PC1-weighted)
- Monthly bar chart, spread chart, per-month table with SOC range
- Backtest cached server-side — no JS re-runs on auto-refresh
- GitHub Pages auto-deploy + 30-min Actions cron"

# ── Push ───────────────────────────────────────────────────────
echo "→ Pushing to GitHub (force — this is a clean publish)..."
git push -u origin main --force

# ── Enable GitHub Pages ────────────────────────────────────────
echo "→ Enabling GitHub Pages..."
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  /repos/${GITHUB_USER}/${REPO_NAME}/pages \
  -f "source[branch]=main" \
  -f "source[path]=/" \
  --silent 2>/dev/null || true

# ── Trigger first workflow ─────────────────────────────────────
echo "→ Triggering first simulation + deploy workflow..."
gh workflow run simulate.yml --repo "${GITHUB_USER}/${REPO_NAME}" 2>/dev/null || true

echo ""
echo "══════════════════════════════════════════"
echo "  ✅ DONE!"
echo ""
echo "  Repo:    https://github.com/${GITHUB_USER}/${REPO_NAME}"
echo "  Portal:  https://${GITHUB_USER}.github.io/${REPO_NAME}/"
echo ""
echo "  GitHub Pages takes ~60 seconds to go live."
echo "  Dashboard auto-refreshes data every 30 minutes via Actions."
echo "══════════════════════════════════════════"
echo ""
