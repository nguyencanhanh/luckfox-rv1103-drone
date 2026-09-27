// Read the ?debug smoothness panel from a real (GPU) headless Chrome over the DevTools
// protocol and save a screenshot.  Fly something first (keyboard, or POST /input).
//   node simulator/probe_debug.mjs "http://127.0.0.1:8777/?watch&debug" [seconds] [out.png] [gpu]
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
import { writeFileSync } from "node:fs";
const [url, secs, shot, gpu] = [process.argv[2], +process.argv[3] || 10, process.argv[4] || "/tmp/probe.png", process.argv[5] === "gpu"];
const DBG = 9341;
const args = ["--headless=new", `--remote-debugging-port=${DBG}`, "--window-size=1400,820", "--user-data-dir=/tmp/lfx_probe_chrome", url];
if (!gpu) args.push("--use-angle=swiftshader", "--enable-unsafe-swiftshader");
const ch = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", args, { stdio: "ignore" });
let t; for (let i = 0; i < 50 && !t; i++) { await sleep(200); try { t = (await (await fetch(`http://127.0.0.1:${DBG}/json`)).json()).find(x => x.type === "page"); } catch {} }
const ws = new WebSocket(t.webSocketDebuggerUrl); let id = 0; const P = new Map();
ws.onmessage = m => { const d = JSON.parse(m.data); if (P.has(d.id)) { P.get(d.id)(d.result); P.delete(d.id); } };
await new Promise(r => ws.onopen = r);
const cdp = (method, params = {}) => new Promise(r => { const i = ++id; P.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await sleep(secs * 1000);
const r = await cdp("Runtime.evaluate", { expression: 'document.getElementById("dbg")?.textContent + "\\nGPU: " + (()=>{const g=document.createElement("canvas").getContext("webgl");const e=g.getExtension("WEBGL_debug_renderer_info");return e?g.getParameter(e.UNMASKED_RENDERER_WEBGL):"?"})()', returnByValue: true });
console.log(r.result.value);
const s = await cdp("Page.captureScreenshot", { format: "png" });
writeFileSync(shot, Buffer.from(s.data, "base64"));
ch.kill(); process.exit(0);
