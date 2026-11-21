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


def mtime(name: str) -> float:
    return design_path(name).stat().st_mtime


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


def create(name: str, title: str, description: str = "", copy_from: str | None = None) -> Design:
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
            "params": {}, "materials": {}, "parts": [], "joints": [], "hardware": [],
        }
    return write(name, raw)


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
