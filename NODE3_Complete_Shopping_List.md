# NODE-3 Complete Shopping List
**For:** Matt Brander · **Date:** 19 May 2026 · **Status:** ESP32 flashed, batteries delivered, breakers + SSR + 36-pin already in hand.

> This is the definitive list. Everything below is needed to wire and commission NODE-3. Grouped by supplier so you can do this in ~6 orders.

---

## ✅ Already in hand — do not re-buy

- 3 × Nissan e-NV200 packs
- LilyGo T-2CAN ESP32, flashed (DALA firmware, Nissan + FoxESS profiles)
- Yazaki 7287-1065-30 pre-crimped 36-pin pigtail
- Spare bare 36-pin connector + crimp pins (backup)
- 3 × TOMZN DC1100V 2-pole 32A breakers (branch protection — one per pack)
- SSR-04 5DD-CN (will become ESP32 → contactor coil driver)
- IP66 enclosure (Rittal AE 1380.500 equivalent)
- Raspberry Pi 4
- 4G router (ZTE combo unit — prototype substitute for RUT240)
- Multimeter ⚠️ *verify CAT III 1000V rating before HV work — if not rated, hire one or buy a Brymen BM235 £80*

---

## ORDER 1 — ARC Components (long-lead item, ORDER FIRST)

| Item | Qty | £ | Link |
|---|---|---|---|
| Albright SW200-22 (12V coil, magnetic blowouts) — main DC contactor | 1 | ~£182 | [arc-components.com](https://www.arc-components.com/sw200-22-albright-single-acting-solenoid-contactor-12v-intermittent-5231.html) |

**Lead time 8–10 weeks** — every other item ships in days. Place this order today.

---

## ORDER 2 — RS Components UK (next-day delivery)

| Item | Qty | Search / Part No. |
|---|---|---|
| Anderson SB175 connector housings — red | 3 | RS [6120093](https://uk.rs-online.com/web/p/battery-connectors/6120093) (or eBay pair pack) |
| Anderson SB175 housings — black/grey | 3 | Same listing, different colour |
| Anderson 175A contacts for 35mm² cable | 12 | Search "SB175 contact 50mm²" |
| Phoenix Contact USLKG 6 earth busbar | 1 | RS part 1208420 |
| DIN rail (35mm × 1m length) | 1 | Search "DIN rail 35mm" |
| M4 / M6 cable glands for Rittal box | 6 mixed | Search "PG cable gland kit" |
| 120Ω 0.25W resistors | pack | Search "120 ohm resistor 100 pack" |
| Mornsun B2412S-1WR2 (isolated 12V DC-DC) | 1 | Search Mornsun or substitute with Recom RKZ-1212S |
| Inline fuse holder + 1A fuse (for Yazaki Pin 1 12V supply) | 1 | Standard automotive blade fuse |

Rough total: ~£100–130

---

## ORDER 3 — Farnell / CPC (specialist parts)

| Item | Qty | Search / Notes |
|---|---|---|
| Arcol HS50 or RH50 500Ω 50W aluminium-clad resistor (precharge) | 1 | Search "Arcol HS50 500R" or "Vishay LPS0600 500R 50W" |
| Omron G8P-1A4P or similar 12V SPST automotive relay (precharge) | 1 | 10A contacts is plenty |
| Tinned copper busbar 6×30mm × 200mm length | 2 | Search "tinned copper busbar"; or buy 1m and cut |
| M10 insulated busbar standoffs, 1000V rated | 4 | Search "busbar insulator standoff 1000V" |
| Logic-level optoisolator (PC817 or TLP785) for ESP32 → SSR drive | pack of 5 | Optional — SSR-04 5DD already has opto on input, may not need |

Rough total: ~£30–50

---

## ORDER 4 — Amazon UK (next-day, commodity bits)

| Item | Qty | Search / Link |
|---|---|---|
| Waveshare 2-CH Isolated CAN HAT (MCP2515 + SN65HVD230) | 1 | [Amazon B087RJ6XGG](https://www.amazon.co.uk/Waveshare-CAN-HAT-SN65HVD230-Protection/dp/B087RJ6XGG) |
| YHDC SCT-013-100 CT clamps | 2 | Search "YHDC SCT-013-100" |
| DS18B20 waterproof temperature probes | 6 (pack of 6 or 10) | Search "DS18B20 waterproof probe 6" |
| 4.7kΩ resistor (1-wire bus pull-up) | 1 (or pack) | Any resistor pack |
| DROK 12V → 5V buck converter, 3A | 1 | Search "DROK LM2596 12V to 5V" |
| Heat shrink kit (large diameters incl. 20mm, red + black) | 1 | Search "heat shrink tubing kit large" |
| Self-amalgamating tape — red roll | 1 | Scapa 2702 or Scotch 23 |
| Self-amalgamating tape — black roll | 1 | Same |
| Cable ties + cable labels | 1 set | Standard |
| Insulated screwdriver set, VDE 1000V rated | 1 | Wera, Wiha, or Knipex VDE set |
| Safety glasses (rated for arc) | 1 | Bolle or 3M |

Rough total: ~£140–180

---

## ORDER 5 — Eland Cables / 123electrical / local wholesaler (HV cable)

| Item | Qty | Notes |
|---|---|---|
| 35mm² orange H07RN-F rubber cable | 10 m roll | DC-rated 600V+, orange = HV/EV convention |
| 16mm² green/yellow earth cable | 5 m | Bonds Rittal box, pack chassis, inverter chassis |
| M8 tinned copper ring crimp lugs for 35mm² | 20 pack | Hex crimp pattern, NOT pliers-crimped |
| M6 ring lugs (for earth bonding to chassis points) | 10 pack | For 16mm² earth cable |

Suppliers:
- [Eland Cables](https://www.elandcables.com)
- [123electrical.co.uk](https://www.123electrical.co.uk)
- [TLC Direct](https://www.tlc-direct.co.uk)
- Local electrical wholesaler (Edwardes, Rexel, City Electrical Factors) — usually best price & next-day

Rough total: ~£120–160

---

## ORDER 6 — SafetyGloves.co.uk

| Item | Qty | £ | Link |
|---|---|---|---|
| Class 0 1000V insulating gloves (EN60903) | 1 pair | ~£30 | [safetygloves.co.uk](https://www.safetygloves.co.uk/class-0-electrical-gloves.html) |
| Leather oversleeves for Class 0 gloves | 1 pair | ~£20 | Same supplier |
| Insulation resistance tester (megger), 1000V — **hire don't buy if one-time** | 1 | £25/day hire from HSS / Brandon Hire | Search "Megger MIT400 hire" |

Rough total: ~£50 (excl. hired megger)

---

## ORDER 7 — Tool hire (NOT a purchase)

| Item | Where | Why |
|---|---|---|
| Hydraulic hex crimp tool for 35mm² lugs | HSS Hire, Brandon Hire, Speedy Hire | A bad crimp on 35mm² at 30A continuous = hot joint = fire. Pliers don't cut it. ~£25/day hire. |
| 1000V megger (insulation tester) | HSS Hire | One-shot test before energising. |

---

## ORDER 8 — Optional but recommended

| Item | Qty | Notes |
|---|---|---|
| Latching IP67 E-stop mushroom button, NC contact | 1 | RS or Toolstation. Schneider XALK178 or generic ~£15–40. Wires in series with contactor coil 12V — press = drop bus. |
| ABC fire extinguisher (or Class D for lithium-specific) | 1 | Mount near the install. Class D lithium-specific is best but ABC is acceptable. |
| HV warning signs / labels "DANGER 400V DC" | pack | RS, eBay, Amazon |
| Lockout-tagout tags (for SDP plugs while working) | 1 set | Standard industrial LOTO kit |

---

## Quick decision tree

**If the contactor needs to be ordered first (it does):** place ORDER 1 right now — it's the 8-week clock.

**While you wait:** ORDERS 2–6 will all arrive within a week. You can wire the entire LV/comms side, bench-test the ESP32 ↔ Nissan BMS ↔ FoxESS CAN chain, lay out the Rittal box, prepare all 35mm² cable runs with crimped lugs, and have everything ready so when the Albright arrives it's a 30-minute fit-and-test job.

**Email Solent Renewables NOW** to ask whether the FoxESS KH10.5 has internal precharge. If yes, skip the Arcol resistor and Omron relay (items in ORDER 3).

---

## Total estimated cash outlay (updated)

| Order | ~£ |
|---|---|
| 1. ARC (Albright) | 182 |
| 2. RS (connectors, busbar, DC-DC) | 115 |
| 3. Farnell (precharge, busbars) | 40 |
| 4. Amazon (CAN HAT, sensors, tape, screwdrivers) | 150 |
| 5. Cable wholesaler (HV cable, lugs) | 140 |
| 6. Safety (gloves) | 50 |
| 7. Tool hire (crimp + megger) | 50 |
| 8. E-stop + extinguisher + labels | 60–100 |
| **TOTAL** | **~£790–930** |

Saved ~£100–200 by reusing the enclosure, RPi, router, and DMM.

---

## Final sanity check before you click "buy"

1. ✅ IP66 enclosure — confirmed in hand
2. ✅ RPi 4 + 4G router (ZTE combo for prototype) — confirmed in hand
3. ⚠️ Multimeter — confirm it's **CAT III 1000V** rated. If it's CAT II 600V (typical hobby DMM), hire/buy a CAT III 1000V before HV work.
4. ☐ Has Solent Renewables confirmed FoxESS internal precharge?
5. ✅ TOMZN breakers — 2-pole, 1100V DC confirmed
6. ☐ Do you have an existing earth bonding point at the install location?

**On the ZTE router substitution:** fine for prototype, but two things to check — (a) does it have a free LAN port for the RPi (most ZTE combo units do), and (b) is signal/RSRP decent at the install location? RUT240 has better antennas; if the ZTE drops 4G frequently you'll lose telemetry. Worth a coverage test before committing.
