// UI smoke test: drives the real viewer in headless Chrome over the DevTools protocol.
// Needs the server running (woodpecker serve) and Google Chrome. Run: node tests/ui_smoke.mjs
// It works on a throwaway copy of tv-cart (designs/ui-smoke.json) and deletes it after.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.WOODPECKER_URL || "http://127.0.0.1:8790";
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const api = async (path, body) => {
  const r = await fetch(BASE + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  return r.json();
};
let failures = 0;
const imported = [];  // catalog files this run created, removed at the end
const REPO = join(dirname(fileURLToPath(import.meta.url)), "..");
const check = (ok, msg) => { console.log(`${ok ? "ok  " : "FAIL"} ${msg}`); if (!ok) failures++; };

const created = await api("/api/designs", { name: "ui-smoke", title: "UI smoke test", copy_from: "tv-cart" });
if (created.error) { console.error(created.error); process.exit(1); }

const profile = mkdtempSync(join(tmpdir(), "wp-chrome-"));
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--window-size=1400,900", "about:blank"], { stdio: "ignore" });

try {
  let target;
  for (let i = 0; i < 50 && !target; i++) {
    try { target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json(); }
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

  // open the page ourselves: newer Chrome ignores the URL given to /json/new
  await send("Page.navigate", { url: `${BASE}/?design=ui-smoke&view=top` });
  check(await waitFor("!!window.wp?.state.data"), "viewer loads the design");

  // ---- draw a board on the floor in front of the cart (top view)
  await evaluate("wp.setTool('board'); document.querySelector('#boardMat').value = 'ply18'; document.querySelector('#boardOrient').value = 'flat'; true");
  // zoom out (− key) so the spot in front of the cart is on screen below the header
  const z = await evaluate("wp.camera.zoom");
  for (let i = 0; i < 3; i++) await send("Input.dispatchKeyEvent", { type: "keyDown", key: "-", text: "-" });
  check(await evaluate(`wp.camera.zoom < ${z}`), "− zooms out");
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

  // ---- layers: hide a group, solo a material, all back on
  await evaluate("document.querySelector('#layersBody').hidden && document.querySelector('#layersBtn').click(); true");
  check(await waitFor("document.querySelectorAll('#layersBody [data-layer=groups]').length > 0", 3000), "layers panel lists the groups");
  const grp = await evaluate("document.querySelector('#layersBody [data-layer=groups]').dataset.key");
  await evaluate("document.querySelector('#layersBody [data-layer=groups]').click(); true");
  check(await evaluate(`[...wp.meshes().values()].every(({ mesh, part }) => mesh.visible === ((part.group || 'Parts') !== ${JSON.stringify(grp)}))`),
    `unticking group "${grp}" hides exactly its parts`);
  check(await evaluate(`JSON.parse(localStorage.getItem('wp.layers.ui-smoke')).groups[${JSON.stringify(grp)}] === false`), "layer choice is remembered");
  await evaluate("document.querySelector('#layersBody [data-all=\"1\"]').click(); true");
  const mat = await evaluate("document.querySelector('#layersBody [data-solo=mats]')?.dataset.key ?? null");
  if (mat) {
    await evaluate("document.querySelector('#layersBody [data-solo=mats]').click(); true");
    check(await evaluate(`[...wp.meshes().values()].every(({ mesh, part }) => mesh.visible === ((part.component ? 'Products' : part.material) === ${JSON.stringify(mat)}))`),
      `clicking material "${mat}" shows only it`);
    await evaluate("document.querySelector('#layersBody [data-solo=mats]').click(); true");
  }
  check(await evaluate("[...wp.meshes().values()].every(({ mesh }) => mesh.visible)"), "clicking it again shows everything");

  // ---- navigation: pad buttons, keys, fit, double-click
  const navPress = (n) => evaluate(`(() => { const b = document.querySelector('#nav [data-nav=${n}]');
    b.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true })); b.dispatchEvent(new PointerEvent('pointerup', { bubbles: true })); return true; })()`);
  const tgt = () => evaluate("wp.controls.target.toArray()");
  const t0 = await tgt();
  await navPress("pan-r");
  const t1 = await tgt();
  check(t1[0] > t0[0], `top view: ▶ moves the view right (${Math.round(t0[0])} → ${Math.round(t1[0])})`);
  check(await evaluate("document.querySelector('#nav [data-nav=turn-l]').disabled"), "turn buttons are off in flat views");
  const z0 = await evaluate("wp.camera.zoom");
  await navPress("zoom-i");
  check(await evaluate(`wp.camera.zoom > ${z0}`), "+ zooms in");
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "1", text: "1" });
  check(await waitFor("wp.state.view === 'persp'", 2000), "key 1 goes to 3D");
  const az = "(() => { const o = wp.camera.position.clone().sub(wp.controls.target); return Math.atan2(o.y, o.x); })()";
  const a0 = await evaluate(az);
  await navPress("turn-r");
  check(Math.abs((await evaluate(az)) - a0) > 0.01, "↻ turns the 3D view");
  await evaluate("wp.select('base_top'); wp.fit(); true");
  await sleep(600);
  check(await evaluate(`(() => { const b = new (wp.controls.target.constructor)(); const box = wp.meshes().get('base_top').mesh;
    box.geometry.computeBoundingBox(); box.geometry.boundingBox.getCenter(b).applyMatrix4(box.matrixWorld);
    return b.distanceTo(wp.controls.target) < 5; })()`), "F fits the selected part (target at its centre)");
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape" });
  await evaluate("wp.fit(); true");
  await sleep(600);
  const tb = await tgt();
  const spot = await evaluate(`(() => {  // centre of another part, on screen
    const r = document.querySelector('#canvas').getBoundingClientRect();
    for (const { mesh } of wp.meshes().values()) {
      mesh.geometry.computeBoundingBox();
      const c = mesh.geometry.boundingBox.getCenter(wp.controls.target.clone()).applyMatrix4(mesh.matrixWorld);
      const v = c.clone().project(wp.camera), x = r.left + (v.x + 1) / 2 * r.width, y = r.top + (1 - v.y) / 2 * r.height;
      if (c.distanceTo(wp.controls.target) > 100 && x > r.left + 300 && x < r.right - 200 && y > r.top + 60 && y < r.bottom - 160) return [x, y];
    }
    return null;
  })()`);
  for (const n of [1, 2]) {
    await send("Input.dispatchMouseEvent", { type: "mousePressed", x: spot[0], y: spot[1], button: "left", clickCount: n });
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: spot[0], y: spot[1], button: "left", clickCount: n });
  }
  await sleep(600);
  const ta = await tgt();
  check(Math.hypot(ta[0] - tb[0], ta[1] - tb[1], ta[2] - tb[2]) > 1, "double-click moves the view to that spot");
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "4", text: "4" });
  await waitFor("wp.state.view === 'top'", 2000);

  // ---- product picker: live IKEA search, import, place
  await evaluate("document.querySelector('#addProduct').click(); true");
  check(await waitFor("document.querySelector('#catDlg').open", 3000), "product dialog opens");
  await evaluate("const q = document.querySelector('#catQ'); q.value = 'lack side table'; q.dispatchEvent(new Event('input')); true");
  const gotIkea = await waitFor("document.querySelectorAll('#ikeaList [data-ikea]').length > 0", 20000);
  check(gotIkea, "live IKEA results appear");
  if (gotIkea) {
    const no = await evaluate("document.querySelector('#ikeaList [data-ikea]').dataset.ikea");
    const before = (await api("/api/designs/ui-smoke")).design.parts.length;
    await evaluate("document.querySelector('#ikeaList [data-ikea]').click(); true");
    check(await waitFor(`wp.state.data.design.parts.length > ${before}`, 30000), `IKEA product ${no} is imported and placed`);
    const placed = (await api("/api/designs/ui-smoke")).design.parts.filter((p) => p.component).map((p) => p.component);
    const id = placed.find((c) => c.endsWith(no));
    if (id) imported.push(join(REPO, "catalog", "ikea", `${id}.json`));
    check(!!id, `part uses the imported catalog item (${id})`);
  }

  // ---- New design dialog: blank design with starter materials
  await api("/api/designs/ui-smoke-new/delete", {}).catch(() => {});
  await evaluate("document.querySelector('#newDesign').click(); true");
  check(await waitFor("document.querySelector('#newDlg').open", 3000), "new design dialog opens");
  await evaluate(`(() => { const t = document.querySelector('#ndTitle'); t.value = 'UI smoke new'; t.dispatchEvent(new Event('input'));
    document.querySelector('#newDlg button[value=ok]').click(); return true; })()`);
  check(await waitFor("wp.state.name === 'ui-smoke-new' && document.querySelector('#design').value === 'ui-smoke-new'", 8000),
    "new blank design is created and opened");
  check(await waitFor("document.querySelector('#boardMat').options.length >= 3", 3000), "blank design has starter materials for the Board tool");
  await api("/api/designs/ui-smoke-new/delete", {});

  // ---- select a whole group, move it as one, then regroup the selection
  await send("Page.enable");
  let promptAnswer = null;
  const onPrompt = (e) => { const m = JSON.parse(e.data); if (m.method === "Page.javascriptDialogOpening" && m.params.type === "prompt") {
    ws.send(JSON.stringify({ id: 99998, method: "Page.handleJavaScriptDialog", params: { accept: true, promptText: promptAnswer } })); } };
  ws.addEventListener("message", onPrompt);
  await evaluate("document.querySelector('#design').value = 'ui-smoke'; document.querySelector('#design').dispatchEvent(new Event('change')); true");
  await waitFor("wp.state.name === 'ui-smoke' && wp.state.data.design.parts.length > 3", 8000);
  await evaluate("wp.setTool('move'); document.querySelector('[data-tab=part]').click(); wp.state.selected.clear(); wp.renderPart(); true");
  check(await waitFor("!!document.querySelector('#tab-part [data-grp]')", 3000), "the part list shows clickable group names");
  const grpName = await evaluate(`[...document.querySelectorAll('#tab-part [data-grp]')].map((h) => h.dataset.grp)
    .find((g) => wp.state.data.design.parts.filter((p) => (p.group || 'Parts') === g && p.kind !== 'reference').length > 1)`);
  await evaluate(`document.querySelector('#tab-part [data-grp="${grpName}"]').click(); true`);
  const selIds = await evaluate("[...wp.state.selected]");
  check(selIds.length > 1 && await evaluate("!!wp.tcontrols.object"), `clicking group “${grpName}” selects its ${selIds.length} parts and shows the Move handle`);
  const before = await evaluate(`Object.fromEntries(${JSON.stringify(selIds)}.map((i) => [i, wp.state.data.design.parts.find((p) => p.id === i).at[0]]))`);
  await evaluate(`(() => { const t = wp.tcontrols; t.dispatchEvent({ type: 'dragging-changed', value: true });
    wp.proxy.position.x += 100; t.dispatchEvent({ type: 'objectChange' });
    t.dispatchEvent({ type: 'dragging-changed', value: false }); return true; })()`);
  check(await waitFor(`${JSON.stringify(selIds)}.every((i) => Math.abs(wp.state.data.design.parts.find((p) => p.id === i).at[0] - ${JSON.stringify(before)}[i] - 100) < 0.01)`, 8000),
    "Move moves every selected part by the same 100 mm");
  await evaluate("document.querySelector('#undo').click(); true");
  check(await waitFor(`${JSON.stringify(selIds)}.every((i) => Math.abs(wp.state.data.design.parts.find((p) => p.id === i).at[0] - ${JSON.stringify(before)}[i]) < 0.01)`, 8000),
    "one Undo puts them all back");
  await evaluate(`wp.state.selected = new Set(${JSON.stringify(selIds.slice(0, 2))}); wp.renderPart(); true`);
  promptAnswer = "Smoke group";
  check(await waitFor("!!document.querySelector('#groupSel')", 3000), "Group… appears with several parts selected");
  await evaluate("document.querySelector('#groupSel').click(); true");
  check(await waitFor(`${JSON.stringify(selIds.slice(0, 2))}.every((i) => wp.state.data.design.parts.find((p) => p.id === i).group === 'Smoke group')`, 8000),
    "Group… puts the selected parts in the named group");
  ws.removeEventListener("message", onPrompt);

  // ---- Duplicate the open design, then place the original inside the copy
  await api("/api/designs/ui-smoke-copy/delete", {}).catch(() => {});
  await evaluate("document.querySelector('#design').value = 'ui-smoke'; document.querySelector('#design').dispatchEvent(new Event('change')); true");
  await waitFor("wp.state.name === 'ui-smoke'", 5000);
  await evaluate("document.querySelector('#dupDesign').click(); true");
  check(await waitFor("document.querySelector('#newDlg').open && document.querySelector('#ndFrom').value === 'ui-smoke'", 3000),
    "Duplicate opens the dialog with this design as the source");
  check(await evaluate("document.querySelector('#ndName').value === 'ui-smoke-copy' && document.querySelector('#ndTitle').value.endsWith('(copy)')"),
    "Duplicate suggests a copy name and title");
  await evaluate("document.querySelector('#newDlg button[value=ok]').click(); true");
  check(await waitFor("wp.state.name === 'ui-smoke-copy'", 8000), "the copy is created and opened");
  const nOrig = (await api("/api/designs/ui-smoke")).design.parts.length;
  check((await api("/api/designs/ui-smoke-copy")).design.parts.length === nOrig, "the copy has the same parts");

  await evaluate("document.querySelector('#addProduct').click(); true");
  await evaluate("const q2 = document.querySelector('#catQ'); q2.value = 'ui smoke'; q2.dispatchEvent(new Event('input')); true");
  check(await waitFor("!!document.querySelector('#dsgList [data-dsg=\"ui-smoke\"]')", 5000), "Your designs lists the other design");
  check(await evaluate("!document.querySelector('#dsgList [data-dsg=\"ui-smoke-copy\"]')"), "…but not the open one");
  await evaluate("document.querySelector('#dsgList [data-dsg=\"ui-smoke\"]').click(); true");
  check(await waitFor("wp.state.data.design.parts.some((p) => p.component === 'design:ui-smoke')", 8000), "the design is placed in the copy");
  const placedParts = (await api("/api/designs/ui-smoke-copy")).design.parts.filter((p) => p.component === "design:ui-smoke");
  check(placedParts.length === nOrig && placedParts.every((p) => p.id.startsWith("ui_smoke/")), "all its parts come along under one id");
  const m0 = (await api("/api/designs/ui-smoke-copy/mtime")).mtime;
  await sleep(1100);
  await api("/api/designs/ui-smoke/parts/base_top/move", { delta: [10, 0, 0] });
  check((await api("/api/designs/ui-smoke-copy/mtime")).mtime > m0, "editing the placed design marks the copy changed (viewer reloads)");

  // ---- Delete: warns where it is placed, then removes it and opens another design
  await evaluate("document.querySelector('#design').value = 'ui-smoke'; document.querySelector('#design').dispatchEvent(new Event('change')); true");
  await waitFor("wp.state.name === 'ui-smoke'", 5000);
  let dialogText = "";
  const onDialog = (e) => { const m = JSON.parse(e.data); if (m.method === "Page.javascriptDialogOpening") { dialogText = m.params.message;
    ws.send(JSON.stringify({ id: 99999, method: "Page.handleJavaScriptDialog", params: { accept: true } })); } };
  ws.addEventListener("message", onDialog);
  await evaluate("document.querySelector('#delDesign').click(); true");
  check(await waitFor("wp.state.name && wp.state.name !== 'ui-smoke'", 8000), "Delete removes the design and opens another");
  check(dialogText.includes("UI smoke test (copy)"), "the confirm names the design it is placed in");
  check(!(await api("/api/designs")).some((d) => d.name === "ui-smoke"), "it is gone from the list");
  ws.removeEventListener("message", onDialog);

  // ---- holes are cut once Manifold arrives
  check(await waitFor("!!wp.state.wasm", 20000), "Manifold (WebAssembly) loads");

  const shot = await send("Page.captureScreenshot", { format: "png" });
  const out = join(tmpdir(), "woodpecker-ui-smoke.png");
  writeFileSync(out, Buffer.from(shot.result.data, "base64"));
  console.log(`screenshot: ${out}`);
  ws.close();
} finally {
  await fetch(`${BASE}/api/designs/ui-smoke/delete`, { method: "POST" }).catch(() => {});
  await fetch(`${BASE}/api/designs/ui-smoke-copy/delete`, { method: "POST" }).catch(() => {});
  for (const f of imported) if (existsSync(f)) rmSync(f);
  const exited = new Promise((r) => chrome.once("exit", r));
  chrome.kill();
  await Promise.race([exited, sleep(5000)]);
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch { /* temp dir */ }
}
process.exit(failures ? 1 : 0);
