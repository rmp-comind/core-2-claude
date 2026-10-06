#!/usr/bin/env python3
# /// script
# dependencies = ["pyserial"]
# ///
"""Serial helpers for the Core2.

    serialtool.py PORT stop              Ctrl-C whatever is running, leave a REPL
    serialtool.py PORT monitor [SECS]    print console output (Ctrl-C to quit; SECS to stop after)
"""
import sys, time
import serial


def stop(port):
    with serial.Serial(port, 115200, timeout=0.3) as s:
        for _ in range(6):
            s.write(b"\x03")
            time.sleep(0.25)
        s.read(65536)


def monitor(port, secs=None):
    s = serial.Serial()
    s.port, s.baudrate, s.timeout = port, 115200, 0.3
    s.dtr = s.rts = False  # opening must not reset the board
    s.open()
    t0 = time.time()
    try:
        while secs is None or time.time() - t0 < secs:
            data = s.read(4096)
            if data:
                sys.stdout.write(data.decode("utf-8", "replace"))
                sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        s.close()


if __name__ == "__main__":
    port, cmd = sys.argv[1], sys.argv[2]
    if cmd == "stop":
        stop(port)
    elif cmd == "monitor":
        monitor(port, float(sys.argv[3]) if len(sys.argv) > 3 else None)
    else:
        sys.exit(__doc__)
