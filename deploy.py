#!/usr/bin/env python3
# /// script
# dependencies = ["pyserial"]
# ///
"""Upload the dashboard to a Core2 running UIFlow2 MicroPython.

    uv run deploy.py [--port /dev/cu.wchusbserial...]

Reads secrets from .env (CLAUDE_APIKEY, WIFI_SSID, WIFI_PASS, MY_IDS, TZ_OFFSET_MIN, CYCLE_S),
writes them to the device as /flash/secrets.py, uploads device/*, sets UIFlow's
boot_option to 0 (run main.py directly, skip the launcher) and resets the board.
"""
import argparse, glob, os, subprocess, sys, tempfile, time
import serial

ROOT = os.path.dirname(os.path.abspath(__file__))
FILES = ["net.py", "api.py", "ui.py", "ca.pem", "main.py"]


def env():
    vals = {}
    for line in open(os.path.join(ROOT, ".env")):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def interrupt(port):
    """Stop whatever is running (dashboard loop or UIFlow launcher) and leave a REPL."""
    with serial.Serial(port, 115200, timeout=0.3) as s:
        for _ in range(6):
            s.write(b"\x03")
            time.sleep(0.25)
        s.read(65536)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=(glob.glob("/dev/cu.wchusbserial*") + glob.glob("/dev/cu.usbserial*") + [None])[0])
    port = ap.parse_args().port
    if not port:
        sys.exit("No Core2 serial port found; pass --port")
    e = env()
    ids = tuple(s.strip() for s in e.get("MY_IDS", "").split(",") if s.strip())
    secrets = "ADMIN_KEY = %r\nWIFI_SSID = %r\nWIFI_PASS = %r\nMY_IDS = %r\nTZ_OFFSET_MIN = %d\nCYCLE_S = %s\n" % (
        e["CLAUDE_APIKEY"], e["WIFI_SSID"], e["WIFI_PASS"], ids, int(e.get("TZ_OFFSET_MIN", 0)),
        float(e.get("CYCLE_S", 15)))
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(secrets)
    try:
        interrupt(port)
        cmd = ["uvx", "mpremote", "connect", port, "resume", "exec", "pass"]
        cmd += ["+", "resume", "cp", f.name, ":/flash/secrets.py"]
        for name in FILES:
            cmd += ["+", "resume", "cp", os.path.join(ROOT, "device", name), ":/flash/" + name]
        cmd += ["+", "resume", "exec", "import esp32; n=esp32.NVS('uiflow'); n.set_u8('boot_option', 0); n.commit()"]
        cmd += ["+", "resume", "reset"]
        subprocess.run(cmd, check=True)
    finally:
        os.unlink(f.name)
    print("Deployed to", port)


if __name__ == "__main__":
    main()
