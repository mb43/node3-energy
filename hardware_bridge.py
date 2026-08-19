#!/usr/bin/env python3
"""
hardware_bridge.py — NODE-3 Hardware Control Bridge
====================================================
Reads dispatch_plan.json and sends real charge/discharge commands to the
FoxESS KH10.5 HV inverter.

CONTROL PATHS (priority order — local first, no cloud required)
---------------------------------------------------------------
  1. Modbus RTU  Pi USB-RS485 (JZK adapter) → FoxESS RS485 com port  [PRIMARY]
  2. Modbus TCP  Pi LAN → FoxESS local IP                            [SECONDARY]
  3. FoxESS API  Pi → internet → foxesscloud.com                     [FALLBACK]
  4. MQTT        Pi → Mosquitto → T-2CAN ESP32                       [ALT]

OPERATIONAL MODES
-----------------
  pre_commissioning  No commands. Simulation only.
  self_consumption   Charge from grid. 0W export. (before G99)
  full_export        Charge + export to grid. (after G99 live)

WIRING (Modbus RTU path)
------------------------
  JZK USB-RS485 adapter plugged into Pi USB port → appears as /dev/ttyUSB1
  (T-2CAN USB takes /dev/ttyUSB0)
  JZK A+ → FoxESS RS485 com port A
  JZK B- → FoxESS RS485 com port B
  JZK GND → FoxESS GND

ENV VARS
--------
  FOXESS_RS485_PORT   e.g. /dev/ttyUSB1  (primary path)
  FOXESS_RS485_BAUD   default 9600
  FOXESS_MODBUS_ADDR  default 247 (0xF7 = FoxESS default slave address)
  FOXESS_MODBUS_HOST  inverter LAN IP (secondary path)
  FOXESS_API_KEY      cloud API key (fallback only)
  FOXESS_DEVICE_SN    inverter serial number (cloud fallback)
  MQTT_HOST           broker IP (alt path)
  NODE3_MODE          pre_commissioning|self_consumption|full_export
  NODE3_G99_ACTIVE    1 = G99 live, raises export cap to 5.75kWh/slot
"""

import os, json, time, hashlib, logging
from datetime import datetime, timezone
from pathlib import Path
import node3_config as _cfg

BASE_DIR           = Path(__file__).parent
DISPATCH_PLAN_FILE = BASE_DIR / "dispatch_plan.json"
MODE_FILE          = BASE_DIR / "node3_mode.json"
HW_LOG_FILE        = BASE_DIR / "hardware_log.json"

# ── Modbus RTU — PRIMARY ──────────────────────────────────────────────────────
FOXESS_RS485_PORT  = os.environ.get("FOXESS_RS485_PORT", "")
FOXESS_RS485_BAUD  = int(os.environ.get("FOXESS_RS485_BAUD", "9600"))
FOXESS_MODBUS_ADDR = int(os.environ.get("FOXESS_MODBUS_ADDR", "247"))

# ── Modbus TCP — secondary ────────────────────────────────────────────────────
FOXESS_MODBUS_HOST = os.environ.get("FOXESS_MODBUS_HOST", "")
FOXESS_MODBUS_PORT = int(os.environ.get("FOXESS_MODBUS_PORT", "502"))

# ── FoxESS Cloud API — fallback only ─────────────────────────────────────────
FOXESS_API_BASE    = "https://www.foxesscloud.com/op/v0"
FOXESS_API_KEY     = os.environ.get("FOXESS_API_KEY", "")
FOXESS_DEVICE_SN   = os.environ.get("FOXESS_DEVICE_SN", "")

# ── MQTT ──────────────────────────────────────────────────────────────────────
MQTT_HOST  = os.environ.get("MQTT_HOST", "")
MQTT_PORT  = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "node3/cmd")

# ── FoxESS KH10.5 HV Modbus register map ─────────────────────────────────────
# Confirm against FoxESS KH Series Modbus RTU Communication Protocol doc
# These are the standard KH series holding registers:
MODBUS_REG_WORK_MODE    = 0x09D0   # R/W work mode
MODBUS_REG_EXPORT_LIMIT = 0x09D2   # R/W export power limit (W)
MODBUS_REG_SOC          = 0x0103   # R   battery SOC (%)

# Work mode register values
MODBUS_WM = {"SelfUse": 0, "ForceChg": 6, "ForceDischg": 7}

# DNO export caps — FOUND BROKEN 19 Aug 2026: these were the kWh-per-HALF-HOUR-
# SLOT figures (3.68kWh, 5.75kWh) multiplied by 1000 and mislabeled as Watts.
# MODBUS_REG_EXPORT_LIMIT / feedInLimitPower both expect a continuous POWER
# figure, not an energy-per-slot figure — converting kWh/half-hour -> continuous
# W requires dividing by 0.5h (i.e. x2), which was never done. Every real
# "full_export" command sent to the inverter was capping export at HALF the
# legal/intended limit (fail-safe direction — under, not over — but a
# persistent ~50% under-realisation of export revenue that was invisible from
# the software side, since simulate.py/server.py have no knowledge that this
# file was independently re-capping exports).
#
# Real DNO legal continuous power maxima (hard safety ceiling — NEVER send
# more than this regardless of what node3_config's export_kw is set to):
_G98_LEGAL_MAX_W = 7360    # 32A x 230V single-phase
_G99_LEGAL_MAX_W = 11500   # 50A x 230V single-phase (pending ref 260420-000198)


def get_export_w():
    """
    Export power cap (Watts) per mode, honouring the operator-configurable
    export_kw setting (node3_config.json / /api/settings) for G98 — Matt's
    actual live connection — while hard-clamping to the real legal maximum as
    a safety backstop against a mistyped setting. G99 stays FIXED at the real
    DNO figure (not tied to the configurable setting): it represents a
    different physical grid connection, not a tunable operating choice — same
    convention as simulate.py/server.py's EXPORT_KWH_G99.
    """
    try:
        configured_w = _cfg.load_config()["export_kw"] * 1000.0
    except Exception:
        configured_w = _G98_LEGAL_MAX_W
    return {
        "none": 0,
        "g98":  min(max(0.0, configured_w), _G98_LEGAL_MAX_W),
        "g99":  _G99_LEGAL_MAX_W,
    }


EXPORT_W = get_export_w()   # snapshot at import; resolve_command() re-reads live via get_export_w()

DEFAULT_MODE = {
    "operational_mode": "pre_commissioning",
    "g99_active": False,
    "hardware_enabled": False,
    "last_command": None, "last_command_ts": None,
    "last_command_path": None, "last_error": None,
}

logging.basicConfig(level=logging.INFO,
    format="[HW-BRIDGE %(asctime)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("hardware_bridge")


# ── Mode management ───────────────────────────────────────────────────────────
def load_mode_config():
    try:
        cfg = json.loads(MODE_FILE.read_text()) if MODE_FILE.exists() else dict(DEFAULT_MODE)
    except Exception:
        cfg = dict(DEFAULT_MODE)
    env = os.environ.get("NODE3_MODE", "")
    if env in ("pre_commissioning", "self_consumption", "full_export"):
        cfg["operational_mode"] = env
    if os.environ.get("NODE3_G99_ACTIVE") == "1":
        cfg["g99_active"] = True
    return cfg

def save_mode_config(cfg):
    try:
        MODE_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception as e:
        log.warning(f"save_mode_config: {e}")

def set_mode(mode, g99_active=None):
    valid = ("pre_commissioning", "self_consumption", "full_export")
    if mode not in valid:
        raise ValueError(f"Mode must be one of {valid}")
    cfg = load_mode_config()
    cfg["operational_mode"] = mode
    cfg["hardware_enabled"] = mode != "pre_commissioning"
    if g99_active is not None:
        cfg["g99_active"] = bool(g99_active)
    save_mode_config(cfg)
    log.info(f"Mode -> {mode}")
    return cfg


# ── Dispatch plan ─────────────────────────────────────────────────────────────
def get_current_slot_action():
    try:
        plan = json.loads(DISPATCH_PLAN_FILE.read_text())
    except Exception as e:
        log.warning(f"dispatch_plan: {e}")
        return "idle"
    if not plan:
        return "idle"
    now = datetime.now(timezone.utc)
    slot = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
    slot_ts = slot.timestamp()
    for fmt in (slot.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
                slot.strftime("%Y-%m-%dT%H:%M:00+00:00")):
        if fmt in plan:
            log.info(f"slot {fmt} -> {plan[fmt]}")
            return plan[fmt]
    for k, v in plan.items():
        try:
            if abs(datetime.fromisoformat(k.replace("Z", "+00:00")).timestamp() - slot_ts) <= 300:
                return v
        except Exception:
            pass
    log.warning(f"No plan entry for {slot.isoformat()}")
    return "idle"


# ── Command resolution ────────────────────────────────────────────────────────
def resolve_command(action, mode, g99):
    export_w = get_export_w()   # re-read live so a settings change takes effect immediately
    cap = export_w["g99"] if g99 else export_w["g98"]
    if mode == "pre_commissioning":
        return {"work_mode": None, "export_limit_w": None, "send": False,
                "reason": "pre_commissioning — no hardware commands"}
    if mode == "self_consumption":
        wm = "ForceChg" if action == "charge" else "SelfUse"
        return {"work_mode": wm, "export_limit_w": export_w["none"],
                "send": True, "reason": f"{action} -> {wm}, 0W export (no G99)"}
    if mode == "full_export":
        wm = {"charge": "ForceChg", "discharge": "ForceDischg"}.get(action, "SelfUse")
        return {"work_mode": wm, "export_limit_w": cap,
                "send": True, "reason": f"{action} -> {wm}, export cap={cap}W"}
    return {"work_mode": None, "export_limit_w": None, "send": False,
            "reason": f"unknown mode '{mode}'"}


# ── PATH 1: Modbus RTU via USB-RS485 (PRIMARY) ───────────────────────────────
def send_via_modbus_rtu(cmd):
    if not FOXESS_RS485_PORT:
        return False
    try:
        from pymodbus.client import ModbusSerialClient
        c = ModbusSerialClient(port=FOXESS_RS485_PORT, baudrate=FOXESS_RS485_BAUD,
                               bytesize=8, parity="N", stopbits=1, timeout=3)
        if not c.connect():
            log.warning(f"RTU: cannot open {FOXESS_RS485_PORT}")
            return False
        wm = MODBUS_WM.get(cmd["work_mode"], 0)
        r1 = c.write_register(MODBUS_REG_WORK_MODE, wm, slave=FOXESS_MODBUS_ADDR)
        ok1 = not r1.isError()
        ok2 = True
        if cmd["export_limit_w"] is not None:
            r2 = c.write_register(MODBUS_REG_EXPORT_LIMIT, cmd["export_limit_w"],
                                  slave=FOXESS_MODBUS_ADDR)
            ok2 = not r2.isError()
        c.close()
        log.info(f"RTU: {cmd['work_mode']}({wm}) export={cmd['export_limit_w']}W ok={ok1 and ok2}")
        return ok1 and ok2
    except ImportError:
        log.warning("RTU: pip install pymodbus pyserial")
        return False
    except Exception as e:
        log.warning(f"RTU: {e}")
        return False


# ── PATH 2: Modbus TCP ────────────────────────────────────────────────────────
def send_via_modbus_tcp(cmd):
    if not FOXESS_MODBUS_HOST:
        return False
    try:
        from pymodbus.client import ModbusTcpClient
        c = ModbusTcpClient(FOXESS_MODBUS_HOST, port=FOXESS_MODBUS_PORT, timeout=5)
        if not c.connect():
            return False
        wm = MODBUS_WM.get(cmd["work_mode"], 0)
        ok1 = not c.write_register(MODBUS_REG_WORK_MODE, wm, slave=FOXESS_MODBUS_ADDR).isError()
        ok2 = True
        if cmd["export_limit_w"] is not None:
            ok2 = not c.write_register(MODBUS_REG_EXPORT_LIMIT, cmd["export_limit_w"],
                                       slave=FOXESS_MODBUS_ADDR).isError()
        c.close()
        log.info(f"TCP: {cmd['work_mode']} export={cmd['export_limit_w']}W ok={ok1 and ok2}")
        return ok1 and ok2
    except Exception as e:
        log.warning(f"TCP: {e}")
        return False


# ── PATH 3: FoxESS Cloud API (fallback) ──────────────────────────────────────
def send_via_foxess_api(cmd):
    if not FOXESS_API_KEY or not FOXESS_DEVICE_SN:
        return False
    try:
        import requests
        ts  = str(int(time.time() * 1000))
        sig = hashlib.md5(f"{FOXESS_API_KEY}\n{ts}".encode()).hexdigest()
        h   = {"token": FOXESS_API_KEY, "timestamp": ts, "signature": sig,
               "lang": "en", "Content-Type": "application/json"}
        ok1 = requests.post(f"{FOXESS_API_BASE}/device/setting",
            json={"sn": FOXESS_DEVICE_SN, "key": "workMode", "value": cmd["work_mode"]},
            headers=h, timeout=15).json().get("errno", -1) == 0
        ok2 = True
        if cmd["export_limit_w"] is not None:
            ok2 = requests.post(f"{FOXESS_API_BASE}/device/setting",
                json={"sn": FOXESS_DEVICE_SN, "key": "feedInLimitPower",
                      "value": cmd["export_limit_w"]},
                headers=h, timeout=15).json().get("errno", -1) == 0
        log.info(f"API: {cmd['work_mode']} ok={ok1 and ok2}")
        return ok1 and ok2
    except Exception as e:
        log.warning(f"API: {e}")
        return False


# ── PATH 4: MQTT ──────────────────────────────────────────────────────────────
def send_via_mqtt(cmd, action, mode):
    if not MQTT_HOST:
        return False
    try:
        import paho.mqtt.publish as pub
        pub.single(MQTT_TOPIC, payload=json.dumps({
            "action": action, "work_mode": cmd["work_mode"],
            "export_limit_w": cmd["export_limit_w"], "mode": mode,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}),
            hostname=MQTT_HOST, port=MQTT_PORT, qos=1)
        log.info(f"MQTT: {action} -> {cmd['work_mode']}")
        return True
    except Exception as e:
        log.warning(f"MQTT: {e}")
        return False


# ── Hardware log ──────────────────────────────────────────────────────────────
def _log(entry):
    try:
        data = json.loads(HW_LOG_FILE.read_text()) if HW_LOG_FILE.exists() else []
        data.append(entry)
        HW_LOG_FILE.write_text(json.dumps(data[-200:], indent=2))
    except Exception as e:
        log.warning(f"hw_log: {e}")


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────
def send_current_command():
    cfg    = load_mode_config()
    mode   = cfg.get("operational_mode", "pre_commissioning")
    g99    = cfg.get("g99_active", False)
    ts     = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    action = get_current_slot_action()
    cmd    = resolve_command(action, mode, g99)

    result = {"ts": ts, "mode": mode, "lp_action": action,
              "work_mode": cmd["work_mode"], "export_limit_w": cmd["export_limit_w"],
              "reason": cmd["reason"], "sent": False, "path": None, "error": None}

    if not cmd["send"]:
        log.info(f"No command: {cmd['reason']}")
        _log(result)
        _save_state(cfg, result)
        return result

    log.info(f"-> action={action} mode={mode} wm={cmd['work_mode']} exp={cmd['export_limit_w']}W")

    sent = path = None
    for fn, key, cond in [
        (lambda: send_via_modbus_rtu(cmd),        "modbus_rtu", FOXESS_RS485_PORT),
        (lambda: send_via_modbus_tcp(cmd),        "modbus_tcp", FOXESS_MODBUS_HOST),
        (lambda: send_via_foxess_api(cmd),        "foxess_api", FOXESS_API_KEY),
        (lambda: send_via_mqtt(cmd, action, mode),"mqtt",        MQTT_HOST),
    ]:
        if cond and fn():
            sent, path = True, key
            break

    if not sent:
        err = "No control path. Set FOXESS_RS485_PORT (primary) or FOXESS_MODBUS_HOST."
        log.error(err)
        result["error"] = err
    else:
        result["sent"] = True
        result["path"] = path
        log.info(f"Sent via {path}")

    _log(result)
    _save_state(cfg, result)
    return result


def _save_state(cfg, result):
    cfg.update({"last_command": result.get("work_mode"),
                "last_command_ts": result.get("ts"),
                "last_command_path": result.get("path"),
                "last_error": result.get("error")})
    save_mode_config(cfg)


def get_status():
    cfg = load_mode_config()
    try:
        hw_log = json.loads(HW_LOG_FILE.read_text()) if HW_LOG_FILE.exists() else []
    except Exception:
        hw_log = []
    return {
        "operational_mode":  cfg.get("operational_mode"),
        "hardware_enabled":  cfg.get("hardware_enabled", False),
        "g99_active":        cfg.get("g99_active", False),
        "last_command":      cfg.get("last_command"),
        "last_command_ts":   cfg.get("last_command_ts"),
        "last_command_path": cfg.get("last_command_path"),
        "last_error":        cfg.get("last_error"),
        "control_paths": {
            "modbus_rtu":  bool(FOXESS_RS485_PORT),
            "modbus_tcp":  bool(FOXESS_MODBUS_HOST),
            "foxess_api":  bool(FOXESS_API_KEY and FOXESS_DEVICE_SN),
            "mqtt":        bool(MQTT_HOST),
        },
        "recent_commands": hw_log[-10:],
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--set-mode", choices=["pre_commissioning","self_consumption","full_export"])
    p.add_argument("--g99", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--mode", choices=["pre_commissioning","self_consumption","full_export"])
    a = p.parse_args()

    if a.status:
        print(json.dumps(get_status(), indent=2)); raise SystemExit(0)
    if a.set_mode:
        print(json.dumps(set_mode(a.set_mode, g99_active=a.g99 or None), indent=2)); raise SystemExit(0)
    if a.mode:
        os.environ["NODE3_MODE"] = a.mode
    if a.g99:
        os.environ["NODE3_G99_ACTIVE"] = "1"
    if a.dry_run:
        cfg    = load_mode_config()
        action = get_current_slot_action()
        cmd    = resolve_command(action, cfg.get("operational_mode","pre_commissioning"),
                                 cfg.get("g99_active", False))
        print(f"DRY RUN | mode={cfg.get('operational_mode')} action={action} "
              f"-> {cmd['work_mode']} {cmd['export_limit_w']}W | send={cmd['send']}")
    else:
        print(json.dumps(send_current_command(), indent=2))
