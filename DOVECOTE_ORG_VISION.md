# DovecoteSystems — Organisation Architecture & Product Vision
*Captured: 11 September 2026 — Permanent strategic document*

---

## The Company

**Dovecote Systems Ltd** is an energy technology and enterprise digital infrastructure company.

**Mission**: Provide fixed-price, affordable electrical energy to everyone — premium prosumer customers fund the infrastructure that makes it possible for low-income households.

**Flagship product**: Node-3 — 72kWh battery arbitrage system (Octopus Agile, FoxESS KH10.5, Nissan second-life cells).

**Second major product line**: Rover Enterprise Workspace — self-hosted, open-source enterprise collaboration platform for regulated industries (NHS-first).

---

## GitHub Organisation: `DovecoteSystems`

Private GitHub organisation. All Dovecote code lives here — separate from personal repos.

### Repo Structure

```
DovecoteSystems/
├── node3/            Battery arbitrage engine — LP dispatch, Agile pricing, MQTT pipeline
├── rover/            VDI platform (Proxmox/Guacamole) + SHANE identity layer
├── dovecote-infra/   Shared: Docker configs, NOMAD templates, CI/CD pipelines
├── dovecote-ai/      AI agent configs, MCP integrations, virtual technician logic
└── dovecote-www/     Public marketing + product site
```

Each repo contains a `CLAUDE.md` — the AI agent briefing file. Any Claude session or autonomous agent opening a repo instantly knows the architecture, constraints, and operating rules. This is the foundation of the self-healing, AI-operated infrastructure.

### Business Documents
Business plans, financial models, and contracts are **not in git** (binary files version badly).
They live in Dovecote's own Nextcloud instance — see Rover Enterprise Workspace below.
Each repo README links to the relevant Nextcloud folder.

---

## Product 1: Node-3

See `node3/` repo and `NODE3_MASTER_CHARTER.md` for full spec.

**Summary**: 72kWh second-life battery, FoxESS KH10.5 inverter, Octopus Agile arbitrage, LP optimal dispatch (scipy HiGHS), MQTT telemetry from LilyGo T-2CAN.

**Business model**:
- Tier 1: £30–35k hardware sale + £49/month sub (affluent prosumer, Z15 miner, pool heating)
- Tier 2: £0 upfront, £19–25/month fixed (social housing, Dovecote owns node)
- Tier 1 margin funds Tier 2 hardware

**Z15 integration**: Bitmain Antminer Z15 (1.51kW baseload, 36kWh/day) mines Zcash. Node-3 cuts miner power cost from 41% to 18% of gross revenue. Waste heat → cabin/pool via 100mm duct + motorised damper (£80 implementation).

---

## Product 2: Rover Enterprise Workspace

The natural next layer of Rover — a complete, self-hosted enterprise digital workspace for regulated industries.

### The Stack

```
Proxmox (compute layer)
  └── NOMAD (orchestration — one command deploys entire stack)
        ├── Keycloak        ← unified SSO/identity for ALL Dovecote services
        ├── Nextcloud       ← self-hosted storage + collaboration
        ├── OnlyOffice      ← collaborative document editing (native Nextcloud)
        └── Rover VDI       ← Windows VMs via NFC tap-card thin clients
```

All components are **pre-built Proxmox templates**, deployed by NOMAD as a single stack. Zero per-user Microsoft licensing after hardware.

### Keycloak — The Identity Linchpin

Keycloak provides unified SSO across every Dovecote service:
- Rover VDI logins
- Nextcloud + OnlyOffice
- Node-3 dashboard (currently unauth'd — Keycloak is the fix)
- SHANE physical access management
- Future customer portals and APIs

One credential. One audit trail. Federated across the entire product family.

### The NHS Proposition

Microsoft 365 has persistent GDPR exposure for NHS trusts: data residency, third-party access, opaque audit trails.

Rover Enterprise Workspace delivers:
- **Full Microsoft 365 replacement** — Word/Excel/email/storage/video, all on-prem
- **No data leaves the trust's network** — air-gappable if required
- **GDPR-clean** by architecture, not policy
- **Deployed in a day** via NOMAD (vs weeks for M365 migration)
- **Near-zero ongoing licensing** — Proxmox, Nextcloud, OnlyOffice, Keycloak are all open-source
- **Self-healing** via dovecote-ai virtual technician layer

This is the product no one else delivers cleanly for NHS/regulated industries.

**Market**: NHS trusts, regulated SMEs, local councils, housing associations (natural crossover with Node-3 Tier 2 customers).

### Dovecote Internal Use

Dovecote Systems Ltd runs its own Nextcloud instance. Company documents, contracts, financial models, and business plans all live there — not Google Drive. Dovecote sells what it uses. This is the authentic pitch.

---

## Product 3: AI Virtual Technician Layer (`dovecote-ai`)

The `dovecote-ai` repo is the intelligence layer across all Dovecote products:

- **Node-3**: alerts → agent diagnoses → GitHub issue raised or auto-remediation applied
- **Rover**: VDI fault detected → agent remediates or escalates with full context
- **SHANE**: access event → agent logs, audits, flags anomalies
- **Nextcloud/Keycloak**: admin tasks automated by AI agents with appropriate permissions

Each repo's `CLAUDE.md` is the agent briefing. The `dovecote-infra` repo provides the shared deployment substrate. The org is a set of self-describing, AI-operable systems — designed from the outset to run with minimal human intervention.

---

## The Flywheel

```
Tier 1 hardware sale (£30-35k)
  → £12-17k margin
  → funds 2-3 Tier 2 node installs
  → each Tier 2 node → £931/yr net recurring
  → 50 nodes → £82,500/yr recurring
  → Rover Enterprise Workspace installs → NHS trust recurring contracts
  → AI virtual technicians run the fleet
```

Fixed bills. For everyone. Built on open standards. Operated by AI.

---

*This document is the permanent architectural north star for Dovecote Systems Ltd.  
Keep it current. It is the briefing every human and AI agent needs before touching Dovecote infrastructure.*
