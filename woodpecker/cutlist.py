"""Cut list, stock to buy (with cutting layouts), bought items, cost, and a tip check."""
from __future__ import annotations

import math
from collections import OrderedDict

from .model import Design, Part

# ---------------------------------------------------------------- cut list


def _cut_dims(p: Part) -> dict:
    dims = sorted((round(v, 1) for v in p.size), reverse=True)
    if p.kind == "lumber":
        return {"length": dims[0], "section": sorted(dims[1:])}
    return {"length": dims[0], "width": dims[1], "thickness": dims[2]}


def cut_list(design: Design) -> dict:
    materials = design.raw.get("materials", {})
    rows: "OrderedDict[tuple, dict]" = OrderedDict()
    for p in design.parts:
        if p.kind not in ("sheet", "lumber"):
            continue
        d = _cut_dims(p)
        shape = {"gusset": "triangle", "cylinder": "round", "sphere": "ball", "prism": "profile"}.get(p.shape, "rect")
        ends = tuple(round(a, 1) for a in p.ends)
        notes = tuple(p.cut_notes)
        key = (p.material, shape, d["length"], d.get("width"), tuple(d.get("section", ())), ends, notes)
        row = rows.setdefault(key, {
            "material": p.material,
            "material_name": materials[p.material].get("name", p.material),
            "kind": p.kind, "shape": shape, **d, "qty": 0, "parts": [], "names": [],
            "ends": list(ends) if any(ends) else None, "cut_notes": list(notes),
        })
        row["qty"] += 1
        row["parts"].append(p.id)
        base = p.base_name
        if base not in row["names"]:
            row["names"].append(base)

    out_rows = []
    for r in rows.values():
        names = r.pop("names")
        r["label"] = names[0] if len(names) == 1 else (
            " / ".join(names) if len(names) <= 3 else f"{names[0]} … ({len(names)} names)")
        out_rows.append(r)
    stock = stock_to_buy(design, out_rows)
    bought = bought_items(design)
    hardware = hardware_list(design)
    return {
        "rows": out_rows, "stock": stock, "bought": bought, "hardware": hardware,
        "cost": cost(design, stock, bought, hardware),
    }


# ---------------------------------------------------------------- stock + layouts

def stock_to_buy(design: Design, rows: list[dict]) -> list[dict]:
    materials = design.raw.get("materials", {})
    shop = design.raw.get("shop", {})
    kerf = float(shop.get("kerf", 3))
    result = []
    for mat_id, m in materials.items():
        mine = [r for r in rows if r["material"] == mat_id]
        if not mine:
            continue
        if m.get("kind") == "lumber":
            stock_len = float(m.get("stock_length", 3000))
            pieces = sorted(((r["length"], r["label"]) for r in mine for _ in range(r["qty"])),
                            key=lambda x: -x[0])
            boards, too_long = _first_fit(pieces, stock_len, kerf)
            result.append({
                "material": mat_id, "name": m.get("name", mat_id), "kind": "lumber",
                "count": len(boards), "unit": f"{stock_len:g} mm length", "stock_length": stock_len,
                "detail": [{"cuts": [c[0] for c in b], "labels": [c[1] for c in b],
                            "offcut": round(stock_len - sum(c[0] for c in b) - kerf * len(b), 1)} for b in boards],
                "warnings": [f"{lbl} ({l:g} mm) is longer than the {stock_len:g} mm stock" for l, lbl in too_long],
                "method": "first-fit decreasing, kerf included",
            })
        elif m.get("kind") == "sheet":
            sx, sy = (float(v) for v in m.get("stock", [2500, 1250]))
            grain = bool(m.get("grain", False))
            pieces, warnings = [], []
            for r in mine:
                L, W = r["length"], r["width"]
                if r["shape"] == "triangle":
                    # two identical right triangles nest into one rectangle
                    pairs, single = divmod(r["qty"], 2)
                    pieces += [(L, W, f"{r['label']} ×2 (cut diagonally)")] * pairs
                    pieces += [(L, W, r["label"])] * single
                else:
                    pieces += [(L, W, r["label"])] * r["qty"]
            fits = [p for p in pieces if _fits(p[0], p[1], sx, sy, grain)]
            for p in pieces:
                if p not in fits:
                    warnings.append(f"{p[2]} ({p[0]:g}x{p[1]:g}) does not fit a {sx:g}x{sy:g} sheet")
            sheets = _guillotine(fits, sx, sy, kerf, grain)
            area = sum(r["w"] * r["h"] for s in sheets for r in s["rects"])
            result.append({
                "material": mat_id, "name": m.get("name", mat_id), "kind": "sheet",
                "count": len(sheets), "unit": f"{sx:g}x{sy:g} mm sheet", "sheet": [sx, sy],
                "used_fraction": round(area / (len(sheets) * sx * sy), 2) if sheets else 0,
                "layouts": sheets, "warnings": warnings,
                "method": "guillotine layout, kerf included" + ("" if grain else ", pieces may rotate"),
            })
    return result


def _fits(L, W, sx, sy, grain):
    return (L <= sx and W <= sy) or (not grain and L <= sy and W <= sx)


def _first_fit(pieces, stock_len, kerf):
    boards: list[list[tuple]] = []
    too_long = []
    for piece in pieces:
        if piece[0] > stock_len:
            too_long.append(piece)
            continue
        for b in boards:
            if sum(c[0] for c in b) + kerf * len(b) + piece[0] <= stock_len + 1e-6:
                b.append(piece)
                break
        else:
            boards.append([piece])
    return boards, too_long


def _guillotine(pieces, sx, sy, kerf, grain):
    """Best-area-fit guillotine packing. Returns sheets of placed rects (x, y, w, h, label)."""
    order = sorted(pieces, key=lambda p: (-(p[0] * p[1]), -max(p[0], p[1])))
    sheets: list[dict] = []
    for L, W, label in order:
        placed = False
        for sh in sheets:
            if _place(sh, L, W, label, kerf, grain):
                placed = True
                break
        if not placed:
            sh = {"free": [(0.0, 0.0, sx, sy)], "placed": []}
            sheets.append(sh)
            _place(sh, L, W, label, kerf, grain)
    return [{"rects": [{"x": round(x, 1), "y": round(y, 1), "w": w, "h": h, "label": lbl}
                       for x, y, w, h, lbl in sh["placed"]]} for sh in sheets]


def _place(sh, L, W, label, kerf, grain):
    best = None
    for i, (fx, fy, fw, fh) in enumerate(sh["free"]):
        for w, h in ([(L, W)] if grain else [(L, W), (W, L)]):
            if w <= fw + 1e-6 and h <= fh + 1e-6:
                waste = fw * fh - w * h
                if best is None or waste < best[0]:
                    best = (waste, i, w, h)
    if best is None:
        return False
    _, i, w, h = best
    fx, fy, fw, fh = sh["free"].pop(i)
    sh["placed"].append((fx, fy, w, h, label))
    # split along the shorter leftover so the bigger offcut stays whole
    rw, rh = fw - w - kerf, fh - h - kerf
    if rw * fh > fw * rh:
        right, top = (fx + w + kerf, fy, rw, fh), (fx, fy + h + kerf, w, rh)
    else:
        right, top = (fx + w + kerf, fy, rw, h), (fx, fy + h + kerf, fw, rh)
    for r in (right, top):
        if r[2] > 1 and r[3] > 1:
            sh["free"].append(r)
    return True


# ---------------------------------------------------------------- bought things

def bought_items(design: Design) -> list[dict]:
    """Catalog components (one per instance, not per panel)."""
    seen: "OrderedDict[str, dict]" = OrderedDict()
    for p in design.parts:
        if p.kind != "component":
            continue
        c = design.components.get(p.component, {})
        it = seen.setdefault(p.component, {
            "catalog_id": p.component, "item": f"{c.get('brand', '')} {c.get('name', p.component)}".strip(),
            "article": c.get("article"), "url": c.get("url"), "price": c.get("price"),
            "instances": set(),
        })
        it["instances"].add(p.instance)
    out = []
    for it in seen.values():
        it["qty"] = len(it.pop("instances"))
        out.append(it)
    return out


def hardware_list(design: Design) -> list[dict]:
    """Modelled hardware parts (counted) plus the design's `hardware` list."""
    items: "OrderedDict[str, dict]" = OrderedDict()
    materials = design.raw.get("materials", {})
    for p in design.parts:
        if p.kind != "hardware":
            continue
        m = materials[p.material]
        it = items.setdefault(p.material, {
            "item": m.get("name", p.material), "qty": 0, "notes": m.get("notes", ""), "modelled": True,
            "price_eur": m.get("price_eur"),
        })
        it["qty"] += 1
    for h in design.raw.get("hardware", []):
        items[f"_{len(items)}"] = {"item": h["item"], "qty": h.get("qty", 1),
                                   "notes": h.get("notes", ""), "modelled": False,
                                   "price_eur": h.get("price_eur")}
    return list(items.values())


def cost(design: Design, stock, bought, hardware) -> dict:
    """Only prices written in the design or catalog; nothing is guessed."""
    materials = design.raw.get("materials", {})
    lines, missing = [], []

    def line(item, qty, unit, source=None):
        if unit is None:
            missing.append(item)
            return
        lines.append({"item": item, "qty": qty, "unit_eur": float(unit),
                      "total_eur": round(qty * float(unit), 2), "source": source})

    for s in stock:
        m = materials.get(s["material"], {})
        line(f"{s['name']} ({s['unit']})", s["count"], m.get("price_eur"), m.get("price_source"))
    for b in bought:
        p = b.get("price") or {}
        unit = p.get("amount") if p.get("currency", "EUR") == "EUR" else None
        line(b["item"], b["qty"], unit, b.get("url"))
    for h in hardware:
        line(h["item"], h["qty"], h.get("price_eur"))
    return {"lines": lines, "total_eur": round(sum(x["total_eur"] for x in lines), 2), "missing": missing}


# ---------------------------------------------------------------- stability

def part_mass(p: Part, materials: dict) -> float:
    if p.mass_kg is not None:
        return float(p.mass_kg)
    m = materials.get(p.material, {})
    if "mass_kg" in m:
        return float(m["mass_kg"])
    density = float(m.get("density", 0))  # kg/m3
    return p.volume_mm3 * 1e-9 * density


def _hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) -
                                   (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(p)
        return h

    lower, upper = half(pts), half(reversed(pts))
    return lower[:-1] + upper[:-1]


def _ray_exit(hull, o, d):
    """Distance from o (inside) along unit direction d to the hull boundary."""
    best = math.inf
    n = len(hull)
    for i in range(n):
        a, b = hull[i], hull[(i + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]
        den = d[0] * ey - d[1] * ex
        if abs(den) < 1e-12:
            continue
        t = ((a[0] - o[0]) * ey - (a[1] - o[1]) * ex) / den
        u = ((a[0] - o[0]) * d[1] - (a[1] - o[1]) * d[0]) / den
        if t >= -1e-9 and -1e-9 <= u <= 1 + 1e-9:
            best = min(best, t)
    return best


def _inside(hull, o):
    n = len(hull)
    sign = 0
    for i in range(n):
        a, b = hull[i], hull[(i + 1) % n]
        c = (b[0] - a[0]) * (o[1] - a[1]) - (b[1] - a[1]) * (o[0] - a[0])
        if abs(c) < 1e-9:
            continue
        s = 1 if c > 0 else -1
        if sign and s != sign:
            return False
        sign = s
    return True


def stability(design: Design) -> dict:
    """Centre of gravity and how far the piece can lean before it tips.

    The footprint is the convex hull of everything touching the floor (z = 0). Casters
    and other hardware feet count at their centre (that is where a caster pivots).
    """
    materials = design.raw.get("materials", {})
    total = 0.0
    moment = [0.0, 0.0, 0.0]
    breakdown = []
    for p in design.parts:
        m = part_mass(p, materials)
        if m <= 0:
            continue
        c = p.centroid()
        total += m
        for i in range(3):
            moment[i] += m * c[i]
        breakdown.append({"part": p.id, "name": p.name, "mass_kg": round(m, 2)})
    if total == 0:
        return {"total_mass_kg": 0, "note": "no masses known"}
    cog = [v / total for v in moment]
    if design.raw.get("anchored"):
        text = design.raw["anchored"] if isinstance(design.raw["anchored"], str) \
            else "Fixed to footings, so there is no tip check."
        return {"total_mass_kg": round(total, 1), "cog_mm": [round(v) for v in cog],
                "mass_breakdown": breakdown, "anchored": text,
                "note": f"About {total:.0f} kg of parts with a known weight. {text}"}

    pts = []
    for p in design.parts:
        if abs(p.at[2]) > 0.5:
            continue
        if p.kind == "hardware":
            pts.append(((p.at[0] + p.max[0]) / 2, (p.at[1] + p.max[1]) / 2))
        else:
            pts += [(v[0], v[1]) for v in p.solid.verts if abs(v[2]) < 0.5]
    hull = _hull([(round(x, 3), round(y, 3)) for x, y in pts])
    if len(hull) < 3:
        return {"total_mass_kg": round(total, 1), "cog_mm": [round(v) for v in cog],
                "note": "nothing (or only a line) touches the floor at z=0, so no footprint"}

    top = max(p.max[2] for p in design.parts)
    h = max(cog[2], 1.0)
    o = (cog[0], cog[1])
    tips = {}
    inside = _inside(hull, o)
    for name, d in {"forward": (0, -1), "backward": (0, 1), "left": (-1, 0), "right": (1, 0)}.items():
        dist = _ray_exit(hull, o, d) if inside else 0.0
        if not inside or dist == math.inf:
            tips[name] = {"lever_mm": 0, "tip_angle_deg": 0, "push_at_top_kg": 0,
                          "note": "centre of gravity is outside the footprint: it falls over"}
            continue
        tips[name] = {
            "lever_mm": round(dist),
            "tip_angle_deg": round(math.degrees(math.atan2(dist, h)), 1),
            "push_at_top_kg": round(total * dist / top, 1),
        }
    worst = min(tips, key=lambda k: tips[k]["tip_angle_deg"])
    xs, ys = [p[0] for p in hull], [p[1] for p in hull]
    return {
        "total_mass_kg": round(total, 1),
        "cog_mm": [round(v) for v in cog],
        "footprint_mm": {"x": [round(min(xs)), round(max(xs))], "y": [round(min(ys)), round(max(ys))],
                         "hull": [[round(x), round(y)] for x, y in hull]},
        "top_mm": round(top),
        "tip": tips,
        "weakest": worst,
        "mass_breakdown": sorted(breakdown, key=lambda b: -b["mass_kg"]),
    }
