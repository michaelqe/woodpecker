"""Cut list, stock to buy, hardware list, and a stability (tip) check."""
from __future__ import annotations

import math
from collections import OrderedDict

from .model import Design, Part

G = 9.81


def _cut_dims(p: Part) -> dict:
    dims = sorted(p.size, reverse=True)
    if p.kind == "lumber":
        return {"length": dims[0], "section": sorted(dims[1:])}
    # sheet: length x width x thickness, longest first
    return {"length": dims[0], "width": dims[1], "thickness": dims[2]}


def cut_list(design: Design) -> dict:
    materials = design.raw.get("materials", {})
    rows: "OrderedDict[tuple, dict]" = OrderedDict()
    for p in design.parts:
        if p.kind not in ("sheet", "lumber"):
            continue
        d = _cut_dims(p)
        shape = "triangle" if p.shape == "gusset" else "rect"
        key = (p.material, shape, d["length"], d.get("width"), tuple(d.get("section", ())))
        row = rows.setdefault(key, {
            "material": p.material,
            "material_name": materials[p.material].get("name", p.material),
            "kind": p.kind, "shape": shape, **d, "qty": 0, "parts": [], "names": [],
        })
        row["qty"] += 1
        row["parts"].append(p.id)
        if p.name not in row["names"]:
            row["names"].append(p.name)

    out_rows = []
    for r in rows.values():
        r["label"] = " / ".join(r.pop("names"))
        out_rows.append(r)
    return {
        "rows": out_rows,
        "stock": stock_to_buy(design, out_rows),
        "hardware": hardware_list(design),
    }


def stock_to_buy(design: Design, rows: list[dict]) -> list[dict]:
    materials = design.raw.get("materials", {})
    kerf = float(design.raw.get("shop", {}).get("kerf", 3))
    result = []
    for mat_id, m in materials.items():
        mine = [r for r in rows if r["material"] == mat_id]
        if not mine:
            continue
        if m.get("kind") == "lumber":
            stock_len = float(m.get("stock_length", 3000))
            pieces = sorted((r["length"] for r in mine for _ in range(r["qty"])), reverse=True)
            boards, too_long = _first_fit(pieces, stock_len, kerf)
            result.append({
                "material": mat_id, "name": m.get("name", mat_id), "kind": "lumber",
                "count": len(boards), "unit": f"{stock_len:g} mm length",
                "detail": [{"cuts": b, "offcut": round(stock_len - sum(b) - kerf * len(b), 1)} for b in boards],
                "warnings": [f"piece {l:g} mm is longer than {stock_len:g} mm stock" for l in too_long],
                "method": "first-fit decreasing, kerf included",
            })
        elif m.get("kind") == "sheet":
            sx, sy = m.get("stock", [2500, 1250])
            area = 0.0
            warnings = []
            for r in mine:
                a = r["length"] * r["width"] * (0.5 if r["shape"] == "triangle" else 1)
                area += a * r["qty"]
                if not ((r["length"] <= max(sx, sy)) and (r["width"] <= min(sx, sy))):
                    warnings.append(f"{r['label']} ({r['length']:g}x{r['width']:g}) does not fit one sheet")
            waste = float(design.raw.get("shop", {}).get("sheet_waste", 0.25))
            sheet_area = sx * sy
            count = max(1, math.ceil(area * (1 + waste) / sheet_area))
            result.append({
                "material": mat_id, "name": m.get("name", mat_id), "kind": "sheet",
                "count": count, "unit": f"{sx:g}x{sy:g} mm sheet",
                "used_fraction": round(area / (count * sheet_area), 2),
                "warnings": warnings,
                "method": f"area estimate with {int(waste * 100)}% waste (no nesting yet)",
            })
    return result


def _first_fit(pieces, stock_len, kerf):
    boards: list[list[float]] = []
    too_long = []
    for piece in pieces:
        if piece + kerf > stock_len + 1e-6 and piece > stock_len:
            too_long.append(piece)
            continue
        for b in boards:
            if sum(b) + kerf * len(b) + piece <= stock_len + 1e-6:
                b.append(piece)
                break
        else:
            boards.append([piece])
    return boards, too_long


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
        })
        it["qty"] += 1
    for h in design.raw.get("hardware", []):
        items[f"_{len(items)}"] = {"item": h["item"], "qty": h.get("qty", 1),
                                   "notes": h.get("notes", ""), "modelled": False}
    return list(items.values())


# ---------------------------------------------------------------- stability

def part_mass(p: Part, materials: dict) -> float:
    if p.mass_kg is not None:
        return float(p.mass_kg)
    m = materials[p.material]
    if "mass_kg" in m:
        return float(m["mass_kg"])
    density = float(m.get("density", 0))  # kg/m3
    return p.volume_mm3 * 1e-9 * density


def stability(design: Design) -> dict:
    """Centre of gravity and how far the piece can lean before it tips.

    The footprint is the outline of every part that touches the floor (z == 0),
    e.g. the casters. Masses come from density x volume, or a part/material's
    explicit `mass_kg`; loose hardware in the `hardware` list counts if it gives
    `mass_kg` per item and `at` (otherwise it is ignored).
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

    feet = [p for p in design.parts if abs(p.at[2]) < 0.5]
    if not feet:
        return {"total_mass_kg": round(total, 2), "cog": [round(v) for v in cog],
                "note": "nothing touches the floor (z=0), so no footprint"}
    # casters pivot near their centres, not their outer edge: use foot centres
    cx = [p.at[0] + p.size[0] / 2 for p in feet]
    cy = [p.at[1] + p.size[1] / 2 for p in feet]
    lo_x, hi_x, lo_y, hi_y = min(cx), max(cx), min(cy), max(cy)

    top = max(p.max[2] for p in design.parts)
    h = cog[2]
    directions = {
        "forward": cog[1] - lo_y,
        "backward": hi_y - cog[1],
        "left": cog[0] - lo_x,
        "right": hi_x - cog[0],
    }
    tips = {}
    for d, dist in directions.items():
        if dist <= 0:
            tips[d] = {"lever_mm": round(dist), "tip_angle_deg": 0, "push_at_top_kg": 0,
                       "note": "centre of gravity is outside the footprint: it falls over"}
            continue
        tips[d] = {
            "lever_mm": round(dist),
            "tip_angle_deg": round(math.degrees(math.atan2(dist, h)), 1),
            # horizontal push at the very top that starts tipping (static)
            "push_at_top_kg": round(total * dist / top, 1),
        }
    worst = min(tips, key=lambda k: tips[k]["tip_angle_deg"])
    return {
        "total_mass_kg": round(total, 1),
        "cog_mm": [round(v) for v in cog],
        "footprint_mm": {"x": [round(lo_x), round(hi_x)], "y": [round(lo_y), round(hi_y)]},
        "top_mm": round(top),
        "tip": tips,
        "weakest": worst,
        "mass_breakdown": sorted(breakdown, key=lambda b: -b["mass_kg"]),
    }
