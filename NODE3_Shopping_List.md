# NODE-3 Shopping List — Live Links
**Generated:** 2026-05-19 · For: Matt Brander · System: 3× Nissan e-NV200 packs → FoxESS KH10.5

> ⚠️ **Albright SW200-22 has an 8–10 week lead time at ARC Components.** This is your binding constraint. Order it FIRST, today. Everything else can be sourced in parallel. You can wire and bench-test the LV/comms side without it; you cannot energise the HV bus without it.

---

## TIER 1 — Critical safety / long lead

| # | Item | Where | Approx £ | Notes |
|---|---|---|---|---|
| 1 | **Albright SW200-22** (12V coil, magnetic blowouts) | [ARC Components](https://www.arc-components.com/sw200-22-albright-single-acting-solenoid-contactor-12v-intermittent-5231.html) — pre-order, 8–10 wk lead | ~£182 | Order TODAY. If lead time intolerable: try [EV Drives (US, faster ship)](https://evdrives.com/product/albright-sw200-style-main-contactor-12v-24v-36v-48v-64v-72v/), or eBay for [genuine used Albright](https://www.ebay.com/itm/126498464745). Avoid "style" / "compatible" — buy genuine only. |
| 2 | **Class 0 1000V insulating gloves** + leather overglove | [SafetyGloves.co.uk](https://www.safetygloves.co.uk/class-0-electrical-gloves.html) from £29.16; [Reece Safety](https://www.reecesafety.co.uk/class-0-1000v-electrical-insulation-gloves.html); [EV Safety](https://evsafety.co.uk/products/class-0-electrical-insulating-gloves) | ~£40–80 | EN60903 certified. Buy leather oversleeves too — Class 0 alone tears easily. |
| 3 | **CAT III 1000V DMM** (if you don't already own one) | Fluke 117 / 87V from [RS Components](https://uk.rs-online.com), [Farnell](https://uk.farnell.com), Toolstation; budget option: Brymen BM235 | £80–350 | Cheaper DMMs are CAT II 600V — not safe at this DC voltage. |

## TIER 2 — HV side, needed before energising

| # | Item | Where | Approx £ | Notes |
|---|---|---|---|---|
| 4 | **Anderson SB175 connectors** ×3 pairs (6 housings + 6 contacts for 35mm²) | [RS Online UK](https://uk.rs-online.com/web/p/battery-connectors/6120093) (next-day); [Fourby](https://fourby.co.uk/product/anderson-connector-sb-175a-600v/); [SplitCharge](https://www.splitcharge.co.uk/product/anderson-connectior-175amp-600v-grey-plug-cable-terminal-battery-power/) | ~£9–12 each housing, contacts extra | Buy red AND black housings so + and − can't be swapped. |
| 5 | **Rittal AE 1380.500** IP66 enclosure (380×380×210) | [Parmley Graham](https://www.parmley-graham.co.uk/1380500) £87.22; [Farnell](https://uk.farnell.com/rittal/ae1380/cabinet-380x380x210mm/dp/1198829); [Radward](https://www.radward.co.uk/rittal/ae-1380-500) | ~£87–110 | AE 1380.500 is now superseded by 1380.000 — functionally identical, either is fine. |
| 6 | **Precharge resistor** 470Ω or 500Ω, 50W aluminium-housed | [Farnell](https://uk.farnell.com) search "Arcol HS50 500R" or "RH50 470R"; [RS Components](https://uk.rs-online.com); CPC | ~£8–15 | Wirewound, aluminium clad, fix to a chunk of ali for heatsinking. |
| 7 | **Precharge relay** — small SPST 12V coil, 10A contacts | Any standard automotive relay; [Farnell Omron G8P-1A4P](https://uk.farnell.com); eBay | ~£4 | Only carries current for 5–10 sec at a time through the resistor. |
| 8 | **120Ω 0.25W resistors ×5** (CAN termination) | Pack of 100 from [Amazon UK](https://www.amazon.co.uk), Farnell, RS | ~£3 | Cheap; buy a strip not a single. |
| 9 | **35mm² orange H07RN-F** rubber cable (5m positive, 5m negative — buy 10m roll) | [Eland Cables](https://www.elandcables.com), [Batt+, BatteryHookup](https://www.batteryhookup.co.uk); [123electrical](https://www.123electrical.co.uk) | ~£10–14/m | DC-rated 600V+, orange = standard EV/HV colour code. |
| 10 | **M8 ring crimp lugs** for 35mm² ×20 | RS / Farnell / [CableLugsDirect](https://www.cablelugsdirect.co.uk) | ~£20 pack | Tinned copper, hex crimp pattern. |
| 11 | **Hex crimp die set for 35mm² lugs** (or hire) | TLC Direct, eBay (Knipex / Klauke clone); HSS Hire if one-time | ~£60 to buy, ~£25/day hire | Pliers will give you a bad crimp = fire risk. Don't substitute. |
| 12 | **Earth busbar** — Phoenix Contact USLKG 6 (DIN-rail PE block) ×1 + green/yellow 16mm² earth cable | [RS](https://uk.rs-online.com) part 1208420; Farnell | ~£8 busbar + £4/m cable | |
| 13 | **Self-amalgamating tape** — red and black, plus general black | Screwfix / Toolstation / Amazon (Scapa 2702 or 3M Scotch 23) | ~£8/roll | For wrapping crimped HV terminations. |

## TIER 3 — Comms / LV / ESP32 side

| # | Item | Where | Approx £ | Notes |
|---|---|---|---|---|
| 14 | **LilyGo T-2CAN** (ESP32-S3, dual CAN) | [Banggood UK](https://uk.banggood.com/LILYGO-T-2CAN-ESP32-S3-WiFi-Bluetooth-Development-Board-16MB-Flash-8MB-PSRAM-Stand-Alone-CAN-Controller-QWIIC-Interface-Compatible-IoT-Automotive-Solution-Wireless-Module-p-2043732.html) ~$30; [OpenELAB](https://openelab.io/products/lilygo-t-2can-esp32s3-qwiic) (24mo UK warranty); [official LilyGo](https://lilygo.cc/en-us/products/t-2can) | ~£25–28 | The ONE ESP32 the design calls for. Buy a spare. |
| 15 | **Waveshare 2-CH Isolated CAN HAT** (MCP2515 + SN65HVD230, isolated) | [Amazon UK B087RJ6XGG](https://www.amazon.co.uk/Waveshare-CAN-HAT-SN65HVD230-Protection/dp/B087RJ6XGG); [Waveshare direct](https://www.waveshare.com/2-ch-can-hat.htm) | ~£25 | Made for RPi but the isolated CAN channels are what you want. Use one of its channels on the FoxESS side. |
| 16 | **Mornsun B2412S-1WR2** isolated 12V DC-DC | [Rapid Electronics](https://www.rapidonline.com) (search Mornsun); compare on [Octopart](https://octopart.com/b2412s-1wr2-mornsun-28156381). Newer B2412S-1WR3G is a drop-in upgrade. | ~£8–12 | If your input rail is already 12V, you can substitute B1212S-1WR2 (12→12 isolated) instead. |
| 17 | **DROK 12V→5V buck** (for ESP32 5V rail) | Amazon UK, eBay — generic LM2596 or DROK 12-24→5V module | ~£5 | Standard kit. |
| 18 | **Raspberry Pi 4 4GB** (if not already in hand) | [The Pi Hut](https://thepihut.com), [Pimoroni](https://shop.pimoroni.com), Farnell | ~£70–85 | Per SLAB spec. |
| 19 | **Teltonika RUT240** 4G router (if not already in hand) | [4Gltemall](https://www.4gltemall.com), [Teltonika UK distributors](https://teltonika-networks.com) | ~£110 | Per SLAB spec. |
| 20 | **6 × DS18B20** 1-wire temperature sensors (waterproof probes) | Amazon UK 6-pack; [The Pi Hut](https://thepihut.com); CPC | ~£8 pack of 6 | 2 per pack. |
| 21 | **4.7 kΩ pull-up resistor** for 1-wire bus | Already in any resistor pack | <£1 | |
| 22 | **2 × YHDC SCT-013-100** CT clamps | [Amazon UK](https://www.amazon.co.uk) — search "YHDC SCT-013-100"; [OpenEnergyMonitor shop](https://shop.openenergymonitor.com) | ~£10–15 each | Voltage-output 50mA / 100A version preferred; or 0–1V output. |
| 23 | **Latching IP67 E-stop mushroom button (NC)** | [RS Components](https://uk.rs-online.com) — search "Allen-Bradley 800FM-MT44XM01" or "Schneider XALK178"; Toolstation has cheaper generics | ~£15–40 | Must be NC (normally-closed). Wire in series with contactor coil 12V supply — pressing it drops the contactor. |

## TIER 4 — Already on hand (verify before fitting)

| Item | Status |
|---|---|
| 3× Nissan e-NV200 packs | ✅ (Bill of Sale 28 Apr 2026) |
| Yazaki 36-pin pre-crimped pigtail | ✅ |
| Spare 36-pin bare connector + crimps | ✅ (keep as backup) |
| TOMZN TOPV-32 ×3 DC breakers | ⚠️ Confirm **2-pole, 550V DC, 10kA**. If 1P, do not fit. |
| SSR-04 5DD-CN | ❌ Do not use as main contactor. Repurpose for low-voltage switching only. |

---

## Total cash outlay (rough)

| Tier | Total |
|---|---|
| Tier 1 (safety + long-lead) | ~£250–310 |
| Tier 2 (HV side) | ~£280–360 |
| Tier 3 (comms / LV) | ~£260–320 |
| **Grand total (excl. Pi/RUT240 if already owned)** | **~£790–990** |

Aligns with SLAB Build Spec §10 estimate of ~£940 materials.

---

## Order-today list (just the urgent stuff)

1. Albright SW200-22 — ARC Components (kicks off the 8–10 wk clock)
2. Class 0 1000V gloves — SafetyGloves.co.uk
3. CAT III 1000V DMM — if you don't already own one
4. Rittal AE 1380.500 — Parmley Graham

Everything else can ship from Amazon/RS/Farnell on next-day, so you can decide tomorrow.

---

## Things I cannot give you a link to (need a human or a phone call)

- **FoxESS internal precharge confirmation.** Email Solent Renewables (the installer who'd handle the G99 commissioning). If FoxESS handles precharge internally, items 6 + 7 are unnecessary.
- **G99 approval letter** (ref 260420-000198 submitted 20 Apr 2026). Until SSEN approves, you can build but not export.
