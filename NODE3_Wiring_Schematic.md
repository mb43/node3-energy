# NODE-3 Full Wiring Schematic & Build Checklist
**Author:** Matt Brander · **Generated:** 2026-05-19 · **Source spec:** SLAB Build Spec, G99 A1-1, SLD Rev A

> ⚠️ **HIGH VOLTAGE DC — 360V to 403V nominal.** A shock at this voltage is lethal. Wear Class 0 (1000V) gloves. Use insulated tools. Work one-handed. Have a buddy and an emergency-stop plan before any pack is connected. Never work alone on energised DC.

---

## 1. System Overview

| Block | Part |
|---|---|
| Battery × 3 | Nissan e-NV200 24kWh packs, 360V DC nominal, parallel |
| Main contactor | **Albright SW200-22 with magnetic blowouts** (200A, 12V coil) — NOT a generic AliExpress relay |
| Branch fuses × 3 | Littelfuse KLDR125 (125A, 600VDC, Class J) on Eaton CH10J600 DIN holders |
| HV junction box | Rittal AE 1380.500, IP66 |
| Pack connectors | Anderson SB175 (175A, 600VDC) — one pair per pack branch |
| Inverter | FoxESS KH10.5 HV hybrid, 10.5 kW, single-phase 230V AC |
| BMS bridge | **1 × LilyGo T-2CAN** (ESP32-S3, dual CAN) running DALA Battery-Emulator |
| CAN isolator | Waveshare MCP2551 isolated CAN — **mandatory** on FoxESS side |
| Telemetry | Raspberry Pi 4 (4GB) + Teltonika RUT240 (4G/WiFi) |
| Sense connector | Yazaki 7287-1065-30 (36-pin) on Nissan BMS — you have the pre-crimped pigtail |
| LV supply | Mornsun B2412S-1WR2 isolated 12V (contactor coil, ESP32, BMS wake) |
| Temp sensing | 6 × DS18B20 (2 per pack), 1-wire to RPi |
| Current sensing | 2 × YHDC SCT-013-100 CT clamps (import/export), to RPi |

---

## 2. HV DC Power Wiring (the dangerous side)

```
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │  PACK 1     │    │  PACK 2     │    │  PACK 3     │
   │  e-NV200    │    │  e-NV200    │    │  e-NV200    │
   │  360V DC    │    │  360V DC    │    │  360V DC    │
   │             │    │             │    │             │
   │ [SDP plug]  │    │ [SDP plug]  │    │ [SDP plug]  │ ← Service Disconnect Plugs (always pulled before any work)
   └──+──────−───┘    └──+──────−───┘    └──+──────−───┘
      │      │           │      │           │      │
      │      │           │      │           │      │   35mm² orange H07RN-F (600V DC), M8 crimp lugs
      │      │           │      │           │      │
   [SB175 +/−]        [SB175 +/−]        [SB175 +/−]   ← Anderson SB175 connectors, one pair per pack
      │      │           │      │           │      │
   ───┴──────┴──── ──────┴──────┴──── ──────┴──────┴───   ENTRY INTO HV JUNCTION BOX (Rittal AE 1380.500, IP66)
      │      │           │      │           │      │
   [F1: 125A]            [F2: 125A]         [F3: 125A]     Littelfuse KLDR125 Class J fuses
   600VDC                600VDC             600VDC         on Eaton CH10J600 DIN holders
      │      │           │      │           │      │
      └──┬───┴───────────┴──┬───┴───────────┴──┬───┘
         │                  │                  │       Tinned-copper busbars (6×30mm), 1000V standoffs
         │     +VE BUS  ────┼──────────────────┘
         │                  │
         │   −VE BUS  ──────┘
         │
         │   ┌─────────────────────────────────────┐
         │   │  PRECHARGE CIRCUIT  (see §5)        │
         │   │  500Ω 50W resistor + small relay    │
         │   │  in parallel with main contactor    │
         │   └─────────────────────────────────────┘
         │                  │
      ┌──┴──────────────────┴──┐
      │  ALBRIGHT SW200-22     │  ← MAIN DC CONTACTOR — must have magnetic blowouts
      │  with magnetic blowouts│     Coil: 12V DC from Mornsun B2412S, driven by LilyGo GPIO via opto + MOSFET
      │  200A continuous       │
      └───────────┬────────────┘
                  │
                  │  to FoxESS proprietary HV battery connector
                  ▼
         ┌─────────────────────┐
         │  FoxESS KH10.5      │
         │  HV Hybrid Inverter │ ──→  AC: 230V single-phase via consumer unit → DNO meter → grid
         │  10.5 kW            │
         └─────────────────────┘
```

**Wiring rules:**
- All HV positive cables wrapped in **red** self-amalgamating tape; negative in **black**.
- Label every cable end **"DANGER 400V DC"**.
- Crimp with hex die, not pliers; M8 lug ring terminals.
- 35mm² minimum — never go thinner on the DC bus.
- All HV joints inside the Rittal box, on insulated standoffs, with covers.
- One **earth busbar** (Phoenix Contact USLKG 6) bonds the Rittal box, pack chassis, inverter chassis, and CU earth bar.

---

## 3. LV / Comms / Sense Wiring

```
                    ┌──────────────────────────────────────┐
                    │  Mornsun B2412S-1WR2  (isolated)     │
                    │  Input: 12V (from RUT240 PSU or PSU) │
                    │  Output: 12V isolated LV rail        │
                    └──────────┬───────────────────────────┘
                               │
       ┌───────────────────────┼───────────────────────┬─────────────────┐
       │                       │                       │                 │
       ▼                       ▼                       ▼                 ▼
  ┌────────────┐         ┌──────────────┐      ┌─────────────┐    ┌─────────────┐
  │ ALBRIGHT   │         │  LilyGo      │      │ Nissan BMS  │    │ Waveshare   │
  │ COIL       │         │  T-2CAN      │      │ Pin 1 (12V) │    │ MCP2551 ISO │
  │ (200A      │         │  ESP32-S3    │      │ wakes BMS   │    │ CAN module  │
  │  contactor)│         │  USB-C power │      │             │    │ powered side│
  └─────▲──────┘         │              │      └──────┬──────┘    └──────▲──────┘
        │                │  CAN-A H/L   │             │ Pin 2 (GND)      │
        │ relay drive    │  CAN-B H/L   │             │                  │
        │ from GPIO      └──┬────────┬──┘             │                  │
        │  via opto+MOSFET  │        │                │                  │
        │                   │        │                │                  │
        └───────────────────┘        │                │                  │
                                     │                │                  │
                                CAN-B │                │                  │
                                     │                │                  │
                                     └────────────────┼──────────────────┘   ← CAN-B isolated, then to FoxESS
                                                      │
                                CAN-A ────────────────┘
                                       to Yazaki 36-pin pins 3 (CAN-H) & 4 (CAN-L)

  ┌───────────────────────────────────────────────────────────────────┐
  │  Raspberry Pi 4 (4GB)                                             │
  │   • USB serial to LilyGo (telemetry passthrough)                  │
  │   • GPIO 1-wire bus → 6 × DS18B20 (2 per pack, on Vbat-/cool side)│
  │   • 2 × CT clamps via ADC → import/export                         │
  │   • Ethernet/WiFi → Teltonika RUT240 → Octopus API + portal       │
  │   • Drives history.csv, server.py Flask portal                    │
  └───────────────────────────────────────────────────────────────────┘
```

### Yazaki 7287-1065-30 — pin map you actually wire

| Pin | Signal | Goes to |
|---|---|---|
| 1 | +12V (wakes BMS) | Mornsun 12V rail, via 1A fuse |
| 2 | GND | LV ground bar |
| 3 | CAN-H | LilyGo T-2CAN, CAN-A H |
| 4 | CAN-L | LilyGo T-2CAN, CAN-A L |
| 5–36 | Cell taps + NTCs | **DO NOT CONNECT** — leave isolated in heatshrink, label "do not touch" |

**Termination:** Add a **120Ω resistor** across CAN-H/L at each physical end of each bus segment (CAN-A and CAN-B both). The Nissan BMS already has one — you only need to add 120Ω at the LilyGo end. On CAN-B, add one at the LilyGo end and one at the FoxESS end of the bus (after the isolator).

### LilyGo T-2CAN — pin usage

| Pin / function | Wired to |
|---|---|
| 5V (USB-C or VIN) | LV 12V → step-down to 5V (DROK buck) |
| GND | LV ground |
| CAN-A H / L | Yazaki pins 3 / 4 |
| CAN-B H / L | Waveshare MCP2551 isolator (logic side) |
| GPIO (e.g. IO4) | Opto-isolator → MOSFET → contactor coil drive |
| GPIO (e.g. IO5) | E-stop monitor (read NC contact through opto) |

---

## 4. AC Side (for completeness)

```
FoxESS KH10.5 AC OUT  ──┬── 32A 2P MCB ──┬── consumer unit ──┬── DNO meter ──┬── grid
                        │                │                   │               │
                       CT1 (export)     CT2 (import)        Earth bond      G99 protection
                                                                            (ROCOF + Vector Shift,
                                                                             integrated in FoxESS)
```

---

## 5. Precharge circuit (THE GAP IN YOUR PARTS)

Closing the SW200-22 directly onto a discharged/empty inverter DC bus = massive inrush current → contact pitting → eventual weld. You need a precharge.

**Standard precharge:**
```
+VE bus ──┬──[ 500Ω 50W resistor ]──[ small SPST relay ]──┬── inverter +
          │                                                │
          └────────────[ SW200-22 main ]──────────────────┘── inverter +
```

Sequence (driven by LilyGo firmware):
1. Pull in small precharge relay → 500Ω current limits inrush, bus charges through resistor (~5–10s)
2. Once inverter DC bus reaches ~95% of pack voltage (sensed via FoxESS CAN or simple voltage divider), pull in SW200-22 main
3. Drop precharge relay
4. (On shutdown: open SW200-22 first, then optionally precharge relay)

**FoxESS HV inverters often include internal precharge** — but this is undocumented in the SLAB spec and Rev A SLD. **Verify with Solent Renewables / FoxESS support before energising.** If FoxESS handles it internally, this whole block isn't needed.

---

## 6. What you have vs what you need

### ✅ You have
- 3 × Nissan e-NV200 packs (per Bill of Sale 28 Apr 2026)
- Pre-crimped Yazaki 36-pin pigtail
- Spare bare 36-pin connector + crimps (good — keep as backup)
- Some relays (AliExpress)
- Some fuse holders / breakers

### ❌ Missing / verify-before-wiring (in priority order)

| # | Item | Why critical | Notes |
|---|---|---|---|
| 1 | **Albright SW200-22 (or equivalent with magnetic blowouts)** | Switching 400V DC without arc blowouts = welded contacts + arc flash. AliExpress relays almost certainly inadequate. | Must be DC-rated 400V+, with blowouts. ARC Components stocks. ~£182. |
| 2 | **Littelfuse KLDR125 Class J fuses × 3** | Generic AC fuses do not safely interrupt DC at 600V. Class J or class T mandatory. | Check the holders/breakers you have — are they DC-rated 600V+? If not, throw them out for HV use. |
| 3 | **Eaton CH10J600 DIN fuse holders × 3** | DC-rated holder for the above fuses. | Confirm yours match. |
| 4 | **Anderson SB175 connector pairs × 3** | Pack-side disconnects, 175A 600VDC. | Couldn't see these in your inventory. |
| 5 | **Precharge resistor (500Ω, 50W, wirewound) + small precharge relay** | Avoids contactor weld on cold inrush. | Skip ONLY if FoxESS confirms internal precharge. |
| 6 | **Waveshare MCP2551 isolated CAN module** | FoxESS CAN can sit at ±110V to PE — will destroy the LilyGo and possibly you. Non-negotiable. | ~£8. |
| 7 | **LilyGo T-2CAN board** (ESP32-S3 dual CAN) | The single ESP32 the whole design needs. | ~£28. |
| 8 | **Mornsun B2412S-1WR2 isolated 12V DC-DC** | Isolated LV rail for contactor coil + ESP32. | Or equivalent isolated 12V supply. |
| 9 | **120Ω CAN termination resistors × 3** | CAN bus reflections without terminators = intermittent comms. | 1/4W, dirt cheap. |
| 10 | **35mm² orange H07RN-F cable + M8 lugs + hex crimp die** | The actual HV power cable. | ~£120/10m + lugs + die. |
| 11 | **Rittal AE 1380.500 (or equivalent IP66 enclosure)** | Houses HV joints, busbars, contactor, fuses. | ~£200. |
| 12 | **Insulated tinned copper busbars + 1000V standoffs** | Inside the Rittal box. | ~£40. |
| 13 | **Earth busbar (Phoenix USLKG 6) + heavy earth cable** | Single-point earth for pack chassis + inverter + box. | ~£20. |
| 14 | **Latching IP67 E-stop mushroom button (NC)** | Yanks contactor coil supply on emergency. | ~£15. |
| 15 | **6 × DS18B20 + 1-wire harness** | Temperature monitoring. | Cheap. |
| 16 | **2 × YHDC SCT-013-100 CT clamps + burden resistor + ADC** | Import/export current measurement. | Cheap. |
| 17 | **Class 0 (1000V) electrical gloves + insulated tools** | PPE. Non-optional. | ~£60. |
| 18 | **DMM rated CAT III 1000V** | For voltage checks before/during work. | If not already in toolkit. |

---

## 7. Pre-energise checklist (do not skip)

1. [ ] All 3 Service Disconnect Plugs pulled, in your pocket, not in the packs
2. [ ] All pack +/− cables connected, torqued to 45 N·m, labelled
3. [ ] All fuses installed, contactor mounted, coil wired but **coil supply disconnected**
4. [ ] Earth bond confirmed end-to-end with continuity tester
5. [ ] Insulation resistance test (1000V megger) between +VE bus and chassis, −VE bus and chassis — must be > 1 MΩ
6. [ ] LV side powered up, LilyGo flashed with DALA + FoxESS profile, BMS comms confirmed on bench BEFORE pack connection
7. [ ] CAN-B isolated path confirmed (multimeter: no continuity between LilyGo GND and FoxESS-side CAN module isolated side)
8. [ ] Precharge sequence tested into a dummy capacitive load (or confirmed FoxESS internal precharge)
9. [ ] E-stop drops contactor coil — verified with low-voltage test
10. [ ] **Only now** insert one SDP, close that pack's SB175, verify pack 1 voltage at junction box with DMM
11. [ ] Repeat for pack 2 and pack 3 — **verify all three are within 5V of each other before paralleling**, otherwise massive equalisation current
12. [ ] Command precharge → main contactor sequence from LilyGo
13. [ ] Inverter wake-up, G99 self-test, monitor CAN traffic from LilyGo for first 30 min

**If any pack voltage is more than ~5V off the others, do not parallel them.** Charge/discharge the outlier with a bench supply or pack charger until they're within range. Paralleling packs with significant voltage delta dumps hundreds of amps between them through the SB175 contacts — guaranteed damage.

---

## 8. Open questions to resolve before final wiring

1. **AliExpress relay model number?** — let me verify it's safe for 400V DC switching.
2. **Fuse holders/breakers you have — what part number and DC voltage rating?** Probably need replacing for HV.
3. **FoxESS internal precharge — confirmed or not?** Email Solent Renewables before energising.
4. **Cooling — Option A (A/C) or Option B (forced air)?** SLAB spec leaves this open.
5. **G99 approval status** — last documented as pending (ref 260420-000198). You can wire, but do not energise to grid until approved.
