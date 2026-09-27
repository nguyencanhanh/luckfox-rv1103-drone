// End-to-end check of the 3D page with real key events, the way a person flies it:
// calibrate, arm, take off, altitude hold, fly forward, land, disarm.  Also the
// "clicked a button, then pressed Space" case that used to toggle ARM twice.
//
//   node simulator/e2e_keyboard.mjs          (needs Google Chrome and build/libsim)
//
// Starts its own server.py on a spare port, drives headless Chrome over the DevTools
// protocol (Node 22's built-in WebSocket), reads the simulator state from /events.
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
import { writeFileSync } from "node:fs";
import path from "node:path";

const HERE = path.dirname(new URL(import.meta.url).pathname);
const PORT = 8797, DBG = 9337;
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const srv = spawn("python3", [path.join(HERE, "server.py"), "--port", String(PORT)], { stdio: "ignore" });
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${DBG}`, "--use-angle=swiftshader",
  "--enable-unsafe-swiftshader", "--window-size=1400,820", "--user-data-dir=/tmp/lfx_e2e_chrome",
  `http://127.0.0.1:${PORT}/`], { stdio: "ignore" });
const done = (code) => { chrome.kill(); srv.kill(); process.exit(code); };

async function state() {
  const r = await fetch(`http://127.0.0.1:${PORT}/events`);
  const rd = r.body.getReader();
  let buf = "";
  while (!buf.includes("\n\n")) buf += new TextDecoder().decode((await rd.read()).value);
  rd.cancel();
  return JSON.parse(buf.slice(buf.indexOf("{"), buf.indexOf("\n\n")));
}

let ws, id = 0;
const pending = new Map();
function cdp(method, params = {}) {
  return new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
}
const KEYS = { " ": ["Space", 32], w: ["KeyW", 87], s: ["KeyS", 83], "2": ["Digit2", 50], h: ["KeyH", 72],
  c: ["KeyC", 67], ArrowUp: ["ArrowUp", 38] };
async function key(k, type) {
  const [code, vk] = KEYS[k];
  await cdp("Input.dispatchKeyEvent", { type, key: k, code, windowsVirtualKeyCode: vk });
}
async function press(k) { await key(k, "keyDown"); await sleep(40); await key(k, "keyUp"); }
async function hold(k, ms) { await key(k, "keyDown"); await sleep(ms); await key(k, "keyUp"); }

let fails = 0;
function check(ok, what, s) {
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${what}  (state ${s.state}, h ${(-s.z).toFixed(2)} m, crashed ${s.crashed})`);
  if (!ok) fails++;
}

try {
  let target;
  for (let i = 0; i < 50 && !target; i++) {
    await sleep(200);
    try { target = (await (await fetch(`http://127.0.0.1:${DBG}/json`)).json()).find((t) => t.type === "page"); } catch {}
  }
  ws = new WebSocket(target.webSocketDebuggerUrl);
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (pending.has(d.id)) { pending.get(d.id)(d.result); pending.delete(d.id); } };
  await new Promise((r) => (ws.onopen = r));
  await sleep(2500);                                   // page + three.js load, gyro calibration

  console.log("e2e: fly the 3D page with key events");
  await press("c"); await sleep(1500);
  // the old bug: click a button (it keeps focus), then Space
  await cdp("Runtime.evaluate", { expression: 'document.getElementById("bCam").click()' });
  await press(" "); await sleep(400);
  let s = await state();
  check(s.state === 1, "Space after clicking a button arms once", s);

  await hold("w", 2200); await sleep(800);
  s = await state();
  check(s.state === 1 && -s.z > 1.0, "W climbs off the pad", s);

  await press("2"); await press("h"); await sleep(1500);
  const h0 = -(await state()).z;
  await sleep(2000);
  s = await state();
  check(Math.abs(-s.z - h0) < 0.4, `ALT HOLD keeps height (${h0.toFixed(2)} m)`, s);

  await hold("ArrowUp", 1500);
  s = await state();
  check(Math.hypot(s.vx, s.vy) > 1.0, "arrow up flies forward", s);
  await sleep(1500);

  for (let i = 0; i < 40 && -(await state()).z > 0.02; i++) await hold("s", 500);
  await sleep(500);
  s = await state();
  check(-s.z < 0.05 && !s.crashed, "S in ALT HOLD lands without crashing", s);
  await press(" "); await sleep(400);
  s = await state();
  check(s.state === 0 && !s.crashed, "Space disarms on the ground", s);

  const shot = await cdp("Page.captureScreenshot", { format: "png" });
  writeFileSync("/tmp/lfx_e2e.png", Buffer.from(shot.data, "base64"));
  console.log(`e2e: ${fails} failed (screenshot /tmp/lfx_e2e.png)`);
  done(fails ? 1 : 0);
} catch (e) {
  console.error("e2e error:", e);
  done(2);
}
