# VLP Project Tracker — Dovecote Technology Ltd

**Document Version:** 1.0  
**Created:** 18 April 2026  
**Last Updated:** 18 April 2026  
**Owner:** Matt Brander (matt.brander@gmail.com)  
**Company:** Dovecote Technology Ltd

---

## 1. Status Dashboard

| Workstream | Status | Owner | Target Completion |
|-----------|--------|-------|------------------|
| **G99 Application (SSEN)** | NOT STARTED | Matt Brander | Week 2 (technical approval) |
| **Interim VPP (Octopus/Flexitricity)** | NOT STARTED | Matt Brander | Week 1–2 (onboarding call) |
| **Elexon BSC Accession** | NOT STARTED | Matt Brander | Week 2–3 (accession agreement received) |
| **Hardware Commissioning** | NOT STARTED | Matt Brander | Week 1 (batteries arrive) |

**Overall Project Status:** Preparation phase — all workstreams ready to launch simultaneously.

---

## 2. Phase Timeline

### Week 0 (NOW — 18 April 2026)

**Actions to take immediately:**

- [ ] **Send G99 application** to SSEN (notifications.southmicrogen@sse.com)
  - Use: `email_G99_SSEN.md`
  - Confirm receipt and request MPAN form

- [ ] **Contact Octopus Power VPP team** for Kraken Flex registration
  - Use: `email_Octopus_VPP.md`
  - Target: Commercial team response within 5 working days

- [ ] **Contact Elexon** for BSC accession information
  - Use: `email_Elexon_VLP.md`
  - Request: Accession agreement template + onboarding call within 1 week

- [ ] **Send backup enquiry to Flexitricity** (if lead times slip on Octopus)
  - Use: `email_Flexitricity.md`
  - Priority: Lower than Octopus, but maintain parallel engagement

- [ ] **Confirm MPAN and site address** from meter/DNO
  - Critical for all applications
  - Required for: SSEN, Elexon, Octopus, future Host Supplier

---

### Weeks 1–2: Hardware Installation & Initial Approvals

**Key milestones:**

- [ ] **Batteries arrive and installed** (3× Nissan e-NV200)
- [ ] **FoxESS HV10 inverter commissioned** and integrated with Node3 dashboard
- [ ] **Half-hourly smart meter confirmed** as active (mandatory for BSC settlement)
- [ ] **Validate Node3 dashboard** reading live Agile prices + battery SOC
- [ ] **SSEN fast-track acceptance** received (typically 5 working days)
- [ ] **Elexon BSC accession agreement** received
- [ ] **Octopus VPP onboarding call** scheduled

**Go-live prep:**
- Ensure BMS integration complete between Nissan modules and FoxESS HV10
- Validate exports to inverter and grid
- Confirm 32A/50A export capability

---

### Weeks 3–6: CVA/SVA Qualification & Host Supplier Agreement

**Key milestones:**

- [ ] **BSC Accession Agreement signed** and returned to Elexon
- [ ] **Genstar4 (by Enegen) configured** for BSC data exchange
- [ ] **CVA Qualification** initiated (proves real-time data exchange capability)
- [ ] **SVA Qualification** completed (confirms BSC obligation understanding)
- [ ] **Host Supplier Agreement** signed with Octopus Power (or alternative)
- [ ] **MPAN registered** with Host Supplier

**Expected duration:** 3–4 weeks for CVA/SVA qualification process

---

### Weeks 6–8: BMU Registration

**Key milestones:**

- [ ] **CVA/SVA qualifications confirmed** by Elexon
- [ ] **NESO BMU registration application** submitted
  - Submit via NESO Balancing Services portal
  - Requires: MPAN, BM Unit ID, capacity (10.5kW), asset class (battery)
- [ ] **NESO approval** of BMU registration (typically 2–3 weeks)
- [ ] **Node3 dashboard configured** for real-time generation/export telemetry (EMEB format)

---

### Weeks 8–10: Go-Live as VLP

**Key milestones:**

- [ ] **BMU registered and live** on NESO system
- [ ] **First intraday balancing market bids** submitted via Octopus Host Supplier
- [ ] **Kraken Flex participation confirmed** and dispatch signals live
- [ ] **Node3 dashboard operational** for revenue tracking and optimisation
- [ ] **Go-live as independent VLP**

**First revenue expectations:**
- Agile arbitrage: £50–100 per month (32A export limit)
- Kraken Flex flexibility: £20–50 per month (estimated, dependent on grid needs)
- **Total pilot site:** ~£100–150/month, or ~£1,350/year

---

### Weeks 10+: Scaling & Ongoing Optimisation

**Ongoing:**

- [ ] **Migrate from interim VPP** (if applicable) to full BSC VLP role
- [ ] **Monitor and optimise** revenue via Node3 dashboard
- [ ] **Plan second site** based on pilot learnings
- [ ] **Develop replicable deployment process** for third-party sites
- [ ] **Scale to 10–50 sites** over 12–18 months

---

## 3. Key Contacts

| Contact | Organisation | Email | Phone | Role |
|---------|-------------|-------|-------|------|
| **SSEN Grid Services** | Scottish & Southern Electricity Networks | notifications.southmicrogen@sse.com | [DNO portal] | G99 approval, export limit management |
| **Elexon Market Enquiries** | Elexon | marketenquiries@elexon.co.uk | [See website] | BSC accession, VLP registration |
| **Octopus Power Commercial** | Octopus Energy | [via octopus.energy/business] | [Commercial line] | Kraken Flex VPP registration, Host Supplier agreement |
| **Flexitricity Info** | Flexitricity Ltd | info@flexitricity.com | [Via website] | Backup VPP aggregation (if Octopus lead times extend) |
| **Engage Consulting** | VLP Specialist | [TBD] | [TBD] | Optional: VLP accession support (if resources needed) |
| **Limejump** | Shell Energy subsidiary | [TBD] | [TBD] | Alternative Host Supplier option (if Octopus unavailable) |
| **NESO** | National Energy System Operator | neso.energy | [BMU registration portal] | BMU registration, balancing market access |
| **Genstar4 (Enegen)** | BSC Data Exchange Software | [TBD] | [TBD] | Real-time data exchange for CVA/SVA + settlement |

---

## 4. Hardware Commissioning Checklist

### Pre-Installation

- [ ] MPAN confirmed and registered with Octopus Agile
- [ ] Half-hourly smart meter activated and verified as SMETS2 / DCC-enabled
- [ ] Site address finalised and provided to DNO
- [ ] FoxESS HV10 firmware updated to latest stable version
- [ ] Node3 dashboard access confirmed and network ready

### Installation Week (Week 1)

- [ ] **Install 3× Nissan e-NV200 battery modules** in series or parallel configuration (TBD per FoxESS spec)
- [ ] **Confirm BMS integration** between Nissan modules and FoxESS HV10 inverter
  - Verify CAN bus communication
  - Confirm SOC visibility in FoxESS display
  
- [ ] **Install FoxESS HV10 inverter** and connect to local AC distribution
  - Validate grid import/export capability
  - Confirm 32A export working (baseline)
  
- [ ] **Validate smart meter** in near real-time via Node3 dashboard
  - Half-hourly data points should appear on Agile pricing display
  - Confirm import/export readings accurate
  
- [ ] **Test Agile arbitrage** manually (charge on cheap, discharge on expensive)
  - Validate SOC reporting to Node3
  - Confirm export working to grid

### Post-Installation Validation

- [ ] **Confirm 50A export capability** (request upgrade from SSEN if not yet approved)
- [ ] **Node3 dashboard fully operational:**
  - Live Agile pricing display
  - Battery SOC in real-time
  - Grid frequency data (if available)
  - Revenue tracking enabled
  
- [ ] **Provide to all parties:**
  - MPAN: [TO BE CONFIRMED]
  - Site address: [TO BE CONFIRMED]
  - Battery capacity: 72 kWh
  - Inverter rating: 10.5 kW (FoxESS HV10)
  - Current export limit: 32A (3.68 kWh/slot @ 230V)
  - Requested export limit: 50A (5.75 kWh/slot @ 230V)
  - Smart meter status: Active, half-hourly
  - G99 application status: Submitted [DATE]

---

## 5. Revenue Projection

### Per-Site Annual Revenue (Conservative Estimate)

| Revenue Stream | Scenario 1: 32A (Current) | Scenario 2: 50A (Post-G99) |
|---|---|---|
| **Agile Arbitrage Only** | ~£350/yr | ~£600/yr |
| **BM Revenues** (Modo Energy 2025 benchmark: £70k/MW/yr @ 10kW) | ~£700/yr | ~£700/yr |
| **Kraken Flex Flexibility** (estimated, variable) | ~£100–200/yr | ~£100–200/yr |
| **Subtotal (Conservative)** | **~£1,150/yr** | **~£1,400/yr** |
| **Subtotal (Mid-range)** | **~£1,350/yr** | **~£1,600/yr** |

### Fleet Scaling

| Fleet Size | Annual Revenue (Conservative) | Annual Revenue (Mid-range) | Notes |
|---|---|---|---|
| **1 site (pilot)** | ~£1,150–1,350 | ~£1,350–1,600 | Starting point, Q2 2026 |
| **10 sites** | ~£11,500–13,500 | ~£13,500–16,000 | ~£0.96–1.33k/month |
| **25 sites** | ~£28,750–33,750 | ~£33,750–40,000 | ~£2.4–3.33k/month |
| **50 sites** | ~£57,500–67,500 | ~£67,500–80,000 | **Near £50k salary target** |

### Top-Performer Scenario

If revenue reaches top quartile (Modo Energy £100k/MW performers):
- **Per-site annual:** ~£1,000/yr (BM only, excluding Agile + flexibility)
- **50 sites:** ~£50,000–70,000/yr

**Note:** These projections assume:
- Stable Agile price volatility (±£0.15/kWh spread)
- BM participation accessible via Host Supplier + VLP
- No grid congestion limits reducing export availability
- Successful competitor not flooding market (aggregators may increase in 2026–2027)

---

## 6. KPMG CVA/SVA Qualification Prep

### CVA Qualification

**What it proves:** Ability to reliably exchange real-time data with BSC Agents (half-hourly metering data, generation, demand).

**How to achieve:**
1. Install Genstar4 (by Enegen) on Node3 network
2. Connect Genstar4 to NESO EMEB (Energy Metering Exchange Bank) via secure API
3. Perform 2–4 week live trial sending actual meter/generation data
4. NESO validates 100+ consecutive data submissions
5. CVA qualification certificate issued

**Timeline:** 2–3 weeks (parallel with BSC accession)

### SVA Qualification

**What it proves:** Understanding of BSC obligations (Party Conduct Compliance, financial settlement, dispute resolution).

**How to achieve:**
1. Complete Elexon online training module (BSC fundamentals for new parties)
2. Submit written assessment on SVA obligations
3. Elexon reviews and confirms compliance understanding
4. SVA certificate issued

**Timeline:** 1 week (can run parallel with CVA)

### Genstar4 Setup

- **Software:** Genstar4 by Enegen — handles all BSC data exchange (meter reads, generation, demand settlement files)
- **Node3 Integration:** Genstar4 connects via MQTT or REST API to Node3 for real-time meter/SOC data
- **NESO Connection:** Secure encrypted connection to EMEB for half-hourly data submission
- **Cost:** Typically £1,000–2,000/year for SME tier
- **Lead time:** 1–2 weeks installation + configuration

---

## 7. MPAN & Site Data Sheet

**To be completed and sent to:** Octopus Power + Elexon + NESO (once registered)

### Site Identification

| Field | Value | Status |
|-------|-------|--------|
| **MPAN** | [TO BE CONFIRMED] | Pending meter check |
| **Site Address** | [TO BE CONFIRMED] | Pending site confirmation |
| **Site Postcode** | [TO BE CONFIRMED] | Pending site confirmation |
| **Grid Supply Point (GSP)** | [TBD — typically derived from MPAN] | For NESO BMU registration |

### Asset Specification

| Field | Value | Status |
|-------|-------|--------|
| **Battery Capacity** | 72 kWh | Confirmed |
| **Inverter Model** | FoxESS HV10 | Confirmed |
| **Inverter Rating** | 10.5 kW | Confirmed |
| **Battery Type** | 3× Nissan e-NV200 (LV system) | Confirmed |
| **Estimated Round-Trip Efficiency** | ~88% (battery) + 94% (inverter) = ~83% | Estimated |

### Electricity Supply

| Field | Value | Status |
|-------|-------|--------|
| **Current Export Limit** | 32A @ 230V = 3.68 kW (per slot) | Current (baseline) |
| **Requested Export Limit** | 50A @ 230V = 5.75 kW (per slot) | Pending G99 approval |
| **Tariff (Import)** | Octopus Agile | Confirmed |
| **Tariff (Export)** | Octopus Agile (export rate) | Confirmed |
| **Smart Meter Type** | Half-hourly (SMETS2 / DCC) | To be verified in Week 1 |
| **Smart Meter Status** | Active, reading on Node3 | To be verified in Week 1 |

### Regulatory & Market

| Field | Value | Status |
|-------|-------|--------|
| **DNO** | SSEN (Scottish & Southern Electricity Networks) | Confirmed |
| **DNO Region** | Region H (Southern England) | Confirmed |
| **G99 Application Status** | Not yet submitted | Submit Week 0 |
| **G99 Approval Date** | [TO BE DETERMINED] | Expected Week 2 |
| **BSC Party Status** | Accession in progress | Initiate Week 0 |
| **VLP Aggregator** | Octopus Power (interim) | Pending onboarding call |

### Contact & Escalation

| Field | Value |
|-------|-------|
| **Site Owner** | Dovecote Technology Ltd (Matt Brander) |
| **Primary Contact** | Matt Brander (matt.brander@gmail.com) |
| **SSEN Portal Account** | [TO BE SET UP] |
| **Octopus Account** | [TO BE CONFIRMED] |
| **Elexon Contact** | [TO BE ASSIGNED] |

---

## 8. Decision Points & Gating

| Gate | Condition | Owner | By Week |
|------|-----------|-------|--------|
| **Hardware Install Gate** | 3× Nissan modules + FoxESS + smart meter all confirmed operational and reporting to Node3 | Matt Brander | 1 |
| **SSEN Acceptance Gate** | G99 fast-track accepted by SSEN; export limit upgrade (50A) approved or confirmed standard (32A) | SSEN | 2 |
| **Octopus Onboarding Gate** | Kraken Flex registration call completed; Host Supplier agreement terms clear | Octopus Power | 2 |
| **Elexon Accession Gate** | BSC Accession Agreement signed; Genstar4 installed and tested | Matt Brander + Elexon | 3 |
| **CVA/SVA Gate** | Both qualifications completed and confirmed by Elexon; data exchange live | Elexon | 6 |
| **BMU Registration Gate** | NESO BMU live and accepting intraday bids | NESO | 8 |
| **Go-Live Gate** | All systems operational; first revenue received from at least one stream | Matt Brander | 10 |

---

## 9. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **G99 delay** (SSEN backlog) | Medium | 2–4 week slip in export upgrade | Submit immediately; escalate to SSEN if no response in 7 days |
| **Elexon accession timeline slip** | Medium | 2–3 week delay in BSC qualification | Engage Engage Consulting early; parallel engagement with multiple contacts |
| **Smart meter not half-hourly** | Low | Cannot settle BSC; must request DNO upgrade | Verify meter type in Week 0 before batteries arrive |
| **Octopus lead times extend** | Medium | Kraken Flex onboarding delayed by 4–6 weeks | Activate Flexitricity backup; or negotiate interim arrangement with Octopus |
| **Battery supply chain slip** | Low | Installation delayed into Week 2–3 | Confirm delivery date with supplier now; arrange contingency installation slot |
| **FoxESS firmware incompatibility** | Low | Inverter cannot communicate with Nissan BMS | Update firmware pre-installation; confirm compatibility matrix with FoxESS support |
| **Node3 dashboard connectivity loss** | Low | Real-time monitoring/revenue tracking interrupted | Ensure Node3 on resilient network; test failover to mobile hotspot |

---

## 10. Success Metrics

| Metric | Target | Owner | Measurement |
|--------|--------|-------|-------------|
| **Time to go-live as VLP** | ≤ 10 weeks | Matt Brander | Date of first NESO BMU settlement |
| **Monthly revenue (1 site, month 1)** | ≥ £100 | Node3 dashboard | Octopus + BM revenue reports |
| **Fleet readiness (scalability)** | Replicable 3-site deployment by Week 16 | Matt Brander | 3 additional sites commissioned + settled |
| **Customer satisfaction (future)** | NPS ≥ 50 for third-party sites | TBD | Post-deployment feedback |
| **Technical uptime** | ≥ 95% (battery + inverter + export) | Node3 monitoring | Automated alerting logs |

---

## 11. Next Actions (Priority Order)

**TODAY (18 April 2026):**

1. **Send G99 SSEN email** — Use `email_G99_SSEN.md`; confirm receipt and request form
2. **Send Elexon enquiry** — Use `email_Elexon_VLP.md`; request accession agreement + call
3. **Send Octopus VPP email** — Use `email_Octopus_VPP.md`; aim for response within 5 days
4. **Confirm MPAN + site address** — Ring meter/DNO; update Site Data Sheet once confirmed

**Week 0–1:**

5. **Complete G99 form** — Once SSEN confirms receipt and provides form
6. **Prepare Elexon BSC documentation** — Accept accession agreement; arrange call
7. **Validate hardware readiness** — Final checks on FoxESS firmware, Nissan BMS, network

**Week 1+:**

8. **Install hardware** — Batteries, inverter, smart meter verification
9. **Submit G99 to SSEN** — With final MPAN and site details
10. **Go live with Node3 monitoring** — Validate revenue tracking starts

---

## Document Control

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 18 Apr 2026 | Matt Brander | Initial creation; all workstreams in NOT STARTED status |

**Next Review:** 25 April 2026 (post-Week 1 hardware install)
