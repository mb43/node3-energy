# DovecoteSystems — Org-Level AI Agent Briefing
*This file lives at GitHub org level and in each repo. Read this before touching any Dovecote code or infrastructure.*

---

## The Company

**Dovecote Systems Ltd** — energy technology + enterprise digital infrastructure.

**Founder**: Matt Brander (matt.brander@gmail.com)

**Mission**: Fixed-price affordable electrical energy for everyone. Premium prosumer customers fund the infrastructure that makes it possible for low-income households.

This is a real company. Not a hobby. Treat everything accordingly.

---

## Products

### 1. Node-3 — Battery Arbitrage System
- 72kWh second-life Nissan battery + FoxESS KH10.5 inverter
- Octopus Agile tariff — buy cheap overnight, sell at VLP (>40p/kWh)
- LP optimal dispatch (scipy HiGHS) — globally optimal, never greedy
- MQTT telemetry: LilyGo T-2CAN → battery-emulator → mosquitto → server.py
- Z15 Antminer baseload: 1.51kW constant (config: `baseload_kw = 1.51`)
- Repo: `DovecoteSystems/node3`
- Full spec: `NODE3_MASTER_CHARTER.md`, `DOVECOTE_ORG_VISION.md`

### 2. Rover Enterprise Workspace
- Self-hosted Microsoft 365 replacement for regulated industries (NHS-first)
- Stack: Proxmox → NOMAD → Keycloak → Nextcloud → OnlyOffice → Rover VDI
- Pre-built Proxmox templates, one-command NOMAD deployment
- Keycloak = unified SSO across ALL Dovecote services
- Repo: `DovecoteSystems/rover`

### 3. AI Virtual Technician Layer
- Autonomous agents operating across all Dovecote products
- Briefed via per-repo CLAUDE.md files
- Repo: `DovecoteSystems/dovecote-ai`

---

## Architecture Principles

### Identity: Keycloak is the answer for auth
Every Dovecote service authenticates via Keycloak. Node-3 dashboard, Rover VDI, Nextcloud, SHANE, customer portals — all Keycloak. Do not implement bespoke auth in any service.

### Deployment: NOMAD + dovecote-infra
All services deploy via NOMAD templates in `dovecote-infra`. Do not create one-off deployment scripts outside this repo.

### Documents: Nextcloud, not git
Binary files (Word, Excel, PDF) go in Dovecote's Nextcloud. Git is for code and markdown only.

### LP dispatch: never revert to greedy
Node-3 dispatch uses scipy HiGHS LP. This is permanent. Do not reintroduce greedy/phase-2/percentile logic under any circumstances.

### Baseload always accounted for
`baseload_kw` (Z15 miner = 1.51kW) flows through LP dispatch, backtest, and alerts. Never plan dispatch as if baseload doesn't exist.

---

## Business Model

### Tier 1 — Premium Prosumer
- £30–35k hardware + Z15 miner + Node-3, installed
- £49/month subscription
- Customer gets: mining revenue, arbitrage, pool/space heating, fixed energy, eco credentials
- Dovecote gets: £12–17k margin + recurring sub + capital to fund Tier 2

### Tier 2 — Social Affordable
- £0 upfront — Dovecote owns the node hardware
- £19–25/month fixed sub
- Customer saves ~£630/year vs SVT — genuinely life-changing
- Route to scale: housing associations (50–500 installs per deal)

### The Flywheel
1× Tier 1 sale → funds 2–3 Tier 2 installs → recurring revenue → self-funding growth

---

## Key Technical Constants (Node-3)

| Constant | Value | Notes |
|----------|-------|-------|
| `battery_kwh` | 72.0 | 3× Nissan 24kWh packs |
| `import_kw` | 10.0 | Grid import limit |
| `export_kw` | 6.0 | Grid export limit (G99) |
| `min_soc_pct` | 10.0 | Battery floor |
| `baseload_kw` | 1.51 | Z15 Antminer constant load |
| `house_kwh_day` | 12.0 | Profiled household load |
| RTE | 88% | Round-trip efficiency |
| VLP threshold | 40p/kWh | Minimum price to export |

---

## Repo Responsibilities

| Repo | Owns |
|------|------|
| `node3` | Arbitrage engine, MQTT pipeline, Agile pricing, dashboard |
| `rover` | VDI (Proxmox/Guacamole), SHANE, Keycloak integration |
| `dovecote-infra` | Docker, NOMAD templates, CI/CD, shared configs |
| `dovecote-ai` | Agent logic, MCP configs, virtual technician automation |
| `dovecote-www` | Public site, product pages |

---

## What NOT to Do

- Do not implement auth outside Keycloak
- Do not hardcode load values — always read from `node3_config.py`
- Do not revert LP dispatch to greedy
- Do not commit binary documents to git (Word/Excel/PDF → Nextcloud)
- Do not activate Octopus Agile tariff until Node-3 hardware is fully live
- Do not push to production without checking `dovecote-infra` CI passes

---

*Last updated: 11 September 2026*
*Full strategic context: `DOVECOTE_ORG_VISION.md`*
