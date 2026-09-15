# NODE-3 — Definitive Build Spec (Single Source of Truth)
**For:** Matt Brander · **Date:** 30 May 2026 · **Supersedes:** all prior NODE3_*.md files in this folder.

> **Source of truth principle.** This file reconciles:
> 1. Your existing parts on hand
> 2. The DALA Battery-Emulator wiki for Nissan LEAF / e-NV200 (https://github.com/dalathegreat/Battery-Emulator/wiki/Battery:-Nissan-LEAF---e%E2%80%90NV200)
> 3. The 3-pack-parallel-with-1-BMS phase 1 scope you've been advised to start with
> 4. Your three locked-in decisions (DALA SSR drive · drop Albright · OEM Sumitomo plugs)
>
> If anything else in the folder contradicts this file, this file wins.

---

## 1. Topology in one paragraph

3× Nissan e-NV200 24kWh packs are paralleled at a +/− busbar inside one IP65 enclosure. Each pack keeps its own internal precharge resistor and internal positive/negative main contactors — these do all the HV switching. The LilyGo T-2CAN ESP32 (already flashed with DALA "Nissan Leaf 3P" firmware) reads Pack 1's BMS on **CAN-B** (native ESP32-S3 CAN, GPIO 6/7) and reports 3× scaled capacity to the FoxESS KH10.5 on **CAN-A** (MCP2515/2518 add-on, galvanically isolated — no external isolator needed). The LilyGo also drives three SSR-04 channels (precharge, +contactor, −contactor) via GPIOs **IO21** (precharge), **IO48** (positive contactor), **IO17** (negative contactor) on the underside 26-pin expansion header, whose outputs are daisy-chained to the corresponding contactor coil pins on **all three** Yazaki connectors, so all three packs sequence in lockstep. A 12V rail powers Yazaki Pin 1 (BAT+IGN) on all three packs via an E-stop NC contact — pressing E-stop drops the wake signal and all three packs open within ~100 ms. Branch protection is a TOMZN DC 2P breaker per pack; a fourth TOMZN sits downstream of the busbar as the master isolator before the inverter.

**The Node-3 Python system (server.py / simulate.py / hardware_bridge.py) running on the Raspberry Pi 4B is the master controller.** It fetches Octopus Agile prices, runs a linear-programming optimiser to decide charge/discharge schedules, and sends Modbus RTU commands directly to the FoxESS KH10.5 via a USB-RS485 dongle at every 30-minute slot boundary. The T-2CAN/DALA layer is purely a hardware abstraction: it makes the FoxESS accept the LEAF batteries and sequences the contactors. All commercial intelligence — when to charge, when to export, at what rate, respecting G98/G99 export caps — lives in the Pi software layer.

---

## 2. Block diagram (ASCII)

```
                                     ╔══════════════════════╗
                                     ║   FoxESS KH10.5      ║
                                     ║   HV Hybrid Inverter ║
                                     ╚══════╦═══════════════╝
                                            ║ HV DC (~360V) + CAN
            ┌─── CAN-B (isolated) ──────────╫────────┐
            │                               ║        │
            │                       ┌───────╨───────┐│
            │                       │ TOMZN DC 2P   ││  ← MASTER isolator
            │                       │ 1100V 32A     ││
            │                       └───────┬───────┘│
            │                               │        │
            │                  ┌───── +BUSBAR ──────────────────┐
            │                  │ (tinned Cu, 6×30mm × 200mm)    │
            │                  │                                │
            │              ┌───┴───┐    ┌───┴───┐    ┌───┴───┐
            │              │TOMZN  │    │TOMZN  │    │TOMZN  │  ← branch protection
            │              │2P 32A │    │2P 32A │    │2P 32A │
            │              └───┬───┘    └───┬───┘    └───┬───┘
            │                  │            │            │
            │              ╔═══╧═══╗    ╔═══╧═══╗    ╔═══╧═══╗
            │              ║ SDP1  ║    ║ SDP2  ║    ║ SDP3  ║  ← Service Disconnect Plug
            │              ╚═══╤═══╝    ╚═══╤═══╝    ╚═══╤═══╝     (manual, OUT for service)
            │                  │            │            │
            │              ┌───┴───┐    ┌───┴───┐    ┌───┴───┐
            │              │PACK 1 │    │PACK 2 │    │PACK 3 │
            │              │ BMS+  │    │ BMS+  │    │ BMS+  │
            │              │ INT.  │    │ INT.  │    │ INT.  │
            │              │ CONT. │    │ CONT. │    │ CONT. │
            │              └─┬─┬─┬─┘    └─┬─┬───┘    └─┬─┬───┘
            │                │ │ │        │ │          │ │
            │           CAN  │ │ │ Yazaki │ │  Yazaki  │ │  Yazaki
            │           ─────┘ │ │ ───────┘ │  ────────┘ │  ─────────
            │              ┌───┘ │          │            │
            │              │     │  ┌───────┴────────────┴───┐
            │              │     │  │ DAISY-CHAINED signals: │
            │              │     │  │ • BAT+IGN (Pin 1, 12V) │ ← via E-stop NC
            │              │     │  │ • GND     (Pin 2)      │
            │              │     │  │ • Precharge coil       │ ← from SSR1 OUT
            │              │     │  │ • +Contactor coil      │ ← from SSR2 OUT
            │              │     │  │ • −Contactor coil      │ ← from SSR3 OUT
            │              │     │  └────────────────────────┘
            │              │     │
            │       CAN-A │     │ Pack 1 only carries CAN back to LilyGo
            │              │     │
            │           ┌──┴─────┴────┐
            │           │  LilyGo     │
            │           │  T-2CAN     │  IO21 → SSR Ch1 IN (Precharge)
            │           │  ESP32-S3   │  IO48 → SSR Ch2 IN (+Pos Cont)
            │           │  (DALA)     │  IO17 → SSR Ch3 IN (−Neg Cont)
            │           └──┬─────────┬┘  GND  → all SSR IN−
            └──CAN-A───────┘         │    (underside 26-pin expansion header)
              (MCP2515 add-on,       │    (CAN-B = native ESP32, ← LEAF BMS)
               galv. isolated)       │
                                12V from Mean Well DR-60-12 PSU
                                (mains AC 230V → 12V DC 5A DIN rail)
                                     │
                                  E-stop NC in series → pressing = drop all 3 packs
```

---

## 3. Bill of materials — phase 1 (final)

### ✅ Already in hand — do NOT re-buy
- 3 × Nissan e-NV200 24kWh packs (Bill of Sale 28 Apr 2026)
- LilyGo T-2CAN ESP32-S3, flashed with DALA firmware in "Nissan Leaf 3P" mode
- 1 × Yazaki 7287-1065-30 36-pin **pre-crimped** harness
- 1 × Yazaki 7287-1065-30 36-pin **bare** connector + crimp pins (spare)
- 3 × TOMZN DC1100V 2P 32A breakers ← all 3 used for branch protection
- 1 × SSR-04 5DD-CN (4-channel SSR module) ← 3 channels used, 1 spare
- IP65 enclosure (TLC CMSB604025, 400×600×250 portrait — collecting locally)
- Raspberry Pi 4 4GB + heatsink/fan
- ZTE 4G router (prototype substitute for RUT240)
- Multimeter ⚠️ verify CAT III 1000V before any HV work

### ❌ Removed from previous BOM (NOT BUYING)
- ~~Albright SW200-22~~ — pack-internal contactors do the work, ~£182 saved
- ~~Arcol HS50 500R precharge resistor~~ — pack has internal precharge, ~£10 saved
- ~~Omron G8P-1A4P precharge relay~~ — not needed, ~£4 saved
- ~~Anderson SB175 connectors x3 pairs~~ — OEM Sumitomo plug is the disconnect, ~£70 saved
- ~~M10 insulated busbar standoffs~~ — no Albright = no big standoffs needed at HV; busbars sit on smaller insulators
- ~~Rittal AE 1380.500~~ — already in hand alternative (TLC CMSB604025)
- ~~CAT III DMM purchase~~ — verify existing meter first

### 🛒 To buy — grouped by supplier

#### ORDER 1 — eBay (HV harness harvest) **DO FIRST**
| Item | Qty | £ | Source |
|---|---|---|---|
| Nissan e-NV200 heater unit (P/N 27143-4FA2B) — buy for the HV cable + Sumitomo plug attached | **3** | £89.10 ea = ~£267 | eBay listing 305824485941 (only 2 available there — find a 3rd from same seller or alt listing) |

You need one HV cable+plug per pack. Cut the heater off and discard. The cable + Sumitomo connector with HVIL pilot pins is what you want.

#### ORDER 2 — RS Components UK (next-day)
| Item | Qty | RS search / part |
|---|---|---|
| Mean Well DR-60-12 (230V AC → 12V DC, 5A, 60W, DIN rail) | 1 | RS "DR-60-12" |
| Phoenix Contact USLKG 6 PE earth busbar | 1 | RS 1208420 |
| DIN rail 35mm × 1m | 1 | Standard |
| Cable gland kit (M16/M20/M25/M40 mixed) | 1 | "PG cable gland kit" |
| Inline blade fuse holder + 1A fuse (for Yazaki Pin 1 supply) | 1 | Standard |
| 120Ω 0.25W resistors (CAN termination, pack of 100) | 1 | Standard |
| Tinned copper busbar 6×30mm × 1m | 1 (cut into 2× 200mm) | "tinned copper busbar 6x30" |
| Insulated standoffs M6, 600V rated × 4 | 4 | "busbar insulator standoff 600V" |

Rough total: ~£100–120

#### ORDER 3 — Amazon UK (next-day)
| Item | Qty | Search |
|---|---|---|
| ~~Waveshare 2-CH Isolated CAN HAT~~ | ~~1~~ | **DO NOT BUY** — T-2CAN CAN-A/CAN-B are already galvanically isolated. No external CAN isolator needed. DALA wiki confirms "FoxESS cannot fry the T-2CAN." |
| YHDC SCT-013-100 CT clamps | 2 | "YHDC SCT-013-100" |
| DS18B20 waterproof temperature probes | 6-pack | "DS18B20 waterproof probe 6" |
| DROK 12V → 5V buck converter, 3A | 1 | "DROK LM2596 12V to 5V" |
| Heat shrink kit (incl. 20mm, red+black) | 1 | "heat shrink tubing kit large" |
| Self-amalgamating tape — red roll | 1 | Scapa 2702 / Scotch 23 |
| Self-amalgamating tape — black roll | 1 | Same |
| Insulated screwdriver set VDE 1000V | 1 | Wera/Wiha/Knipex VDE |
| Safety glasses (arc-rated) | 1 | Bolle / 3M |
| Cable ties + labels | 1 set | Standard |

Rough total: ~£140–170

#### ORDER 4 — AliExpress (Yazaki harness × 2 more)
| Item | Qty | Source |
|---|---|---|
| Yazaki 7287-1065-30 36-pin **pre-crimped** harness | 2 | DALA wiki link: AliExpress 1005005815234149 |

You have 1 already + 1 bare backup. For 3-pack contactor drive you need a Yazaki on **every pack**. Buying 2 pre-crimped is faster than hand-crimping 35 pins twice. (Or use the bare one + crimp 4 pins per pack for the daisy chain — your call.)

Rough total: ~£25–40 incl. shipping

#### ORDER 5 — Cable wholesaler / Eland Cables / 123electrical
| Item | Qty | Notes |
|---|---|---|
| 35mm² orange H07RN-F flexible cable | 5m | DC-rated, orange = EV/HV convention. Pack→busbar runs are short; 5m total covers the busbar→inverter run + spare. |
| 16mm² green/yellow earth cable | 5m | Pack chassis bonds + enclosure bond |
| M8 tinned copper hex-crimp ring lugs for 35mm² | 4 pack | Only needed for the busbar→inverter run + busbar tap |
| M6 ring lugs (for 16mm² earth bonding) | 10 pack | Pack chassis + enclosure + PE busbar |

Rough total: ~£60–80

#### ORDER 6 — SafetyGloves.co.uk
| Item | £ |
|---|---|
| Class 0 1000V insulating gloves (EN60903) | ~£30 |
| Leather oversleeves | ~£20 |

Rough total: ~£50

#### ORDER 7 — Tool hire (one-shot)
| Item | Why | Where |
|---|---|---|
| Hydraulic hex crimp tool for 35mm² lugs | Pliers crimps fail on 35mm² at sustained current = fire risk | HSS / Brandon / Speedy, ~£25/day |
| 1000V insulation tester (megger) | Pre-energise test on each pack-to-busbar string | HSS, ~£25/day |

#### ORDER 8 — Optional but recommended
| Item | £ | Why |
|---|---|---|
| Latching IP67 E-stop mushroom button, NC contact | £15–40 | Schneider XALK178 or equivalent. Wires in series with the 12V Pin 1 feed → press = drop all packs |
| ABC or Class-D fire extinguisher | ~£30 | Mount near install |
| HV warning labels "DANGER 400V DC" | ~£5 | RS / eBay |

---

## 4. Cash total — revised

| Order | Was (prior BOM) | Now |
|---|---|---|
| 1. eBay HV harness × 3 | – | ~£267 |
| 2. RS components | £115 | ~£110 |
| 3. Amazon | £150 | ~£155 |
| 4. AliExpress (Yazaki × 2) | – | ~£35 |
| 5. Cable | £140 | ~£70 |
| 6. Safety gloves | £50 | £50 |
| 7. Tool hire | £50 | £50 |
| 8. E-stop + labels | £60 | ~£60 |
| ARC (Albright) | £182 | **£0** ✂ |
| Farnell (precharge) | £40 | **£0** ✂ |
| **TOTAL** | **~£790–930** | **~£797** |

Roughly the same headline number, but **the £182 Albright + 8-week wait is gone**, and £180-ish has been redirected into the eBay HV harnesses you actually need to physically connect the packs. Net effect: you can wire-and-test this build in **weeks, not months**.

---

## 5. Yazaki 36-pin wiring per pack

Each pack's Yazaki carries the same five low-voltage signals. Only Pack 1 additionally carries CAN.

| Signal | Pin | Pack 1 | Pack 2 | Pack 3 |
|---|---|---|---|---|
| BAT+IGN (12V wake) | Pin 1 | ✅ from 12V rail via E-stop NC + 1A fuse | ✅ same rail (daisy) | ✅ same rail (daisy) |
| GND | Pin 2 | ✅ to common LV GND | ✅ | ✅ |
| CAN-H | Pin 3 | ✅ to LilyGo CAN-B H (native ESP32-S3 CAN) | ❌ leave open | ❌ leave open |
| CAN-L | Pin 4 | ✅ to LilyGo CAN-B L (native ESP32-S3 CAN) | ❌ leave open | ❌ leave open |
| Precharge coil | per DALA wiring diagram | ✅ from SSR1 OUT (12V switched) | ✅ daisy | ✅ daisy |
| +Contactor coil | per DALA wiring diagram | ✅ from SSR2 OUT | ✅ daisy | ✅ daisy |
| −Contactor coil | per DALA wiring diagram | ✅ from SSR3 OUT | ✅ daisy | ✅ daisy |

> **For exact Yazaki pin numbers for the three coil drive signals**, read off the DALA "Detailed connection diagram, with automatic contactor control via SSR" image on https://github.com/dalathegreat/Battery-Emulator/wiki/Battery:-Nissan-LEAF---e%E2%80%90NV200#wiring-diagram — the image labels the pin numbers next to each SSR output. The pin numbers are determined by Nissan's wiring, not by DALA — once you know them they apply to all three packs identically.

Pack 1 CAN bus needs a 120Ω termination resistor across CAN-H/CAN-L at the LilyGo end (the pack itself already terminates at the BMS end).

---

## 6. LilyGo T-2CAN GPIO usage

All contactor GPIOs are on the **underside 26-pin 2.54mm expansion header**, right column.
Right column, counting from top: Row 9 = IO48, Row 10 = IO21, Row 11 = IO17, Row 12 = GND.
Solder wires directly to pads, or fit a 2×13 2.54mm pin header and use Dupont connectors.

| GPIO | Row (right col) | Role | Wired to |
|---|---|---|---|
| IO21 | Row 10 | Precharge SSR drive (3.3V) | SSR-04 channel 1 IN+ |
| IO48 | Row 9  | +Contactor SSR drive (3.3V) | SSR-04 channel 2 IN+ |
| IO17 | Row 11 | −Contactor SSR drive (3.3V) | SSR-04 channel 3 IN+ |
| GND  | Row 12 | Common return | SSR-04 IN− common |
| CAN-B (native ESP32-S3, GPIO 6/7) | — | Pack 1 BMS read | Yazaki Pack 1 Pins 3/4 (CAN-H/L) |
| CAN-A (MCP2515/2518 add-on) | — | FoxESS BAT CAN comms | FoxESS KH10.5 BAT CAN port direct |
| 5V / 3.3V | — | Module power | DROK 12→5V output |

**CAN isolation note:** Both CAN channels on the T-2CAN are galvanically isolated by the MCP2515/TJA1051 transceivers. No external CAN isolator or Waveshare HAT is required. The DALA wiki explicitly states "FoxESS cannot fry the T-2CAN."

**RS485 note (separate from CAN):** The T-2CAN also exposes RS485 on its top 4-pin SH-1.0mm connector (GPIO43=TX, GPIO44=RX). This is **not** used for contactor control. It is a separate independent RS485 port — if needed, it can bridge to an RS485 device. The Pi uses its own USB-RS485 dongle (/dev/ttyUSB1) to talk Modbus RTU directly to the FoxESS control port — that path is entirely independent of the T-2CAN.

**Software control note:** The Pi's Node-3 Python stack (hardware_bridge.py) is the master controller. It sends Modbus RTU commands to the FoxESS every 30 minutes to set charge/discharge mode and export limits. The T-2CAN/DALA handles only battery emulation and contactor sequencing — it does not make any energy trading decisions.

---

## 7. SSR-04 channel allocation

GPIO assignments per DALA wiki confirmed pinout (underside expansion header, right column):

| SSR-04 channel | IN− | IN+ from LilyGo GPIO | Function | OUT (switches 12V to coil) |
|---|---|---|---|---|
| 1 | GND | IO21 (row 10) | Precharge | Precharge coil pin on all 3 Yazakis (daisy-chained) |
| 2 | GND | IO48 (row 9)  | +Contactor | Positive contactor coil pin on all 3 Yazakis |
| 3 | GND | IO17 (row 11) | −Contactor | Negative contactor coil pin on all 3 Yazakis |
| 4 | — | — | Spare | Could drive E-stop status LED, fan, etc. |

Each SSR-04 OUT switches 12V from the same rail that feeds Pin 1. When LilyGo decides it's safe, it sequences: precharge ON → wait → +cont ON → −cont ON → precharge OFF. Each pack's internal BMS sees the coil signal arrive and operates its own internal contactor accordingly.

---

## 8. Commissioning sequence (do EXACTLY in this order)

1. **All 3 SDPs OUT**. Packs are physically broken in the middle, no HV exposed at terminals. Verify with megger between any HV pin and chassis: >10 MΩ.
2. **Wire everything up with NO mains AC** to the DR-60-12 yet. Visual check every termination twice. Self-amalgamating tape on every HV crimp.
3. **Verify each pack's OCV (open-circuit voltage) at the SDP socket** with DMM. All three must read within **5 V** of each other before you parallel them at the busbar. If not, charge/discharge to match before continuing.
4. **Apply mains AC**. 12V rail comes up. Check 12V at Yazaki Pin 1 of each pack via the E-stop loop. Press E-stop → 0V. Release → 12V back.
5. **LilyGo powers up.** Open its web UI on Wi-Fi. Confirm CAN-A is talking to Pack 1's BMS (you'll see SOC/voltage data). Confirm "battery OK" flag.
6. **Insert SDP1.** Pack 1 BMS wakes (you already have 12V on Pin 1). LilyGo sequences SSRs after a few seconds: precharge → +cont → −cont. Pack 1's HV+ terminal should now read its full pack voltage (~360V DC) at the connector.
7. **Verify Pack 1 voltage at the busbar tap** (the pack's HV cable is fitted but the TOMZN branch breaker is OFF — so the busbar itself is dead).
8. **Trip Pack 1 TOMZN ON.** Pack 1 is now on the busbar alone. Verify busbar voltage = pack 1 voltage.
9. **Trip Pack 1 TOMZN OFF.** Insert SDP2. Pack 2's internal contactors close (it gets the same SSR-driven coil signals from the daisy). Verify Pack 2 voltage at its branch breaker.
10. **Verify Pack 1 and Pack 2 are within 5V at their respective branch breakers.** If yes, trip both branch breakers ON. Packs 1 and 2 are now paralleled on the busbar.
11. **Repeat for Pack 3.** Verify within 5V, then trip ON.
12. **Master TOMZN still OFF.** Verify busbar = average pack voltage.
13. **FoxESS off, all DC disconnects OFF.** Wire FoxESS HV input. Verify polarity twice.
14. **Trip master TOMZN ON.** FoxESS sees DC. Bring FoxESS up. It self-tests against G99 (ROCOF + Vector Shift). If anything reads wrong, **press E-stop** — that drops Pin 1 on all 3 packs, all internal contactors open within 100 ms, the bus dies.

---

## 9. Safety chain (what happens when X fails)

| Fault | What opens the circuit |
|---|---|
| Single cell overvoltage in any pack | That pack's own BMS opens its internal contactors. Other 2 packs stay live. ⚠️ Note: with single-BMS-read mode, the LilyGo won't know about a Pack 2/3 internal fault — relies on the pack's own protection. |
| LilyGo crash / firmware fault | SSR drive signals go LOW → coil voltage drops → all contactors open. **Failsafe by design.** |
| 12V rail loss | Pin 1 BAT+IGN drops → BMSes go to sleep → contactors open. |
| Mains AC loss | DR-60-12 has hold-up ~50 ms; then 12V drops; then contactors open. The whole bus dies safely. |
| Person needs to disconnect NOW | **E-stop** — drops Pin 1 across all 3 packs simultaneously. |
| Service work | Pull SDPs (with HV gloves). Each SDP physically breaks the cell string. |
| Branch fault on one pack | That pack's TOMZN trips. Other 2 carry on. |
| Inverter fault | Master TOMZN trips manually OR FoxESS opens its internal DC contactor. |

---

## 10. The eBay HV harness in plain English

Each Nissan e-NV200 has a high-voltage heater (PTC element) that sits between the pack and the cabin. The factory wires the heater to the pack via a proprietary **Sumitomo orange HV connector** with integrated HVIL pilot pins. eBay sellers list these heater units complete with the cable + connector still attached.

You buy 3 of them. You bin (or scrap) the heater itself. You're left with **3 HV cables, each ~600 mm long, with the OEM Sumitomo plug on one end and bare copper on the other**. The Sumitomo plug-pluggs into the pack natively (no adapter needed). The bare end gets your M8 hex crimp ring lugs and bolts to the busbar / branch breaker.

Listing for reference: https://www.ebay.co.uk/itm/305824485941 (£89.10 each, 2 available — need to find a 3rd from a different listing or another seller).

---

## 11. What's still uncertain (don't block on these)

1. **FoxESS internal precharge** — if Solent Renewables confirms KH10.5 already precharges internally, you can skip pre-energising the bus through the inverter. This is a "nice to know" but **does not block the build** since pack-internal precharge handles the pack→busbar side regardless.
2. **G99 approval** (ref 260420-000198 with SSEN, submitted 20 Apr 2026). Can build and bench-test without it. Cannot **export** until approved.
3. **Earth bonding point** at the install location — needed before energising. Site visit / electrician sign-off.

---

## 12. Node-3 Software — Master Controller Architecture

The hardware (DALA/T-2CAN/FoxESS) does nothing intelligent on its own. The **Node-3 Python system on the Raspberry Pi 4B is the master controller** — it makes all commercial and operational decisions.

### Two-layer architecture

```
LAYER 1 — Hardware Abstraction (DALA on T-2CAN ESP32)
──────────────────────────────────────────────────────
  CAN-B (native) ← LEAF BMS (Pack 1) ← SOC, voltage, temperature
  DALA scales 1×24kWh → 3×72kWh (3P firmware mode)
  CAN-A (MCP add-on) → FoxESS BAT CAN port (battery emulation protocol)
  IO21/IO48/IO17 → SSR-04 → contactor coils on all 3 packs

  Result: FoxESS thinks it has a compatible 72kWh battery attached.
  DALA sequences contactors safely. No custom code needed here.

LAYER 2 — Intelligence / Master Control (Node-3 Python on Pi 4B)
──────────────────────────────────────────────────────────────────
  simulate.py         LP-optimal dispatch planner (scipy HiGHS)
                        → fetches Octopus Agile import/export prices
                        → solves LP over 96-slot (48h) lookahead
                        → writes dispatch_plan.json
                        → updates fleet_state.json, history.csv
                        → runs every 30 minutes at slot boundaries

  hardware_bridge.py  Hardware command sender (PRIMARY CONTROL PATH)
                        → reads current slot from dispatch_plan.json
                        → sends Modbus RTU to FoxESS via USB-RS485 dongle
                          (/dev/ttyUSB1, 9600 baud, slave addr 0xF7)
                          - REG 0x09D0: work mode (ForceChg / ForceDischg / SelfUse)
                          - REG 0x09D2: export power limit (W)
                        → falls back to Modbus TCP, FoxESS cloud API, or MQTT
                        → runs after every simulate.py slot

  server.py           Flask REST API + backtest engine
                        → serves dashboard.html operator portal on port 8585
                        → /api/plan, /api/node, /api/backtest, /api/hardware-status
                        → /api/set-mode: switches pre_commissioning / self_consumption / full_export
                        → background scheduler runs simulate.py + hardware_bridge.py
                          at each 30-min slot boundary automatically

  node3_config.py     Single source of truth for configurable parameters
                        → battery_kwh (72), import_kw (10), export_kw (6), min_soc_pct (10)
```

### Operational modes (set via /api/set-mode or hardware_bridge.py --set-mode)

| Mode | What happens |
|---|---|
| `pre_commissioning` | No Modbus commands sent. Simulation only. Safe during build/test. |
| `self_consumption` | Charges from grid, zero export. Use before G99 approval. |
| `full_export` | Full arbitrage — charge cheap, export expensive, up to G98/G99 cap. |

### Control path priority (hardware_bridge.py)

1. **Modbus RTU via USB-RS485** (`/dev/ttyUSB1`) — primary, local, no internet needed
2. **Modbus TCP** (FoxESS LAN IP) — secondary
3. **FoxESS Cloud API** (foxesscloud.com) — fallback only
4. **MQTT** (Pi → Mosquitto → T-2CAN) — alternative

### G99 export cap

G98 (current): 3.68 kW continuous (32A × 230V) — configurable via `export_kw` setting, hard-capped at 7.36 kW legal maximum.
G99 (pending ref 260420-000198): 11.5 kW continuous (50A × 230V) — fixed in code, represents a different physical grid connection, not a configurable parameter.

---

## 13. Files in this folder

| File | Status |
|---|---|
| **NODE3_DEFINITIVE.md** | ⭐ THIS FILE — single source of truth for hardware build |
| **hardware_bridge.py** | ⭐ Node-3 master controller — Modbus RTU to FoxESS |
| **simulate.py** | ⭐ LP dispatch planner — all trading decisions made here |
| **server.py** | Flask API + background scheduler + backtest engine |
| **node3_config.py** | Shared config (battery_kwh, import_kw, export_kw, min_soc_pct) |
| **dashboard.html** | Operator portal UI |
| NODE3_MASTER_CHARTER.md | Corporate/financial strategy |
| NODE3_Wiring_Schematic.md | Superseded — kept for reference |
| NODE3_Shopping_List.md | Superseded |
| NODE3_Complete_Shopping_List.md | Superseded |
| NODE3_Component_Guide.md | Still useful for "what does each part do" deep dives |

Once you're happy with this file, suggest archiving the four superseded files to a `/archive` subfolder so there's no ambiguity.
