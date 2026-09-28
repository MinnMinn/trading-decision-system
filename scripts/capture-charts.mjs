// Screenshot every drawn chart of a built chart artifact (scripts/build-artifact.py), one PNG per
// (chart block, method lane), for visual review -- owner request 2026-09-28: "capture the chart you drew and let
// another subagent judge from the image whether it is drawn to spec". Chrome DevTools Protocol only: no npm deps.
//
// usage: node scripts/capture-charts.mjs <page.html> <outdir> [chromePath]
// writes <outdir>/<block-id>.<lane>.png and <outdir>/manifest.json [{id, lane, file, title, legend}].
// A lane is captured only where the page itself draws it (its .chart-wrap is not hidden) -- this reports what a
// reader sees, it never forces an undrawn lane visible.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [page, outdir, chromeArg] = process.argv.slice(2);
if (!page || !outdir) { console.error("usage: node scripts/capture-charts.mjs <page.html> <outdir> [chromePath]"); process.exit(1); }
const chrome = chromeArg || process.env.CHROME || (process.platform === "win32"
  ? "C:/Program Files/Google/Chrome/Application/chrome.exe" : "google-chrome");
mkdirSync(outdir, { recursive: true });
const port = 9300 + Math.floor(Math.random() * 500);
const prof = mkdtempSync(join(tmpdir(), "cap-"));
const proc = spawn(chrome, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`,
  `--user-data-dir=${prof}`, "--window-size=1600,1000", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let targets;
for (let i = 0; i < 50; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); if (targets.length) break; } catch {}
  await sleep(200);
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0; const pending = new Map();
ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;

await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: pathToFileURL(resolve(page)).href });
await sleep(4000);
await ev(`document.documentElement.style.scrollBehavior='auto'`);
const ids = await ev(`[...document.querySelectorAll('.chart-block')].map(b => b.id)`);
const manifest = [];
for (const lane of ["wyckoff", "ict", "footprint", "heatmap"]) {
  await ev(`setLane(${JSON.stringify(lane)})`);
  await sleep(800);
  for (const bid of ids) {
    const q = `document.getElementById(${JSON.stringify(bid)})`;
    if (await ev(`${q}.querySelector('.chart-wrap').hidden`)) continue;
    await ev(`${q}.scrollIntoView({block:'center', behavior:'instant'})`);
    await sleep(900);
    const box = await ev(`(() => { const b = ${q}, r = b.getBoundingClientRect();
      return {x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height, title: b.querySelector('.chart-title')?.innerText,
              legend: document.getElementById('legend-' + b.id.split('-').slice(1).join('-'))?.innerText || null}; })()`);
    const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      clip: { x: box.x, y: box.y, width: box.w, height: box.h, scale: 1 } });
    const file = join(outdir, `${bid}.${lane}.png`);
    writeFileSync(file, Buffer.from(shot.result.data, "base64"));
    manifest.push({ id: bid, lane, file, title: box.title, legend: box.legend });
  }
}
writeFileSync(join(outdir, "manifest.json"), JSON.stringify(manifest, null, 1));
console.log(`captured ${manifest.length} chart block(s) -> ${outdir}`);
ws.close(); proc.kill();
process.exit(0);
