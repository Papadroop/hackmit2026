// Headless Chrome screenshot over the DevTools protocol (Node 24 has a WebSocket client).
// usage: [VISION=achromatopsia] [MOTION=reduce] [CLIP=x,y,w,h] node snap.mjs <url> <out.png> [width] [height] [js expression to run before the shot]...
// CLIP shoots one CSS-pixel rectangle of the page instead of the viewport, for looking closely at a detail.
// MOTION=reduce emulates prefers-reduced-motion for the reduced-motion pass of ../../menu-design.md §14.
import { spawn } from "node:child_process"
import { writeFileSync, mkdtempSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

const [url, out, w = "1440", h = "900", ...steps] = process.argv.slice(2)
const port = 9333 + Math.floor(Math.random() * 500)
const profile = mkdtempSync(join(tmpdir(), "snap-"))
const chrome = spawn(
  process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ["--headless=new", `--remote-debugging-port=${port}`, "--no-first-run", "--no-default-browser-check",
   `--user-data-dir=${profile}`, `--window-size=${w},${h}`, "--hide-scrollbars", "about:blank"],
  { stdio: "ignore" },
)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
async function targets() {
  for (let i = 0; i < 60; i++) {
    try { return await (await fetch(`http://127.0.0.1:${port}/json`)).json() } catch { await sleep(250) }
  }
  throw new Error("chrome did not start")
}
try {
  const page = (await targets()).find((t) => t.type === "page")
  const ws = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j })
  let id = 0
  const pending = new Map()
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data)
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result) }
  }
  const send = (method, params = {}) => new Promise((res, rej) => { const mid = ++id; pending.set(mid, { res, rej }); ws.send(JSON.stringify({ id: mid, method, params })) })
  await send("Emulation.setDeviceMetricsOverride", { width: +w, height: +h, deviceScaleFactor: 2, mobile: false })
  await send("Page.enable")
  // VISION=achromatopsia|deuteranopia|protanopia|tritanopia|blurredVision renders the page as that viewer sees it.
  if (process.env.VISION) await send("Emulation.setEmulatedVisionDeficiency", { type: process.env.VISION })
  if (process.env.MOTION) await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: process.env.MOTION }] })
  await send("Page.navigate", { url })
  await sleep(2500)
  for (const js of steps) {
    const r = await send("Runtime.evaluate", { expression: js, awaitPromise: true, returnByValue: true })
    if (r.exceptionDetails) console.error("step failed:", js, r.exceptionDetails.text)
    else if (r.result?.value !== undefined) console.log("step:", r.result.value)
    await sleep(700)
  }
  const clip = process.env.CLIP?.split(",").map(Number)
  const shot = await send("Page.captureScreenshot", {
    format: "png",
    ...(clip ? { clip: { x: clip[0], y: clip[1], width: clip[2], height: clip[3], scale: 1 } } : {}),
  })
  writeFileSync(out, Buffer.from(shot.data, "base64"))
  console.log("wrote", out)
  ws.close()
} finally {
  chrome.kill()
}
