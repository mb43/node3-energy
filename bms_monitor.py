#!/usr/bin/env python3
"""
bms_monitor.py — NODE-3 Battery Detail Monitor
================================================
Pack 1  : polls DALA Battery-Emulator HTTP API at LILYGO_IP every POLL_INTERVAL s
Packs 2/3: reads raw BMS CAN frames from Waveshare 2-CH CAN HAT (can0 / can1)
           using Nissan LEAF Gen2 / e-NV200 BMS CAN protocol (500 kbaud)

Output: bms_detail.json  — consumed by /api/battery-detail in server.py

CAN frame protocol source: DALA Battery-Emulator (dalathegreat/Battery-Emulator)
Nissan LEAF Gen2 / e-NV200 — 96 series cell groups, 24/30/40 kWh variants.
Verify frame layout against candump can0 before first use.

ENV VARS
--------
  LILYGO_IP         IP of LilyGo T-2CAN running DALA firmware e.g. 192.168.1.50
  BMS_POLL_INTERVAL seconds between full polls (default 30)
  BMS_CAN_PACK2     SocketCAN interface for Pack 2 (default can0)
  BMS_CAN_PACK3     SocketCAN interface for Pack 3 (default can1)
  BMS_CAN_BITRATE   CAN bitrate bps (default 500000)
"""

import os, json, time, logging, threading
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR      = Path(__file__).parent
OUT_FILE      = BASE_DIR / "bms_detail.json"

LILYGO_IP     = os.environ.get("LILYGO_IP", "")
POLL_INTERVAL = int(os.environ.get("BMS_POLL_INTERVAL", "30"))
CAN_PACK2     = os.environ.get("BMS_CAN_PACK2", "can0")
CAN_PACK3     = os.environ.get("BMS_CAN_PACK3", "can1")
CAN_BITRATE   = int(os.environ.get("BMS_CAN_BITRATE", "500000"))
CAN_GATHER_S  = 5   # seconds to listen on each CAN bus per poll

log = logging.getLogger("bms_monitor")

# ── Nissan LEAF Gen2 / e-NV200 BMS CAN frame IDs ─────────────────────────────
# Source: DALA Battery-Emulator + community reverse-engineering (OpenInverter wiki)
FRAME_VI       = 0x1DB   # Pack voltage + current (HV side)
FRAME_LBC      = 0x1DC   # LBC status flags
FRAME_TEMPS    = 0x55B   # Cell temperatures (4 sensors)
FRAME_SOC      = 0x5BC   # State of Charge (%), capacity flags
FRAME_SOH      = 0x5B3   # State of Health (%)
FRAME_CELL_V1  = 0x5C0   # Cell voltages group A — byte[0] = group 0-11 (4 cells each)
FRAME_CELL_V2  = 0x5C3   # Cell voltages group B — byte[0] = group 12-23
FRAME_BALANCE  = 0x59E   # HV contactor status + cell balance bits


def _parse_1db(d):
    """
    0x1DB — Pack current + voltage.
    Current: bytes [0-1], 10-bit signed, 0.5 A/bit, offset 512 (centre = 0 A)
    Voltage: bytes [2-3] upper 10 bits, 0.5 V/bit
    """
    i_raw = ((d[0] & 0x3F) << 4) | (d[1] >> 4)
    v_raw = ((d[2] & 0x3F) << 4) | (d[3] >> 4)
    current = round((i_raw - 512) * 0.5, 1)   # A (+ = charging, - = discharging)
    voltage = round(v_raw * 0.5, 1)            # V
    return {"voltage_v": voltage, "current_a": current}


def _parse_55b(d):
    """
    0x55B — Cell temperatures (up to 4 sensors).
    Each byte = raw temp, 0xFF = no sensor. Offset: value − 40 = °C.
    """
    temps = []
    for i in range(4):
        if i < len(d) and d[i] != 0xFF:
            temps.append(d[i] - 40)
    return {"temps_c": temps}


def _parse_5bc(d):
    """
    0x5BC — State of Charge + cell voltage limits.
    SOC: byte[0] bits [7:1] = integer %, 1 bit = 0.5% resolution flag
    Max cell: byte[2] bits [7:2] → mV (×10 + 2000)
    Min cell: byte[3] bits [7:2] → mV (×10 + 2000)
    """
    soc = (d[0] >> 1) & 0x7F           # 0–100 %
    max_mv = ((d[2] >> 2) * 10) + 2000
    min_mv = ((d[3] >> 2) * 10) + 2000
    return {"soc_pct": soc, "max_cell_mv": max_mv, "min_cell_mv": min_mv}


def _parse_5b3(d):
    """0x5B3 — State of Health: byte[5] bits [6:0] = SoH %."""
    soh = d[5] & 0x7F if len(d) > 5 else None
    return {"soh_pct": soh}


def _parse_cell_frame(d, cell_mv_dict):
    """
    0x5C0 and 0x5C3 — Individual cell voltages.
    byte[0] bits [7:3] = group index (0-23, 4 cells each → 96 total).
    Cells 1-4 packed as 10-bit values across bytes 1-6.
    Voltage = raw_value + 2000 mV  (range ~2500-4200 mV in operation).

    Layout (each cell = 10 bits):
      cell1: byte1[7:0] + byte2[7:6]  → value bits [9:0]
      cell2: byte2[5:0] + byte3[7:4]  → value bits [9:0]
      cell3: byte3[3:0] + byte4[7:2]  → value bits [9:0]
      cell4: byte4[1:0] + byte5[7:0]  → value bits [9:0] (may be in byte5/6)
    """
    if len(d) < 7:
        return
    group = (d[0] >> 3) & 0x1F    # group 0-23
    if group > 23:
        return
    base = group * 4

    raw = [
        ((d[1] << 2) | (d[2] >> 6)) & 0x3FF,
        ((d[2] << 4) | (d[3] >> 4)) & 0x3FF,
        ((d[3] << 6) | (d[4] >> 2)) & 0x3FF,
        ((d[4] << 8) | d[5])        & 0x3FF,
    ]
    for j, r in enumerate(raw):
        mv = r + 2000
        if 2000 <= mv <= 4500:     # sanity gate
            cell_mv_dict[base + j] = mv


def _gather_can(interface):
    """
    Gather CAN frames from one SocketCAN interface for CAN_GATHER_S seconds.
    Returns parsed pack dict or None on failure.
    """
    try:
        import can
    except ImportError:
        log.warning("python-can not installed — pip install python-can")
        return None

    try:
        bus = can.interface.Bus(channel=interface, interface='socketcan',
                                bitrate=CAN_BITRATE)
    except OSError as e:
        log.debug(f"CAN {interface}: {e}")   # not wired yet — debug not warning
        return None
    except Exception as e:
        log.warning(f"CAN {interface} open: {e}")
        return None

    frames  = {}
    cell_mv = {}
    deadline = time.monotonic() + CAN_GATHER_S

    try:
        while time.monotonic() < deadline:
            msg = bus.recv(timeout=0.5)
            if msg is None:
                continue
            d   = bytes(msg.data)
            fid = msg.arbitration_id
            if   fid == FRAME_VI:
                frames['vi']    = _parse_1db(d)
            elif fid == FRAME_TEMPS:
                frames['temps'] = _parse_55b(d)
            elif fid == FRAME_SOC:
                frames['soc']   = _parse_5bc(d)
            elif fid == FRAME_SOH:
                frames['soh']   = _parse_5b3(d)
            elif fid in (FRAME_CELL_V1, FRAME_CELL_V2):
                _parse_cell_frame(d, cell_mv)
    except Exception as e:
        log.warning(f"CAN {interface} read: {e}")
    finally:
        try:
            bus.shutdown()
        except Exception:
            pass

    if not frames:
        return None   # nothing heard — bus not live

    result = {"source": f"CAN/{interface}", "updated": _now()}
    result.update(frames.get('vi',    {}))
    result.update(frames.get('temps', {}))
    result.update(frames.get('soc',   {}))
    soh_data = frames.get('soh', {})
    if soh_data.get('soh_pct') is not None:
        result.update(soh_data)

    if cell_mv:
        n = max(cell_mv.keys()) + 1
        cells = [cell_mv.get(i) for i in range(n)]
        result["cell_mv"]     = cells
        result["cell_count"]  = len([v for v in cells if v is not None])
        valid = [v for v in cells if v is not None]
        if valid:
            result["min_cell_mv"]     = min(valid)
            result["max_cell_mv"]     = max(valid)
            result["cell_mv_spread"]  = max(valid) - min(valid)

    return result


# ── DALA HTTP poll (Pack 1) ───────────────────────────────────────────────────

_DALA_PATHS = ["/status", "/api/status", "/data", "/api/data", "/api/battery"]


def _poll_dala(ip):
    """
    Fetch cell-level Pack 1 data from DALA Battery-Emulator HTTP endpoint.
    DALA firmware version determines which path returns JSON — tries common ones.
    Returns normalised dict or None.
    """
    if not ip:
        return None

    import urllib.request, urllib.error

    for path in _DALA_PATHS:
        url = f"http://{ip}{path}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=4) as r:
                raw = r.read().decode("utf-8", errors="replace")
                try:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        continue
                    norm = _normalise_dala(data)
                    norm["source"]  = f"DALA HTTP{path}"
                    norm["updated"] = _now()
                    log.debug(f"DALA Pack1 OK via {path}")
                    return norm
                except json.JSONDecodeError:
                    continue   # not JSON (HTML dashboard) — try next path
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue   # path not found, try next
            log.debug(f"DALA {path}: HTTP {e.code}")
        except Exception as e:
            log.debug(f"DALA {path}: {e}")
            break   # unreachable host — stop trying paths

    log.debug(f"DALA: no JSON endpoint found at {ip}")
    return None


def _normalise_dala(d):
    """Map DALA JSON keys (which vary by firmware) to common schema."""
    def _pick(*keys):
        for k in keys:
            v = d.get(k)
            if v is not None:
                return v
        return None

    out = {}
    out["soc_pct"]    = _pick("SOC", "soc", "StateOfCharge", "batterySOC", "BattSOC")
    out["voltage_v"]  = _pick("voltage", "Voltage", "batteryVoltage", "PackVoltage")
    out["current_a"]  = _pick("current", "Current", "batteryCurrent", "PackCurrent")
    out["soh_pct"]    = _pick("StateOfHealth", "SOH", "soh", "BattSOH")

    t = _pick("temperature", "Temperature", "batteryTemperature", "temp_c")
    if t is not None:
        out["temps_c"] = [t] if isinstance(t, (int, float)) else t

    cells = _pick("cellVoltages", "cell_voltages", "CellVoltages", "cells",
                  "CellVoltage", "cell_mv")
    if cells and isinstance(cells, list):
        out["cell_mv"]        = cells
        out["cell_count"]     = len([v for v in cells if v])
        valid = [v for v in cells if v and v > 0]
        if valid:
            out["min_cell_mv"]    = min(valid)
            out["max_cell_mv"]    = max(valid)
            out["cell_mv_spread"] = max(valid) - min(valid)

    # DALA sometimes gives aggregate min/max even without per-cell array
    if "min_cell_mv" not in out:
        mn = _pick("minCellVoltage", "min_cell_voltage", "MinCellVoltage")
        mx = _pick("maxCellVoltage", "max_cell_voltage", "MaxCellVoltage")
        if mn: out["min_cell_mv"] = mn
        if mx: out["max_cell_mv"] = mx

    return {k: v for k, v in out.items() if v is not None}


# ── Main loop ─────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).isoformat()


def _write(detail):
    try:
        OUT_FILE.write_text(json.dumps(detail, indent=2))
    except Exception as e:
        log.warning(f"bms_detail write: {e}")


def poll_once():
    """Single poll of all three packs. Returns the detail dict."""
    detail = {"updated": _now(), "packs": {}}

    # Pack 1 — DALA HTTP
    p1 = _poll_dala(LILYGO_IP)
    detail["packs"]["pack1"] = p1 if p1 else {
        "source": "DALA HTTP", "error": "unavailable",
        "hint": f"Set LILYGO_IP env var (current: '{LILYGO_IP or 'not set'}')"
    }

    # Pack 2 — Waveshare ch1 (can0)
    p2 = _gather_can(CAN_PACK2)
    detail["packs"]["pack2"] = p2 if p2 else {
        "source": f"CAN/{CAN_PACK2}", "error": "unavailable",
        "hint": f"Check: ip link show {CAN_PACK2} | Waveshare HAT fitted + 120Ω terminator"
    }

    # Pack 3 — Waveshare ch2 (can1)
    p3 = _gather_can(CAN_PACK3)
    detail["packs"]["pack3"] = p3 if p3 else {
        "source": f"CAN/{CAN_PACK3}", "error": "unavailable",
        "hint": f"Check: ip link show {CAN_PACK3} | Waveshare HAT fitted + 120Ω terminator"
    }

    _write(detail)
    return detail


def run_loop():
    """Continuous polling daemon — call from server.py background thread."""
    log.info(
        f"BMS monitor started | Pack1=DALA@{LILYGO_IP or 'NOT SET'} "
        f"| Pack2={CAN_PACK2} | Pack3={CAN_PACK3} | interval={POLL_INTERVAL}s"
    )
    while True:
        try:
            poll_once()
        except Exception as e:
            log.warning(f"BMS poll_once: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
        format="[BMS-MON %(asctime)s] %(message)s", datefmt="%H:%M:%S")
    import pprint
    result = poll_once()
    pprint.pprint(result)
    print(f"\nWritten to: {OUT_FILE}")
