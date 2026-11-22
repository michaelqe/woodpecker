"""Read and write design files. The UI and the MCP server both edit through here.

Every write:
  1. applies the change to a copy of the raw JSON,
  2. resolves it (refusing if that produces errors),
  3. snapshots the previous file under .woodpecker/history/<design>/ for undo,
  4. writes atomically. The viewer polls the file's mtime and reloads.
"""
from __future__ import annotations

import copy
import json
import os
import re
import time
from pathlib import Path

from .model import Design, DesignError, resolve

ROOT = Path(os.environ.get("WOODPECKER_HOME", Path(__file__).resolve().parent.parent))
DESIGNS = ROOT / "designs"
STATE = ROOT / ".woodpecker"
HISTORY_KEEP = 200

_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def design_path(name: str) -> Path:
    if not _NAME.match(name):
        raise DesignError(f"bad design name {name!r} (use lowercase letters, digits, - and _)")
    return DESIGNS / f"{name}.json"


def list_designs() -> list[dict]:
    out = []
    for p in sorted(DESIGNS.glob("*.json")):
        try:
            raw = json.loads(p.read_text())
            title = raw.get("title", p.stem)
        except json.JSONDecodeError:
            title = f"{p.stem} (invalid JSON)"
        out.append({"name": p.stem, "title": title, "mtime": p.stat().st_mtime})
    return out


def read_raw(name: str) -> dict:
    p = design_path(name)
    if not p.exists():
        raise DesignError(f"no design {name!r}")
    return json.loads(p.read_text())


def load(name: str) -> Design:
    return resolve(read_raw(name), design_path(name))


def mtime(name: str, _seen: set | None = None) -> float:
    """Newest change to this design or any design placed in it (the viewer reloads on it)."""
    seen = _seen if _seen is not None else set()
    seen.add(name)
    path = design_path(name)
    t = path.stat().st_mtime
    try:
        placed = {sp["design"] for sp in json.loads(path.read_text()).get("parts", [])
                  if isinstance(sp, dict) and isinstance(sp.get("design"), str)}
    except (json.JSONDecodeError, AttributeError):
        return t
    for other in placed - seen:
        try:
            t = max(t, mtime(other, seen))
        except (DesignError, OSError):
            pass
    return t


def write(name: str, raw: dict, *, allow_errors: bool = False, snapshot: bool = True) -> Design:
    path = design_path(name)
    design = resolve(raw, path)
    errors = [i for i in design.issues if i["level"] == "error"]
    if errors and not allow_errors:
        raise DesignError("change refused: " + "; ".join(e["message"] for e in errors))
    if snapshot and path.exists():
        _snapshot(name, path.read_text())
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return design


def _history_dir(name: str) -> Path:
    d = STATE / "history" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot(name: str, text: str) -> None:
    d = _history_dir(name)
    (d / f"{time.time_ns()}.json").write_text(text)
    old = sorted(d.glob("*.json"))
    for f in old[:-HISTORY_KEEP]:
        f.unlink()


def undo(name: str) -> Design:
    snaps = sorted(_history_dir(name).glob("*.json"))
    if not snaps:
        raise DesignError("nothing to undo")
    last = snaps[-1]
    raw = json.loads(last.read_text())
    design = write(name, raw, allow_errors=True, snapshot=False)
    last.unlink()
    return design


# ---------------------------------------------------------------- edits

def _edit(name: str, fn) -> Design:
    raw = copy.deepcopy(read_raw(name))
    fn(raw)
    return write(name, raw)


def set_param(name: str, param: str, value, label: str | None = None, notes: str | None = None) -> Design:
    def fn(raw):
        params = raw.setdefault("params", {})
        cur = params.get(param)
        if isinstance(cur, dict) or label is not None or notes is not None:
            spec = dict(cur) if isinstance(cur, dict) else {}
            spec["value"] = value
            if label is not None:
                spec["label"] = label
            if notes is not None:
                spec["notes"] = notes
            params[param] = spec
        else:
            params[param] = value
    return _edit(name, fn)


def remove_param(name: str, param: str) -> Design:
    def fn(raw):
        if param not in raw.get("params", {}):
            raise DesignError(f"no param {param!r}")
        del raw["params"][param]
    return _edit(name, fn)


def _find(raw, part_id):
    for i, p in enumerate(raw.get("parts", [])):
        if p.get("id") == part_id:
            return i, p
    raise DesignError(f"no part {part_id!r}")


def update_part(name: str, part_id: str, fields: dict) -> Design:
    """Merge `fields` into a part. A field set to None is removed."""
    def fn(raw):
        _, p = _find(raw, part_id)
        for k, v in fields.items():
            if k == "id" and v != part_id:
                _rename(raw, part_id, v)
            if v is None:
                p.pop(k, None)
            else:
                p[k] = v
    return _edit(name, fn)


def _rename(raw, old, new):
    if any(p.get("id") == new for p in raw.get("parts", [])):
        raise DesignError(f"part id {new!r} already exists")
    for j in raw.get("joints", []):
        j["parts"] = [new if x == old else x for x in j.get("parts", [])]


def add_part(name: str, part: dict, after: str | None = None) -> Design:
    def fn(raw):
        parts = raw.setdefault("parts", [])
        if not part.get("id"):
            raise DesignError("part needs an id")
        if any(p.get("id") == part["id"] for p in parts):
            raise DesignError(f"part id {part['id']!r} already exists")
        if after:
            i, _ = _find(raw, after)
            parts.insert(i + 1, part)
        else:
            parts.append(part)
    return _edit(name, fn)


def offset_expr(expr, delta: float):
    """expr + delta, keeping expressions readable: "post_x" -> "post_x + 40"."""
    if abs(delta) < 1e-9:
        return expr
    if isinstance(expr, (int, float)) and not isinstance(expr, bool):
        return round(expr + delta, 2)
    m = re.match(r"^(.*\S)\s*([+-])\s*(\d+(?:\.\d+)?)$", str(expr))
    if m and "(" not in m.group(1)[-1:]:
        base, sign, num = m.group(1), m.group(2), float(m.group(3))
        val = round((num if sign == "+" else -num) + delta, 2)
        if abs(val) < 1e-9:
            return base
        return f"{base} {'+' if val > 0 else '-'} {abs(val):g}"
    return f"{expr} {'+' if delta > 0 else '-'} {abs(round(delta, 2)):g}"


def move_part(name: str, part_id: str, delta: list[float]) -> Design:
    """Move a part spec by delta (mm, world axes). Copies and panels move with it."""
    def fn(raw):
        _, p = _find(raw, part_id)
        at = p.get("at", [0, 0, 0])
        p["at"] = [offset_expr(a, d) for a, d in zip(at, delta)]
    return _edit(name, fn)


def resize_part(name: str, part_id: str, delta: list[float]) -> Design:
    """Grow or shrink a part's local size by delta (mm per local axis)."""
    def fn(raw):
        _, p = _find(raw, part_id)
        if "size" not in p:
            raise DesignError("this part has no size to change (catalog components have fixed sizes)")
        p["size"] = [offset_expr(a, d) for a, d in zip(p["size"], delta)]
    return _edit(name, fn)


def remove_part(name: str, part_id: str) -> Design:
    def fn(raw):
        i, _ = _find(raw, part_id)
        raw["parts"].pop(i)
        for j in raw.get("joints", []):
            j["parts"] = [x for x in j.get("parts", []) if x != part_id]
        raw["joints"] = [j for j in raw.get("joints", []) if len(j.get("parts", [])) >= 2]
    return _edit(name, fn)


def set_joint(name: str, joint: dict) -> Design:
    """Add a joint, or replace the one with the same id."""
    def fn(raw):
        if not joint.get("id"):
            raise DesignError("joint needs an id")
        joints = raw.setdefault("joints", [])
        for i, j in enumerate(joints):
            if j.get("id") == joint["id"]:
                joints[i] = joint
                return
        joints.append(joint)
    return _edit(name, fn)


def remove_joint(name: str, joint_id: str) -> Design:
    def fn(raw):
        before = len(raw.get("joints", []))
        raw["joints"] = [j for j in raw.get("joints", []) if j.get("id") != joint_id]
        if len(raw["joints"]) == before:
            raise DesignError(f"no joint {joint_id!r}")
    return _edit(name, fn)


def set_material(name: str, material_id: str, spec: dict) -> Design:
    def fn(raw):
        raw.setdefault("materials", {})[material_id] = spec
    return _edit(name, fn)


def set_hardware(name: str, items: list[dict]) -> Design:
    def fn(raw):
        raw["hardware"] = items
    return _edit(name, fn)


def set_meta(name: str, title: str | None = None, description: str | None = None) -> Design:
    def fn(raw):
        if title is not None:
            raw["title"] = title
        if description is not None:
            raw["description"] = description
    return _edit(name, fn)


# A blank design starts with common stock so the Board tool has something to draw with.
STARTER_MATERIALS = {
    "ply18": {"name": "Birch plywood 18 mm", "kind": "sheet", "thickness": 18, "stock": [2500, 1250], "density": 680},
    "ply12": {"name": "Birch plywood 12 mm", "kind": "sheet", "thickness": 12, "stock": [2500, 1250], "density": 680},
    "pine18x95": {"name": "Pine board 18x95, planed", "kind": "lumber", "section": [18, 95], "stock_length": 3000, "density": 500},
    "spruce45x45": {"name": "Spruce 45x45, planed", "kind": "lumber", "section": [45, 45], "stock_length": 3000, "density": 450},
    "spruce45x95": {"name": "Spruce 45x95, planed", "kind": "lumber", "section": [45, 95], "stock_length": 3000, "density": 450},
}


def create(name: str, title: str, description: str = "", copy_from: str | None = None,
           created_by: str | None = None) -> Design:
    path = design_path(name)
    if path.exists():
        raise DesignError(f"design {name!r} already exists")
    if copy_from:
        raw = copy.deepcopy(read_raw(copy_from))
        raw["title"] = title
        raw["description"] = description or raw.get("description", "")
    else:
        raw = {
            "title": title, "description": description, "units": "mm",
            "params": {}, "materials": copy.deepcopy(STARTER_MATERIALS), "parts": [], "joints": [], "hardware": [],
        }
    if created_by:
        raw["created_by"] = created_by
    raw.pop("magpie_page_id", None)
    return write(name, raw)


def placed_in(name: str) -> list[dict]:
    """Designs that place this one as a part ({"design": name}); they break if it is deleted."""
    out = []
    for p in sorted(DESIGNS.glob("*.json")):
        if p.stem == name:
            continue
        try:
            raw = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        if any(isinstance(sp, dict) and sp.get("design") == name for sp in raw.get("parts", [])):
            out.append({"name": p.stem, "title": raw.get("title", p.stem)})
    return out


def delete_design(name: str) -> dict:
    """Remove a design file. A snapshot stays in .woodpecker/history/<name>/ to recover it."""
    path = design_path(name)
    if not path.exists():
        raise DesignError(f"no design {name!r}")
    used = placed_in(name)
    _snapshot(name, path.read_text())
    path.unlink()
    return {"deleted": name, "was_placed_in": used}


# ---------------------------------------------------------------- selection

def _selection_file() -> Path:
    STATE.mkdir(parents=True, exist_ok=True)
    return STATE / "selection.json"


def set_selection(design: str, part_ids: list[str]) -> dict:
    sel = {"design": design, "parts": part_ids, "at": time.time()}
    _selection_file().write_text(json.dumps(sel))
    return sel


def get_selection() -> dict:
    f = _selection_file()
    if not f.exists():
        return {"design": None, "parts": []}
    return json.loads(f.read_text())
