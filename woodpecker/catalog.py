"""Catalog of bought products (IKEA furniture, etc.) that designs can drop in as components.

Each product is one JSON file under catalog/<brand>/<id>.json holding the dimensions
the maker publishes (with source URL and date) plus a `geometry` recipe that turns
those dimensions into panels for the viewer, the tip check and the overlap check.
Anything the maker does not publish (panel thickness, usually) is listed in
`assumed` so the viewer and the agent can say so.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model_errors import DesignError

REQUIRED = ("id", "brand", "name", "size", "geometry", "url", "retrieved")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")


def catalog_dir() -> Path:
    from . import store  # late import: store owns ROOT (tests repoint it)
    return store.ROOT / "catalog"


def all_items() -> dict[str, dict]:
    out = {}
    d = catalog_dir()
    if not d.exists():
        return out
    for f in sorted(d.rglob("*.json")):
        try:
            item = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        out[item.get("id", f.stem)] = item
    return out


def get(item_id: str) -> dict:
    items = all_items()
    if item_id not in items:
        raise DesignError(f"no catalog item {item_id!r}")
    return items[item_id]


def search(q: str = "") -> list[dict]:
    terms = [t for t in re.split(r"\W+", q.lower()) if t]
    out = []
    for it in all_items().values():
        hay = " ".join(str(it.get(k, "")) for k in ("id", "brand", "name", "article", "category")).lower()
        if all(t in hay for t in terms):
            out.append(summary(it))
    return out


def by_article(article: str) -> str | None:
    """Catalog id of the item with this maker's article number, if any."""
    a = article.replace(".", "")
    for it in all_items().values():
        if str(it.get("article", "")).replace(".", "") == a:
            return it["id"]
    return None


def summary(it: dict) -> dict:
    return {
        "id": it["id"], "brand": it.get("brand"), "name": it.get("name"),
        "article": it.get("article"), "size_mm": it.get("size"),
        "price": it.get("price"), "load": it.get("load"), "url": it.get("url"),
    }


def add(item: dict) -> dict:
    missing = [k for k in REQUIRED if k not in item]
    if missing:
        raise DesignError(f"catalog item needs {', '.join(missing)}")
    if not _ID.match(item["id"]):
        raise DesignError("catalog id: lowercase letters, digits and dashes")
    generate(item, {})  # validates the geometry recipe
    brand = re.sub(r"[^a-z0-9-]", "-", item["brand"].lower())
    path = catalog_dir() / brand / f"{item['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n")
    return summary(item)


def mass_kg(item: dict) -> tuple[float | None, str]:
    if item.get("mass_kg") is not None:
        return float(item["mass_kg"]), "product weight"
    if item.get("package_kg") is not None:
        return float(item["package_kg"]), "package weight (product is a little lighter)"
    return None, "unknown"


# ---------------------------------------------------------------- generators

def generate(item: dict, options: dict) -> list[dict]:
    """Panels in the product's own frame: x = width, y = depth (front y=0), z = up."""
    geo = {**item["geometry"], **(options or {})}
    W, D, H = (float(v) for v in item["size"])
    gen = geo.get("generator")
    if gen == "cube_grid":
        return _cube_grid(W, D, H, int(geo["cols"]), int(geo["rows"]), float(geo["panel"]),
                          float(geo.get("back", 0)))
    if gen == "carcass":
        return _carcass(W, D, H, float(geo["panel"]), float(geo.get("back", 0)),
                        int(geo.get("shelves", 0)), int(geo.get("partitions", 0)),
                        float(geo.get("plinth", 0)))
    if gen == "table":
        return _table(W, D, H, float(geo.get("top", 40)), float(geo.get("leg", 50)))
    if gen == "vehicle":
        return _vehicle(W, D, H, geo)
    if gen == "block":
        return [_p("body", "Body", [W, D, H], [0, 0, 0])]
    raise DesignError(f"catalog {item.get('id')}: unknown generator {gen!r}")


def _p(sub, name, size, at):
    if min(size) <= 0:
        raise DesignError(f"catalog panel {sub} has non-positive size {size}")
    return {"sub": sub, "name": name, "size": [round(s, 2) for s in size], "at": [round(a, 2) for a in at]}


def _cube_grid(W, D, H, cols, rows, t, back):
    """KALLAX-style: frame, full-width shelves, dividers between shelves, all one thickness."""
    d = D - back
    cw = (W - (cols + 1) * t) / cols
    ch = (H - (rows + 1) * t) / rows
    parts = [
        _p("bottom", "Bottom", [W, d, t], [0, 0, 0]),
        _p("top", "Top", [W, d, t], [0, 0, H - t]),
        _p("side_l", "Left side", [t, d, H - 2 * t], [0, 0, t]),
        _p("side_r", "Right side", [t, d, H - 2 * t], [W - t, 0, t]),
    ]
    for r in range(1, rows):
        parts.append(_p(f"shelf_{r}", f"Shelf {r}", [W - 2 * t, d, t], [t, 0, r * (ch + t)]))
    for c in range(1, cols):
        x = c * (cw + t)
        for r in range(rows):
            parts.append(_p(f"div_{c}_{r}", f"Divider {c}", [t, d, ch], [x, 0, t + r * (ch + t)]))
    if back:
        parts.append(_p("back", "Back", [W, back, H], [0, d, 0]))
    return parts


def _carcass(W, D, H, t, back, shelves, partitions, plinth):
    """BILLY/BESTÅ/EKET-style box: full-height sides, top and bottom between them."""
    d = D - back
    iw = W - 2 * t
    parts = [
        _p("side_l", "Left side", [t, d, H], [0, 0, 0]),
        _p("side_r", "Right side", [t, d, H], [W - t, 0, 0]),
        _p("top", "Top", [iw, d, t], [t, 0, H - t]),
        _p("bottom", "Bottom", [iw, d, t], [t, 0, plinth]),
    ]
    if plinth:
        parts.append(_p("plinth", "Plinth", [iw, t, plinth], [t, 0, 0]))
    if back:
        parts.append(_p("back", "Back", [W, back, H], [0, d, 0]))
    bays = partitions + 1
    bw = (iw - partitions * t) / bays
    z0, z1 = plinth + t, H - t
    for k in range(1, partitions + 1):
        parts.append(_p(f"partition_{k}", f"Partition {k}", [t, d, z1 - z0], [t + k * bw + (k - 1) * t, 0, z0]))
    gap = (z1 - z0 - shelves * t) / (shelves + 1)
    for s in range(1, shelves + 1):
        z = z0 + s * gap + (s - 1) * t
        for b in range(bays):
            x = t + b * (bw + t)
            parts.append(_p(f"shelf_{s}_{b}", f"Shelf {s}", [bw, d, t], [x, 0, z]))
    return parts


def _table(W, D, H, top, leg):
    """Top on four square legs at the corners."""
    parts = [_p("top", "Top", [W, D, top], [0, 0, H - top])]
    for sub, name, x, y in (("leg_fl", "Leg, front left", 0, 0), ("leg_fr", "Leg, front right", W - leg, 0),
                            ("leg_bl", "Leg, back left", 0, D - leg), ("leg_br", "Leg, back right", W - leg, D - leg)):
        parts.append(_p(sub, name, [leg, leg, H - top], [x, y, 0]))
    return parts


def _vehicle(W, L, H, v):
    """A car or van to check fit in carports and garages: x = width, y = length with the
    front bumper at y = 0, z = up. Built from convex pieces: lower body and cabin (side
    profiles extruded across the width), glass, mirrors and round wheels.

    v: wheelbase, front_overhang, wheel_dia, tyre_w, clearance (ground clearance), and shape
    numbers as fractions or mm: bonnet_h (top of the bonnet at the front), belt_h (window
    line), windscreen_base (y where the bonnet meets the glass), windscreen_top (y where the
    glass meets the roof), roof_end (y where the roof starts to fall at the back), tail_h
    (height of the rear edge of the roof line drop), tumblehome (how much narrower the cabin is
    each side), mirror_w (overall width over the mirrors), body_color, glass_color.
    """
    wb, fo = float(v["wheelbase"]), float(v["front_overhang"])
    wd, tw = float(v.get("wheel_dia", 650)), float(v.get("tyre_w", 215))
    gc = float(v.get("clearance", 150))
    bonnet = float(v["bonnet_h"])
    belt = float(v["belt_h"])
    ws0, ws1 = float(v["windscreen_base"]), float(v["windscreen_top"])
    roof_end, tail = float(v["roof_end"]), float(v.get("tail_h", belt))
    th = float(v.get("tumblehome", 70))
    body_c, glass_c = v.get("body_color", "#c4c8cc"), v.get("glass_color", "#2b3a48")
    sill = gc + 0.55 * (wd / 2)  # body bottom between the wheels is lower; keep it simple
    nose = float(v.get("nose", 120))      # rounding at the bumper corners
    parts = []

    def piece(sub, name, profile, x0, width, color):
        parts.append({"sub": sub, "name": name, "shape": "prism", "axis": "x",
                      "profile": [[round(a, 1), round(b, 1)] for a, b in profile],
                      "length": round(width, 1), "at": [round(x0, 1), 0, 0], "color": color})

    # lower body: bumper to bumper, ground clearance to the belt line, bonnet sloping up to the glass
    piece("body", "Body", [(0, gc + nose), (nose, gc), (L - nose, gc), (L, gc + nose), (L, belt),
                           (ws0, belt), (nose * 0.5, bonnet), (0, bonnet - nose * 0.6)], 0, W, body_c)
    # cabin: from the windscreen base over the roof to the tail, a little narrower
    cab = [(ws0, belt), (L - 10, belt), (L - 10, tail), (roof_end, H), (ws1, H)]
    piece("cabin", "Cabin and roof", cab, th, W - 2 * th, body_c)
    # glass: windscreen and side windows, a slim layer just proud of the cabin
    def front_y(z):  # the cabin's sloping front face
        return ws0 + (ws1 - ws0) * (z - belt) / (H - belt)
    zb, zt = belt + 20, H - 35
    piece("windscreen", "Windscreen", [(front_y(zb) - 12, zb), (front_y(zb) + 3, zb),
                                       (front_y(zt) + 3, zt), (front_y(zt) - 12, zt)], th + 40, W - 2 * th - 80, glass_c)
    side = [(ws0 + (ws1 - ws0) * 0.35, belt + 40), (min(L - 60, roof_end + (L - roof_end) * 0.5), belt + 40),
            (roof_end - 30, H - 70), (ws1 + 40, H - 70)]
    from .geometry import is_convex
    if is_convex(side):
        piece("window_l", "Side windows, left", side, th - 8, 10, glass_c)
        piece("window_r", "Side windows, right", side, W - th - 2, 10, glass_c)
    # mirrors
    mw = (float(v.get("mirror_w", W + 300)) - W) / 2
    if mw > 20:
        for side_, x in (("l", -mw), ("r", W)):
            parts.append({"sub": f"mirror_{side_}", "name": "Mirror", "size": [round(mw, 1), 90, 130],
                          "at": [round(x, 1), round(ws0 + 60, 1), round(belt - 20, 1)], "color": body_c})
    # wheels: tyres with a lighter hub
    for axle, y in (("front", fo), ("rear", fo + wb)):
        for side_, x in (("l", 0), ("r", W - tw)):
            parts.append({"sub": f"tyre_{axle}_{side_}", "name": f"Wheel, {axle}", "shape": "cylinder", "axis": "x",
                          "size": [tw, wd, wd], "at": [x - (8 if side_ == "l" else -8), round(y - wd / 2, 1), 0],
                          "color": "#1d1f21"})
            hub = wd * 0.62
            hx = x - 14 if side_ == "l" else x + tw - 2
            parts.append({"sub": f"rim_{axle}_{side_}", "name": f"Rim, {axle}", "shape": "cylinder", "axis": "x",
                          "size": [16, round(hub, 1), round(hub, 1)],
                          "at": [round(hx, 1), round(y - hub / 2, 1), round((wd - hub) / 2, 1)], "color": "#9aa0a6"})
    del sill
    return parts
