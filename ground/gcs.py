#!/usr/bin/env python3
"""Ground station: fly the drone from a browser, see its camera and telemetry.

    # real drone over the USB-ECM link (board at 172.32.0.93, rc-bridge running there)
    python3 ground/gcs.py --drone 172.32.0.93 --video rtsp://172.32.0.93/live/1

    # simulator playing the drone (see ground/README.md)
    python3 ground/gcs.py --drone 127.0.0.1 --video sim

then open http://127.0.0.1:8780

    browser --POST /input 50 Hz--> gcs.py --CRSF RC frames, UDP 50 Hz--> rc-bridge (drone)
    browser <--SSE /events---------  gcs.py <--CRSF telemetry, UDP 20 Hz-- rc-bridge
    browser <--/video.mjpg (MJPEG)-  gcs.py <--ffmpeg <--RTSP H.265------- rkipc (drone camera)

Safety: RC frames go out only while the page keeps sending input (a closed tab or a
frozen browser stops them within 0.2 s, and the drone's own RC timeout then runs the
failsafe), and the ARM channel stays low until the page's arm lock is opened.
Standard library only (+ ffmpeg for video).
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import crsf  # noqa: E402

INPUT_STALE_S = 0.2          # browser silent this long: stop sending RC
RC_HZ = 50


class Link:
    """UDP to / from rc-bridge on the drone."""

    def __init__(self, drone, port):
        self.addr = (drone, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.settimeout(0.2)
        self.lock = threading.Lock()
        self.inp = {"roll": 0, "pitch": 0, "yaw": 0, "throttle": 0, "arm": 0, "mode": 0,
                    "unlocked": 0}
        self.inp_t = 0.0
        self.tel = {}
        self.tel_t = 0.0
        self.attitude = None
        self.flight_mode = ""
        self.sent = 0
        self.rx = 0

    def set_input(self, d):
        with self.lock:
            for k in self.inp:
                if k in d:
                    self.inp[k] = d[k]
            self.inp_t = time.monotonic()

    def channels(self):
        """Sticks -> CRSF ticks in the drone's default map (shared/rc/rc_map.c, AETR)."""
        i = self.inp
        us = [1500] * 16
        us[0] = 1500 + 500 * max(-1, min(1, float(i["roll"])))
        us[1] = 1500 + 500 * max(-1, min(1, float(i["pitch"])))
        us[2] = 1000 + 1000 * max(0, min(1, float(i["throttle"])))
        us[3] = 1500 + 500 * max(-1, min(1, float(i["yaw"])))
        armed = int(i["arm"]) and int(i["unlocked"])
        us[4] = 2000 if armed else 1000                      # AUX1 arm
        us[5] = (1000, 1500, 2000)[max(0, min(2, int(i["mode"])))]  # AUX2: ANGLE/ALT/ACRO
        return [crsf.us_to_ticks(u) for u in us]

    def tx_loop(self):
        period = 1.0 / RC_HZ
        nxt = time.monotonic()
        while True:
            with self.lock:
                fresh = time.monotonic() - self.inp_t < INPUT_STALE_S
                frame = crsf.pack_channels(self.channels()) if fresh else None
            if frame:
                try:
                    self.sock.sendto(frame, self.addr)
                    self.sent += 1
                except OSError:
                    pass
            nxt += period
            time.sleep(max(0.0, nxt - time.monotonic()))

    def rx_loop(self):
        while True:
            try:
                buf, _ = self.sock.recvfrom(1024)
            except (socket.timeout, OSError):
                continue
            for typ, pl in crsf.frames(buf):
                with self.lock:
                    self.rx += 1
                    if typ == crsf.LFX_STATUS:
                        t = crsf.parse_status(pl)
                        if t:
                            self.tel, self.tel_t = t, time.monotonic()
                    elif typ == crsf.FLIGHT_MODE:
                        self.flight_mode = pl.split(b"\0")[0].decode(errors="replace")

    def snapshot(self):
        with self.lock:
            age = time.monotonic() - self.tel_t if self.tel_t else None
            return {"tel": self.tel, "tel_age": age, "flight_mode": self.flight_mode,
                    "sent": self.sent, "rx": self.rx, "inp": dict(self.inp),
                    "sending": time.monotonic() - self.inp_t < INPUT_STALE_S}


class Video:
    """RTSP (H.265 from rkipc) -> MJPEG for <img>, through one ffmpeg process."""

    def __init__(self, url, fps=25, width=704):
        self.url, self.fps, self.width = url, fps, width
        self.frame = None
        self.cv = threading.Condition()
        self.status = "đang kết nối"

    def run(self):
        while True:
            # live camera: no input buffering.  "-flags low_delay" broke HEVC decoding
            # in the offline test (lost references, ~half the frames), so it is not
            # used; whether rkipc's stream tolerates it is UNKNOWN until tried.
            src = (["-fflags", "nobuffer", "-rtsp_transport", "tcp"] if self.url.startswith("rtsp://")
                   else ["-re", "-stream_loop", "-1"])
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"] + src + [
                   "-i", self.url, "-an", "-vf", "scale=%d:-2" % self.width,
                   "-r", str(self.fps), "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg", "-"]
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            except FileNotFoundError:
                self.status = "không có ffmpeg (brew install ffmpeg)"
                return
            buf = b""
            while True:
                chunk = p.stdout.read1(65536)   # whatever is there: read() would wait for 64 KB = 3-4 frames
                if not chunk:
                    break
                buf += chunk
                while True:                     # split the JPEG stream at SOI/EOI
                    s = buf.find(b"\xff\xd8")
                    e = buf.find(b"\xff\xd9", s + 2)
                    if s < 0 or e < 0:
                        break
                    with self.cv:
                        self.frame = buf[s:e + 2]
                        self.status = "ok"
                        self.cv.notify_all()
                    buf = buf[e + 2:]
            p.wait()
            self.status = "mất video, thử lại"
            time.sleep(1.0)


def make_handler(link, video, video_mode, sim_url):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                body = open(os.path.join(HERE, "web", "index.html"), "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            elif path == "/config":
                cfg = {"video": video_mode, "sim_url": sim_url, "drone": "%s:%d" % link.addr}
                body = json.dumps(cfg).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            elif path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    while True:
                        s = link.snapshot()
                        s["video_status"] = video.status if video else None
                        self.wfile.write(b"data: " + json.dumps(s).encode() + b"\n\n")
                        self.wfile.flush()
                        time.sleep(0.05)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            elif path == "/video.mjpg" and video:
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                last = None
                try:
                    while True:
                        with video.cv:
                            video.cv.wait_for(lambda: video.frame is not last, 2.0)
                            last = video.frame
                        if last is None:
                            continue
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(last)).encode() + b"\r\n\r\n" + last + b"\r\n")
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
                link.set_input(json.loads(self.rfile.read(n) or b"{}"))
            except ValueError:
                self.send_error(400)
                return
            self.send_response(204)
            self.end_headers()

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--drone", default="172.32.0.93", help="address of the drone's rc-bridge")
    ap.add_argument("--drone-port", type=int, default=7700)
    ap.add_argument("--video", default="rtsp://172.32.0.93/live/1",
                    help="rtsp://... (drone camera, /live/1 = 704x576 sub-stream), 'sim' "
                         "(the simulator's FPV view) or 'none'")
    ap.add_argument("--sim-url", default="http://127.0.0.1:8777/?watch&bare&cam=2")
    ap.add_argument("--port", type=int, default=8780)
    a = ap.parse_args()

    link = Link(a.drone, a.drone_port)
    threading.Thread(target=link.tx_loop, daemon=True).start()
    threading.Thread(target=link.rx_loop, daemon=True).start()
    video = None
    mode = "none"
    if a.video.startswith("rtsp://") or os.path.isfile(a.video):   # a file: offline test
        video = Video(a.video)
        threading.Thread(target=video.run, daemon=True).start()
        mode = "mjpeg"
    elif a.video == "sim":
        mode = "sim"
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(link, video, mode, a.sim_url))
    srv.daemon_threads = True
    print("ground station on http://127.0.0.1:%d  ->  drone %s:%d, video %s"
          % (a.port, a.drone, a.drone_port, a.video))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
