# NODE-3 Energy Arbitrage Platform & Website

Public-facing landing page and real-time battery arbitrage operator portal for Dovecote Systems.

**Live website:** [doesnthavetocosttheearth.com](https://doesnthavetocosttheearth.com/)
**Live operator portal:** [doesnthavetocosttheearth.com/dashboard.html](https://doesnthavetocosttheearth.com/dashboard.html) (GitHub Pages) or [portal.doesnthavetocosttheearth.com](https://portal.doesnthavetocosttheearth.com/) (Pi API reverse proxy)

---

## What it is

Node-3 is a real, physical installation: a 72 kWh battery (3× Nissan e-NV200 packs) managed by a FoxESS 10.5 kW HV inverter, exporting to grid under a G98 single-phase DNO connection in Southern England (Region H). It runs on Octopus Agile — variable half-hourly electricity prices published up to 24 hours ahead.

This portal tracks the live arbitrage operation: charge when prices are cheap, export to grid when prices are high, using Octopus Agile Outgoing as the export tariff.

## What it does

- Fetches live Octopus Agile **import** prices (what you pay to charge)
- Fetches live Octopus **Agile Outgoing** export prices (what Octopus pays for grid exports — separate, lower tariff)
- Runs a rolling 48-slot lookahead optimiser: charge in the cheapest slots, export in the most expensive
- Tracks real cumulative profit from history.csv (updated every 30 min via GitHub Actions)
- Shows a 12-month historical backtest using 12 months of real Agile price data (server-side Python, cached)
- Homeowner benefit: **£0 electricity cost** for up to 12 kWh/day — the battery covers the home's daily consumption from its charge cycles at no cost to the occupant

**The Grid P&L figure (Export Income − Charge Cost) is real cash paid by Octopus into Dovecote's bank account.** It is not a theoretical saving, not an avoided cost, not a modelled benefit — it is the actual money transferred: Octopus charges for electricity drawn to charge the battery, and pays for electricity exported to the grid. The difference is Dovecote's bank balance movement.

The battery also serves the home's 12 kWh/day consumption from those same charge cycles. The homeowner pays nothing for electricity up to that fair-use cap. The Grid P&L demonstrates the system remains commercially positive even while providing that free electricity — the arbitrage margin covers both the home load and generates cash surplus.

## Algorithm

**LP‑optimal dispatch** – the live system (and the 12‑month back‑test) uses a linear‑programming model (SciPy’s `linprog` with HiGHS) to globally optimise charge/discharge over the full 48‑slot look‑ahead, maximising export revenue minus charge cost while respecting SOC limits, inverter charge rate, and DNO export caps (G98/G99).
**Fallback** – if SciPy/HiGHS is unavailable, the system falls back to the original percentile‑threshold heuristic (BUY_PCT = 35 %, SELL_PCT = 60 %).
## Hardware

| Component | Spec |
|-----------|------|
| Battery | 72 kWh nominal (3× Nissan e-NV200 packs) |
| Inverter | FoxESS 10.5 kW HV |
| Export cap | 3.68 kWh/slot (G98 single-phase, 32A) |
| Charge rate | 5.25 kWh/slot (10.5 kW × 0.5h) |
| Min SOC reserve | 7.2 kWh (10%) |
| Solar | None modelled (pure arbitrage) |
| Location | Southern England, Region H |

## Wiring Schematic

The full wiring schematic and build checklist can be found in **[NODE3_Wiring_Schematic.md](NODE3_Wiring_Schematic.md)**.

## Quick start

```bash
# macOS — double-click run-portal-direct.command (no Docker needed)
# Or manually:
pip install -r requirements.txt
python simulate.py --backfill   # populate last 48 hours of real prices
python server.py --port 8585    # start Flask API
# Open http://localhost:8585
```

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `AGILE_REGION` | `H` | Octopus region code (H = Southern England) |
| `LATITUDE` | `50.9` | For Open-Meteo solar forecast |
| `LONGITUDE` | `-1.4` | For Open-Meteo solar forecast |
| `NODE3_API_KEY` | *(unset)* | Optional API key for /api/trigger and /api/reset |

## Octopus region codes

A=Eastern · B=East Midlands · C=London · D=N Wales/Merseyside · E=Midlands · F=NE England · G=NW England · **H=Southern** · J=SE England · K=SW England · L=Yorkshire · M=N Scotland · N=S Scotland · P=S Wales

## Architecture

```
index.html           Public-facing landing page for Dovecote Systems (doesnthavetocosttheearth.com).
style.css            Unified CSS design system (dark mode, glassmorphism, responsive utilities).
dashboard.html       Self-contained operator portal. Displays live telemetry from server,
                     historical backtest graphs, and rolling 48-slot dispatch schedules.

simulate.py          Rolling-window optimiser + slot simulator. Writes history.csv.
                     Runs every 30 min via GitHub Actions cron.

server.py            Flask REST API + backtest engine.
  /api/node          Current SOC, profit, last action
  /api/prices        Last 48h of Agile import prices
  /api/history       Recent slot-by-slot history (up to 200 rows)
  /api/backtest      12-month historical backtest (Python, cached 24h)
  /api/trigger       Manually trigger simulate.py (GET=single, POST?mode=backfill)
  /api/status        Server health + data freshness

.github/workflows/   simulate.yml — 30-min cron + GitHub Pages deploy
```

## API endpoints

```
GET /api/node          Current state: SOC, profit, last action, thresholds
GET /api/prices        Agile import prices (last 48h, 96 slots)
GET /api/history       Slot history CSV as JSON (limit=N)
GET /api/backtest      12-month backtest results (cached; ?force=1 to re-run)
GET /api/status        Server health check
GET/POST /api/trigger  Run simulate.py (?mode=backfill for 48h replay)
POST /api/reset        Clear state + history (requires NODE3_API_KEY if set)
```
## Local Docker Replica

To spin up a safe, isolated copy of the portal for development or testing:

```bash
# Build the replica image
docker compose -f docker-compose.replica.yml build

# Run the replica (exposes on host port 8586)
docker compose -f docker-compose.replica.yml up -d
```

The replica mounts the host `data/` directory read‑only, so any live CSV/JSON files remain untouched. Adjust the port mapping in `docker-compose.replica.yml` if you need a different host port.

---

Built by Matt Brander · Dovecote Technology · Part of the NODE-3 energy management platform
