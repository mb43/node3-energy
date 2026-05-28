# NODE-3 PROJECT & ARBITRAGE SYSTEM – FULL EXPORT

## Overview
This document contains the full design, architecture, and implementation details for the Node-3 energy system and live arbitrage simulation platform.

---

## PART 1: NODE-3 PHYSICAL SYSTEM

### Battery Configuration
- 3x Nissan e-NV200 24kWh packs
- Vertical “bookcase” orientation
- Total weight ~900kg

### Cabinet Dimensions
- External: 1700mm (L) x 1300mm (H) x 950mm (D)
- Internal: 1650mm x 1200mm x 900mm

### Structure
- 40x40x3mm steel frame
- 5mm base plate
- Cross members every 400mm

### Battery Mounting
- Bottom steel tray
- Side rails (bolt-on)
- Top restraint bar (M10)

### Cooling
- 3x intake fans (bottom, aligned to ducts)
- Top exhaust vents/fans
- Airflow: bottom → through pack → top

### Electrical Flow
Battery → Isolator → Fuse → Pre-charge → Contactor → Inverter

### Control System
- Raspberry Pi
- Dala Battery Emulator (CAN)
- Relay board (contactor, precharge, fans)

---

## PART 2: SOFTWARE ARCHITECTURE

### Structure
- Backend (Python)
- Frontend (HTML/JS)
- GitHub Actions (cron every 30 mins)

### Data Sources
- Octopus Agile API (pricing)
- Open-Meteo (weather)

---

## SIMULATION MODEL

### Assumptions
- Battery: 60kWh (50kWh usable)
- Load: 12kWh/day
- Solar: dynamic via weather
- Charge rate: 10kW equivalent

---

## CORE STRATEGY

BUY:
- When price < 30th percentile

SELL:
- When price > 75th percentile

RESERVE:
- Maintain 10kWh minimum SOC

---

## FLEET SYSTEM

- Multi-home simulation (default 10 homes)
- Each home:
  - Independent SOC
  - Independent profit tracking
- Aggregated fleet profit

---

## DASHBOARD

- Live profit display
- Historical graph (Chart.js)
- Updates every 30 seconds

---

## AUTOMATION

- GitHub Actions runs every 30 mins
- Appends results to history.csv
- Frontend reads live data

---

## FUTURE EXTENSIONS

- Real inverter integration (FOX)
- Stripe billing
- Customer portal
- AI optimisation layer

---

## PURPOSE

This system enables:
- Real-world validation of energy arbitrage
- Continuous data collection
- Scalable multi-home deployment

---

## END
