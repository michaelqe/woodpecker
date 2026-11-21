"""Server-side pictures of a design (PNG), with no browser: a small numpy z-buffer renderer.

Draws the same convex solids the viewer gets from model.py, flat-shaded, with part
outlines, reference parts (the TV, glazing) see-through like in the viewer, and overall
dimension lines on the flat views. Used for the Magpie page and `wp_export_images`.
Holes cut by joints are not drawn here (the viewer does those with Manifold).
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .model import Design

WOOD = ["#c8b08a", "#b89a6e", "#d6c29b", "#a88a62", "#c9a77c"]
BG = (243, 241, 236)
EDGE = (40, 32, 26)
REF_EDGE = (120, 126, 134)
INK = (60, 60, 60)
SS = 2  # supersampling

# name: (direction the camera looks along, screen-up hint, label)
VIEWS = {
    "3d": ((1.0, 1.35, -0.85), (0, 0, 1), "3D, front left"),
    "3d-back": ((-1.1, -1.3, -0.8), (0, 0, 1), "3D, back right"),
    "front": ((0, 1, 0), (0, 0, 1), "Front"),
    "side": ((-1, 0, 0), (0, 0, 1), "Side (from the right)"),
    "top": ((0, 0, -1), (0, 1, 0), "Top"),
}


def _rgb(hexstr: str) -> np.ndarray:
    h = hexstr.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def part_color(p, design: Design) -> np.ndarray:
    own = ((design.raw.get("materials") or {}).get(p.material) or {}).get("color")
    if own and p.kind != "component":
        return _rgb(own)
    if p.kind == "component":
        c = (design.components.get(p.component) or {}).get("color")
        return _rgb(c or "#e9e7e2")
    if p.kind == "hardware":
        return _rgb("#4a4c50" if p.material == "ballast" else "#7a7f86")
    if p.kind == "reference":
        return _rgb("#262a30")
    ids = [m for m, v in (design.raw.get("materials") or {}).items() if v.get("kind") in ("sheet", "lumber")]
    i = ids.index(p.material) if p.material in ids else 0
    return _rgb(WOOD[i % len(WOOD)])


def _basis(look, up_hint):
    f = np.array(look, float)
    f /= np.linalg.norm(f)
    r = np.cross(f, up_hint)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return r, u, f


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def render(design: Design, view: str = "3d", size=(1200, 900), title: str | None = None) -> bytes:
    look, up_hint, label = VIEWS[view]
    r, u, f = _basis(look, up_hint)
    W, H = size[0] * SS, size[1] * SS
    flat = view in ("front", "side", "top")
    parts = [p for p in design.parts if p.solid is not None]
    if not parts:
        img = Image.new("RGB", size, BG)
        ImageDraw.Draw(img).text((24, 20), f"{title or design.title}: no parts yet", fill=INK, font=_font(22))
        return _png(img)

    allv = np.concatenate([np.asarray(p.solid.verts, float) for p in parts])
    sx, sy = allv @ r, allv @ u
    margin_frac = 0.16 if flat else 0.08
    span_x, span_y = sx.max() - sx.min(), sy.max() - sy.min()
    scale = min(W * (1 - 2 * margin_frac) / max(span_x, 1), H * (1 - 2 * margin_frac - 0.06) / max(span_y, 1))
    cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2

    def project(v):
        v = np.asarray(v, float)
        return np.stack([W / 2 + (v @ r - cx) * scale, H / 2 + 0.03 * H - (v @ u - cy) * scale, v @ f], axis=-1)

    light = -np.array(look, float) / np.linalg.norm(look) * 0.55 + np.array([-0.35, -0.25, 0.75])
    light /= np.linalg.norm(light)

    def pass_(group):
        z = np.full((H, W), np.inf, np.float32)
        col = np.zeros((H, W, 3), np.float32)
        ids = np.full((H, W), -1, np.int32)
        fid = 0
        for p in group:
            base = part_color(p, design)
            verts = np.asarray(p.solid.verts, float)
            sv = project(verts)
            for face, n in zip(p.solid.faces, p.solid.normals()):
                n = np.asarray(n, float)
                fid += 1
                if np.dot(n, f) >= -1e-9:  # back face (convex solids)
                    continue
                shade = 0.55 + 0.45 * max(0.0, float(np.dot(n, light)))
                c = np.clip(base * shade, 0, 255)
                for i in range(1, len(face) - 1):
                    _tri(sv[[face[0], face[i], face[i + 1]]], z, col, ids, c, fid)
        return z, col, ids

    solids = [p for p in parts if p.kind != "reference"]
    refs = [p for p in parts if p.kind == "reference"]
    z, col, ids = pass_(solids)
    img = np.where(np.isinf(z)[..., None], np.array(BG, np.float32), col)
    img = _edges(img, ids, EDGE)
    if refs:
        rz, rcol, rids = pass_(refs)
        front = rz < z
        img = np.where(front[..., None], img * 0.55 + rcol * 0.45, img)
        img = _edges(img, np.where(front, rids, -1), REF_EDGE)

    out = Image.fromarray(img.astype(np.uint8)).resize(size, Image.LANCZOS)
    d = ImageDraw.Draw(out)
    b = design.bounds(include_reference=False)
    d.text((20, 16), f"{title or design.title} - {label}", fill=INK, font=_font(22))
    sz = b.get("size")
    if sz:
        d.text((20, size[1] - 34), f"Overall {sz[0]:.0f} x {sz[1]:.0f} x {sz[2]:.0f} mm (W x D x H)",
               fill=INK, font=_font(18))
    if flat and sz:
        _dims(d, design, view, lambda v: project(v)[..., :2] / SS)
    return _png(out)


def _tri(t, z, col, ids, c, fid):
    H, W = z.shape
    x0, x1 = int(max(0, math.floor(t[:, 0].min()))), int(min(W - 1, math.ceil(t[:, 0].max())))
    y0, y1 = int(max(0, math.floor(t[:, 1].min()))), int(min(H - 1, math.ceil(t[:, 1].max())))
    if x1 < x0 or y1 < y0:
        return
    (ax, ay, az), (bx, by, bz), (qx, qy, qz) = t
    den = (by - qy) * (ax - qx) + (qx - bx) * (ay - qy)
    if abs(den) < 1e-9:
        return
    ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1]
    px, py = xs + 0.5, ys + 0.5
    w0 = ((by - qy) * (px - qx) + (qx - bx) * (py - qy)) / den
    w1 = ((qy - ay) * (px - qx) + (ax - qx) * (py - qy)) / den
    w2 = 1 - w0 - w1
    eps = -1e-6
    inside = (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
    if not inside.any():
        return
    depth = (w0 * az + w1 * bz + w2 * qz).astype(np.float32)
    zs = z[y0:y1 + 1, x0:x1 + 1]
    win = inside & (depth < zs - 1e-3)
    zs[win] = depth[win]
    col[y0:y1 + 1, x0:x1 + 1][win] = c
    ids[y0:y1 + 1, x0:x1 + 1][win] = fid


def _edges(img, ids, color):
    e = np.zeros(ids.shape, bool)
    for dy, dx in ((0, 1), (1, 0), (0, 2), (2, 0)):
        a = ids[: ids.shape[0] - dy, : ids.shape[1] - dx]
        b = ids[dy:, dx:]
        diff = (a != b) & ((a >= 0) | (b >= 0))
        e[: ids.shape[0] - dy, : ids.shape[1] - dx] |= diff
    return np.where(e[..., None], np.array(color, np.float32), img)


def _dims(d, design, view, proj):
    """Overall width/depth and height lines outside the drawing."""
    b = design.bounds(include_reference=False)
    lo, hi = b["min"], b["max"]
    font = _font(17)
    ax_h = {"front": 0, "side": 1, "top": 0}[view]  # horizontal extent axis
    ax_v = {"front": 2, "side": 2, "top": 1}[view]  # vertical extent axis
    corner = [lo[0], lo[1], lo[2]]
    if view == "front":
        corner[1] = lo[1]
    a = list(corner)
    bpt = list(corner)
    bpt[ax_h] = hi[ax_h]
    c = list(corner)
    c[ax_v] = hi[ax_v]
    pa, pb, pc = (proj(np.array(v, float)) for v in (a, bpt, c))
    # horizontal: below the drawing
    ymax = max(pa[1], pb[1]) + 28
    d.line([(pa[0], ymax), (pb[0], ymax)], fill=INK, width=1)
    for x in (pa[0], pb[0]):
        d.line([(x, ymax - 7), (x, ymax + 7)], fill=INK, width=1)
    txt = f"{hi[ax_h] - lo[ax_h]:.0f}"
    tw = d.textlength(txt, font=font)
    d.text(((pa[0] + pb[0]) / 2 - tw / 2, ymax + 6), txt, fill=INK, font=font)
    # vertical: left of the drawing
    xmin = min(pa[0], pc[0]) - 28
    d.line([(xmin, pa[1]), (xmin, pc[1])], fill=INK, width=1)
    for y in (pa[1], pc[1]):
        d.line([(xmin - 7, y), (xmin + 7, y)], fill=INK, width=1)
    txt = f"{hi[ax_v] - lo[ax_v]:.0f}"
    tw = d.textlength(txt, font=font)
    d.text((xmin - tw - 10, (pa[1] + pc[1]) / 2 - 9), txt, fill=INK, font=font)


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def render_all(design: Design, size=(1200, 900)) -> dict[str, bytes]:
    return {v: render(design, v, size) for v in VIEWS}
