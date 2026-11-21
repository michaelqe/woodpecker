// UI smoke test: drives the real viewer in headless Chrome over the DevTools protocol.
// Needs the server running (woodpecker serve) and Google Chrome. Run: node tests/ui_smoke.mjs
// It works on a throwaway copy of tv-cart (designs/ui-smoke.json) and deletes it after.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.env.WOODPECKER_URL || "http://127.0.0.1:8790";
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const api = async (path, body) => {
  const r = await fetch(BASE + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  return r.json();
};
let failures = 0;
const check = (ok, msg) => { console.log(`${ok ? "ok  " : "FAIL"} ${msg}`); if (!ok) failures++; };

const created = await api("/api/designs", { name: "ui-smoke", title: "UI smoke test", copy_from: "tv-cart" });
if (created.error) { console.error(created.error); process.exit(1); }

const profile = mkdtempSync(join(tmpdir(), "wp-chrome-"));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--window-size=1400,900", "about:blank"], { stdio: "ignore" });

try {
  let target;
  for (let i = 0; i < 50 && !target; i++) {
    try { target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?${BASE}/?design=ui-smoke&view=top`, { method: "PUT" })).json(); }
    catch { await sleep(200); }
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let id = 0;
  const pending = new Map();
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  });
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const evaluate = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description || "eval failed");
    return r.result?.result?.value;
  };
  const waitFor = async (expr, ms = 15000) => {
    for (const t = Date.now(); Date.now() - t < ms; await sleep(150)) if (await evaluate(expr)) return true;
    return false;
  };
  const screen = (x, y, z) => evaluate(`(() => {
    const V = wp.proxy.position.constructor, v = new V(${x}, ${y}, ${z}).project(wp.camera);
    const r = document.querySelector('#canvas').getBoundingClientRect();
    return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height];
  })()`);
  const click = async ([x, y]) => {
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
  };
  const part = async (pid) => (await api("/api/designs/ui-smoke")).design.parts.find((p) => p.id === pid);

  check(await waitFor("!!window.wp?.state.data"), "viewer loads the design");

  // ---- draw a board on the floor in front of the cart (top view)
  await evaluate("wp.setTool('board'); document.querySelector('#boardMat').value = 'ply18'; document.querySelector('#boardOrient').value = 'flat'; true");
  await click(await screen(100, -400, 0));
  await click(await screen(700, -100, 0));
  check(await waitFor("document.querySelector('#boardDlg').open", 3000), "board dialog opens after two clicks");
  await evaluate("document.querySelector('#bdName').value = 'Test shelf'; document.querySelector('#boardDlg button[value=ok]').click(); true");
  check(await waitFor("wp.state.data.design.parts.some((p) => p.id === 'test_shelf')"), "board is added to the design");
  const shelf = await part("test_shelf");
  check(shelf && shelf.size.join() === "600,300,18" && shelf.at.join() === "100,-400,0",
    `board size/position from the clicks (got ${shelf?.size} at ${shelf?.at})`);

  // ---- move a part with the gizmo's events
  await evaluate("wp.setTool('move'); wp.select('base_top'); true");
  await evaluate(`(() => { const t = wp.tcontrols; t.dispatchEvent({ type: 'dragging-changed', value: true });
    wp.proxy.position.x += 52; t.dispatchEvent({ type: 'objectChange' });
    t.dispatchEvent({ type: 'dragging-changed', value: false }); return true; })()`);
  check(await waitFor("wp.state.data.design.parts.find((p) => p.id === 'base_top').at[0] === 50"), "move snaps to 10 mm and saves");

  // ---- resize
  await evaluate("wp.setTool('size'); wp.select('base_top'); true");
  await evaluate(`(() => { const t = wp.tcontrols; t.dispatchEvent({ type: 'dragging-changed', value: true });
    wp.proxy.scale.y = 1.1; t.dispatchEvent({ type: 'objectChange' });
    t.dispatchEvent({ type: 'dragging-changed', value: false }); return true; })()`);
  check(await waitFor("wp.state.data.design.parts.find((p) => p.id === 'base_top').size[1] === 660"), "resize grows the part 60 mm deep");
  const raw = await (await fetch(`${BASE}/api/designs/ui-smoke`)).json();
  check(raw.design.params.length > 0, "design still resolves");

  // ---- holes are cut once Manifold arrives
  check(await waitFor("!!wp.state.wasm", 20000), "Manifold (WebAssembly) loads");

  const shot = await send("Page.captureScreenshot", { format: "png" });
  const out = join(tmpdir(), "woodpecker-ui-smoke.png");
  writeFileSync(out, Buffer.from(shot.result.data, "base64"));
  console.log(`screenshot: ${out}`);
  ws.close();
} finally {
  await fetch(`${BASE}/api/designs/ui-smoke/delete`, { method: "POST" }).catch(() => {});
  const exited = new Promise((r) => chrome.once("exit", r));
  chrome.kill();
  await Promise.race([exited, sleep(5000)]);
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch { /* temp dir */ }
}
process.exit(failures ? 1 : 0);
