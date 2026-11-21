// Woodpecker viewer. Z is up, millimetres throughout (1 unit = 1 mm).
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/OrbitControls.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (n) => (Math.round(n * 10) / 10).toLocaleString("en-US", { maximumFractionDigits: 1 });
const dims = (s) => s.map(fmt).join(" × ");

const state = {
  name: null, data: null, mtime: 0,
  selected: new Set(), view: "persp", showRef: true, fitted: false,
};

// ------------------------------------------------------------------ three setup
const canvas = $("#canvas");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0b0b);

scene.add(new THREE.HemisphereLight(0xffffff, 0x303030, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(-1500, -2500, 3000);
scene.add(sun);
const fill = new THREE.DirectionalLight(0xffffff, 0.5);
fill.position.set(2000, 1500, 1000);
scene.add(fill);

// 100 mm grid with a 1 m grid on top, lying on the floor (z = 0)
function makeGrid(size, div, color) {
  const g = new THREE.GridHelper(size, div, color, color);
  g.rotation.x = Math.PI / 2;
  g.material.transparent = true;
  g.material.opacity = 0.6;
  return g;
}
const gridFine = makeGrid(6000, 60, 0x1c1c1c);
const gridMajor = makeGrid(6000, 6, 0x333333);
gridMajor.position.z = 0.5;
scene.add(gridFine, gridMajor);

const persp = new THREE.PerspectiveCamera(35, 1, 10, 100000);
persp.up.set(0, 0, 1);
const ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, -100000, 100000);
let camera = persp;
let controls = null;

const partsGroup = new THREE.Group();
scene.add(partsGroup);
const meshes = new Map(); // part id -> {mesh, edges, part}

const ACCENT = 0x1ba1e2;
const WOOD = [0xc8b08a, 0xb89a6e, 0xd6c29b, 0xa88a62, 0xc9a77c];
function colorFor(part) {
  if (part.kind === "hardware") return part.material === "ballast" ? 0x4a4c50 : 0x7a7f86;
  if (part.kind === "reference") return 0x262a30;
  const ids = Object.keys(state.data.design.materials).filter((m) => {
    const k = state.data.design.materials[m].kind;
    return k === "sheet" || k === "lumber";
  });
  return WOOD[Math.max(0, ids.indexOf(part.material)) % WOOD.length];
}

function gussetGeometry(p) {
  // Right-triangle prism. Profile in (u, v) where v is up; u is y for front/back
  // legs and x for left/right legs; the prism is extruded along the remaining axis.
  const [sx, sy, sz] = p.size;
  const alongY = p.leg === "front" || p.leg === "back";
  const su = alongY ? sy : sx, st = alongY ? sx : sy;
  const tri = (p.leg === "back" || p.leg === "right")
    ? [[0, 0], [su, 0], [su, sz]]
    : [[0, 0], [su, 0], [0, sz]];
  const P = (u, v, t) => (alongY ? [t, u, v] : [u, t, v]);
  const a = tri.map(([u, v]) => P(u, v, 0));
  const b = tri.map(([u, v]) => P(u, v, st));
  const faces = [
    [a[0], a[1], a[2]], [b[0], b[2], b[1]],
    [a[0], b[0], b[1]], [a[0], b[1], a[1]],
    [a[1], b[1], b[2]], [a[1], b[2], a[2]],
    [a[2], b[2], b[0]], [a[2], b[0], a[0]],
  ];
  const pos = new Float32Array(faces.flat(2));
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.computeVertexNormals();
  return g;
}

function buildScene() {
  for (const { mesh, edges } of meshes.values()) {
    mesh.geometry.dispose(); mesh.material.dispose(); edges.geometry.dispose(); edges.material.dispose();
  }
  partsGroup.clear();
  meshes.clear();
  for (const p of state.data.design.parts) {
    let geom;
    if (p.shape === "gusset") {
      geom = gussetGeometry(p);
    } else {
      geom = new THREE.BoxGeometry(...p.size);
      geom.translate(p.size[0] / 2, p.size[1] / 2, p.size[2] / 2);
    }
    const ref = p.kind === "reference";
    const mat = new THREE.MeshStandardMaterial({
      color: colorFor(p), roughness: 0.85, metalness: p.kind === "hardware" ? 0.3 : 0,
      transparent: ref, opacity: ref ? 0.45 : 1, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
    });
    const mesh = new THREE.Mesh(geom, mat);
    mesh.position.set(...p.at);
    mesh.userData.id = p.id;
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geom, 25),
      new THREE.LineBasicMaterial({ color: ref ? 0x555b63 : 0x1a1410 }),
    );
    edges.position.copy(mesh.position);
    partsGroup.add(mesh, edges);
    meshes.set(p.id, { mesh, edges, part: p });
  }
  for (const id of [...state.selected]) if (!meshes.has(id)) state.selected.delete(id);
  applyVisibility();
  applySelection();
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
    edges.material.color.setHex(on ? ACCENT : part.kind === "reference" ? 0x555b63 : 0x1a1410);
  }
}

// ------------------------------------------------------------------ cameras / views
function bounds() {
  const b = state.data.design.bounds;
  const c = b.min.map((v, i) => (v + b.max[i]) / 2);
  return { c, s: b.size, r: Math.max(...b.size, 300) };
}

function resize() {
  const { clientWidth: w, clientHeight: h } = canvas.parentElement;
  renderer.setSize(w, h, false);
  persp.aspect = w / h;
  persp.updateProjectionMatrix();
  fitOrtho(false);
}

function fitOrtho(resetZoom = true) {
  if (!state.data) return;
  const { s } = bounds();
  const { clientWidth: w, clientHeight: h } = canvas.parentElement;
  const aspect = w / h;
  const [ex, ey] = state.view === "front" ? [s[0], s[2]] : state.view === "side" ? [s[1], s[2]] : [s[0], s[1]];
  let half = Math.max(ey, ex / aspect) * 0.65;
  ortho.left = -half * aspect; ortho.right = half * aspect; ortho.top = half; ortho.bottom = -half;
  if (resetZoom) ortho.zoom = 1;
  ortho.updateProjectionMatrix();
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".views button").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  const { c, r } = bounds();
  const target = new THREE.Vector3(...c);
  if (controls) controls.dispose();
  if (view === "persp") {
    camera = persp;
    camera.position.set(c[0] - r * 1.3, c[1] - r * 2.2, c[2] + r * 1.1);
  } else {
    camera = ortho;
    const d = r * 4;
    if (view === "front") { ortho.up.set(0, 0, 1); ortho.position.set(c[0], c[1] - d, c[2]); }
    if (view === "side") { ortho.up.set(0, 0, 1); ortho.position.set(c[0] + d, c[1], c[2]); }
    if (view === "top") { ortho.up.set(0, 1, 0); ortho.position.set(c[0], c[1], c[2] + d); }
    fitOrtho(true);
  }
  controls = new OrbitControls(camera, canvas);
  controls.target.copy(target);
  controls.enableRotate = view === "persp";
  controls.screenSpacePanning = true;
  controls.zoomToCursor = true;
  controls.update();
}

// ------------------------------------------------------------------ picking
const ray = new THREE.Raycaster();
const ndc = new THREE.Vector2();
function pick(ev) {
  const r = canvas.getBoundingClientRect();
  ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ndc, camera);
  const hits = ray.intersectObjects([...meshes.values()].filter((m) => m.mesh.visible).map((m) => m.mesh));
  // let clicks fall through a translucent reference (the TV) to what is behind it
  const solid = hits.find((h) => meshes.get(h.object.userData.id).part.kind !== "reference");
  return (solid || hits[0])?.object.userData.id ?? null;
}

let down = null;
canvas.addEventListener("pointerdown", (e) => { down = { x: e.clientX, y: e.clientY }; });
canvas.addEventListener("pointerup", (e) => {
  if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) return;
  const id = pick(e);
  if (e.shiftKey || e.metaKey) {
    if (id) state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id);
  } else {
    state.selected = new Set(id ? [id] : []);
  }
  selectionChanged();
});
canvas.addEventListener("pointermove", (e) => {
  if (e.buttons) { $("#hover").hidden = true; return; }
  const id = pick(e);
  const h = $("#hover");
  if (!id) { h.hidden = true; canvas.style.cursor = ""; return; }
  const p = meshes.get(id).part;
  h.textContent = `${p.name} · ${dims([...p.size].sort((a, b) => b - a))}`;
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
  fetch("/api/selection", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ design: state.name, parts: [...state.selected] }),
  });
}
function select(id) { state.selected = new Set([id]); selectionChanged(); showTab("part"); }

// ------------------------------------------------------------------ panels
const partById = (id) => state.data.design.parts.find((p) => p.id === id);

function renderPart() {
  const el = $("#tab-part");
  const d = state.data.design;
  if (state.selected.size === 1) {
    const p = partById([...state.selected][0]);
    const m = d.materials[p.material] || {};
    const joints = d.joints.filter((j) => j.parts.includes(p.id));
    const sorted = [...p.size].sort((a, b) => b - a);
    el.innerHTML = `
      <h2>${esc(p.name)}</h2>
      <p class="muted small">${esc(p.group)} · ${esc(p.id)}</p>
      <p>${esc(p.role) || '<span class="muted">No role written yet.</span>'}</p>
      ${p.notes ? `<p class="muted">${esc(p.notes)}</p>` : ""}
      <dl class="kv">
        <dt>Material</dt><dd>${esc(m.name || p.material)}</dd>
        <dt>Cut size</dt><dd>${dims(sorted)} mm${p.shape === "gusset" ? " (triangle)" : ""}</dd>
        <dt>Size x·y·z</dt><dd>${dims(p.size)}</dd>
        <dt>Position</dt><dd>${dims(p.at)}</dd>
      </dl>
      <h3>Joints</h3>
      ${joints.length ? joints.map((j) => `
        <div class="joint"><b>${esc(j.type)}</b> with
          ${j.parts.filter((x) => x !== p.id).map((x) => `<span class="chip" data-sel="${esc(x)}">${esc(partById(x)?.name || x)}</span>`).join("")}
          ${j.fasteners ? `<div class="small">${esc(j.fasteners)}</div>` : ""}
          ${j.notes ? `<div class="small muted">${esc(j.notes)}</div>` : ""}
        </div>`).join("") : '<p class="muted">None.</p>'}
      <p class="muted small" style="margin-top:16px">Ask the agent “explain this” to talk it through.</p>`;
  } else {
    const groups = {};
    for (const p of d.parts) (groups[p.group || "Parts"] ||= []).push(p);
    el.innerHTML = `
      <h2>${esc(d.title)}</h2>
      <p class="muted">${esc(d.description)}</p>
      ${state.selected.size > 1 ? `<p>${state.selected.size} parts selected.</p>` : '<p class="muted small">Click a part to inspect it. Shift-click to select several.</p>'}
      <div class="plist">${Object.entries(groups).map(([g, ps]) => `
        <div class="grp"><h3>${esc(g)}</h3>${ps.map((p) => `
          <div class="row ${state.selected.has(p.id) ? "sel" : ""}" data-sel="${esc(p.id)}">
            <span>${esc(p.name)}</span><span class="muted small">${dims([...p.size].sort((a, b) => b - a))}</span>
          </div>`).join("")}</div>`).join("")}
      </div>`;
  }
}

function renderParams() {
  const el = $("#tab-params");
  const ps = state.data.design.params;
  const row = (p) => {
    const derived = !p.label;
    return `<div class="param ${derived ? "derived" : ""}">
      <div><div>${esc(p.label || p.name)}</div><div class="name">${esc(p.name)}${p.notes ? " · " + esc(p.notes) : ""}</div></div>
      <input data-param="${esc(p.name)}" value="${esc(p.expr)}" spellcheck="false">
      ${typeof p.expr === "string" ? `<div class="val">= ${fmt(p.value)}</div>` : ""}
    </div>`;
  };
  el.innerHTML = `
    <p class="muted small">Millimetres. Type a number or an expression (e.g. <code>base_w - 2 * ply</code>) and press Enter.</p>
    ${ps.filter((p) => p.label).map(row).join("")}
    <h3>Derived</h3>
    ${ps.filter((p) => !p.label).map(row).join("")}`;
}

function renderCut() {
  const c = state.data.cutlist;
  const el = $("#tab-cut");
  el.innerHTML = `
    <h3>Cut list (mm)</h3>
    <table><tr><th>Qty</th><th>Part</th><th class="n">L × W × T</th></tr>
    ${c.rows.map((r) => `<tr class="click" data-sel="${esc(r.parts[0])}">
      <td class="n">${r.qty}</td>
      <td>${esc(r.label)}<div class="small muted">${esc(r.material_name)}${r.shape === "triangle" ? " · triangle" : ""}</div></td>
      <td class="n">${r.kind === "lumber" ? `${fmt(r.length)} × ${fmt(r.section[1])} × ${fmt(r.section[0])}` : `${fmt(r.length)} × ${fmt(r.width)} × ${fmt(r.thickness)}`}</td>
    </tr>`).join("")}</table>
    <h3>Stock to buy</h3>
    <table>${c.stock.map((s) => `<tr><td class="n">${s.count}</td><td>${esc(s.name)}<div class="small muted">${esc(s.unit)} · ${esc(s.method)}${s.used_fraction != null ? ` · ${Math.round(s.used_fraction * 100)}% used` : ""}</div>
      ${s.detail ? `<div class="small muted">${s.detail.map((b, i) => `Board ${i + 1}: ${b.cuts.map(fmt).join(" + ")} (offcut ${fmt(b.offcut)})`).join("<br>")}</div>` : ""}
      ${(s.warnings || []).map((w) => `<div class="small" style="color:var(--warn)">${esc(w)}</div>`).join("")}</td></tr>`).join("")}</table>
    <h3>Hardware</h3>
    <table>${c.hardware.map((h) => `<tr><td class="n">${h.qty}</td><td>${esc(h.item)}${h.notes ? `<div class="small muted">${esc(h.notes)}</div>` : ""}</td></tr>`).join("")}</table>`;
}

function renderCheck() {
  const { design: d, stability: s } = state.data;
  const el = $("#tab-check");
  const issues = d.issues.length
    ? d.issues.map((i) => `<div class="issue ${i.level}" ${i.part ? `data-sel="${esc(i.part)}"` : ""}>${esc(i.message)}</div>`).join("")
    : '<p class="ok">No issues.</p>';
  let stab = `<p class="muted">${esc(s.note || "")}</p>`;
  if (s.tip) {
    stab = `
      <dl class="kv">
        <dt>Total mass</dt><dd>${fmt(s.total_mass_kg)} kg</dd>
        <dt>Centre of gravity</dt><dd>${fmt(s.cog_mm[2])} mm up</dd>
        <dt>Top</dt><dd>${fmt(s.top_mm)} mm</dd>
      </dl>
      <table style="margin-top:8px"><tr><th>Tips</th><th class="n">Lean</th><th class="n">Push at top</th></tr>
      ${Object.entries(s.tip).map(([k, t]) => `<tr><td>${k}${k === s.weakest ? " ·&nbsp;weakest" : ""}</td><td class="n">${fmt(t.tip_angle_deg)}°</td><td class="n">${fmt(t.push_at_top_kg)} kg</td></tr>`).join("")}
      </table>
      <p class="muted small">“Lean” is how far it can tilt before it falls; “push” is the sideways force at the very top that starts it tipping, with the brakes on. Footprint = caster centres.</p>
      <h3>Heaviest parts</h3>
      <table>${s.mass_breakdown.slice(0, 6).map((m) => `<tr class="click" data-sel="${esc(m.part)}"><td>${esc(m.name)}</td><td class="n">${fmt(m.mass_kg)} kg</td></tr>`).join("")}</table>`;
  }
  el.innerHTML = `<h3>Issues</h3>${issues}<h3>Stability</h3>${stab}`;
}

function renderAll() {
  renderPart(); renderParams(); renderCut(); renderCheck();
  const b = state.data.design.bounds.size;
  $("#overall").textContent = `Overall ${dims(b)} mm (W × D × H)  ·  grid 100 mm`;
  const n = state.data.design.issues.length;
  document.querySelector('[data-tab="check"]').textContent = n ? `Check (${n})` : "Check";
}

function showTab(t) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  document.querySelectorAll(".tab").forEach((el) => { el.hidden = el.id !== `tab-${t}`; });
}

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

async function loadDesign(name, { keepView = false } = {}) {
  try {
    const data = await api(`/api/designs/${name}`);
    state.data = data; state.mtime = data.mtime; state.name = name;
    showError(null);
    buildScene();
    renderAll();
    if (!state.fitted || !keepView) { setView(state.view); state.fitted = true; }
    $("#status").textContent = `loaded ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    showError(`Could not load ${name}: ${err.message}`);
  }
}

let polls = 0;
async function refreshDesignList() {
  const list = await api("/api/designs");
  const sel = $("#design");
  const names = [...sel.options].map((o) => o.value).join();
  if (names === list.map((d) => d.name).join()) return;
  sel.innerHTML = list.map((d) => `<option value="${esc(d.name)}">${esc(d.title)}</option>`).join("");
  sel.value = state.name;
}

async function poll() {
  if (!state.name) return;
  try {
    if (++polls % 5 === 0) await refreshDesignList();
    const { mtime } = await api(`/api/designs/${state.name}/mtime`);
    if (mtime !== state.mtime) {
      state.mtime = mtime;
      await loadDesign(state.name, { keepView: true });
      $("#status").textContent = `updated ${new Date().toLocaleTimeString()}`;
    }
  } catch { /* server restarting */ }
}

// ------------------------------------------------------------------ events
document.querySelector(".views").addEventListener("click", (e) => {
  const v = e.target.dataset.view;
  if (v) setView(v);
});
document.querySelector(".tabs").addEventListener("click", (e) => { if (e.target.dataset.tab) showTab(e.target.dataset.tab); });
$("#panel").addEventListener("click", (e) => {
  const t = e.target.closest("[data-sel]");
  if (t) select(t.dataset.sel);
});
$("#panel").addEventListener("keydown", async (e) => {
  const inp = e.target.closest("input[data-param]");
  if (!inp || e.key !== "Enter") return;
  const raw = inp.value.trim();
  const value = raw !== "" && !Number.isNaN(Number(raw)) ? Number(raw) : raw;
  try {
    const data = await api(`/api/designs/${state.name}/params`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: inp.dataset.param, value }),
    });
    state.data = data; state.mtime = data.mtime;
    showError(null);
    buildScene(); renderAll(); showTab("params");
    $("#status").textContent = `${inp.dataset.param} = ${raw}`;
  } catch (err) { showError(err.message); }
});
$("#showRef").addEventListener("change", (e) => { state.showRef = e.target.checked; applyVisibility(); });
$("#undo").addEventListener("click", async () => {
  try {
    const data = await api(`/api/designs/${state.name}/undo`, { method: "POST" });
    state.data = data; state.mtime = data.mtime;
    showError(null); buildScene(); renderAll();
    $("#status").textContent = "undone";
  } catch (err) { $("#status").textContent = err.message; }
});
$("#design").addEventListener("change", (e) => {
  state.selected.clear(); state.fitted = false;
  try { localStorage.setItem("wp.design", e.target.value); } catch { /* private mode */ }
  loadDesign(e.target.value);
});
document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, select")) return;
  if (e.key === "Escape") { state.selected.clear(); selectionChanged(); }
  const views = { 1: "persp", 2: "front", 3: "side", 4: "top" };
  if (views[e.key]) setView(views[e.key]);
  if (e.key === "f") setView(state.view);
});
new ResizeObserver(resize).observe(canvas.parentElement);

function frame() {
  controls?.update();
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}

(async function init() {
  const list = await api("/api/designs");
  const sel = $("#design");
  sel.innerHTML = list.map((d) => `<option value="${esc(d.name)}">${esc(d.title)}</option>`).join("");
  let saved = null;
  try { saved = localStorage.getItem("wp.design"); } catch { /* private mode */ }
  const start = new URLSearchParams(location.search).get("design") || (list.some((d) => d.name === saved) ? saved : list[0]?.name);
  if (!start) { showError("No designs yet. Ask the agent to create one (wp_create_design)."); return; }
  sel.value = start;
  resize();
  await loadDesign(start);
  setInterval(poll, 1000);
  frame();
})();
