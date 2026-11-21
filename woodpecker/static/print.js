// Printable build sheet: drawings with dimensions, cut list, layouts, shopping, steps.
import * as THREE from "three";
import { buildMeshes, disposeMeshes, loadManifold, makeLights, orthoFor } from "./scene.js";
import { drawDims, overallDims } from "./dims.js";
import { boardSvg, sheetSvg } from "./layouts.js";
import * as U from "./units.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const num = (n, d = 1) => (Math.round(n * 10 ** d) / 10 ** d).toLocaleString("en-US", { maximumFractionDigits: d });
const name = decodeURIComponent(location.pathname.split("/").pop());

async function render() {
  const data = await (await fetch(`/api/designs/${name}`)).json();
  if (data.error) { $("#sheet").textContent = data.error; return; }
  const { design: d, cutlist: c, stability: s } = data;
  document.title = `${d.title} · build sheet`;
  const wasm = await loadManifold();
  const drawings = renderDrawings(d, wasm);

  const params = d.params.filter((p) => p.label);
  $("#sheet").innerHTML = `
    <h1>${esc(d.title)}</h1>
    <p class="muted">${esc(d.description)}</p>
    <p class="muted">Overall ${U.dims(d.bounds.size)} (W × D × H) · printed ${new Date().toLocaleDateString()}</p>

    <h2>Drawings</h2>
    <div class="views">${drawings.map((v) => `<figure><img src="${v.src}" alt="${esc(v.label)}"><figcaption>${esc(v.label)}</figcaption></figure>`).join("")}</div>

    <div class="cols">
      <div>
        <h2>Key measurements</h2>
        <table>${params.map((p) => `<tr><td>${esc(p.label)}</td><td class="n">${p.unit === "mm" ? U.len(p.value) : `${num(p.value, 2)} ${esc(p.unit)}`}</td></tr>`).join("")}</table>
      </div>
      <div>
        <h2>Stability</h2>
        ${s.tip ? `<table>
          <tr><td>Total mass</td><td class="n">${num(s.total_mass_kg)} kg</td></tr>
          <tr><td>Centre of gravity height</td><td class="n">${U.len(s.cog_mm[2])}</td></tr>
          ${Object.entries(s.tip).map(([k, t]) => `<tr><td>Tips ${k}</td><td class="n">${num(t.tip_angle_deg)}° · ${num(t.push_at_top_kg)} kg push at top</td></tr>`).join("")}
        </table>` : `<p class="muted">${esc(s.note || "")}</p>`}
        ${d.issues.length ? `<p class="warn">${d.issues.length} open issue${d.issues.length > 1 ? "s" : ""} in the design (see the Check tab).</p>` : ""}
      </div>
    </div>

    <h2>Cut list (${esc(U.unitLabel())})</h2>
    <table><tr><th></th><th>Qty</th><th>Part</th><th>Material</th><th class="n">Length</th><th class="n">Width</th><th class="n">Thick</th></tr>
    ${c.rows.map((r) => `<tr><td class="box"></td><td class="n">${r.qty}</td>
      <td>${esc(r.label)}${r.shape === "triangle" ? " (triangle)" : ""}${r.ends ? `<div class="muted">ends ${num(r.ends[0])}° / ${num(r.ends[1])}°</div>` : ""}${(r.cut_notes || []).map((n) => `<div class="muted">${esc(n)}</div>`).join("")}</td>
      <td>${esc(r.material_name)}</td>
      <td class="n">${U.len(r.length, { bare: true })}</td>
      <td class="n">${U.len(r.kind === "lumber" ? r.section[1] : r.width, { bare: true })}</td>
      <td class="n">${U.len(r.kind === "lumber" ? r.section[0] : r.thickness, { bare: true })}</td></tr>`).join("")}
    </table>

    <h2>Cutting layouts</h2>
    ${c.stock.map((st) => `<p><b>${st.count} × ${esc(st.name)}</b> <span class="muted">(${esc(st.unit)}, ${esc(st.method)})</span></p>
      <div class="layouts">${st.kind === "sheet"
        ? st.layouts.map((_, i) => `<div><div class="muted">Sheet ${i + 1}</div>${sheetSvg(st, i, { width: 300, light: true })}</div>`).join("")
        : st.detail.map((_, i) => `<div><div class="muted">Board ${i + 1}</div>${boardSvg(st, i, { width: 300, light: true })}</div>`).join("")}</div>
      ${(st.warnings || []).map((w) => `<p class="warn">${esc(w)}</p>`).join("")}`).join("")}

    <h2>Shopping list</h2>
    <table><tr><th></th><th>Qty</th><th>Item</th><th class="n">Price</th></tr>
      ${c.stock.map((st) => `<tr><td class="box"></td><td class="n">${st.count}</td><td>${esc(st.name)} (${esc(st.unit)})</td><td class="n"></td></tr>`).join("")}
      ${c.bought.map((b) => `<tr><td class="box"></td><td class="n">${b.qty}</td><td>${esc(b.item)} <span class="muted">${esc(b.article || "")}</span></td><td class="n">${b.price ? `${num(b.price.amount, 2)} ${esc(b.price.currency)}` : ""}</td></tr>`).join("")}
      ${c.hardware.map((h) => `<tr><td class="box"></td><td class="n">${h.qty}</td><td>${esc(h.item)}${h.notes ? ` <span class="muted">${esc(h.notes)}</span>` : ""}</td><td class="n">${h.price_eur != null ? `${num(h.price_eur, 2)} €` : ""}</td></tr>`).join("")}
    </table>
    ${c.cost.lines.length ? `<p>Priced items: <b>${num(c.cost.total_eur, 2)} €</b>${c.cost.missing.length ? ` <span class="muted">(${c.cost.missing.length} items unpriced)</span>` : ""}</p>` : ""}

    <h2>Assembly</h2>
    <ol class="steps">${d.joints.map((j) => `<li><b>${esc(j.parts.map((ref) => partName(d, ref)).join(" + "))}</b>: ${esc(j.type)}.
      ${j.fasteners ? esc(j.fasteners) + "." : ""} ${j.notes ? `<span class="muted">${esc(j.notes)}</span>` : ""}</li>`).join("")}</ol>

    <h2>Parts and what they do</h2>
    <table>${groupRoles(d).map((p) => `<tr><td style="width:30%"><b>${esc(p.name)}</b></td><td>${esc(p.role)}${p.notes ? ` <span class="muted">${esc(p.notes)}</span>` : ""}</td></tr>`).join("")}</table>
    ${Object.values(d.components || {}).map((cp) => `
      <h2>${esc(cp.brand)} ${esc(cp.name)}</h2>
      <p>${esc(cp.construction || "")}</p>
      ${(cp.assumed || []).length ? `<p class="warn">Assumed (not published): ${cp.assumed.map(esc).join("; ")}</p>` : ""}
      <p class="muted">Source: ${esc(cp.url)}</p>`).join("")}
  `;
  $("#msg").textContent = "Ready.";
}

function partName(d, ref) {
  const ps = d.parts.filter((p) => p.id === ref || p.source === ref || p.id.startsWith(ref + "/"));
  if (!ps.length) return ref;
  const n = ps[0].name.replace(/ \d+( \(mirrored\))?$| \(mirrored\)$|:.*$/, "");
  return ps.length > 1 && !ps[0].component ? `${n} (×${ps.length})` : n;
}

function groupRoles(d) {
  const seen = new Map();
  for (const p of d.parts) {
    if (seen.has(p.source)) continue;
    seen.set(p.source, { name: partName(d, p.source), role: p.role, notes: p.notes });
  }
  return [...seen.values()];
}

function renderDrawings(d, wasm) {
  const W = 900, H = 620;
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(2);
  renderer.setSize(W, H, false);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xffffff);
  makeLights(scene);
  const group = new THREE.Group();
  scene.add(group);
  const meshes = buildMeshes(d, group, wasm);
  for (const { edges, part } of meshes.values()) edges.material.color.setHex(part.kind === "reference" ? 0x9aa0a6 : 0x222222);

  const out = [];
  const views = [["persp", "3D view"], ["front", "Front"], ["side", "Side (from the right)"], ["top", "Top"]];
  const b = d.bounds;
  const c = b.min.map((v, i) => (v + b.max[i]) / 2);
  const r = Math.max(...b.size, 300);
  for (const [view, label] of views) {
    let cam;
    if (view === "persp") {
      cam = new THREE.PerspectiveCamera(30, W / H, 10, 200000);
      cam.up.set(0, 0, 1);
      cam.position.set(c[0] - r * 1.4, c[1] - r * 2.4, c[2] + r * 1.2);
      cam.lookAt(...c);
    } else {
      cam = orthoFor(view, b, W / H);
      cam.zoom = 0.85; cam.updateProjectionMatrix();
    }
    renderer.render(scene, cam);
    const cv = document.createElement("canvas");
    cv.width = W * 2; cv.height = H * 2;
    const ctx = cv.getContext("2d");
    ctx.drawImage(renderer.domElement, 0, 0);
    ctx.scale(2, 2);
    if (view !== "persp") drawDims(ctx, cam, W, H, overallDims(view, b, Math.max(80, r * 0.06)),
      { color: "#222", bg: "rgba(255,255,255,.9)", font: "20px Segoe UI, system-ui, sans-serif" });
    out.push({ src: cv.toDataURL("image/png"), label });
  }
  disposeMeshes(meshes, group);
  renderer.dispose();
  return out;
}

$("#units").value = U.getUnit();
$("#units").addEventListener("change", (e) => { U.setUnit(e.target.value); $("#msg").textContent = "Rendering drawings…"; render(); });
render().catch((e) => { $("#msg").textContent = `Failed: ${e.message}`; });
