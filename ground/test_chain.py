#!/usr/bin/env python3
"""End-to-end remote-control test, all on this computer:

  this script (as the browser) -> ground/gcs.py -> UDP CRSF -> linux/rc-bridge (host build)
    -> fc_ipc page (file) -> simulator/server.py --ipc (the flight core + physics)
    -> telemetry back the same way

Checks: arm only after the lock is opened, take off, ALT_HOLD, telemetry round trip,
and that a ground station that goes silent mid-air makes the drone fail-safe and land.

    make -C simulator && make -C linux/rc-bridge
    python3 ground/test_chain.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IPC = "/tmp/lfx_ipc_test.bin"
SIM_PORT, GCS_PORT, UDP_PORT = 8791, 8781, 7711
procs = []
fails = 0


def start(*cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    return p


def sse(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        for line in r:
            if line.startswith(b"data: "):
                return json.loads(line[6:])


def sim_state():
    return sse("http://127.0.0.1:%d/events" % SIM_PORT)


def gcs_state():
    return sse("http://127.0.0.1:%d/events" % GCS_PORT)


def fly(seconds, **inp):
    """Be the browser: post the sticks at 50 Hz for `seconds`."""
    body = dict({"roll": 0, "pitch": 0, "yaw": 0, "throttle": 0, "arm": 0, "mode": 0,
                 "unlocked": 0}, **inp)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        req = urllib.request.Request("http://127.0.0.1:%d/input" % GCS_PORT,
                                     data=json.dumps(body).encode(), method="POST")
        urllib.request.urlopen(req, timeout=1).read()
        time.sleep(0.02)


def check(ok, what, s):
    global fails
    print("  %s  %s  (state %s, h %.2f m, crashed %s)" % (
        "PASS" if ok else "FAIL", what, int(s["state"]), -s["z"], int(s["crashed"])))
    if not ok:
        fails += 1


def main():
    if os.path.exists(IPC):
        os.remove(IPC)
    start(sys.executable, os.path.join(ROOT, "simulator", "server.py"),
          "--port", str(SIM_PORT), "--ipc", IPC)
    time.sleep(1.5)
    start(os.path.join(ROOT, "linux", "rc-bridge", "build", "rc-bridge"),
          "--shm", IPC, "--udp", str(UDP_PORT))
    start(sys.executable, os.path.join(ROOT, "ground", "gcs.py"), "--drone", "127.0.0.1",
          "--drone-port", str(UDP_PORT), "--video", "none", "--port", str(GCS_PORT))
    time.sleep(1.5)
    print("remote-control chain: gcs -> UDP -> rc-bridge -> IPC -> flight core")

    fly(2.0)                                              # gyro calibration, link up
    g = gcs_state()
    s = sim_state()
    check(g["tel_age"] is not None and g["tel_age"] < 0.5 and g["tel"].get("calib_done") == 1,
          "telemetry reaches the ground station", s)
    check(int(g["tel"].get("rc_source", 0)) == 2, "drone reports the network as RC source", s)

    fly(0.5, arm=1)                                       # lock still closed
    s = sim_state()
    check(s["state"] == 0, "ARM switch ignored while the ground-station lock is closed", s)
    fly(0.3, unlocked=1)
    fly(0.5, unlocked=1, arm=1)
    s = sim_state()
    check(s["state"] == 1, "arms after unlocking", s)

    fly(1.5, unlocked=1, arm=1, throttle=0.62)
    fly(3.0, unlocked=1, arm=1, throttle=0.5, mode=1)
    s = sim_state()
    h1 = -s["z"]
    fly(2.0, unlocked=1, arm=1, throttle=0.5, mode=1)
    s = sim_state()
    check(h1 > 1.5 and abs(-s["z"] - h1) < 0.3, "takes off and holds height (%.2f m)" % h1, s)
    g = gcs_state()
    check(abs(g["tel"]["height_cm"] / 100.0 - (-s["z"])) < 0.6,
          "telemetry height %.2f m matches the drone" % (g["tel"]["height_cm"] / 100.0), s)

    # the ground station goes silent (closed tab / crashed laptop)
    t0 = time.monotonic()
    states = set()
    while time.monotonic() - t0 < 45:
        s = sim_state()
        states.add(int(s["state"]))
        if s["state"] == 0:
            break
        time.sleep(0.1)
    check(2 in states and 3 in states and s["state"] == 0 and not s["crashed"]
          and -s["z"] < 0.05, "silent ground station: failsafe hold -> land -> disarm", s)

    print("chain test: %d failed" % fails)


if __name__ == "__main__":
    try:
        main()
    finally:
        for p in procs:
            p.terminate()
    sys.exit(1 if fails else 0)
