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
