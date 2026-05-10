# NODE-3 "Slab" — Bespoke Steel Frame & Enclosure Build Specification
*Dovecote Systems Ltd — Node-3 BESS Build Brief*
*For fabricator, electrician, and commissioning engineer*

---

## 1. BATTERY PACK DIMENSIONS — Nissan e-NV200 24kWh (AZE0 Generation)

> ⚠️ **IMPORTANT — Frame sizing note**: Each pack occupies a large footprint. The original charter estimated 1.5m × 1.2m × 0.9m. The actual pack dimensions below will require a revised enclosure — see Section 2.

### Per-Pack Dimensions (3 packs total)

| Dimension | Value | Notes |
|-----------|-------|-------|
| Length (longest axis) | **1,578 mm** | Along vehicle fore-aft axis |
| Width | **1,102 mm** | Across vehicle width |
| Height (depth of pack) | **266 mm** | Thin flat slab format |
| Weight | **~262 kg** | Per pack (confirmed from EV database) |
| **Total stack weight (3×)** | **~786 kg** | + frame ~80kg = ~870kg total |
| Nominal voltage | **360 V DC** | 96 cells in series |
| Fully charged voltage | **~403 V DC** | Max |
| Capacity | **24 kWh** | Per pack / 72kWh total |

### Internal Module Layout
- 48 modules per pack
- Each module: **303 mm × 223 mm × 55 mm**, weight ~3.8 kg
- Modules are 2P2S grouped into the 96S chain
- Cell chemistry: NMC lithium-ion (Nissan/AESC cells)

### Mounting Holes (Vehicle Bolt Pattern)
- **16 mounting points** total per pack, arranged on perimeter flanges
- Bolt size: **M10** (14mm spanner AF)
- Torque: **45 N·m** (ZE0/AZE0 generation = same as e-NV200 24kWh)
- Flange width: ~20 mm, holes on approximately 300mm pitch along long sides, ~200mm pitch on short sides

> 📐 **For your fabricator**: Physically measure and template the actual bolt hole positions before cutting frame steel — exact positions vary slightly between manufacture dates. Make a paper template from the pack before welding.

### Terminals & Service Disconnect
- **High-voltage positive / negative terminals**: M8 stud posts, located at one end of the pack (short edge)
- Terminal spacing: ~150mm centre-to-centre
- **Service Disconnect Plug (SDP)**: orange lever-lock plug on top centre of pack. **Must be pulled before any work on the DC circuit.** This opens the pack mid-point at ~180V isolation.
- **12V BMS supply connector**: small low-voltage connector at same end as HV terminals — provides 12V power to wake the BMS and enable CAN communication
- **BMS / CAN connector**: **Yazaki 7287-1065-30 (36-pin)** — AZE0 generation (2013–2023). Carries CAN-H, CAN-L, cell temperature sensors, and 12V BMS supply. This is the connector used by the DALA Battery Emulator interface (see Section 7).

### Cooling System (e-NV200 Specific)
The e-NV200 packs use **active refrigerant cooling** (unlike Leaf which is passive air-cooled). Each pack has:
- A chilled aluminium cooling plate integrated under the module stack
- **Two refrigerant service ports** (high-side and low-side) at one short end of the pack
- Connected in the vehicle to the cabin A/C compressor circuit

---

## 2. REVISED ENCLOSURE DIMENSIONS

Three packs, when arranged most compactly, require:

### Recommended Orientation: Flat stacked, longest dimension horizontal

Pack orientation: lying flat, 1578mm along width of enclosure, 1102mm along depth, 266mm tall per pack.

**Three packs stacked:**

| Enclosure Axis | Required |
|----------------|---------|
| Width (W) | ≥ **1,640 mm** (1578 mm + 62mm frame clearance) |
| Depth (D) | ≥ **1,150 mm** (1102 mm + 48mm frame clearance) |
| Pack stack height | 3 × 266mm = **798 mm** |
| Total height with inverter above | ≥ **1,400 mm** (packs + 250mm inverter mounting bay + frame) |

> This is significantly larger than the original charter spec of 1.5m × 1.2m × 0.9m. The original dimensions assumed smaller packs. The frame must be engineered to this scale or the packs disassembled to module level and rebuilt into a slimmer form factor (see Section 9).

**Alternative: Side-by-side inline (for lower height)**

Three packs side by side in the 266mm dimension: 3 × 266 = 798mm deep, 1578mm wide, 1102mm tall. Same footprint issue — width still 1578mm.

**Structural note:** At ~870kg total weight on a concrete plinth, this is a significant civil engineering load. Plinth must be reinforced. Consult a structural engineer for the pad spec.

---

## 3. STEEL FRAME SPECIFICATION

### Material
- **3mm steel RHS (Rectangular Hollow Section)**, hot-dip galvanised or zinc-phosphate primed before powder coat
- Main structural members: **80 × 40 × 3mm RHS**
- Pack support ledges (bearing the 262kg pack weight): **80 × 80 × 5mm SHS** with welded M10 nut inserts at mounting hole pattern
- Frame finish: **RAL 9005 Jet Black powder coat** (Dovecote brand), 80µm DFT
- Lifting points: 4× M20 eye bolts at frame top corners (for crane/hiab)

### Battery Pack Cradle Design
- Each pack sits on two longitudinal steel ledges with rubber isolating pads (10mm shore 60A neoprene)
- Packs secured by M10 × 30mm bolts through the 16 flange points into weld-nuts in frame
- Electrical isolation between pack housing and frame: neoprene pad + nylon bolt sleeves in mounting holes
- Pack-to-pack electrical interconnects (parallel configuration) via 35mm² flexible welding cable + M8 copper busbars at HV terminals

### Wiring / Busbar Trays
- Dedicated cable tray runs inside frame for LV comms wiring (separate from HV runs)
- HV DC runs in **orange 35mm² cable** minimum, routed in separate metallic conduit, clearly labelled HV
- HV clearance to frame steelwork: minimum 50mm

---

## 4. HV DC POWER — INVERTER TO BATTERY ARRAY

### FoxESS KH10.5 HV Battery Interface
The KH10.5 uses a **proprietary FoxESS HV battery connector** (not standard MC4). It is supplied with the inverter. It carries:
- DC+ and DC− power conductors
- CAN bus communication lines (for the FoxESS HV2600 battery protocol)
- A 12V auxiliary supply line

**This connector cannot be replaced with a generic part — use the FoxESS-supplied connector.**

> ⚠️ **CAN voltage hazard**: FoxESS inverters can present up to **110V DC between the CAN pins and protective earth**. A **CAN isolator must be fitted** between the FoxESS battery port CAN lines and the DALA bridge board. Without it the bridge hardware will be destroyed on first power-up. See Section 7.

### Architecture for Three-Pack Array

```
FoxESS KH10.5 HV
       │
  [FoxESS battery cable]  ← proprietary connector, supplied with inverter
       │
  [HV Junction Box]  ← IP66 Rittal AE, mounted on frame
       │     │     │
   [Pack 1] [Pack 2] [Pack 3]   ← each via 35mm² H07RN-F + Anderson SB175 connector
```

CAN communication from one representative pack BMS → DALA LilyGo bridge → FoxESS KH10.5 (see Section 7).

### Junction Box Specification

| Component | Part | Notes |
|-----------|------|-------|
| Enclosure | **Rittal AE 1380.500**, 400×400×210mm, IP66 | Steel, DIN rail fitted |
| Internal busbars | 6mm × 30mm tinned copper bar, 500mm lengths | Two rails: positive + negative |
| Busbar standoffs | Phoenix Contact or Hager DIN-mount insulators | ×8, rated 1000V |
| Busbar end caps | Red (positive) / Black (negative) | Safety — cap all live busbar ends |
| Pack output connectors (×3) | **Anderson SB175, grey housing, 600VDC, 175A** | Industry standard for BESS at 400V DC. One cable-end + one panel-mount per pack run |
| Anderson contacts | **Anderson #1331G2** for 35mm²/2AWG wire | ×12 total (2 per connector end) |
| DC fusing | **Littelfuse KLDR125** (125A, 600VDC, Class J) per pack branch in **Eaton CH10J600** DIN holder | ×3 sets — fuse protects 35mm² cable |
| Main DC contactor | **Albright SW200-22**, 200A, 12V coil, **with magnetic blowouts** | SW200-22 variant specifically — blowouts are essential at 400V DC to extinguish arc on contact open |
| Earth busbar | Phoenix Contact USLKG 6, DIN mount | Common earth point inside JB |

> ⚠️ **Do not substitute a plain SW200 without magnetic blowouts** — at 400V DC the arc will not self-extinguish and is a fire risk.

### Cable Specification
- Inverter → Junction Box: FoxESS-supplied cable (use as-is, do not extend)
- Junction Box → each pack (×3): **35mm² orange flexible welding cable, H07RN-F**, max 1.5m per run, crimped with hydraulic tool
  - Pack terminal end: **35mm² M8 copper lug** (Klauke K35M8 or equivalent) bolted direct to pack HV M8 stud post
  - Junction box end: **Anderson SB175 cable-end housing + #1331G2 contacts**
- All HV cable rated ≥600V DC, orange sheathed, labelled **"DANGER — HIGH VOLTAGE 400V DC"** every 300mm with self-laminating cable markers
- Wrap all bolted HV terminal connections with **self-amalgamating tape** (red = positive, black = negative) after torquing

### Crimp Tool Requirement
35mm² cable lugs **cannot be hand-crimped**. A hydraulic crimper with 35mm² hexagonal die is required (Silverline 633824 or equivalent). Undersized crimps are a fire and arc-flash risk at 400V DC.

---

## 5. COOLING SYSTEM DESIGN

### Heat Load Analysis
At Node-3 operating profile (58kWh/day at 0.15C):
- Battery heat generation: ~150–250W across all 3 packs combined (low — 0.15C is gentle)
- FoxESS KH10.5 inverter heat: ~500W (rated by FoxESS, concentrated)
- **Total enclosure heat load: ~700–750W**

### Option A — Reuse e-NV200 Refrigerant Cooling (Preferred for pack longevity)
Each pack's integrated cooling plate is connected via refrigerant ports. You can retrofit a standalone cooling circuit:
- **Small automotive A/C compressor** (e.g., Sanden SD7H15, 12V/24V DC driven): ~800W cooling capacity — sufficient
- **Condenser + fan unit** (like an automotive mini-split evaporator): mounted on enclosure exterior
- Refrigerant: R134a circuit connecting to the 3 packs in parallel (same refrigerant as OEM)
- This keeps cells at 20–30°C in all UK weather — maximises cycle life to 3,000+ cycles

### Option B — Forced Air Cooling (Simpler, lower cost)
If refrigerant circuit is too complex:
- Two 200mm IP65 axial fans ducted through enclosure (draw air in at bottom, exhaust at top via IP66 baffled louvres)
- Internal air guided past pack surfaces via 2mm steel baffles
- A/C thermal cutout at 45°C cell temp triggers additional fan speed
- Adequate for UK climate given the low C-rate
- **Less suitable for summer heatwaves** — cell temperatures can reach 40°C+ which accelerates degradation

### Recommendation
**Option A for a permanent installation.** The e-NV200 packs already have the cooling plates built in — it's cheaper to use them than ignore them. A second-hand automotive A/C compressor unit costs £150–300 and will extend pack life significantly.

---

## 6. WATERPROOFING — IP65 SPECIFICATION

### Enclosure Shell
- **Steel outer shell**: 3mm mild steel, fully welded, continuously sealed (no bolt-on panels except access door)
- **Access door**: Full front swing-open door, piano hinge, 3-point compression latch
- **Door seal**: 12mm solid neoprene D-profile foam seal, compressed on close — achieves IP65
- **All cable penetrations**: IP68 cable glands minimum (Hawke International 501 series or equivalent), sized per cable OD
  - 35mm² H07RN-F OD ≈ 14–15mm → **M25 Hawke 501/453** glands
  - LV comms cables → M20 glands
- **Breather / pressure equalisation valve**: 1× Roxtec IP66 breather vent, prevents pressure differential from thermal cycling
- **Roof**: Integral sloped roof (5° minimum pitch) to shed water, with drip edge overhang
- **Base**: Sealed to concrete plinth using closed-cell foam strip + M10 anchor bolts into plinth, sealed with MS sealant

### Ventilation (for inverter section)
- The FoxESS inverter MUST have its own ventilation — it has integral fans that need airflow
- If inverter is inside the enclosure, route dedicated ventilation with IP66 inlet/outlet baffles
- Preferred: mount inverter in a separately ventilated compartment (partition within enclosure), isolated from battery bay

### Finishing for Weatherproofing
- External: RAL 9005 powder coat, 80µm, with Qualicoat-rated primer
- Internal: white 60µm epoxy powder coat (reflective, aids cell temperature monitoring)
- All welded seams: internal sealer coat before final powder coat
- Stainless steel hardware throughout (M10 304 SS bolts, washers, nuts)

---

## 7. INTEGRATED COMMS & ELECTRONICS

### Internal Electronics Bay
- Dedicated sub-enclosure within frame: **400 × 600mm DIN rail panel** on hinged bracket
- IP20 internally (main enclosure is IP65 — electronics bay inside gets ambient protection)

### BMS / Inverter CAN Bridge — DALA Battery Emulator

The **DALA Battery Emulator** (open source, [github.com/dalathegreat/Battery-Emulator](https://github.com/dalathegreat/Battery-Emulator)) is the confirmed working CAN bridge between the Nissan e-NV200 OEM BMS and the FoxESS KH10.5 inverter.

**How it works:**
- The Nissan OEM BMS in one representative pack remains intact and active (powered by the 12V rail)
- DALA firmware reads the Nissan BMS CAN bus (battery protocol) via the Yazaki 36-pin connector
- DALA re-transmits to the FoxESS KH10.5 in its native **FoxESS HV2600/ECS4100 CAN protocol**
- FoxESS KH10.5 receives SoC, voltage, temperature, and charge/discharge enable signals as if talking to a native FoxESS battery

**Hardware:**
- **LilyGo T-2CAN** ESP32-S3 board — dual CAN channels: Channel A → Nissan BMS, Channel B → FoxESS inverter port
- Firmware: flash DALA Battery-Emulator via PlatformIO (VSCode). Config: `BATTERY_TYPE = NISSAN_LEAF_BATTERY`, `INVERTER_PROTOCOL = FOXESS_CAN`, target board `LILYGO_T2CAN`

**Nissan BMS connector wiring (Yazaki 36-pin, AZE0 generation):**

| Pin | Signal | Connect to |
|-----|--------|-----------|
| Pin 1 | 12V supply | 12V rail (wakes BMS) |
| Pin 2 | GND | System GND |
| Pin 3 | CAN-H | LilyGo T-2CAN — CAN-A H |
| Pin 4 | CAN-L | LilyGo T-2CAN — CAN-A L |

> Verify pin positions against physical pack before wiring — positions are consistent across AZE0 production but confirm from a pack pinout diagram.

> ⚠️ **CAN isolator is mandatory on the FoxESS side** — FoxESS CAN pins can be 110V relative to PE. Fit a **Waveshare isolated CAN MCP2551 module** between LilyGo CAN-B and the FoxESS battery port CAN lines. Without it the LilyGo will be destroyed on first power-up.

### Components Table

| Component | Specification | Purpose |
|-----------|--------------|---------|
| CAN bridge | **LilyGo T-2CAN** (ESP32-S3, dual CAN) + DALA Battery-Emulator firmware | Nissan BMS CAN → FoxESS HV2600 protocol translation |
| CAN isolator | **Waveshare CAN MCP2551 isolated module** | Isolates FoxESS CAN high-voltage from LilyGo — mandatory |
| Nissan BMS connector | **Yazaki 7287-1065-30 pigtail harness (36-pin)** — pre-crimped flying leads | CAN-H/L + 12V wake to pack BMS |
| 12V→5V converter | DROK mini buck DIN rail, 12V→5V USB output | Powers LilyGo T-2CAN from 12V rail |
| DC-DC converter | 12V 5A isolated (e.g. Mornsun B2412S-1WR2) | 12V rail for DALA, contactors, comms |
| Raspberry Pi 4 | 4GB RAM | Telemetry → Node-3 portal |
| 4G/WiFi modem | Teltonika RUT240 (DIN rail) | Remote monitoring, API connectivity |
| CT clamps (×2) | YHDC SCT-013-100 | Import/export current monitoring |
| Temperature sensors | DS18B20 × 6 (2 per pack) | Pack temperature monitoring |
| Status LED strip | 12V RGBW LED, weatherproof | External status indicator |
| Emergency stop | IP67 panel-mount E-stop mushroom | Latching 24V NC, opens main contactor |
| RJ45 panel connectors | ×2 IP67 EtherCon | Portal / Ethernet access |

### Communication Architecture

```
Nissan e-NV200 OEM BMS (pack 1)
         │  CAN bus via Yazaki 36-pin
    [CAN isolator — Waveshare MCP2551]
         │
    LilyGo T-2CAN (DALA firmware)
         │  FoxESS HV2600 CAN protocol
    FoxESS KH10.5 HV inverter
         │
    [Also: LilyGo USB → Raspberry Pi]
                   │
              Teltonika 4G modem
                   │
             Node-3 Flask API
                   │
            GitHub (history.csv)
```

---

## 8. BRANDING

### "NODE-3 by Dovecote" Identity

| Element | Specification |
|---------|--------------|
| Primary colour | **RAL 9005 Jet Black** (shell + frame) |
| Accent colour | **RAL 6018 Yellow-Green** (door panel reveal, LED strip) or Dovecote green #3fb950 |
| Logo | **DOVECOTE** wordmark in reverse (white on black), 100mm high, centred on door |
| Node designation | **"N-3"** in 60mm stencil font below logo |
| Warning labels | Orange HV hazard labels (IEC 60417-6042) at all HV access points |
| Status window | 80 × 40mm polycarbonate window in door with internal RGB LED visible externally (green=charging, amber=idle, red=fault) |
| QR code plate | Stainless brushed plate, laser-engraved QR linking to portal URL — mounted beside access door |
| Rating plate | Stainless laser-engraved: company name, serial N-3-001, voltage 360V DC, capacity 72kWh, IP65, year |

---

## 9. ALTERNATIVE: MODULE-LEVEL REBUILD (Smaller Footprint)

If the full-pack configuration is impractical for the driveway footprint, the packs can be disassembled to module level and rebuilt into a custom form factor:

- 3 packs × 48 modules = **144 modules**
- Each module: 303 × 223 × 55mm, 3.8kg
- 144 modules arranged in a 6-deep × 24-wide wall: 6 × 55mm = 330mm deep, 24 × 223mm = 5,352mm wide — not ideal
- Better: 4 stacks of 36 modules each: 36 × 55mm = 1,980mm tall stack, each stack 303 × 223mm footprint — manageable

Module-level rebuild requires a more sophisticated BMS (each module is 2 cells = 7.6V nominal, 8 modules in series = 60.8V block, then parallel/series arrangement to hit 360V).

**This is a significant engineering project** — only recommended if the full-pack format is physically impossible on site.

---

## 10. PROCUREMENT LIST (Single Purchase Order)

### Structural / Enclosure

| Item | Spec | Source | Est. Cost |
|------|------|--------|-----------|
| 3mm steel RHS 80×40 | 6m lengths × 20 | Steel stockholder | ~£400 |
| 3mm steel sheet (enclosure panels) | 1500×3000mm sheets × 4 | Steel stockholder | ~£500 |
| RAL 9005 powder coat | By fabricator (labour + material) | Local fabricator | ~£300 |

### HV DC Power

| Item | Spec | Source | Est. Cost |
|------|------|--------|-----------|
| Rittal AE 1380.500 junction box | 400×400×210mm IP66 | Rittal / RS | ~£90 |
| **Albright SW200-22 DC contactor** | 200A, 12V coil, **with magnetic blowouts** — SW200-22 specifically | [ARC Components](https://www.arc-components.com) | ~£182 inc VAT |
| **Littelfuse KLDR125 fuse** (×3) | 125A, 600VDC, Class J | RS / Farnell | ~£25 each |
| **Eaton CH10J600 fuse holder** (×3) | DIN rail, 600VDC, Class J | RS / Farnell | ~£15 each |
| **Anderson SB175 housings, grey** (×6) | 600VDC, 175A, single-action | [splitcharge.co.uk](https://www.splitcharge.co.uk) / RS | ~£9 each |
| **Anderson #1331G2 contacts** (×12) | For 35mm²/2AWG wire | Same | ~£4 each |
| 35mm² orange flex cable H07RN-F | 10m roll | TLC Direct / Lapp | ~£120 |
| 35mm² M8 copper crimp lugs (×12) | Klauke K35M8 | RS / CPC | ~£1.20 each |
| 35mm² M10 copper crimp lugs (×6) | Klauke K35M10 | RS / CPC | ~£1.50 each |
| 6×30mm tinned copper busbar | 500mm lengths ×2 | Metallic Resources / eBay | ~£15 each |
| DIN busbar standoff insulators (×8) | Phoenix Contact or Hager, 35mm DIN | RS | ~£20 |
| Busbar end caps red/black (×8) | Match busbar width | RS | ~£8 |
| **Hydraulic cable lug crimper** | 16–400mm² with 35mm² hex die (Silverline 633824) | Machine Mart / Amazon | ~£45 |
| IP68 cable glands M25 (×8) | Hawke 501/453/UNIV/M25 — for 35mm² HV cable | RS | ~£6 each |
| IP68 cable glands M20 (×4) | Hawke 501/453/UNIV/M20 — for LV comms | RS | ~£4 each |
| IEC 60417-6042 HV hazard labels (×10) | Orange self-adhesive | RS / Amazon | ~£10 |
| "DANGER 400V DC" cable markers (×20) | Self-laminating, every 300mm on HV runs | RS / Brady | ~£12 |
| Self-amalgamating tape red (×2 rolls) | Terminal insulation, positive side | RS / Screwfix | ~£8 |
| Self-amalgamating tape black (×2 rolls) | Terminal insulation, negative side | RS / Screwfix | ~£8 |

### DALA CAN Bridge & BMS Electronics

| Item | Spec | Source | Est. Cost |
|------|------|--------|-----------|
| **LilyGo T-2CAN** ESP32-S3 board | Dual CAN — replaces Batrium entirely | AliExpress / Amazon | ~£28 |
| **Waveshare CAN MCP2551 isolated module** | CAN isolator — mandatory for FoxESS side | Amazon / Waveshare | ~£8 |
| **Yazaki 7287-1065-30 pigtail harness** | 36-pin BMS connector, pre-crimped flying leads, AZE0 generation | eBay — search "Nissan Leaf BMS connector 36 pin pigtail" | ~£18 |
| 12V→5V DIN buck converter (USB output) | Powers LilyGo from 12V rail | Amazon | ~£6 |

### Monitoring & Comms

| Item | Spec | Source | Est. Cost |
|------|------|--------|-----------|
| DC-DC converter | 12V 5A isolated (Mornsun B2412S-1WR2) | RS / Mornsun | ~£25 |
| Raspberry Pi 4 4GB + case | ×1 | CPC / Pi Shop | ~£85 |
| Teltonika RUT240 4G router | ×1 | Teltonika / Amazon | ~£110 |
| DS18B20 temp sensors + cable | ×6 (2 per pack) | Amazon / RS | ~£30 |
| CT clamps YHDC SCT-013-100 | ×2 | Amazon / RS | ~£20 |
| IP67 E-stop mushroom | ×1 | RS / Farnell | ~£25 |
| IP67 EtherCon RJ45 panel connectors | ×2 | RS | ~£20 |

### Cooling (Option A)

| Item | Spec | Source | Est. Cost |
|------|------|--------|-----------|
| Sanden SD7H15 A/C compressor (12V DC) | ×1 | eBay / specialist | ~£150–300 |
| Roxtec IP66 breather vent | ×2 | RS / Roxtec | ~£40 |

---

### Cost Summary

| Category | Est. Total |
|----------|-----------|
| Structural / enclosure (materials) | ~£1,200 |
| HV DC power (JB, contactor, fuses, connectors, cable, tools, labels) | ~£940 |
| DALA CAN bridge & BMS electronics | ~£60 |
| Monitoring & comms | ~£315 |
| Cooling (Option A) | ~£190 |
| **Est. Total Materials** | **~£2,705** |

> Fabrication labour (frame welding, panel work, powder coat finish): est. **£800–1,200** for a competent local fabricator with EV/industrial experience.

---

## DOCUMENT STATUS
*Version 2.0 — 21 April 2026*
*Corrections from v1.0:*
*— CAN bridge changed from Batrium WatchMon Core to DALA Battery Emulator on LilyGo T-2CAN (confirmed FoxESS KH CAN compatible)*
*— Pack connectors corrected from REMA MRC 320A (96V-rated forklift connector) to Anderson SB175 (600VDC rated — correct for 400V BESS)*
*— Albright contactor specified as SW200-22 with magnetic blowouts (essential at 400V DC — plain SW200 is unsuitable)*
*— Fuses updated to Littelfuse KLDR125 / Eaton CH10J600 (Class J, 600VDC, confirmed UK availability)*
*— CAN isolator added as mandatory safety item between FoxESS port and DALA board*
*— Yazaki 36-pin connector (7287-1065-30) confirmed as AZE0 BMS connector*
*For review by fabricator and commissioning electrician before cutting steel.*
*Nissan e-NV200 pack mounting hole template must be made from physical packs before frame fabrication.*
