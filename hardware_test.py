#!/usr/bin/env python3
"""
hardware_test.py — NODE-3 LV Component Verification
====================================================
Run this DIRECTLY on the Pi (NOT in Docker) to verify each piece of
LV hardware before touching anything HV.

Usage:
    python3 hardware_test.py            # run all tests
    python3 hardware_test.py --mqtt     # MQTT SOC subscription only (blocking)
    python3 hardware_test.py --modbus   # RS485 port test only

Prerequisites (run once on Pi):
    pip3 install paho-mqtt pymodbus pyserial --break-system-packages
"""

import sys, os, time, json, argparse, subprocess
from datetime import datetime

MQTT_HOST  = os.environ.get("MQTT_HOST", "localhost")   # Pi's own Mosquitto
MQTT_PORT  = int(os.environ.get("MQTT_PORT", "1883"))
BATT_TOPIC = os.environ.get("BATTERY_EMULATOR_MQTT_TOPIC", "battery-emulator")
RS485_PORT = os.environ.get("FOXESS_RS485_PORT", "/dev/ttyUSB0")
MODBUS_ADDR = int(os.environ.get("FOXESS_MODBUS_ADDR", "247"))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m→\033[0m"
WARN = "\033[93m!\033[0m"


def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ── TEST 1: USB device detection ─────────────────────────────────────────────

def test_usb_devices():
    section("TEST 1: USB serial devices")
    import glob
    devices = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    if not devices:
        print(f"  {FAIL}  No USB serial devices found")
        print(f"  {INFO}  Plug in JZK USB-RS485 adapter and/or T-2CAN USB and re-run")
        return False

    print(f"  {PASS}  Found {len(devices)} USB serial device(s):")
    for d in devices:
        try:
            result = subprocess.run(
                ["udevadm", "info", "--query=property", "--name", d],
                capture_output=True, text=True, timeout=5
            )
            vendor = ""
            for line in result.stdout.splitlines():
                if "ID_VENDOR=" in line:
                    vendor = line.split("=", 1)[1]
            print(f"        {d}  {vendor}")
        except Exception:
            print(f"        {d}")

    # Check /dev/serial/by-id for stable names
    by_id = sorted(glob.glob("/dev/serial/by-id/*"))
    if by_id:
        print(f"\n  {INFO}  Stable /dev/serial/by-id names (use these in production):")
        for s in by_id:
            target = os.path.realpath(s)
            print(f"        {s}")
            print(f"            → {target}")

    return True


# ── TEST 2: Docker containers running ────────────────────────────────────────

def test_docker():
    section("TEST 2: Docker containers")
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=10
        )
        lines = [l for l in result.stdout.strip().splitlines() if l]
        if not lines:
            print(f"  {FAIL}  No containers running")
            print(f"  {INFO}  Run: docker compose -f docker-compose.yml -f docker-compose.pi.yml up -d")
            return False

        expected = {"node3-portal", "node3-mosquitto"}
        running = set()
        for line in lines:
            name = line.split("\t")[0]
            running.add(name)
            status = line.split("\t")[1] if "\t" in line else ""
            icon = PASS if "Up" in status else FAIL
            print(f"  {icon}  {line}")

        missing = expected - running
        for m in missing:
            print(f"  {FAIL}  {m} is NOT running — check docker compose logs")

        return len(missing) == 0

    except FileNotFoundError:
        print(f"  {FAIL}  Docker not found — is it installed?")
        return False
    except Exception as e:
        print(f"  {FAIL}  {e}")
        return False


# ── TEST 3: MQTT broker reachable ────────────────────────────────────────────

def test_mqtt_broker():
    section("TEST 3: MQTT broker (Mosquitto)")
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print(f"  {FAIL}  paho-mqtt not installed")
        print(f"  {INFO}  pip3 install paho-mqtt --break-system-packages")
        return False

    connected = []

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            connected.append(True)
        else:
            connected.append(False)

    client = mqtt.Client(client_id="hw-test-ping", clean_session=True)
    client.on_connect = on_connect
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=5)
        client.loop_start()
        time.sleep(2)
        client.loop_stop()
        client.disconnect()
    except Exception as e:
        print(f"  {FAIL}  Cannot connect to {MQTT_HOST}:{MQTT_PORT} — {e}")
        print(f"  {INFO}  Is node3-mosquitto container running? (see test 2)")
        return False

    if connected and connected[0]:
        print(f"  {PASS}  Mosquitto broker at {MQTT_HOST}:{MQTT_PORT} — reachable")
        return True
    else:
        print(f"  {FAIL}  Mosquitto connect rejected")
        return False


# ── TEST 4: Battery-Emulator MQTT subscription ───────────────────────────────

def test_mqtt_soc(timeout=30):
    section(f"TEST 4: Battery-Emulator MQTT SOC (waiting up to {timeout}s)")
    print(f"  {INFO}  Subscribing to '{BATT_TOPIC}' on {MQTT_HOST}:{MQTT_PORT}")
    print(f"  {INFO}  Power on T-2CAN if not already on — waiting...")

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print(f"  {FAIL}  paho-mqtt not installed")
        return False

    received = []

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(BATT_TOPIC)
            print(f"  {INFO}  Connected — waiting for Battery-Emulator message...")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            received.append(payload)
        except Exception:
            received.append({"raw": msg.payload.decode()})

    client = mqtt.Client(client_id="hw-test-soc", clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
        client.loop_start()
        deadline = time.time() + timeout
        while time.time() < deadline and not received:
            time.sleep(1)
            remaining = int(deadline - time.time())
            print(f"\r  {INFO}  Waiting... {remaining}s remaining", end="", flush=True)
        client.loop_stop()
        client.disconnect()
        print()
    except Exception as e:
        print(f"\n  {FAIL}  MQTT error: {e}")
        return False

    if not received:
        print(f"  {FAIL}  No message received in {timeout}s")
        print(f"  {INFO}  Check T-2CAN is:")
        print(f"          1. Powered (USB to Pi or separate 5V)")
        print(f"          2. WiFi configured (SSID/password set via AP mode)")
        print(f"          3. MQTT server = this Pi's IP (not 'localhost' — use actual IP)")
        print(f"          4. MQTT topic = '{BATT_TOPIC}'")
        pi_ip = get_pi_ip()
        if pi_ip:
            print(f"  {INFO}  This Pi's IP appears to be: {pi_ip}")
        return False

    payload = received[0]
    print(f"  {PASS}  Battery-Emulator message received!")
    for k, v in payload.items():
        print(f"          {k}: {v}")

    soc = payload.get("SOC") or payload.get("soc")
    if soc is not None:
        soc_kwh = round(float(soc) / 100.0 * 72.0, 2)
        print(f"\n  {PASS}  SOC: {soc}%  =  {soc_kwh} kWh  (72 kWh nominal)")
        if float(soc) < 1:
            print(f"  {WARN}  SOC is 0% — BMS may not be powered or CAN not connected")
    else:
        print(f"  {WARN}  No SOC field in payload — check Battery-Emulator config")

    return True


# ── TEST 5: RS485 port open ───────────────────────────────────────────────────

def test_rs485():
    section("TEST 5: JZK USB-RS485 adapter (Modbus RTU path)")
    try:
        import serial
    except ImportError:
        print(f"  {FAIL}  pyserial not installed")
        print(f"  {INFO}  pip3 install pyserial --break-system-packages")
        return False

    if not os.path.exists(RS485_PORT):
        print(f"  {FAIL}  {RS485_PORT} does not exist")
        print(f"  {INFO}  Plug JZK USB-RS485 into Pi and check with:  ls /dev/ttyUSB*")
        return False

    try:
        s = serial.Serial(RS485_PORT, baudrate=9600, bytesize=8,
                          parity="N", stopbits=1, timeout=1)
        s.close()
        print(f"  {PASS}  {RS485_PORT} opened successfully at 9600/8N1")
        print(f"  {INFO}  FoxESS inverter is NOT connected yet — that's fine for this test")
        print(f"  {INFO}  Wiring when ready:")
        print(f"          JZK A+ → FoxESS RS485 COM port A")
        print(f"          JZK B- → FoxESS RS485 COM port B")
        print(f"          JZK GND → FoxESS GND")
        return True
    except serial.SerialException as e:
        print(f"  {FAIL}  Cannot open {RS485_PORT}: {e}")
        print(f"  {INFO}  Try:  sudo chmod 666 {RS485_PORT}")
        print(f"  {INFO}  Or add pi user to dialout:  sudo usermod -a -G dialout pi")
        return False


# ── TEST 6: Modbus RTU send (only if FoxESS is powered) ─────────────────────

def test_modbus_rtu():
    section("TEST 6: Modbus RTU — read work mode register (requires FoxESS powered)")
    print(f"  {WARN}  This test only makes sense when FoxESS inverter is ON (HV connected)")
    print(f"  {INFO}  Skipping active Modbus read — run hardware_bridge.py --status instead")
    print(f"  {INFO}  Command:  python3 hardware_bridge.py --status")
    print(f"  {INFO}  Dry run:  python3 hardware_bridge.py --dry-run")
    return None  # not applicable at LV stage


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_pi_ip():
    try:
        result = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=5
        )
        ips = result.stdout.strip().split()
        # Return first non-loopback IPv4
        return next((ip for ip in ips if ip.startswith(("192.", "10.", "172."))), None)
    except Exception:
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Node-3 LV hardware verification")
    parser.add_argument("--mqtt",   action="store_true", help="MQTT SOC subscription only (blocking 60s)")
    parser.add_argument("--modbus", action="store_true", help="RS485 port test only")
    parser.add_argument("--all",    action="store_true", help="Run all tests (default)")
    args = parser.parse_args()

    print(f"\n{'═'*60}")
    print(f"  NODE-3 LV Hardware Test  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*60}")

    pi_ip = get_pi_ip()
    if pi_ip:
        print(f"  Pi IP: {pi_ip}  (use this as MQTT broker IP in T-2CAN config)")
    print(f"  RS485 port: {RS485_PORT}")
    print(f"  MQTT broker: {MQTT_HOST}:{MQTT_PORT}")
    print(f"  Battery-Emulator topic: {BATT_TOPIC}")

    if args.mqtt:
        test_mqtt_broker()
        test_mqtt_soc(timeout=60)
        return
    if args.modbus:
        test_usb_devices()
        test_rs485()
        return

    # Default: run all
    results = {}
    results["usb"]     = test_usb_devices()
    results["docker"]  = test_docker()
    results["mqtt"]    = test_mqtt_broker()
    results["soc"]     = test_mqtt_soc(timeout=30)
    results["rs485"]   = test_rs485()
    test_modbus_rtu()

    # Summary
    section("SUMMARY")
    all_pass = True
    for name, result in results.items():
        if result is True:
            print(f"  {PASS}  {name}")
        elif result is False:
            print(f"  {FAIL}  {name}")
            all_pass = False
        else:
            print(f"  {WARN}  {name} (skipped)")

    print()
    if all_pass:
        print(f"  {PASS}  All LV tests passed — ready to wire CAN-A to Nissan Yazaki fly lead")
    else:
        print(f"  {WARN}  Fix the failures above before proceeding to CAN wiring")

    print()


if __name__ == "__main__":
    main()
