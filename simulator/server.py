#!/usr/bin/env python3
"""Real-time bridge between the C simulator (build/libsim) and the 3D page.

    make run                      (or: python3 server.py [--port 8777] [--vib])
    then open http://127.0.0.1:8777

The flight code that runs here is the same C that the MCU builds; this file
only paces it against the wall clock (50 steps of 20 ms per second, each
step = 20 loop ticks at 1 kHz) and moves numbers between it and the browser:

    GET  /           the page (web/index.html)
    GET  /events     server-sent events, the state at ~30 Hz
    POST /input      sticks, switches and fault buttons as JSON

Standard library only, bound to 127.0.0.1.
"""

import argparse
import ctypes
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "build", "libsim.dylib" if sys.platform == "darwin" else "libsim.so")
WEB = os.path.join(HERE, "web")


class Sim:
    def __init__(self, vib):
        if not os.path.exists(LIB):
            sys.exit("build the library first: make -C %s" % HERE)
        self.lib = ctypes.CDLL(LIB)
        L = self.lib
        L.sim_init.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int]
        L.sim_set_pilot.argtypes = [ctypes.c_void_p] + [ctypes.c_float] * 4 + [ctypes.c_int] * 2
        L.sim_set_faults.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        L.sim_set_wind.argtypes = [ctypes.c_void_p] + [ctypes.c_float] * 3
        L.sim_step.argtypes = [ctypes.c_void_p, ctypes.c_int]
        L.sim_state_names.restype = ctypes.c_char_p
        L.sim_get_state.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int]
        L.sim_request_level_calibration.argtypes = [ctypes.c_void_p]
        L.sim_sizeof.restype = ctypes.c_ulong
        self.names = L.sim_state_names().decode().split(",")
        self.buf = (ctypes.c_float * 128)()
        self.size = L.sim_sizeof()
        self.mem = ctypes.create_string_buffer(self.size)
        self.vib = vib
        self.lock = threading.Lock()
        self.inp = {}
        self.reset()

    def reset(self, seed=None):
        with self.lock:
            ctypes.memset(self.mem, 0, self.size)
            self.lib.sim_init(self.mem, seed or int(time.time()) & 0xFFFF, 0 if self.vib else 1)
            self.inp = {"roll": 0, "pitch": 0, "yaw": 0, "throttle": 0, "arm": 0, "mode": 0,
                        "link_cut": 0, "imu_fail": 0, "wind": 0}
            self.calibrate_pending = True

    def apply_input(self, d):
        with self.lock:
            self.inp.update({k: d[k] for k in d if k in self.inp})
            if d.get("calibrate"):
                self.calibrate_pending = True

    def step(self, ticks):
        with self.lock:
            i = self.inp
            L = self.lib
            L.sim_set_pilot(self.mem, float(i["roll"]), float(i["pitch"]), float(i["yaw"]),
                            float(i["throttle"]), int(i["arm"]), int(i["mode"]))
            L.sim_set_faults(self.mem, int(i["link_cut"]), int(i["imu_fail"]))
            w = float(i["wind"])
            # speed w from the north-north-east, gusts 40 % of it
            L.sim_set_wind(self.mem, w * 0.894, w * 0.447, w * 0.4)
            if self.calibrate_pending:
                L.sim_request_level_calibration(self.mem)
                self.calibrate_pending = False
            L.sim_step(self.mem, ticks)

    def state(self):
        with self.lock:
            n = self.lib.sim_get_state(self.mem, self.buf, len(self.buf))
            return {self.names[k]: round(self.buf[k], 5) for k in range(n)}


def make_handler(sim):
    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                body = open(os.path.join(WEB, "index.html"), "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    while True:
                        self.wfile.write(b"data: " + json.dumps(sim.state()).encode() + b"\n\n")
                        self.wfile.flush()
                        time.sleep(1 / 30)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/input":
                self.send_error(404)
                return
            n = int(self.headers.get("Content-Length", 0))
            try:
                d = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                self.send_error(400)
                return
            if d.get("reset"):
                sim.reset()
            else:
                sim.apply_input(d)
            self.send_response(204)
            self.end_headers()

    return H


def pace(sim):
    period, ticks = 0.02, 20
    nxt = time.monotonic()
    while True:
        sim.step(ticks)
        nxt += period
        delay = nxt - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            nxt = time.monotonic()      # fell behind: do not try to catch up


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--vib", action="store_true", help="add the ASSUMED frame vibration")
    a = ap.parse_args()
    sim = Sim(a.vib)
    threading.Thread(target=pace, args=(sim,), daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(sim))
    srv.daemon_threads = True
    print("simulator on http://127.0.0.1:%d  (Ctrl-C to stop)" % a.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
