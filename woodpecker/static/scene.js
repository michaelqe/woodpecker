// Turn resolved parts (world-space convex solids from Python) into three.js meshes.
// Shared by the viewer and the print page.
import * as THREE from "three";

export const ACCENT = 0x1ba1e2;
const WOOD = [0xc8b08a, 0xb89a6e, 0xd6c29b, 0xa88a62, 0xc9a77c];
const EDGE = 0x1a1410, EDGE_REF = 0x555b63, EDGE_COMP = 0x8d8a84;

export function colorFor(part, design) {
  if (part.color) return new THREE.Color(part.color).getHex();
  const own = design.materials?.[part.material]?.color;
  if (own && !part.component) return new THREE.Color(own).getHex();
  if (part.component) {
    const c = design.components?.[part.component]?.color;
    return c ? new THREE.Color(c).getHex() : 0xe9e7e2;
  }
  if (part.kind === "hardware") return part.material === "ballast" ? 0x4a4c50 : 0x7a7f86;
  if (part.kind === "reference") return 0x262a30;
  const ids = Object.keys(design.materials).filter((m) => ["sheet", "lumber"].includes(design.materials[m].kind));
  return WOOD[Math.max(0, ids.indexOf(part.material)) % WOOD.length];
}

export const edgeColor = (part) => (part.kind === "reference" ? EDGE_REF : part.kind === "component" ? EDGE_COMP : EDGE);

// Flat shading per face, except faces in a smooth group (a cylinder's side, a sphere),
// whose vertex normals are averaged within the group so they shade round.
function triangulate(mesh) {
  const V = mesh.verts, sm = mesh.smooth;
  const fn = mesh.faces.map((f) => {
    const n = [0, 0, 0];
    for (let i = 0; i < f.length; i++) {
      const a = V[f[i]], b = V[f[(i + 1) % f.length]];
      n[0] += (a[1] - b[1]) * (a[2] + b[2]); n[1] += (a[2] - b[2]) * (a[0] + b[0]); n[2] += (a[0] - b[0]) * (a[1] + b[1]);
    }
    const l = Math.hypot(...n) || 1;
    return n.map((c) => c / l);
  });
  const vn = new Map();  // "group:vertex" -> summed normal
  if (sm) mesh.faces.forEach((f, fi) => { if (sm[fi]) for (const k of f) {
    const key = `${sm[fi]}:${k}`, s = vn.get(key) || [0, 0, 0];
    vn.set(key, s.map((c, j) => c + fn[fi][j]));
  } });
  const pos = [], nor = [];
  mesh.faces.forEach((f, fi) => {
    for (let i = 1; i < f.length - 1; i++) {
      for (const k of [f[0], f[i], f[i + 1]]) {
        pos.push(...V[k]);
        let n = fn[fi];
        if (sm && sm[fi]) { const s = vn.get(`${sm[fi]}:${k}`); const l = Math.hypot(...s) || 1; n = s.map((c) => c / l); }
        nor.push(...n);
      }
    }
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  return g;
}

// ---------------------------------------------------------------- Manifold (holes)
let manifoldPromise = null;
export function loadManifold() {
  if (!manifoldPromise) {
    manifoldPromise = import("/static/vendor/manifold.js")
      .then(async (mod) => { const w = await mod.default(); w.setup(); return w; })
      .catch((e) => { console.warn("Manifold unavailable; holes will not be drawn", e); return null; });
  }
  return manifoldPromise;
}

function toManifold(wasm, mesh) {
  const tri = [];
  for (const f of mesh.faces) for (let i = 1; i < f.length - 1; i++) tri.push(f[0], f[i], f[i + 1]);
  const m = new wasm.Mesh({
    numProp: 3,
    vertProperties: new Float32Array(mesh.verts.flat()),
    triVerts: new Uint32Array(tri),
  });
  m.merge();
  return new wasm.Manifold(m);
}

function cutGeometry(wasm, part, byId) {
  const tools = [...(part.cutouts || [])];
  for (const id of part.subtract || []) if (byId.has(id)) tools.push(byId.get(id).mesh);
  if (!tools.length) return null;
  const made = [];
  try {
    let host = toManifold(wasm, part.mesh); made.push(host);
    for (const t of tools) {
      const tm = toManifold(wasm, t); made.push(tm);
      host = host.subtract(tm); made.push(host);
    }
    const out = host.getMesh();
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(out.vertProperties.slice(), out.numProp === 3 ? 3 : out.numProp));
    g.setIndex(new THREE.BufferAttribute(out.triVerts.slice(), 1));
    const flat = g.toNonIndexed();
    flat.computeVertexNormals();
    g.dispose();
    return flat;
  } catch (e) {
    console.warn(`cut failed for ${part.id}`, e);
    return null;
  } finally {
    for (const m of made) { try { m.delete(); } catch { /* already freed */ } }
  }
}

/** Build meshes for every part. Returns Map id -> {mesh, edges, part}. Holes are cut when
 *  Manifold is available (pass the loaded module, or null to skip). */
export function buildMeshes(design, group, wasm) {
  const byId = new Map(design.parts.map((p) => [p.id, p]));
  const out = new Map();
  for (const p of design.parts) {
    let geom = (wasm && (p.cutouts?.length || p.subtract?.length)) ? cutGeometry(wasm, p, byId) : null;
    geom ||= triangulate(p.mesh);
    const ref = p.kind === "reference" && !(p.component && !p.component.startsWith("design:"));  // catalog cars are solid; a placed design keeps its see-through references
    const mat = new THREE.MeshStandardMaterial({
      color: colorFor(p, design), roughness: 0.85, metalness: p.kind === "hardware" ? 0.3 : 0,
      transparent: ref, opacity: ref ? 0.45 : 1, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
    });
    const mesh = new THREE.Mesh(geom, mat);
    mesh.userData.id = p.id;
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geom, 25),
      new THREE.LineBasicMaterial({ color: edgeColor(p) }));
    group.add(mesh, edges);
    out.set(p.id, { mesh, edges, part: p });
  }
  return out;
}

export function disposeMeshes(map, group) {
  for (const { mesh, edges } of map.values()) {
    mesh.geometry.dispose(); mesh.material.dispose(); edges.geometry.dispose(); edges.material.dispose();
  }
  group.clear();
  map.clear();
}

export function makeLights(scene) {
  scene.add(new THREE.HemisphereLight(0xffffff, 0x303030, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.position.set(-1500, -2500, 3000);
  const fill = new THREE.DirectionalLight(0xffffff, 0.5);
  fill.position.set(2000, 1500, 1000);
  scene.add(sun, fill);
}

/** Point an orthographic camera at the bounds from the front, side or top. */
export function orthoFor(view, bounds, aspect, cam = new THREE.OrthographicCamera()) {
  const s = bounds.size, c = bounds.min.map((v, i) => (v + bounds.max[i]) / 2);
  const [ex, ey] = view === "front" ? [s[0], s[2]] : view === "side" ? [s[1], s[2]] : [s[0], s[1]];
  const half = Math.max(ey, ex / aspect) * 0.62 + 120;
  cam.left = -half * aspect; cam.right = half * aspect; cam.top = half; cam.bottom = -half;
  cam.near = -100000; cam.far = 100000; cam.zoom = 1;
  const d = Math.max(...s, 1000) * 4;
  if (view === "top") { cam.up.set(0, 1, 0); cam.position.set(c[0], c[1], c[2] + d); }
  else { cam.up.set(0, 0, 1); cam.position.set(view === "side" ? c[0] + d : c[0], view === "front" ? c[1] - d : c[1], c[2]); }
  cam.lookAt(...c);
  cam.updateProjectionMatrix();
  return cam;
}
