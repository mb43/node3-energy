# NODE-3 Component Guide & Full Connectivity
**For:** Matt Brander · **Date:** 19 May 2026 · **System:** 3× Nissan e-NV200 (360V parallel) → FoxESS KH10.5 → grid, with LilyGo T-2CAN BMS bridge

This document explains what every part does, where it sits, and how it connects to everything else. Four signal paths run through the system simultaneously: **HV power**, **LV control**, **comms (CAN)**, and **sensing/telemetry**.

---

## 1. The four paths at a glance

```
        ┌──────────────────────────────────────────────────────────────┐
        │                                                              │
        │   HV POWER ───────────────────────────────────────────────►  │   Energy: pack → inverter → grid
        │      (orange 35mm² H07RN-F, 400V DC, 30A nominal)            │
        │                                                              │
        │   LV CONTROL ◄─── ESP32 GPIO ─── E-stop ───► contactor coil  │   Decisions: ESP32 says yes/no, coil opens/closes
        │      (12V DC isolated rail, mA-level)                        │
        │                                                              │
        │   CAN COMMS ◄──── Nissan BMS ──── ESP32 ──── FoxESS ────►    │   Conversation: "SoC 87%, OK to charge at 3kW"
        │      (CAN 2.0, twisted pair, 500 kbps)                       │
        │                                                              │
        │   SENSING ◄──── temp/current/voltage ──── RPi ──── 4G ────►  │   Observation: logs, portal, alerts
        │      (1-wire, analogue, USB, ethernet)                       │
        │                                                              │
        └──────────────────────────────────────────────────────────────┘
```

The HV power path is the muscle. The other three exist to control it safely and tell you what it's doing.

---

## 2. HV POWER PATH — energy flow

### 2.1 Nissan e-NV200 24kWh packs ×3
**What it does:** Stores the energy. Each pack is 48 cells × 7.5V = 360V DC nominal, ~67Ah, 24kWh.
**Where it sits:** Three of them — wherever you've sited them (typically a ventilated outbuilding or steel container). Each is ~262 kg.
**Wired to:** Its own SB175 connector pair on top. Internally the pack has its own BMS (one of which you'll use), HV+ and HV− terminals, and a Yazaki 36-pin signal connector.

### 2.2 Service Disconnect Plug (SDP) — already part of each pack
**What it does:** Splits the pack in half mechanically. With the SDP pulled, the pack's internal HV bus is broken — each half is ~180V max, much safer to work on. Pull this BEFORE touching anything.
**Where it sits:** Orange lever-lock on top of each pack.
**Wired to:** Internal pack circuitry only. Yours to operate manually. **Pull all 3 before any wiring or maintenance — keep them in your pocket so nobody can re-insert them.**

### 2.3 Anderson SB175 connector pair (per pack)
**What it does:** Quick-disconnect for the pack's HV cables. Rated 175A continuous at 600VDC. Lets you disconnect a pack from the bus without unscrewing M8 lugs.
**Where it sits:** Between each pack's HV terminals and the cable run to the junction box.
**Wired to:** Pack + and − terminals via 35mm² lugs on one side; 35mm² cable to the Rittal junction box on the other side. **Use red and grey/black housings to enforce + / − polarity.**

### 2.4 TOMZN DC1100V 2-pole 32A breakers ×3
**What it does:** Branch overcurrent protection. If a pack tries to deliver fault current (cable short, contactor weld, internal pack fault) the breaker trips and isolates that branch — protecting the cable, the other packs, and you.
**Where it sits:** Inside the Rittal junction box, on DIN rail. One breaker per pack branch.
**Wired to:** + leg through pole 1, − leg through pole 2. **Single lever = both legs disconnect simultaneously.** Observe the polarity arrows on the body — DC breakers are direction-sensitive.

### 2.5 Tinned copper busbars (+VE and −VE rails)
**What it does:** Common connection point. All three pack branches land here after their breakers, and the contactor + precharge tap off from here.
**Where it sits:** Inside the Rittal junction box, on 1000V insulated standoffs, away from the metal walls.
**Wired to:** Three breaker outputs feed in (+ bar and − bar separate). Contactor and precharge tap off the + bar; − bar goes straight through to the inverter's HV− terminal.

### 2.6 Precharge resistor (500Ω 50W) + small 12V SPST relay
**What it does:** Solves an inrush problem. The FoxESS inverter has large input capacitors. Slamming 400V onto them directly draws hundreds of amps for milliseconds — pits the Albright's contacts and shortens its life. The precharge circuit briefly connects the bus through a 500Ω resistor instead, gently filling the inverter caps over ~5 seconds. Once the inverter side voltage matches the pack side, the main contactor closes and the precharge relay opens.
**Where it sits:** Inside the Rittal box, mounted in **parallel** with the Albright contactor — both ends connected across the contactor's main terminals.
**Wired to:** + bus → 500Ω resistor → SPST relay contact → inverter HV+ side of the Albright. The relay's coil is driven by an ESP32 GPIO via a small driver (or even the SSR). **You may not need this if FoxESS handles precharge internally — confirm with Solent Renewables before fitting.**

### 2.7 Albright SW200-22 main DC contactor
**What it does:** The single most important safety device in the system. Connects/disconnects the entire battery bus from the inverter. Designed to break 400V DC under load — its magnetic blowouts physically stretch the arc away from the contacts so it extinguishes. When the 12V coil drops, the contacts open under spring force — fails OPEN, which is what you want.
**Where it sits:** Inside the Rittal box, on a mounting plate, with airflow around it.
**Wired to:**
  - Main terminals: + bus → contactor → inverter HV+ (35mm² cable both sides)
  - Coil terminals: 12V supply through the E-stop NC contact, then through the SSR (driven by ESP32 GPIO)
  - The precharge circuit sits across the main terminals

### 2.8 FoxESS KH10.5 HV hybrid inverter
**What it does:** Converts DC battery voltage to 230V AC for the grid, and bi-directionally — also takes grid AC and charges the batteries when there's surplus or cheap import (Octopus Agile windows). Handles G99 grid protection internally (ROCOF + Vector Shift anti-islanding).
**Where it sits:** Wall-mounted near the consumer unit. Needs ventilation — dissipates ~500W under load.
**Wired to:**
  - DC IN: FoxESS proprietary HV connector → 35mm² to Rittal box (the contactor's other side)
  - AC OUT: through a 32A 2-pole MCB into your consumer unit → grid
  - CAN port: to the Waveshare isolated CAN module (NOT direct to the ESP32 — see §4.4)
  - Earth: bonded to the same earth busbar as the Rittal box and pack chassis

### 2.9 AC consumer unit → DNO meter → grid
**What it does:** Standard household AC distribution. Your installed CU should already exist. Add a dedicated 32A 2-pole MCB for the inverter's AC connection.
**Where it sits:** Existing CU location.
**Wired to:** Inverter AC OUT → 32A MCB → main busbar → meter → DNO supply. The two CT clamps go around the meter tails to measure import/export.

---

## 3. LV CONTROL PATH — decisions and actuation

The control path is what tells the contactor when to close, when to open, and protects against single-point failures.

### 3.1 12V DC supply (mains PSU, ~5A DIN-rail unit)
**What it does:** Powers everything on the LV side. Mean Well DR-60-12 or similar — 60W, DIN-rail, 230V AC in → 12V DC out.
**Where it sits:** Inside the Rittal box (or in a separate small enclosure if you want to keep mains AC out of the HV box).
**Wired to:** Feeds the Mornsun DC-DC, the contactor coil rail (via E-stop), the Nissan BMS wake (Yazaki Pin 1), and the precharge relay coil.

### 3.2 Mornsun B2412S-1WR2 isolated DC-DC
**What it does:** Provides an isolated 12V rail for sensitive electronics (the ESP32 and the BMS). "Isolated" means there's no electrical connection between input and output grounds — protects the ESP32 and BMS from any noise or fault on the contactor coil side.
**Where it sits:** Inside the Rittal box, on the LV side.
**Wired to:** Input: 12V from main PSU. Output: 12V isolated → feeds ESP32 VIN (via DROK buck → 5V), and Yazaki Pin 1 (via 1A fuse) to wake the Nissan BMS.

### 3.3 E-stop button (latching IP67 mushroom, NC contact)
**What it does:** Your panic button. Press it = mechanically breaks the contactor coil's 12V supply = contactor drops open = bus is dead. The latching action means once pressed it stays pressed until twisted to release — prevents accidental re-energising during an incident.
**Where it sits:** Wall-mounted somewhere immediately accessible from where you'd be working — outside the Rittal box, at chest height, unobstructed.
**Wired to:** In series with the contactor coil's 12V supply line. NC means the contact is closed during normal operation; pressing the button opens it.

### 3.4 SSR-04 5DD-CN solid-state relay (your existing AliExpress part)
**What it does:** Acts as a logic-level amplifier. The ESP32's GPIO pin can only output 3.3V at a few mA — nowhere near enough to energise the Albright's 12V/1A coil. The SSR sits between them: ESP32 GPIO drives the SSR's input optocoupler (mA-level), and the SSR's output passes the 12V coil current through.
**Where it sits:** Inside the Rittal box, between the ESP32 board and the Albright coil terminals.
**Wired to:** Input (logic side): ESP32 GPIO pin + ground reference. Output (power side): in series with the 12V → E-stop → coil chain.

### 3.5 Small 12V SPST automotive relay (precharge driver)
**What it does:** Drives the precharge resistor circuit. Short-duty cycle (5–10 seconds at startup, sometimes shutdown).
**Where it sits:** Inside the Rittal box, on the HV side near the precharge resistor.
**Wired to:** Coil: ESP32 GPIO (via SSR or transistor) + 12V. Contacts: in series with the 500Ω resistor across the Albright's main terminals.

---

## 4. COMMS PATH — the CAN conversation

The CAN bus is how the Nissan BMS, the ESP32, and the FoxESS inverter talk to each other. It's two separate buses — Nissan-side (CAN-A) and FoxESS-side (CAN-B) — because they speak different dialects and run at different common-mode voltages.

### 4.1 Yazaki 7287-1065-30 36-pin connector (your pre-crimped pigtail)
**What it does:** Physical interface to the Nissan e-NV200 pack's onboard signals. Has 36 pins total; you only use 4. The rest carry cell-tap voltages and NTC thermistor data that DALA firmware doesn't need.
**Where it sits:** Plugs into the signal port on **Pack 1** (the pack whose internal BMS you're keeping live). Packs 2 and 3 don't need their BMS active — their cell-level monitoring is sacrificed for simplicity; DALA assumes all packs are roughly balanced because they're paralleled.
**Wired to:**
  - Pin 1 (12V): from Mornsun isolated rail, through 1A inline fuse → wakes the Nissan BMS chip
  - Pin 2 (GND): to the LV ground bar (note: this is the *isolated* ground from the Mornsun output, not the main 12V ground)
  - Pin 3 (CAN-H): to LilyGo T-2CAN, CAN-A H pin
  - Pin 4 (CAN-L): to LilyGo T-2CAN, CAN-A L pin
  - Pins 5–36: **leave unconnected**. Heatshrink each one individually, bundle them, label "DO NOT TOUCH — cell taps live at pack potential" (they can sit at 360V relative to chassis when the pack is alive).

### 4.2 Nissan e-NV200 OEM BMS (inside Pack 1, factory-installed)
**What it does:** Monitors all 48 cells inside its own pack — voltage, temperature, balance current — and broadcasts the data on the Nissan CAN bus. DALA firmware reads this data and uses it to control charge/discharge limits.
**Where it sits:** Inside Pack 1, factory installed. You don't touch it; you just wake it (12V on Pin 1) and listen to its CAN messages.
**Wired to:** Internally to all the cells; externally to the Yazaki connector.

### 4.3 LilyGo T-2CAN (your flashed ESP32)
**What it does:** The brain. Runs DALA Battery-Emulator firmware:
  - **Reads** Nissan CAN frames on CAN-A → extracts SoC, voltage, temp, current limits
  - **Translates** into FoxESS HV2600 protocol
  - **Writes** these as FoxESS-format CAN frames on CAN-B → inverter believes it's talking to a FoxESS battery
  - **Drives** the contactor coil via GPIO → SSR → coil (closes the bus when conditions are safe; opens on fault)
  - **Drives** the precharge relay via GPIO (small SPST relay)
  - **Sends telemetry** to the RPi via USB serial (so the Pi can log/display it)
**Where it sits:** Inside the Rittal box, ideally in its own small enclosure or on a stand-off panel away from HV terminations. Powered via USB-C (5V from DROK buck off the Mornsun isolated 12V rail).
**Wired to:**
  - VIN/USB: 5V from DROK buck
  - GND: isolated ground
  - CAN-A H/L: Yazaki pins 3/4 (twisted pair, ideally CAT5 colour pairs)
  - CAN-B H/L: Waveshare isolated CAN module logic-side pins
  - GPIO (e.g. IO4): SSR input (contactor coil drive)
  - GPIO (e.g. IO5): E-stop status monitor (so firmware knows when button is pressed)
  - GPIO (e.g. IO6): precharge relay drive
  - USB to RPi 4: telemetry / firmware updates

### 4.4 Waveshare 2-CH Isolated CAN HAT (one channel used)
**What it does:** Galvanic isolation between the ESP32 and the FoxESS CAN port. The FoxESS HV battery CAN can sit at **±110V DC to protective earth** because it shares ground reference with the HV bus. If you wired the ESP32 directly to the FoxESS CAN, that voltage would punch straight through the ESP32 and into your USB cable — destroying the ESP32, the RPi, and potentially you. The isolator has an internal transformer and optocouplers — data passes, voltage does not.
**Where it sits:** Inside the Rittal box, mounted between the ESP32 and the cable that runs to the inverter.
**Wired to:**
  - Logic side: powered from ESP32 5V/GND, CAN-H/L to ESP32 CAN-B pins
  - Isolated side: powered from a SEPARATE small 5V source (a second DROK buck off the 12V), CAN-H/L runs to the FoxESS CAN port via twisted pair
  - **No ground connection between the two sides — that's the whole point.**

### 4.5 120Ω CAN termination resistors ×3
**What it does:** Stops electrical reflections on the CAN bus. Without terminators, signal bounces off the end of the cable like an echo in a tunnel and corrupts data.
**Where it sits:**
  - One across CAN-H/L at the **LilyGo end of CAN-A** (the Nissan BMS already has one at its end of the bus, so just one more at your end)
  - One across CAN-H/L at the **LilyGo end of CAN-B** (between LilyGo and Waveshare logic side)
  - One across CAN-H/L at the **FoxESS end** of the cable from the Waveshare isolated side (closer to the inverter)
**Wired to:** Just soldered across the H and L pins at each termination point.

### 4.6 FoxESS CAN port
**What it does:** Receives BMS data, controls charge/discharge rate accordingly. Without seeing a battery on this port, the inverter won't operate.
**Where it sits:** On the inverter housing — usually a small RJ-style connector or terminal block. Check the FoxESS manual for pinout.
**Wired to:** Waveshare isolated CAN module's isolated-side CAN-H/L via shielded twisted pair (CAT5 with shield earthed at one end only).

---

## 5. SENSING / TELEMETRY PATH

### 5.1 6 × DS18B20 waterproof temperature probes
**What it does:** Monitors pack temperature. Two per pack (one on the cool side, one on the warm side / near terminals). 1-wire protocol — all six share a single data bus.
**Where it sits:** Stick-on or strapped to each pack body.
**Wired to:** All six in parallel on the 1-wire bus → RPi GPIO 4 (default 1-wire pin) with a 4.7kΩ pull-up to 3.3V. Each sensor has 3 wires: VCC (3.3V), GND, DATA.

### 5.2 2 × YHDC SCT-013-100 CT clamps
**What it does:** Measures AC current at the meter tails — one on the import leg, one on the export leg — so the RPi can log net import/export per half-hour slot (matches Octopus Agile billing).
**Where it sits:** Clamped around the live conductor at the consumer unit / meter tails.
**Wired to:** Output to the RPi via an ADC (MCP3008 SPI chip, or a small ADS1115 I2C HAT) with a burden resistor and bias network to centre the AC signal at ~1.65V.

### 5.3 Raspberry Pi 4 (your existing one)
**What it does:** Telemetry brain. Reads temp sensors, CT clamps, USB serial from the ESP32. Logs to history.csv. Runs the Flask portal (server.py) so you can hit a web page showing current state. Talks to the Octopus API for energy prices and to your MQTT broker if you have one.
**Where it sits:** Inside or near the Rittal box, on DIN rail or a shelf. Needs decent airflow.
**Wired to:**
  - Power: 5V/3A USB-C from a dedicated PSU (not off the contactor 12V — keep clean)
  - USB-A: to LilyGo T-2CAN (telemetry)
  - GPIO: 1-wire bus → DS18B20s
  - SPI or I2C: to ADC for CT clamps
  - Ethernet: to ZTE router

### 5.4 ZTE 4G router (your prototype substitute for RUT240)
**What it does:** Provides internet for the RPi → Octopus API calls, remote portal access, any MQTT brokering.
**Where it sits:** Inside the Rittal box, or in a separate weatherproof location for better signal.
**Wired to:** RPi via Ethernet; powered separately (usually 12V DC barrel jack).

---

## 6. EARTH / PROTECTIVE BONDING

This is the layer everyone forgets and it's the layer that saves your life when something goes wrong.

### 6.1 Phoenix Contact USLKG 6 earth busbar
**What it does:** Single-point earth — every metal chassis that could become live in a fault bonds back to here, and from here a single heavy earth cable runs to your consumer unit's main earth terminal.
**Where it sits:** On the DIN rail inside the Rittal box, painted green/yellow or labelled "PE".
**Wired to:**
  - Rittal box body (M6 earth stud on the box)
  - All three pack chassis (via 16mm² green/yellow leads, one per pack)
  - FoxESS inverter chassis (its earth stud)
  - Consumer unit main earth terminal (heavy 16mm² run)

### 6.2 Cable / lug colour discipline
- HV+ wrap: **red** self-amalgamating
- HV− wrap: **black** self-amalgamating
- Earth: **green/yellow** insulation, always
- Every HV cable end labelled "DANGER 400V DC"

---

## 7. Physical layout

### 7.1 Inside the Rittal box (top-down view)
```
┌──────────────────────────────────────────────────────────┐
│  ┌── DIN RAIL ─────────────────────────────────────┐     │
│  │ [TOMZN1] [TOMZN2] [TOMZN3] [PE bar] [DR-60-12] │     │
│  └─────────────────────────────────────────────────┘     │
│                                                          │
│   + BUSBAR  ═══════════════════════                      │
│                                                          │
│   ─ BUSBAR  ═══════════════════════                      │
│                                                          │
│              [PRECHARGE: 500Ω resistor + relay]          │
│                                                          │
│        ┌──────────────────────────────┐                  │
│        │  ALBRIGHT SW200-22           │   ← main contactor on mounting plate
│        │  (with magnetic blowouts)    │     directly between busbars and inverter feed
│        └──────────────────────────────┘                  │
│                                                          │
│   ┌──────── LV SUB-PANEL ──────────┐                     │
│   │ [Mornsun] [SSR-04] [LilyGo]    │                     │
│   │ [Waveshare CAN isolator]       │                     │
│   │ [RPi 4]   [ZTE router]         │                     │
│   └────────────────────────────────┘                     │
│                                                          │
│  Cable glands at bottom for:                             │
│   - 3× 35mm² HV pack feeds                               │
│   - 35mm² HV inverter feed                               │
│   - 16mm² earth                                          │
│   - mains 230V AC for DR-60-12 PSU                       │
│   - Yazaki harness from Pack 1                           │
│   - Comms (RPi ethernet, CAN to inverter)                │
└──────────────────────────────────────────────────────────┘

External E-stop button mounts on the wall next to the box.
FoxESS inverter mounts separately on a nearby wall.
```

### 7.2 On the packs (top of each)
```
┌─────────────────────────────────┐
│  PACK n                         │
│                                 │
│   [HV+]                  [HV−]  │  ← M8 studs, 35mm² lug to SB175
│                                 │
│   [SDP plug — orange lever]     │  ← pull this before any work
│                                 │
│   [Yazaki 36-pin]               │  ← only Pack 1 plugged; Packs 2-3 left blank
│                                 │
│   [DS18B20 ×2 stuck to body]    │  ← thermal probes
│                                 │
│   [Chassis earth stud]          │  ← 16mm² green/yellow back to PE bar
└─────────────────────────────────┘
```

---

## 8. The end-to-end commissioning sequence (in plain English)

1. **You** physically wire everything per the diagram. All three SDPs pulled and in your pocket.
2. **You** apply mains 230V AC to the DR-60-12 PSU. LV side comes alive: 12V everywhere, Mornsun produces isolated 12V, RPi boots, ESP32 boots, ZTE router gets online.
3. **ESP32** boots into DALA firmware, sees no CAN traffic on CAN-A (because Pack 1's BMS isn't awake yet — needs 12V on Yazaki Pin 1, which the Mornsun is now providing), waits a few seconds.
4. **Nissan BMS in Pack 1** wakes, starts broadcasting cell data on CAN-A.
5. **ESP32** reads the BMS data, translates to FoxESS format, starts emitting on CAN-B → FoxESS sees "a battery" appear on its CAN bus, runs its own self-checks.
6. **You** insert SDP into Pack 1 only, walk to the Rittal box, multimeter the + and − busbar against earth — should read ~360V on +, ~0V on −. (If it reads anything else, stop and diagnose.)
7. **You** insert SDP into Pack 2. Voltage shouldn't move much (TOMZN breaker for Pack 2 is open — flip its lever after checking Pack 2's voltage matches Pack 1 within ±5V).
8. **You** repeat for Pack 3.
9. **ESP32** runs precharge sequence — commands the small SPST relay to close, monitors inverter-side voltage rise via FoxESS CAN feedback. When inverter caps are ~95% charged, commands the SSR-04, which closes the Albright contactor's coil circuit, contactor pulls in, then ESP32 drops the precharge relay.
10. **FoxESS** sees full bus voltage, runs G99 self-tests (anti-islanding, ROCOF, voltage limits), waits 20s reconnection delay, then enables grid export.
11. **RPi** starts logging — sensor data + CAN telemetry from the LilyGo via USB → history.csv → Flask portal at `http://node3.local`.

At any moment, **press the E-stop**. The coil supply drops. The Albright opens. The bus is dead within 50ms.

---

## 9. Common-sense rules

- **Pull the SDPs before any wiring change.** Always.
- **Never bench-test the HV side with all 3 SDPs in.** Always isolate by pulling SDPs.
- **Test the E-stop on day 1** with a continuity meter, then again with low-voltage power applied, before HV is ever live.
- **Don't bond the two sides of the Waveshare isolator with a stray ground.** That defeats the entire isolator.
- **Match pack voltages within 5V before paralleling**, or you'll see hundreds of amps of equalisation current the moment you flip the third breaker.
- **Every screw torqued.** Loose HV joints heat up and start fires.
- **Megger test before energising.** 1000V insulation tester between + bus and chassis must read > 1 MΩ. Same for − bus.
