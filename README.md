# NODE-3 Energy Arbitrage Platform & Website

Public-facing landing page and real-time battery arbitrage operator portal for Dovecote Systems.

**Live operator portal:** [dovecoteltd.co.uk:8585](http://dovecoteltd.co.uk:8585) — currently connects through to Matt's Mac.

> ⚠️ **doesnthavetocosttheearth.com is DEFUNCT** (superseded 19 Aug 2026 by dovecoteltd.co.uk). Do not treat it as live: the GitHub Actions cron that was supposed to refresh `history.csv`/`prices.json` every 30 min (`.github/workflows/simulate.yml`) was deleted 10 May 2026 and never restored, so that GitHub Pages site has been silently serving numbers frozen at the initial commit ever since — it will show stale figures labelled as if they were today's. `portal.doesnthavetocosttheearth.com` (the old Pi reverse-proxy subdomain) no longer resolves at all. If this project is later revived on that domain, either restore the cron job or clearly mark the site as non-live before trusting anything it shows.

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
| Inverter | FoxESS KH10.5 HV |
| Export cap | 3.0 kWh/slot G98 (configurable ≤ 3.68 kWh/slot, 32A legal max) |
| Charge rate | 5.0 kWh/slot (10 kW × 0.5h, configurable) |
| Min SOC reserve | 7.2 kWh (10%) |
| Solar | None modelled (pure arbitrage) |
| Location | Southern England, Region H |
| BMS comms | LilyGo T-2CAN CAN-B (native) ← LEAF BMS Pack 1 |
| FoxESS BAT CAN | LilyGo T-2CAN CAN-A (MCP2515 add-on) → FoxESS BAT CAN port |
| Master control | Modbus RTU: Pi /dev/ttyUSB1 → FoxESS RS485 port (hardware_bridge.py) |

## Wiring Schematic

Interactive schematic (full HV+LV system, LV-only control wiring, and pin-by-pin connection tables): **[NODE3_Schematic.html](NODE3_Schematic.html)**.

Full build checklist, BOM, and 14-step commissioning sequence: **[NODE3_DEFINITIVE.md](NODE3_DEFINITIVE.md)** (single source of truth — supersedes NODE3_Wiring_Schematic.md, which is superseded/archived in `_to_delete/`).

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

Node-3 is a two-layer system. The Python stack on the Pi is the master controller.

```
LAYER 1 — Hardware Abstraction (LilyGo T-2CAN, DALA firmware)
  CAN-B (native ESP32-S3) ← LEAF BMS Pack 1 (reads SOC, voltage, temp)
  DALA scales 24kWh → 72kWh (3P firmware) for FoxESS
  CAN-A (MCP2515 add-on, isolated) → FoxESS BAT CAN port
  IO21/IO48/IO17 (underside expansion header) → SSR-04 → contactors on all 3 packs

LAYER 2 — Master Controller (Raspberry Pi 4B, Python)

simulate.py          LP-optimal dispatch planner (scipy HiGHS).
                     Fetches Octopus Agile prices → solves LP over 96-slot lookahead →
                     writes dispatch_plan.json. Runs every 30 min at slot boundaries.

hardware_bridge.py   ★ MASTER CONTROL ★ — sends actual commands to FoxESS.
                     Reads dispatch_plan.json → sends Modbus RTU via USB-RS485 dongle
                     (/dev/ttyUSB1, 9600 baud) → FoxESS RS485 control port.
                     Work mode register 0x09D0 (ForceChg/ForceDischg/SelfUse).
                     Export limit register 0x09D2 (Watts, G98/G99 cap enforced).
                     Falls back: Modbus TCP → FoxESS cloud API → MQTT.
                     Modes: pre_commissioning (safe/no commands) | self_consumption | full_export

server.py            Flask REST API + backtest engine (port 8585).
  /api/node          Current SOC, profit, last action
  /api/prices        Last 48h of Agile import prices
  /api/history       Recent slot-by-slot history (up to 200 rows)
  /api/backtest      12-month historical backtest (Python LP, cached 24h)
  /api/backtest-lp   LP vs greedy comparison, day-by-day
  /api/plan          Forward dispatch plan with SOC trace and G98/G99 P&L
  /api/trigger       Manually trigger simulate.py (GET=single, POST?mode=backfill)
  /api/status        Server health + data freshness
  /api/hardware-status  Hardware bridge status: mode, last command, control paths
  /api/set-mode      Change operational mode (pre_commissioning|self_consumption|full_export)
  /api/alerts        Active operational alerts (SOC low, expensive import, baseload)
  /api/settings      GET/POST configurable params (battery_kwh, import_kw, export_kw)
  /api/reset         Clear state + history (requires NODE3_API_KEY)

node3_config.py      Single source of truth for physical parameters (72kWh/10kW/6kW).
                     Persisted to node3_config.json. Editable via /api/settings.

index.html           Public-facing landing page (dovecoteltd.co.uk).
style.css            Unified CSS design system (dark mode, glassmorphism).
dashboard.html       Operator portal: live telemetry, backtest graphs, dispatch schedule.
```

## API endpoints

```
GET  /api/node              Current state: SOC, profit, last action
GET  /api/prices            Agile import prices (last 48h, 96 slots)
GET  /api/history           Slot history CSV as JSON (limit=N)
GET  /api/backtest          12-month LP backtest results (cached 24h; ?force=1 to re-run)
GET  /api/backtest-lp       LP vs greedy day-by-day comparison (cached 24h)
GET  /api/plan              Forward dispatch plan with SOC trace + G98/G99 P&L
GET  /api/status            Server health + data freshness
GET  /api/hardware-status   Hardware bridge: mode, last Modbus command, control paths
GET  /api/alerts            Active alerts: SOC low, expensive import, baseload
GET  /api/settings          Current configurable params (battery_kwh, import_kw, etc.)
POST /api/settings          Update params (body: {battery_kwh, import_kw, export_kw, ...})
POST /api/set-mode          Change operational mode {mode, g99_active}
GET/POST /api/trigger       Run simulate.py manually (?mode=backfill for 48h replay)
POST /api/reset             Clear state + history (requires NODE3_API_KEY if set)
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
