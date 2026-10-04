#!/usr/bin/env python3
"""
fox_modbus_loop.py — NODE-3 Dynamic Fuse Protection Daemon
===========================================================
Reads real-time grid import from FoxESS KH10.5 HV via Modbus, battery power
from bms_detail.json (already polled by bms_monitor.py), calculates the safe
charge rate to stay under the property's 80A (18.4 kW) fuse, and writes the
limit back to the inverter every 5 seconds.

DATA SOURCES
------------
  Grid power  → Modbus read from Fox ESS register 0x010B  (one register only)
  Bat power   → bms_detail.json written by bms_monitor.py (already live)
  Bat voltage → bms_detail.json (pack1/pack2/pack3 summed or avg)

  Using bms_detail.json for battery data avoids extra Modbus reads and gives
  us real pack voltage for accurate current↔power conversion.

FUSE MATHS
----------
  FUSE_HARD_W  = 80A × 230V = 18,400 W  (absolute property fuse limit)
  FUSE_SAFE_W  = 18,400 - 2,000 = 16,400 W  (2 kW headroom for spikes)

  P_grid       = total site import from grid (house + bat charge + miner)
  P_bat_charge = sum of pack power currently charging (W, from bms_detail)
                 bms_monitor sign: current_a +ve = charging, -ve = discharging

  P_house      = P_grid - P_bat_charge  (other site loads)
  safe_charge_W = FUSE_SAFE_W - P_house
                = FUSE_SAFE_W - P_grid + P_bat_charge
  new_limit_W  = clamp(safe_charge_W, 0, INVERTER_MAX_W=10,500)

MODBUS REGISTERS (FoxESS KH Series RTU Protocol — verify against KH Modbus doc)
--------------------------------------------------------------------------------
  READ (input register, FC=04):
    0x010B  GridPower  W signed int16  (positive = IMPORTING from grid)

  WRITE (holding register, FC=06):
    0x09D5  MaxBatChgCurrent  A × 0.1

SIGN CONVENTION NOTE
--------------------
If grid reads inverted, set env var FOXESS_GRID_SIGN=-1.

CONNECTION
----------
Same env vars as hardware_bridge.py:
  FOXESS_RS485_PORT   /dev/ttyUSB1  (primary)
  FOXESS_RS485_BAUD   9600 (default)
  FOXESS_MODBUS_ADDR  247  (0xF7, FoxESS default)
  FOXESS_MODBUS_HOST  inverter LAN IP  (secondary)

USAGE
-----
  python3 fox_modbus_loop.py              # run daemon
  python3 fox_modbus_loop.py --dry-run    # read only, print calculated limit
  python3 fox_modbus_loop.py --once       # single shot then exit
  python3 fox_modbus_loop.py --interval 10  # change poll interval (default 5s)

DOCKER
------
Add to docker-compose.pi.yml alongside hardware_bridge invocations, or run
as a background thread started by server.py startup sequence.
"""

import os, sys, time, json, logging, signal
from datetime import datetime, timezone
from pathlib import Path

BMS_DETAIL_FILE  = Path(__file__).parent / "bms_detail.json"
GRID_HISTORY_CSV = Path(__file__).parent / "grid_history.csv"

# ── Config ────────────────────────────────────────────────────────────────────
FUSE_HARD_W      = 18_400   # 80A × 230V  — NEVER exceed this
FUSE_MARGIN_W    = 2_000    # safety margin below fuse (spike buffer)
FUSE_SAFE_W      = FUSE_HARD_W - FUSE_MARGIN_W   # = 16,400 W
INVERTER_MAX_W   = 10_500   # KH10.5 rated charge power (AC side, W)
POLL_INTERVAL_S  = int(os.environ.get("FOXESS_LOOP_INTERVAL", "5"))

# Sign correction for grid register — flip if reads inverted
GRID_SIGN = int(os.environ.get("FOXESS_GRID_SIGN", "1"))   # +1 = positive is import
# bms_monitor.py CAN sign: current_a +ve = charging, -ve = discharging (fixed)
BMS_MAX_AGE_S = 30   # reject bms_detail.json if older than this (seconds)

# Connection (same env vars as hardware_bridge.py)
RS485_PORT   = os.environ.get("FOXESS_RS485_PORT", "")
RS485_BAUD   = int(os.environ.get("FOXESS_RS485_BAUD", "9600"))
MODBUS_ADDR  = int(os.environ.get("FOXESS_MODBUS_ADDR", "247"))
MODBUS_HOST  = os.environ.get("FOXESS_MODBUS_HOST", "")
MODBUS_PORT  = int(os.environ.get("FOXESS_MODBUS_PORT", "502"))

# ── Modbus register addresses ─────────────────────────────────────────────────
# Battery data comes from bms_detail.json (bms_monitor.py) — NOT from Fox ESS registers.
# Only ONE register read needed per cycle:
REG_GRID_POWER   = 0x010B   # input  — grid/meter power W (positive = import)
REG_MAX_CHG_CURR = 0x09D5   # holding — max battery charge current A × 0.1

LOG_FILE = Path(__file__).parent / "fuse_loop_log.json"
_MAX_LOG_ENTRIES = 200

logging.basicConfig(level=logging.INFO,
    format="[FUSE-LOOP %(asctime)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("fuse_loop")


# ── Modbus helpers ────────────────────────────────────────────────────────────
def _signed16(v):
    """Convert unsigned 16-bit register value to signed int16."""
    return v if v < 32768 else v - 65536


def _connect_rtu():
    if not RS485_PORT:
        return None
    try:
        from pymodbus.client import ModbusSerialClient
        c = ModbusSerialClient(port=RS485_PORT, baudrate=RS485_BAUD,
                               bytesize=8, parity="N", stopbits=1, timeout=3)
        if c.connect():
            return c
        log.warning(f"RTU: cannot open {RS485_PORT}")
    except ImportError:
        log.error("RTU: pip install pymodbus pyserial")
    except Exception as e:
        log.warning(f"RTU connect: {e}")
    return None


def _connect_tcp():
    if not MODBUS_HOST:
        return None
    try:
        from pymodbus.client import ModbusTcpClient
        c = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT, timeout=5)
        if c.connect():
            return c
        log.warning(f"TCP: cannot connect to {MODBUS_HOST}")
    except Exception as e:
        log.warning(f"TCP connect: {e}")
    return None


def _get_client():
    return _connect_rtu() or _connect_tcp()


def _read_input(client, address, count=1):
    """Read input register(s) using FC=04."""
    r = client.read_input_registers(address, count=count, slave=MODBUS_ADDR)
    if r.isError():
        raise IOError(f"read_input_registers 0x{address:04X}: {r}")
    return r.registers


def _write_holding(client, address, value):
    """Write single holding register using FC=06."""
    r = client.write_register(address, value, slave=MODBUS_ADDR)
    if r.isError():
        raise IOError(f"write_register 0x{address:04X}={value}: {r}")


# ── BMS data from bms_detail.json ────────────────────────────────────────────
def read_bms_state():
    """Read battery state from bms_detail.json (written by bms_monitor.py).
    Returns (bat_charge_w, bat_volt_v, soc_pct) or raises IOError if stale/missing.

    bms_monitor sign convention: current_a > 0 = charging, < 0 = discharging.
    All three packs are summed: total charge power = sum(V_pack × I_pack) for
    packs where I > 0.  Voltage used is average of available packs.
    """
    if not BMS_DETAIL_FILE.exists():
        raise IOError("bms_detail.json not found — is bms_monitor.py running?")

    data = json.loads(BMS_DETAIL_FILE.read_text())

    # Staleness check
    updated = data.get("updated", "")
    if updated:
        try:
            from datetime import timezone as _tz
            age_s = (datetime.now(_tz.utc) -
                     datetime.fromisoformat(updated.replace("Z", "+00:00"))).total_seconds()
            if age_s > BMS_MAX_AGE_S:
                raise IOError(f"bms_detail.json is {age_s:.0f}s old (max {BMS_MAX_AGE_S}s)")
        except (ValueError, TypeError):
            pass  # can't parse timestamp — proceed

    packs = data.get("packs", {})
    total_charge_w = 0.0
    voltages = []
    socs = []

    for pk in ("pack1", "pack2", "pack3"):
        p = packs.get(pk, {})
        v = p.get("voltage_v")
        i = p.get("current_a")
        s = p.get("soc_pct")
        if v and i is not None and v > 10:
            voltages.append(v)
            if i > 0:                        # charging
                total_charge_w += v * i
            if s is not None:
                socs.append(s)

    avg_volt = sum(voltages) / len(voltages) if voltages else 300.0
    avg_soc  = sum(socs) / len(socs) if socs else 0.0

    return total_charge_w, avg_volt, avg_soc


# ── Core fuse calculation ─────────────────────────────────────────────────────
def read_grid_power(client):
    """Read grid import power from Fox ESS via Modbus (single register)."""
    regs = _read_input(client, REG_GRID_POWER, count=1)
    return _signed16(regs[0]) * GRID_SIGN   # W, positive = importing


def calculate_safe_charge(grid_power_w, bat_charge_w):
    """Return safe max charge power in Watts.

    P_house      = grid_power_w - bat_charge_w  (other site loads)
    safe_charge  = FUSE_SAFE_W - P_house
                 = FUSE_SAFE_W - grid_power_w + bat_charge_w
    """
    p_house = grid_power_w - bat_charge_w
    safe_w  = FUSE_SAFE_W - p_house
    return max(0.0, min(safe_w, float(INVERTER_MAX_W)))


def power_to_current_register(power_w, bat_volt_v):
    """Convert charge power (W) to maxBatChgCurrent register value (A × 0.1)."""
    if bat_volt_v < 50:
        log.warning(f"bat_volt={bat_volt_v:.1f}V unreliable — using 300V fallback")
        bat_volt_v = 300.0
    return int(round((power_w / bat_volt_v) * 10.0))   # A × 0.1


# ── Log helpers ───────────────────────────────────────────────────────────────
def _log_entry(entry):
    try:
        data = json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []
        data.append(entry)
        LOG_FILE.write_text(json.dumps(data[-_MAX_LOG_ENTRIES:], indent=2))
    except Exception as e:
        log.warning(f"log: {e}")


_GRID_CSV_HEADER = 'ts,grid_power_w,bat_charge_w,bat_volt_v,soc_pct,safe_charge_w\n'
_grid_csv_write_count = 0   # write every N cycles to reduce I/O (still ~every 5s but flush 1/min)

def _log_grid_history(entry):
    """Append one row to grid_history.csv for house load profile learning."""
    global _grid_csv_write_count
    if entry.get('error') or entry.get('grid_power_w') is None:
        return
    try:
        write_header = not GRID_HISTORY_CSV.exists()
        with open(GRID_HISTORY_CSV, 'a', newline='') as f:
            if write_header:
                f.write(_GRID_CSV_HEADER)
            f.write(
                f"{entry.get('ts','')},"
                f"{entry.get('grid_power_w','')},"
                f"{entry.get('bat_charge_w','')},"
                f"{entry.get('bat_volt_v','')},"
                f"{entry.get('soc_pct','')},"
                f"{entry.get('safe_charge_w','')}\n"
            )
        _grid_csv_write_count += 1
        # Rebuild house profile every 1440 cycles (~2h at 5s poll) if enough data
        if _grid_csv_write_count % 1440 == 0:
            try:
                import house_profile as _hp
                _hp.run()
            except Exception as _hpe:
                log.warning(f"house_profile rebuild: {_hpe}")
    except Exception as e:
        log.warning(f"grid_history: {e}")


# ── Single poll cycle ─────────────────────────────────────────────────────────
def run_once(dry_run=False):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {"ts": ts, "error": None, "dry_run": dry_run}

    client = _get_client()
    if client is None:
        msg = "No Modbus connection. Set FOXESS_RS485_PORT or FOXESS_MODBUS_HOST."
        log.error(msg)
        entry["error"] = msg
        _log_entry(entry)
        return entry

    try:
        # Battery state from bms_detail.json (bms_monitor.py already polling)
        bat_charge_w, bat_volt_v, soc_pct = read_bms_state()

        # Grid power — single Modbus read
        grid_power_w = read_grid_power(client)

        safe_w  = calculate_safe_charge(grid_power_w, bat_charge_w)
        reg_val = power_to_current_register(safe_w, bat_volt_v)

        entry.update({
            "grid_power_w":  round(grid_power_w),
            "bat_charge_w":  round(bat_charge_w),
            "bat_volt_v":    round(bat_volt_v, 1),
            "soc_pct":       round(soc_pct, 1),
            "safe_charge_w": round(safe_w),
            "reg_val":       reg_val,
            "written":       False,
        })

        log.info(
            f"grid={grid_power_w:+.0f}W  bat_chg={bat_charge_w:.0f}W  "
            f"volt={bat_volt_v:.1f}V  soc={soc_pct:.0f}%  "
            f"→ safe_charge={safe_w:.0f}W  reg=0x09D5:{reg_val}"
        )

        if not dry_run:
            _write_holding(client, REG_MAX_CHG_CURR, reg_val)
            entry["written"] = True
            log.info(f"Wrote maxBatChgCurrent={reg_val} (0x09D5) → {safe_w:.0f}W limit")

    except Exception as e:
        msg = str(e)
        log.error(f"poll error: {msg}")
        entry["error"] = msg
    finally:
        try:
            client.close()
        except Exception:
            pass

    _log_entry(entry)
    _log_grid_history(entry)
    return entry


# ── Daemon loop ───────────────────────────────────────────────────────────────
_running = True

def _handle_signal(sig, frame):
    global _running
    log.info(f"Signal {sig} — stopping")
    _running = False

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)


def run_daemon(interval=POLL_INTERVAL_S, dry_run=False):
    log.info(f"Fuse protection loop starting — interval={interval}s  "
             f"fuse_safe={FUSE_SAFE_W}W  inverter_max={INVERTER_MAX_W}W  "
             f"dry_run={dry_run}")
    consecutive_errors = 0
    while _running:
        result = run_once(dry_run=dry_run)
        if result.get("error"):
            consecutive_errors += 1
            if consecutive_errors >= 5:
                log.error(f"{consecutive_errors} consecutive errors — backing off 30s")
                time.sleep(30)
                consecutive_errors = 0
                continue
        else:
            consecutive_errors = 0
        time.sleep(interval)
    log.info("Fuse protection loop stopped.")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="NODE-3 Dynamic Fuse Protection Daemon")
    p.add_argument("--dry-run",  action="store_true", help="Read only — do not write to inverter")
    p.add_argument("--once",     action="store_true", help="Single poll then exit")
    p.add_argument("--interval", type=int, default=POLL_INTERVAL_S,
                   help=f"Poll interval seconds (default {POLL_INTERVAL_S})")
    p.add_argument("--status",   action="store_true", help="Print last 10 log entries")
    a = p.parse_args()

    if a.status:
        try:
            data = json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []
            print(json.dumps(data[-10:], indent=2))
        except Exception as e:
            print(f"No log: {e}")
        sys.exit(0)

    if a.once:
        result = run_once(dry_run=a.dry_run)
        print(json.dumps(result, indent=2))
        sys.exit(0 if not result.get("error") else 1)

    run_daemon(interval=a.interval, dry_run=a.dry_run)
