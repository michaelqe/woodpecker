// Dimension lines drawn on a 2D canvas over the 3D view, re-projected every frame.
import * as THREE from "three";
import { len } from "./units.js";

const v = new THREE.Vector3();
function project(p, camera, w, h) {
  v.set(p[0], p[1], p[2]).project(camera);
  return [(v.x + 1) / 2 * w, (1 - v.y) / 2 * h, v.z];
}
const add = (a, d, k) => [a[0] + d[0] * k, a[1] + d[1] * k, a[2] + d[2] * k];

/**
 * dims: [{a, b, dir, off, label?, color?}] — a/b are world points (mm), dir a unit
 * world vector pointing away from the object, off how far out to draw the line (mm).
 */
export function drawDims(ctx, camera, w, h, dims, { color = "#9aa0a6", font = "12px Segoe UI, system-ui, sans-serif", bg = "rgba(11,11,11,.85)" } = {}) {
  ctx.save();
  ctx.font = font;
  ctx.lineWidth = 1;
  for (const d of dims) {
    const col = d.color || color;
    const a2 = add(d.a, d.dir, d.off), b2 = add(d.b, d.dir, d.off);
    const A = project(d.a, camera, w, h), B = project(d.b, camera, w, h);
    const A2 = project(a2, camera, w, h), B2 = project(b2, camera, w, h);
    if ([A, B, A2, B2].some((p) => p[2] > 1 || p[2] < -1)) continue;
    const L = Math.hypot(B2[0] - A2[0], B2[1] - A2[1]);
    if (L < 14) continue;
    ctx.strokeStyle = col;
    ctx.globalAlpha = 0.55;
    ctx.beginPath(); // extension lines, with a small gap from the object
    for (const [P, Q] of [[A, A2], [B, B2]]) {
      const dx = Q[0] - P[0], dy = Q[1] - P[1], l = Math.hypot(dx, dy) || 1;
      ctx.moveTo(P[0] + dx / l * 4, P[1] + dy / l * 4);
      ctx.lineTo(Q[0] + dx / l * 6, Q[1] + dy / l * 6);
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.moveTo(A2[0], A2[1]); ctx.lineTo(B2[0], B2[1]);
    // architectural ticks
    const ux = (B2[0] - A2[0]) / L, uy = (B2[1] - A2[1]) / L, t = 5;
    for (const P of [A2, B2]) {
      ctx.moveTo(P[0] - (ux - uy) * t, P[1] - (uy + ux) * t);
      ctx.lineTo(P[0] + (ux - uy) * t, P[1] + (uy + ux) * t);
    }
    ctx.stroke();
    const label = d.label ?? len(Math.hypot(d.b[0] - d.a[0], d.b[1] - d.a[1], d.b[2] - d.a[2]));
    const mx = (A2[0] + B2[0]) / 2, my = (A2[1] + B2[1]) / 2;
    const tw = ctx.measureText(label).width + 8;
    ctx.fillStyle = bg;
    ctx.fillRect(mx - tw / 2, my - 9, tw, 18);
    ctx.fillStyle = col;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(label, mx, my + 0.5);
  }
  ctx.restore();
}

/** Overall dimensions for an orthographic view of a bounding box. */
export function overallDims(view, b, gap = 120) {
  const [x0, y0, z0] = b.min, [x1, y1, z1] = b.max;
  if (view === "front") return [
    { a: [x0, y0, z0], b: [x1, y0, z0], dir: [0, 0, -1], off: gap },
    { a: [x1, y0, z0], b: [x1, y0, z1], dir: [1, 0, 0], off: gap },
  ];
  if (view === "side") return [
    { a: [x1, y0, z0], b: [x1, y1, z0], dir: [0, 0, -1], off: gap },
    { a: [x1, y1, z0], b: [x1, y1, z1], dir: [0, 1, 0], off: gap },
  ];
  if (view === "top") return [
    { a: [x0, y0, z1], b: [x1, y0, z1], dir: [0, -1, 0], off: gap },
    { a: [x0, y0, z1], b: [x0, y1, z1], dir: [-1, 0, 0], off: gap },
  ];
  return [];
}

/** Width/depth/height of one part's bounding box, placed for the given view. */
export function partDims(view, p, color, gap = 50) {
  const [x0, y0, z0] = p.at, [x1, y1, z1] = p.max;
  const all = {
    x: { a: [x0, y0, z0], b: [x1, y0, z0], dir: view === "top" ? [0, -1, 0] : [0, 0, -1], off: gap, color },
    y: { a: [x1, y0, z0], b: [x1, y1, z0], dir: view === "top" ? [1, 0, 0] : [0, 0, -1], off: gap, color },
    z: { a: [x0, y0, z0], b: [x0, y0, z1], dir: view === "side" ? [0, -1, 0] : [-1, 0, 0], off: gap, color },
  };
  const keep = view === "front" ? ["x", "z"] : view === "side" ? ["y", "z"] : view === "top" ? ["x", "y"] : ["x", "y", "z"];
  return keep.map((k) => all[k]);
}
