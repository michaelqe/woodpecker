// Woodpecker viewer. Z is up, millimetres throughout (1 unit = 1 mm).
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/OrbitControls.js";
import { TransformControls } from "/static/vendor/TransformControls.js";
import { ACCENT, buildMeshes, disposeMeshes, edgeColor, loadManifold, makeLights, orthoFor } from "./scene.js";
import { drawDims, overallDims, partDims } from "./dims.js";
import { boardSvg, sheetSvg } from "./layouts.js";
import * as U from "./units.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = (n, d = 1) => (Math.round(n * 10 ** d) / 10 ** d).toLocaleString("en-US", { maximumFractionDigits: d });
const sortDesc = (a) => [...a].sort((x, y) => y - x);
const qs = new URLSearchParams(location.search);

const state = {
  name: null, data: null, mtime: 0, wasm: null,
  selected: new Set(), view: qs.get("view") || "persp", showRef: true, showDims: true, fitted: false,
  tool: "select", snap: 10, busy: false,
};

// ------------------------------------------------------------------ three setup
const canvas = $("#canvas");
const overlay = $("#overlay");
const octx = overlay.getContext("2d");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0b0b);
makeLights(scene);

function makeGrid(size, div, color) {
  const g = new THREE.GridHelper(size, div, color, color);
  g.rotation.x = Math.PI / 2;
  g.material.transparent = true;
  g.material.opacity = 0.6;
  return g;
}
const gridFine = makeGrid(20000, 200, 0x1c1c1c);
const gridMajor = makeGrid(20000, 20, 0x333333);
gridMajor.position.z = 0.5;
scene.add(gridFine, gridMajor);

const persp = new THREE.PerspectiveCamera(35, 1, 10, 200000);
persp.up.set(0, 0, 1);
const ortho = new THREE.OrthographicCamera();
let camera = persp;
let controls = null;

const partsGroup = new THREE.Group();
scene.add(partsGroup);
let meshes = new Map(); // part id -> {mesh, edges, part}

const tcontrols = new TransformControls(persp, canvas);
tcontrols.setSize(0.8);
scene.add(tcontrols.getHelper());
const proxy = new THREE.Object3D();
scene.add(proxy);

const preview = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1),
  new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.35, depthTest: false }));
preview.visible = false;
scene.add(preview);

// ------------------------------------------------------------------ build
function buildScene() {
  disposeMeshes(meshes, partsGroup);
  meshes = buildMeshes(state.data.design, partsGroup, state.wasm);
  for (const id of [...state.selected]) if (!meshes.has(id)) state.selected.delete(id);
  applyVisibility();
  applySelection();
  attachHandles();
}

function applyVisibility() {
  for (const { mesh, edges, part } of meshes.values()) {
    const v = state.showRef || part.kind !== "reference";
    mesh.visible = v; edges.visible = v;
  }
}

function applySelection() {
  for (const [id, { mesh, edges, part }] of meshes) {
    const on = state.selected.has(id);
    mesh.material.emissive.setHex(on ? ACCENT : 0x000000);
    mesh.material.emissiveIntensity = on ? 0.35 : 0;
    edges.material.color.setHex(on ? ACCENT : edgeColor(part));
  }
}

// ------------------------------------------------------------------ cameras / views
function bounds() {
  const b = state.data.design.bounds;
  const c = b.min.map((v, i) => (v + b.max[i]) / 2);
  return { b, c, r: Math.max(...b.size, 300) };
}

function size() {
  const { clientWidth: w, clientHeight: h } = canvas.parentElement;
  return { w, h };
}

function resize() {
  const { w, h } = size();
  renderer.setSize(w, h, false);
  const dpr = Math.min(window.devicePixelRatio, 2);
  overlay.width = w * dpr; overlay.height = h * dpr;
  overlay.style.width = `${w}px`; overlay.style.height = `${h}px`;
  octx.setTransform(dpr, 0, 0, dpr, 0, 0);
  persp.aspect = w / h;
  persp.updateProjectionMatrix();
  if (state.data && camera === ortho) {
    const z = ortho.zoom, pos = ortho.position.clone(), t = controls?.target.clone();
    orthoFor(state.view, state.data.design.bounds, w / h, ortho);
    ortho.zoom = z; ortho.position.copy(pos); ortho.updateProjectionMatrix();
    if (t) controls.target.copy(t);
  }
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".views button").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  const { c, r } = bounds();
  if (controls) controls.dispose();
  if (view === "persp") {
    camera = persp;
    camera.position.set(c[0] - r * 1.3, c[1] - r * 2.2, c[2] + r * 1.1);
  } else {
    const { w, h } = size();
    camera = orthoFor(view, state.data.design.bounds, w / h, ortho);
  }
  controls = new OrbitControls(camera, canvas);
  controls.target.set(...c);
  controls.enableRotate = view === "persp";
  controls.screenSpacePanning = true;
  controls.zoomToCursor = true;
  controls.update();
  tcontrols.camera = camera;
}

// ------------------------------------------------------------------ picking
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
function setRay(ev) {
  const r = canvas.getBoundingClientRect();
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
}
function hits(ev) {
  setRay(ev);
  return ray.intersectObjects([...meshes.values()].filter((m) => m.mesh.visible).map((m) => m.mesh));
}
function pick(ev) {
  const hs = hits(ev);
  // clicks fall through a translucent reference (the TV) to what is behind it
  const solid = hs.find((h) => meshes.get(h.object.userData.id).part.kind !== "reference");
  return (solid || hs[0])?.object.userData.id ?? null;
}

let down = null;
canvas.addEventListener("pointerdown", (e) => { down = { x: e.clientX, y: e.clientY }; });
canvas.addEventListener("pointerup", (e) => {
  if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) return;
  if (tcontrols.dragging || tcontrols.axis) return;
  if (state.tool === "board") return boardClick(e);
  const id = pick(e);
  if (e.shiftKey || e.metaKey) {
    if (id) state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id);
  } else {
    state.selected = new Set(id ? [id] : []);
  }
  selectionChanged();
});
canvas.addEventListener("pointermove", (e) => {
  if (state.tool === "board") return boardMove(e);
  const h = $("#hover");
  if (e.buttons || tcontrols.dragging) { h.hidden = true; return; }
  const id = pick(e);
  if (!id) { h.hidden = true; canvas.style.cursor = ""; return; }
  const p = meshes.get(id).part;
  h.textContent = `${p.name} · ${U.dims(sortDesc(p.size))}`;
  const r = canvas.getBoundingClientRect();
  h.style.left = `${e.clientX - r.left + 14}px`;
  h.style.top = `${e.clientY - r.top + 10}px`;
  h.hidden = false;
  canvas.style.cursor = "pointer";
});
canvas.addEventListener("pointerleave", () => { $("#hover").hidden = true; });

function selectionChanged() {
  applySelection();
  renderPart();
  attachHandles();
  fetch("/api/selection", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ design: state.name, parts: [...state.selected] }),
  });
}
function select(id) { state.selected = new Set([id]); selectionChanged(); showTab("part"); }

// ------------------------------------------------------------------ move / size handles
let drag = null;
function attachHandles() {
  tcontrols.detach();
  if (!["move", "size"].includes(state.tool) || state.selected.size !== 1) return;
  const id = [...state.selected][0];
  const p = meshes.get(id)?.part;
  if (!p) return;
  if (state.tool === "size" && (!p.aligned || p.kind === "component" || p.mirrored)) {
    status(p.kind === "component" ? "Catalog products have a fixed size." : "Resize works on square-on parts only; ask the agent for tilted ones.");
    return;
  }
  const anchor = state.tool === "size" ? p.at : p.at.map((v, i) => (v + p.max[i]) / 2);
  proxy.position.set(...anchor);
  proxy.scale.set(1, 1, 1);
  proxy.rotation.set(0, 0, 0);
  proxy.updateMatrixWorld();
  tcontrols.setMode(state.tool === "size" ? "scale" : "translate");
  tcontrols.setTranslationSnap(state.snap);
  tcontrols.attach(proxy);
}

tcontrols.addEventListener("dragging-changed", (e) => {
  controls.enabled = !e.value;
  const id = [...state.selected][0];
  if (e.value) {
    drag = { id, start: proxy.position.clone(), copies: [...meshes.values()].filter((m) => m.part.source === meshes.get(id).part.source) };
    return;
  }
  if (!drag) return;
  const d = drag; drag = null;
  const p = meshes.get(d.id).part;
  if (state.tool === "move") {
    const delta = proxy.position.clone().sub(d.start).toArray().map((v) => Math.round(v / state.snap) * state.snap);
    if (delta.some((v) => v)) postPart(d.id, "move", { delta }, `moved ${p.name}`);
  } else {
    const bs = p.max.map((v, i) => v - p.at[i]);
    const s = proxy.scale.toArray();
    const worldDelta = bs.map((v, i) => Math.round((v * s[i] - v) / state.snap) * state.snap);
    const local = [0, 0, 0];
    (p.axis_map || [0, 1, 2]).forEach((w, i) => { local[i] = worldDelta[w]; });
    if (local.some((v) => v)) postPart(d.id, "resize", { delta: local }, `resized ${p.name}`);
    else attachHandles();
  }
});
tcontrols.addEventListener("objectChange", () => {
  if (!drag) return;
  if (state.tool === "move") {
    const off = proxy.position.clone().sub(drag.start);
    for (const m of drag.copies) { m.mesh.position.copy(off); m.edges.position.copy(off); }
  } else {
    const m = meshes.get(drag.id);
    const c = proxy.position;
    for (const o of [m.mesh, m.edges]) {
      o.scale.copy(proxy.scale);
      o.position.set(c.x - proxy.scale.x * c.x, c.y - proxy.scale.y * c.y, c.z - proxy.scale.z * c.z);
    }
  }
});

async function postPart(id, action, body, msg) {
  try {
    const data = await api(`/api/designs/${state.name}/parts/${encodeURIComponent(id)}/${action}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    accept(data, msg);
  } catch (err) {
    showError(err.message);
    buildScene();
  }
}

// ------------------------------------------------------------------ board tool
let board = null; // {p0, z, el}
function snapVal(v, candidates) {
  let best = Math.round(v / state.snap) * state.snap;
  let bd = Math.abs(best - v) + 1e-9;
  for (const c of candidates) {
    const d = Math.abs(c - v);
    if (d < 15 && d < bd) { best = c; bd = d; }
  }
  return best;
}
function edgesOf(axis) {
  const out = [];
  for (const { part } of meshes.values()) if (part.kind !== "reference") out.push(part.at[axis], part.max[axis]);
  return out;
}
function planePoint(e) {
  // a horizontal plane: the top face under the cursor, or the floor
  let z = board?.z;
  if (z == null) {
    const hs = hits(e).filter((h) => meshes.get(h.object.userData.id).part.kind !== "reference");
    const top = hs.find((h) => h.face && h.face.normal.z > 0.9);
    z = top ? top.point.z : 0;
  } else setRay(e);
  const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), -z);
  const p = new THREE.Vector3();
  if (!ray.ray.intersectPlane(plane, p)) return null;
  return { x: snapVal(p.x, edgesOf(0)), y: snapVal(p.y, edgesOf(1)), z };
}
function boardSpec(p0, p1) {
  const mat = state.data.design.materials[$("#boardMat").value];
  if (!mat) return null;
  const orient = $("#boardOrient").value;
  if (mat.kind === "sheet") {
    const t = mat.thickness || 18;
    if (orient === "upright") {
      const alongX = Math.abs(p1.x - p0.x) >= Math.abs(p1.y - p0.y);
      const L = Math.max(alongX ? Math.abs(p1.x - p0.x) : Math.abs(p1.y - p0.y), 10);
      const H = +$("#boardLen").value || 600;
      return alongX ? { size: [L, t, H], at: [Math.min(p0.x, p1.x), p0.y, p0.z] } : { size: [t, L, H], at: [p0.x, Math.min(p0.y, p1.y), p0.z] };
    }
    return { size: [Math.max(Math.abs(p1.x - p0.x), 10), Math.max(Math.abs(p1.y - p0.y), 10), t], at: [Math.min(p0.x, p1.x), Math.min(p0.y, p1.y), p0.z] };
  }
  const [a, b] = [...(mat.section || [45, 95])].sort((x, y) => x - y);
  if (orient === "upright") return { size: [b, a, +$("#boardLen").value || 1000], at: [p0.x, p0.y, p0.z] };
  const alongX = Math.abs(p1.x - p0.x) >= Math.abs(p1.y - p0.y);
  const L = Math.max(alongX ? Math.abs(p1.x - p0.x) : Math.abs(p1.y - p0.y), 10);
  const [w, h] = orient === "edge" ? [a, b] : [b, a];
  return alongX
    ? { size: [L, w, h], at: [Math.min(p0.x, p1.x), p0.y, p0.z] }
    : { size: [w, L, h], at: [p0.x, Math.min(p0.y, p1.y), p0.z] };
}
function showPreview(spec) {
  if (!spec) { preview.visible = false; return; }
  preview.scale.set(...spec.size);
  preview.position.set(spec.at[0] + spec.size[0] / 2, spec.at[1] + spec.size[1] / 2, spec.at[2] + spec.size[2] / 2);
  preview.visible = true;
  $("#hover").hidden = false;
  $("#hover").textContent = U.dims(spec.size);
}
function boardMove(e) {
  const p = planePoint(e);
  if (!p) return;
  const r = canvas.getBoundingClientRect();
  const h = $("#hover");
  h.style.left = `${e.clientX - r.left + 14}px`; h.style.top = `${e.clientY - r.top + 10}px`;
  if (!board) {
    h.hidden = false; h.textContent = `${U.len(p.x)}, ${U.len(p.y)} · click to start`;
    preview.visible = false;
    return;
  }
  showPreview(boardSpec(board.p0, p));
}
function boardClick(e) {
  const p = planePoint(e);
  if (!p) return;
  const upright = $("#boardOrient").value === "upright" && state.data.design.materials[$("#boardMat").value]?.kind === "lumber";
  if (!board && !upright) { board = { p0: p, z: p.z }; status("Click again to finish the board (Esc cancels)."); return; }
  const spec = boardSpec(board ? board.p0 : p, p);
  board = null; preview.visible = false;
  if (spec) askBoardName(spec);
}
function askBoardName(spec) {
  const n = state.data.design.parts.filter((p) => p.group === "Drawn").length + 1;
  const dlg = $("#boardDlg");
  $("#bdName").value = `Board ${n}`;
  $("#bdRole").value = "";
  $("#bdSize").textContent = U.dims(spec.size);
  dlg.showModal();
  dlg.onclose = async () => {
    if (dlg.returnValue !== "ok") return;
    const name = $("#bdName").value.trim() || `Board ${n}`;
    let id = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "board";
    const ids = new Set(state.data.design.parts.map((p) => p.source));
    let k = 2; const base = id; while (ids.has(id)) id = `${base}_${k++}`;
    const part = {
      id, name, group: "Drawn", material: $("#boardMat").value,
      size: spec.size.map((v) => Math.round(v * 10) / 10), at: spec.at.map((v) => Math.round(v * 10) / 10),
      role: $("#bdRole").value.trim(),
    };
    try {
      const data = await api(`/api/designs/${state.name}/parts`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ part }),
      });
      accept(data, `added ${name}`);
      select(id);
    } catch (err) { showError(err.message); }
  };
}

// ------------------------------------------------------------------ tools
function setTool(t) {
  state.tool = t;
  document.querySelectorAll(".tools button[data-tool]").forEach((b) => b.classList.toggle("on", b.dataset.tool === t));
  $("#boardOpts").hidden = t !== "board";
  board = null; preview.visible = false;
  canvas.style.cursor = t === "board" ? "crosshair" : "";
  attachHandles();
  const hints = {
    select: "Click a part to inspect it.",
    move: "Select a part, then drag an arrow. Copies move together.",
    size: "Select a part, then drag a handle to make it longer, wider or thicker.",
    board: "Click on the floor or on a top face, then click again to finish.",
  };
  status(hints[t]);
}

function fillBoardMaterials() {
  const sel = $("#boardMat");
  const prev = sel.value;
  const mats = Object.entries(state.data.design.materials).filter(([, m]) => ["sheet", "lumber"].includes(m.kind));
  sel.innerHTML = mats.map(([id, m]) => `<option value="${esc(id)}">${esc(m.name || id)}</option>`).join("");
  if (mats.some(([id]) => id === prev)) sel.value = prev;
}

// ------------------------------------------------------------------ catalog picker
// Local catalog first (instant), then a live IKEA search below it (debounced). Picking an
// IKEA result imports it into the local catalog, then drops it into the design.
const loadText = (load) => load ? Object.entries(load).map(([k, v]) => `${k.replace(/_kg$/, "").replace(/_/g, " ")} ${v} kg`).join(", ") : "";
let ikeaTimer = null, ikeaSeq = 0;
async function openCatalog() {
  const dlg = $("#catDlg");
  const render = async () => {
    const q = $("#catQ").value;
    const items = await api(`/api/catalog?q=${encodeURIComponent(q)}`);
    $("#catList").innerHTML = items.length ? items.map((it) => `
      <div class="cat" data-cat="${esc(it.id)}">
        <div><b>${esc(it.name)}</b> <span class="muted small">${esc(it.brand)} ${esc(it.article || "")}</span></div>
        <div class="small muted">${U.dims(it.size_mm)} (W × D × H)${it.price ? ` · ${num(it.price.amount, 2)} ${esc(it.price.currency)}` : ""}${it.load ? " · " + loadText(it.load) : ""}</div>
      </div>`).join("") : '<p class="muted small">Nothing in your catalog matches.</p>';
    clearTimeout(ikeaTimer);
    const box = $("#ikeaList");
    if (q.trim().length < 2) { box.innerHTML = '<p class="muted small">Type at least 2 letters to search IKEA too.</p>'; return; }
    box.innerHTML = '<p class="muted small">Searching IKEA…</p>';
    const seq = ++ikeaSeq;
    ikeaTimer = setTimeout(async () => {
      try {
        const r = await api(`/api/ikea?q=${encodeURIComponent(q)}`);
        if (seq !== ikeaSeq) return;
        $("#ikeaHead").textContent = `From IKEA (${r.market.split("/")[0].toUpperCase()}, live)`;
        box.innerHTML = r.results.length ? r.results.map((h) => `
          <div class="cat" ${h.in_catalog ? `data-cat="${esc(h.in_catalog)}"` : `data-ikea="${esc(h.item_no)}"`}>
            ${h.image ? `<img src="${esc(h.image)}" alt="" loading="lazy">` : ""}
            <div><b>${esc(h.name)}</b> ${esc(h.type || "")}${h.variant ? `, ${esc(h.variant)}` : ""} <span class="muted small">${esc(h.article)}${h.in_catalog ? " · in your catalog" : ""}</span></div>
            <div class="small muted">${esc(h.size_text || "")}${h.price ? ` · ${num(h.price.amount, 2)} ${esc(h.price.currency)}` : ""}${h.combination ? " · combination" : ""}</div>
          </div>`).join("") : '<p class="muted small">IKEA found nothing.</p>';
      } catch (err) {
        if (seq === ikeaSeq) box.innerHTML = `<p class="muted small">IKEA search failed: ${esc(err.message)}</p>`;
      }
    }, 350);
  };
  $("#catQ").oninput = render;
  await render();
  dlg.showModal();
}
async function placeProduct(itemId) {
  const item = await api(`/api/catalog/${itemId}`);
  const b = state.data.design.bounds;
  const base = item.name.split(/[ ,]/)[0].toLowerCase().replace(/[^a-z0-9]+/g, "_") || "product";
  const ids = new Set(state.data.design.parts.map((p) => p.source));
  let id = base, k = 2; while (ids.has(id)) id = `${base}_${k++}`;
  const part = {
    id, name: item.name.split(",")[0], group: "Bought", component: item.id,
    at: [Math.round((b.max[0] + 200) / 10) * 10, 0, 0], role: "",
  };
  const data = await api(`/api/designs/${state.name}/parts`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ part }),
  });
  const guessed = item.assumed?.length ? ` (guessed: ${item.assumed.join("; ")})` : "";
  accept(data, `added ${part.name} beside the design; use Move to place it${guessed}`);
  select(state.data.design.parts.find((p) => p.source === id)?.id);
}
$("#catDlg").addEventListener("click", async (e) => {
  const el = e.target.closest("[data-cat],[data-ikea]");
  if (!el) return;
  try {
    let itemId = el.dataset.cat;
    if (!itemId) {
      el.classList.add("busy");
      status("fetching the product from IKEA…");
      const r = await api("/api/ikea/import", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ref: el.dataset.ikea }),
      });
      itemId = r.id;
    }
    $("#catDlg").close();
    await placeProduct(itemId);
  } catch (err) {
    el.classList.remove("busy");
    $("#catDlg").close();
    showError(err.message);
  }
});

// ------------------------------------------------------------------ panels
const partById = (id) => state.data.design.parts.find((p) => p.id === id);
const refName = (ref) => {
  const ps = state.data.design.parts.filter((p) => p.id === ref || p.source === ref || p.id.startsWith(ref + "/"));
  if (!ps.length) return ref;
  if (ps.length === 1) return ps[0].name;
  return ps[0].name.replace(/ \d+$| \(mirrored\)$|:.*$/, "") + ` (${ps.length})`;
};

function renderPart() {
  const el = $("#tab-part");
  const d = state.data.design;
  if (state.selected.size === 1) {
    const p = partById([...state.selected][0]);
    const m = d.materials[p.material] || {};
    const comp = p.component ? d.components[p.component] : null;
    const keys = new Set([p.id, p.source, p.id.split("/")[0]]);
    const joints = d.joints.filter((j) => j.parts.some((x) => keys.has(x)));
    const copies = d.parts.filter((x) => x.source === p.source && !x.component).length;
    el.innerHTML = `
      <h2>${esc(p.name)}</h2>
      <p class="muted small">${esc(p.group)} · ${esc(p.id)}${copies > 1 ? ` · one of ${copies} copies` : ""}</p>
      <p>${esc(p.role) || '<span class="muted">No role written yet. Ask the agent to describe what it does.</span>'}</p>
      ${p.notes ? `<p class="muted">${esc(p.notes)}</p>` : ""}
      <dl class="kv">
        <dt>${comp ? "Product" : "Material"}</dt><dd>${comp ? `<a href="${esc(comp.url)}" target="_blank" rel="noopener">${esc(comp.name)}</a>` : esc(m.name || p.material)}</dd>
        <dt>${comp ? "Panel" : "Cut size"}</dt><dd>${U.dims(sortDesc(p.size))}${p.shape === "gusset" ? " (triangle)" : ""}</dd>
        ${p.ends ? `<dt>End cuts</dt><dd>${num(p.ends[0])}° / ${num(p.ends[1])}°</dd>` : ""}
        ${p.aligned ? "" : "<dt>Placed</dt><dd>at an angle</dd>"}
        <dt>Occupies</dt><dd>${U.dims(p.max.map((v, i) => v - p.at[i]))} (x·y·z)</dd>
        <dt>From</dt><dd>${U.dims(p.at)}</dd>
        ${(p.cut_notes || []).map((n) => `<dt>Cut</dt><dd>${esc(n)}</dd>`).join("")}
      </dl>
      ${comp ? `
        <h3>${esc(comp.brand)} ${esc(comp.article || "")}</h3>
        <dl class="kv">
          <dt>Size</dt><dd>${U.dims(comp.size_mm)} (W × D × H)</dd>
          ${comp.load ? Object.entries(comp.load).map(([k, v]) => `<dt>${esc(k.replace(/_kg$/, "").replace(/_/g, " "))}</dt><dd>${v} kg max</dd>`).join("") : ""}
          ${comp.price ? `<dt>Price</dt><dd>${num(comp.price.amount, 2)} ${esc(comp.price.currency)}</dd>` : ""}
        </dl>
        ${comp.construction ? `<p class="small">${esc(comp.construction)}</p>` : ""}
        ${(comp.assumed || []).length ? `<p class="small warnline">Assumed: ${comp.assumed.map(esc).join("; ")}</p>` : ""}` : ""}
      <h3>Joints</h3>
      ${joints.length ? joints.map((j) => `
        <div class="joint"><b>${esc(j.type)}</b> with
          ${j.parts.filter((x) => !keys.has(x)).map((x) => `<span class="chip" data-sel="${esc(partById(x)?.id || state.data.design.parts.find((q) => q.source === x || q.id.startsWith(x + "/"))?.id || x)}">${esc(refName(x))}</span>`).join("")}
          ${j.fasteners ? `<div class="small">${esc(j.fasteners)}</div>` : ""}
          ${j.notes ? `<div class="small muted">${esc(j.notes)}</div>` : ""}
        </div>`).join("") : '<p class="muted">None.</p>'}
      <div class="actions"><button id="delPart">Delete ${copies > 1 ? "all copies" : comp ? "product" : "part"}</button></div>
      <p class="muted small">Ask tab: “explain this”.</p>`;
    $("#delPart").onclick = async () => {
      if (!confirm(`Delete ${p.name}${copies > 1 ? ` and its ${copies - 1} copies` : ""}? (Undo brings it back.)`)) return;
      state.selected.clear();
      await postPart(p.id, "delete", {}, `deleted ${p.name}`);
    };
  } else {
    const groups = {};
    for (const p of d.parts) (groups[p.group || "Parts"] ||= []).push(p);
    el.innerHTML = `
      <h2>${esc(d.title)}</h2>
      <p class="muted">${esc(d.description)}</p>
      ${state.selected.size > 1 ? `<p>${state.selected.size} parts selected.</p>` : '<p class="muted small">Click a part to inspect it. Shift-click to select several.</p>'}
      <div class="plist">${Object.entries(groups).map(([gname, ps]) => `
        <div class="grp"><h3>${esc(gname)}</h3>${ps.map((p) => `
          <div class="row ${state.selected.has(p.id) ? "sel" : ""}" data-sel="${esc(p.id)}">
            <span>${esc(p.name)}</span><span class="muted small">${U.dims(sortDesc(p.size))}</span>
          </div>`).join("")}</div>`).join("")}
      </div>`;
  }
}

function paramValue(p) {
  if (p.unit !== "mm") return `${num(p.value, 2)} ${p.unit}`;
  return U.len(p.value);
}
function renderParams() {
  const el = $("#tab-params");
  const ps = state.data.design.params;
  const row = (p) => {
    const literal = typeof p.expr !== "string";
    const shown = literal ? (p.unit === "mm" ? U.len(p.expr, { bare: true }) : String(p.expr)) : p.expr;
    return `<div class="param ${p.label ? "" : "derived"}">
      <div><div>${esc(p.label || p.name)}${p.unit !== "mm" ? ` <span class="muted small">(${esc(p.unit)})</span>` : ""}</div>
        <div class="name">${esc(p.name)}${p.notes ? " · " + esc(p.notes) : ""}</div></div>
      <input data-param="${esc(p.name)}" data-unit="${esc(p.unit)}" value="${esc(shown)}" spellcheck="false">
      ${literal ? "" : `<div class="val">= ${esc(paramValue(p))}</div>`}
    </div>`;
  };
  el.innerHTML = `
    <p class="muted small">Numbers are in ${esc(U.unitLabel())} (you can also type 18mm, 3/4", 1' 6"). Expressions are always millimetres. Enter applies.</p>
    ${ps.filter((p) => p.label).map(row).join("")}
    <h3>Derived</h3>
    ${ps.filter((p) => !p.label).map(row).join("") || '<p class="muted">None.</p>'}`;
}

function renderCut() {
  const c = state.data.cutlist;
  const el = $("#tab-cut");
  const unitHead = U.getUnit() === "in" ? "in" : U.getUnit();
  el.innerHTML = `
    <div class="actions"><a class="btn" href="/print/${esc(state.name)}" target="_blank">Printable build sheet</a>
      ${state.page?.enabled ? `<button id="publishNow" title="Update the Magpie page now (it also updates by itself ~20 s after changes)">Publish to Magpie now</button>` : ""}
      ${state.page?.url ? `<a class="btn" href="${esc(state.page.url)}" target="_blank" rel="noopener">Open Magpie page</a>` : ""}</div>
    <h3>Cut list (${unitHead})</h3>
    ${c.rows.length ? `<table><tr><th>Qty</th><th>Part</th><th class="n">L × W × T</th></tr>
    ${c.rows.map((r) => `<tr class="click" data-sel="${esc(r.parts[0])}">
      <td class="n">${r.qty}</td>
      <td>${esc(r.label)}<div class="small muted">${esc(r.material_name)}${r.shape === "triangle" ? " · triangle" : ""}${r.ends ? ` · ends ${num(r.ends[0])}° / ${num(r.ends[1])}°` : ""}</div>
        ${(r.cut_notes || []).map((n) => `<div class="small">${esc(n)}</div>`).join("")}</td>
      <td class="n">${r.kind === "lumber" ? `${U.len(r.length, { bare: true })} × ${U.len(r.section[1], { bare: true })} × ${U.len(r.section[0], { bare: true })}` : `${U.len(r.length, { bare: true })} × ${U.len(r.width, { bare: true })} × ${U.len(r.thickness, { bare: true })}`}</td>
    </tr>`).join("")}</table>` : '<p class="muted">Nothing to cut.</p>'}
    <h3>Stock to buy</h3>
    ${c.stock.map((s) => `<div class="stock"><div><b>${s.count} ×</b> ${esc(s.name)} <span class="small muted">${esc(s.unit)}${s.used_fraction != null ? ` · ${Math.round(s.used_fraction * 100)}% used` : ""}</span></div>
      ${(s.warnings || []).map((w) => `<div class="small warnline">${esc(w)}</div>`).join("")}
      ${s.kind === "sheet" ? s.layouts.map((_, i) => `<div class="small muted">Sheet ${i + 1}</div>${sheetSvg(s, i)}`).join("") : s.detail.map((b, i) => `<div class="small muted">Board ${i + 1} · offcut ${U.len(b.offcut)}</div>${boardSvg(s, i)}`).join("")}
      <div class="small muted">${esc(s.method)}</div></div>`).join("") || '<p class="muted">None.</p>'}
    ${c.bought.length ? `<h3>Bought items</h3><table>${c.bought.map((b) => `<tr><td class="n">${b.qty}</td><td><a href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.item)}</a><div class="small muted">${esc(b.article || "")}</div></td><td class="n">${b.price ? `${num(b.price.amount, 2)} ${esc(b.price.currency)}` : ""}</td></tr>`).join("")}</table>` : ""}
    <h3>Hardware</h3>
    <table>${c.hardware.map((h) => `<tr><td class="n">${h.qty}</td><td>${esc(h.item)}${h.notes ? `<div class="small muted">${esc(h.notes)}</div>` : ""}</td><td class="n">${h.price_eur != null ? `${num(h.price_eur, 2)} €` : ""}</td></tr>`).join("")}</table>
    <h3>Cost</h3>
    ${c.cost.lines.length ? `<table>${c.cost.lines.map((l) => `<tr><td class="n">${l.qty}</td><td>${esc(l.item)}${l.source ? `<div class="small muted">${/^https?:/.test(l.source) ? `<a href="${esc(l.source)}" target="_blank" rel="noopener">source</a>` : esc(l.source)}</div>` : ""}</td><td class="n">${num(l.total_eur, 2)} €</td></tr>`).join("")}
      <tr><td></td><td><b>Total for priced items</b></td><td class="n"><b>${num(c.cost.total_eur, 2)} €</b></td></tr></table>` : ""}
    ${c.cost.missing.length ? `<p class="small muted">No price yet for ${c.cost.missing.length} item${c.cost.missing.length > 1 ? "s" : ""}: ${c.cost.missing.slice(0, 4).map(esc).join(", ")}${c.cost.missing.length > 4 ? "…" : ""}. Ask the agent to look them up.</p>` : ""}`;
}

function renderCheck() {
  const { design: d, stability: s } = state.data;
  const el = $("#tab-check");
  const issues = d.issues.length
    ? d.issues.map((i) => `<div class="issue ${i.level}" ${i.part ? `data-sel="${esc(partById(i.part)?.id || "")}"` : ""}>${esc(i.message)}</div>`).join("")
    : '<p class="ok">No issues.</p>';
  let stab = `<p class="muted">${esc(s.note || "")}</p>`;
  if (s.tip) {
    stab = `
      <dl class="kv">
        <dt>Total mass</dt><dd>${num(s.total_mass_kg)} kg</dd>
        <dt>Centre of gravity</dt><dd>${U.len(s.cog_mm[2])} up</dd>
        <dt>Top</dt><dd>${U.len(s.top_mm)}</dd>
      </dl>
      <table style="margin-top:8px"><tr><th>Tips</th><th class="n">Lean</th><th class="n">Push at top</th></tr>
      ${Object.entries(s.tip).map(([k, t]) => `<tr><td>${k}${k === s.weakest ? " ·&nbsp;weakest" : ""}</td><td class="n">${num(t.tip_angle_deg)}°</td><td class="n">${num(t.push_at_top_kg)} kg</td></tr>`).join("")}
      </table>
      <p class="muted small">“Lean” is how far it can tilt before it falls; “push” is the sideways force at the very top that starts it tipping, with the brakes on. Footprint = everything touching the floor (casters at their centres).</p>
      <h3>Heaviest parts</h3>
      <table>${s.mass_breakdown.slice(0, 6).map((m) => `<tr class="click" data-sel="${esc(m.part)}"><td>${esc(m.name)}</td><td class="n">${num(m.mass_kg)} kg</td></tr>`).join("")}</table>`;
  }
  const comps = Object.values(d.components || {});
  const loads = comps.filter((c) => c.load).map((c) => `<div class="small">${esc(c.name)}: ${Object.entries(c.load).map(([k, v]) => `${esc(k.replace(/_kg$/, "").replace(/_/g, " "))} ${v} kg`).join(", ")}</div>`).join("");
  el.innerHTML = `<h3>Issues</h3>${issues}<h3>Stability</h3>${stab}${loads ? `<h3>Published load limits</h3>${loads}` : ""}`;
}

function renderAll() {
  renderPart(); renderParams(); renderCut(); renderCheck();
  fillBoardMaterials();
  const b = state.data.design.bounds.size;
  $("#overall").textContent = `Overall ${U.dims(b)} (W × D × H)  ·  grid ${U.getUnit() === "in" ? '4″ ≈ 100 mm' : "100 mm"}`;
  const n = state.data.design.issues.length;
  document.querySelector('[data-tab="check"]').textContent = n ? `Check (${n})` : "Check";
}

function showTab(t) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  document.querySelectorAll(".tab").forEach((el) => { el.hidden = el.id !== `tab-${t}`; });
  if (t === "ask") loadChat();
}

// ------------------------------------------------------------------ chat
let chatLoaded = null;
async function loadChat() {
  if (chatLoaded === state.name) return;
  chatLoaded = state.name;
  const [st, h] = await Promise.all([api("/api/chat"), api(`/api/chat/${state.name}`)]);
  $("#chatLog").innerHTML = "";
  if (!st.available) addMsg("system", "Claude CLI not found. Set WOODPECKER_CLAUDE to its path and restart the server.");
  else if (!h.messages.length) addMsg("system", "Ask about this design. Click a part first to say “this”. Try: “make the base 650 deep”, “explain this”, “what will it cost?”");
  for (const m of h.messages) addMsg(m.role, m.text);
}
function addMsg(role, text) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  $("#chatLog").append(el);
  $("#chatLog").scrollTop = 1e9;
  return el;
}
async function sendChat() {
  const box = $("#chatIn");
  const text = box.value.trim();
  if (!text || state.busy) return;
  box.value = "";
  state.busy = true;
  $("#chatSend").disabled = true;
  addMsg("user", text);
  let cur = null;
  const tools = addMsg("tools", "thinking…");
  try {
    const r = await fetch(`/api/chat/${state.name}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, selection: [...state.selected] }),
    });
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    const used = [];
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 1);
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.type === "text") { cur = addMsg("assistant", ev.text); }
        else if (ev.type === "tool") { used.push(ev.name); tools.textContent = `used: ${used.join(", ")}`; }
        else if (ev.type === "error") addMsg("error", ev.text);
      }
    }
    if (!used.length) tools.remove();
    else $("#chatLog").append(tools);
    poll();
  } catch (err) {
    addMsg("error", err.message);
  } finally {
    state.busy = false;
    $("#chatSend").disabled = false;
    if (cur) $("#chatLog").scrollTop = 1e9;
  }
}
$("#chatSend").addEventListener("click", sendChat);
$("#tab-cut").addEventListener("click", async (e) => {
  if (e.target.id !== "publishNow") return;
  e.target.disabled = true; e.target.textContent = "Publishing…";
  try {
    state.page = await api(`/api/designs/${state.name}/publish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    await refreshPageLink(); renderCut(); status("Magpie page updated");
  } catch (err) { showError(err.message); renderCut(); }
});
$("#chatIn").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } });
$("#chatReset").addEventListener("click", async () => {
  if (!confirm("Start a new conversation for this design?")) return;
  await api(`/api/chat/${state.name}/reset`, { method: "POST" });
  chatLoaded = null; loadChat();
});

// ------------------------------------------------------------------ data
async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function showError(msg) {
  const e = $("#error");
  e.hidden = !msg;
  e.textContent = msg || "";
}
function status(t) { $("#status").textContent = t; }

function accept(data, msg) {
  state.data = data; state.mtime = data.mtime;
  showError(null);
  buildScene(); renderAll();
  if (msg) status(msg);
}

async function refreshPageLink() {
  const a = $("#pageLink");
  try {
    const p = await api(`/api/designs/${state.name}/page`);
    state.page = p;
    a.hidden = !p.url;
    if (p.url) { a.href = p.url; a.title = p.error ? `Last publish failed: ${p.error}` : "Drawings, shopping list and cut list in Magpie"; }
    a.textContent = p.error ? "Magpie page (out of date)" : "Magpie page";
  } catch { a.hidden = true; }
}

async function loadDesign(name, { keepView = false } = {}) {
  try {
    const data = await api(`/api/designs/${name}`);
    const switched = state.name !== name;
    state.name = name;
    accept(data);
    if (switched) refreshPageLink();
    if (!state.fitted || !keepView) { setView(state.view); state.fitted = true; }
    status(`loaded ${new Date().toLocaleTimeString()}`);
  } catch (err) {
    showError(`Could not load ${name}: ${err.message}`);
  }
}

let polls = 0;
async function refreshDesignList() {
  const list = await api("/api/designs");
  const sel = $("#design");
  if ([...sel.options].map((o) => o.value).join() === list.map((d) => d.name).join()) return;
  sel.innerHTML = list.map((d) => `<option value="${esc(d.name)}">${esc(d.title)}</option>`).join("");
  sel.value = state.name;
}
async function poll() {
  if (!state.name || drag) return;
  try {
    if (++polls % 5 === 0) await refreshDesignList();
    if (polls % 15 === 0) refreshPageLink();
    const { mtime } = await api(`/api/designs/${state.name}/mtime`);
    if (mtime !== state.mtime) {
      state.mtime = mtime;
      await loadDesign(state.name, { keepView: true });
      status(`updated ${new Date().toLocaleTimeString()}`);
    }
  } catch { /* server restarting */ }
}

// ------------------------------------------------------------------ new design
const slug = (t) => t.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
  .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
$("#newDesign").addEventListener("click", async () => {
  const list = await api("/api/designs");
  $("#ndFrom").innerHTML = `<option value="">a blank design (common plywood and timber ready)</option>` +
    list.map((d) => `<option value="${esc(d.name)}">a copy of ${esc(d.title)}</option>`).join("");
  for (const id of ["#ndTitle", "#ndName", "#ndAsk"]) $(id).value = "";
  $("#ndName").dataset.touched = "";
  $("#ndPage").textContent = state.page?.enabled ? "A Magpie page with drawings, shopping list and cut list is made for it and kept up to date." : "";
  $("#newDlg").showModal();
});
$("#ndTitle").addEventListener("input", () => { if (!$("#ndName").dataset.touched) $("#ndName").value = slug($("#ndTitle").value); });
$("#ndName").addEventListener("input", () => { $("#ndName").dataset.touched = "1"; });
$("#newDlg").addEventListener("close", async () => {
  if ($("#newDlg").returnValue !== "ok") return;
  const title = $("#ndTitle").value.trim();
  const name = $("#ndName").value.trim() || slug(title);
  const ask = $("#ndAsk").value.trim();
  if (!title || !name) return;
  try {
    await api("/api/designs", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, title, description: ask, copy_from: $("#ndFrom").value || null }),
    });
    const list = await api("/api/designs");
    $("#design").innerHTML = list.map((d) => `<option value="${esc(d.name)}">${esc(d.title)}</option>`).join("");
    $("#design").value = name;
    state.selected.clear(); state.fitted = false; chatLoaded = null;
    try { localStorage.setItem("wp.design", name); } catch { /* private mode */ }
    await loadDesign(name);
    setTimeout(refreshPageLink, 4000);
    if (ask) {
      showTab("ask");
      await loadChat();
      $("#chatIn").value = ask;
      sendChat();
    } else {
      status(`created ${title}: draw boards, add products, or ask the agent`);
    }
  } catch (err) { showError(err.message); }
});

// ------------------------------------------------------------------ events
document.querySelector(".views").addEventListener("click", (e) => { if (e.target.dataset.view) setView(e.target.dataset.view); });
document.querySelector(".tools").addEventListener("click", (e) => { if (e.target.dataset.tool) setTool(e.target.dataset.tool); });
document.querySelector(".tabs").addEventListener("click", (e) => { if (e.target.dataset.tab) showTab(e.target.dataset.tab); });
$("#panel").addEventListener("click", (e) => {
  const t = e.target.closest("[data-sel]");
  if (t && t.dataset.sel) select(t.dataset.sel);
});
$("#panel").addEventListener("keydown", async (e) => {
  const inp = e.target.closest("input[data-param]");
  if (!inp || e.key !== "Enter") return;
  const raw = inp.value.trim();
  let value;
  if (inp.dataset.unit === "mm") {
    const mm = U.parseLen(raw);
    value = mm != null ? Math.round(mm * 100) / 100 : raw;
  } else {
    value = raw !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
  }
  try {
    const data = await api(`/api/designs/${state.name}/params`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: inp.dataset.param, value }),
    });
    accept(data, `${inp.dataset.param} = ${raw}`);
    showTab("params");
  } catch (err) { showError(err.message); }
});
$("#showRef").addEventListener("change", (e) => { state.showRef = e.target.checked; applyVisibility(); });
$("#showDims").addEventListener("change", (e) => { state.showDims = e.target.checked; });
$("#units").addEventListener("change", (e) => { U.setUnit(e.target.value); renderAll(); });
$("#snap").addEventListener("change", (e) => { state.snap = +e.target.value; tcontrols.setTranslationSnap(state.snap); });
$("#addProduct").addEventListener("click", openCatalog);
$("#undo").addEventListener("click", async () => {
  try { accept(await api(`/api/designs/${state.name}/undo`, { method: "POST" }), "undone"); }
  catch (err) { status(err.message); }
});
$("#design").addEventListener("change", (e) => {
  state.selected.clear(); state.fitted = false; chatLoaded = null;
  try { localStorage.setItem("wp.design", e.target.value); } catch { /* private mode */ }
  loadDesign(e.target.value);
  if (!$("#tab-ask").hidden) loadChat();
});
document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, select, textarea, dialog")) return;
  if (e.key === "Escape") {
    if (board) { board = null; preview.visible = false; status("cancelled"); return; }
    state.selected.clear(); selectionChanged();
  }
  const views = { 1: "persp", 2: "front", 3: "side", 4: "top" };
  if (views[e.key]) setView(views[e.key]);
  const tools = { v: "select", g: "move", s: "size", b: "board" };
  if (tools[e.key]) setTool(tools[e.key]);
  if (e.key === "f") setView(state.view);
  if ((e.key === "Delete" || e.key === "Backspace") && state.selected.size === 1) $("#delPart")?.click();
  if ((e.metaKey || e.ctrlKey) && e.key === "z") { e.preventDefault(); $("#undo").click(); }
});
new ResizeObserver(resize).observe(canvas.parentElement);

function frame() {
  controls?.update();
  renderer.render(scene, camera);
  const { w, h } = size();
  octx.clearRect(0, 0, w, h);
  if (state.showDims && state.data) {
    const ds = [];
    if (state.view !== "persp") ds.push(...overallDims(state.view, state.data.design.bounds));
    if (state.selected.size === 1) {
      const p = partById([...state.selected][0]);
      if (p) ds.push(...partDims(state.view, p, "#1ba1e2"));
    }
    drawDims(octx, camera, w, h, ds);
  }
  requestAnimationFrame(frame);
}

// handle for debugging and the UI smoke test (tests/ui_smoke.mjs)
window.wp = { state, tcontrols, proxy, get camera() { return camera; }, setTool, select };

(async function init() {
  $("#units").value = U.getUnit();
  const list = await api("/api/designs");
  const sel = $("#design");
  sel.innerHTML = list.map((d) => `<option value="${esc(d.name)}">${esc(d.title)}</option>`).join("");
  let saved = null;
  try { saved = localStorage.getItem("wp.design"); } catch { /* private mode */ }
  const start = qs.get("design") || (list.some((d) => d.name === saved) ? saved : list[0]?.name);
  if (!start) { showError("No designs yet. Click New to start one."); return; }
  sel.value = start;
  resize();
  await loadDesign(start);
  // holes (Manifold, WebAssembly) arrive a moment later; redraw when they do
  loadManifold().then((w) => { state.wasm = w; if (w && state.data) buildScene(); });
  if (qs.get("select")) select(qs.get("select"));
  if (qs.get("tab")) showTab(qs.get("tab"));
  setInterval(poll, 1000);
  frame();
})();
