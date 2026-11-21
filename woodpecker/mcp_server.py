"""MCP tools for agents: read, explain, and edit designs. The viewer reloads on every write."""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from . import cutlist, store
from .model import EPS, Design
from .server import format_cutlist

INSTRUCTIONS = """\
Woodpecker is a woodworking / garage-building design tool. A design is a JSON file of
parametric parts; the human watches it in a 3D viewer (http://127.0.0.1:8790) that
reloads on every change you make.

Model rules:
- Every length is millimetres. Axes: x = width (left->right), y = depth (front->back,
  front is y=0), z = up (floor is z=0).
- A part is a box (or `shape: "gusset"`, a right-triangle knee brace) with `size`
  [x, y, z] and `at` = its minimum corner. Values may be expressions over params,
  e.g. "base_w - 2 * ply". Put anything the human might resize in a param, so
  "make it wider" is one wp_set_param call.
- Every part needs a plain-English `role`: what it does structurally. That is what you
  read back when the human asks "explain this". Add `notes` for build tips.
- Materials have a kind: sheet (plywood; thinnest side must equal thickness), lumber
  (two smallest sides must equal section), hardware (bought, counted in the hardware
  list), reference (shown but not built, e.g. the TV; give mass_kg for the tip check).
- Parts may only overlap if a joint lists both of them (a through-mortise, say).
  Joints also carry the fasteners, which is how a bracket or connection gets explained.
- Gusset `leg` names the side the vertical leg sits on (front/back/left/right); the
  horizontal leg is always at the bottom.

Working loop:
1. "this" / "the selected part" means wp_get_selection. Use wp_explain_part to explain it.
2. Edit with the smallest tool (wp_set_param before wp_update_part before rewriting).
3. After edits, run wp_check: fix new warnings (overlaps, wrong stock sizes, floating
   parts) and report tip-stability changes when the shape or weight moved.
4. wp_cut_list gives the parts list, the stock to buy and the hardware.
5. wp_undo reverts the last write if the human does not like a change.
Do not edit design files by hand while the viewer is open; use the tools (they validate
and keep undo history).
"""

mcp = MCPServer("woodpecker", instructions=INSTRUCTIONS)


def _summary(d: Design) -> dict:
    st = cutlist.stability(d)
    return {
        "design": d.name,
        "issues": d.issues,
        "overall_mm": d.bounds(include_reference=False)["size"],
        "parts": len(d.parts),
        "tip_weakest": {"direction": st.get("weakest"),
                        **(st.get("tip", {}).get(st.get("weakest"), {}))} if st.get("tip") else None,
    }


def _touching(d: Design, part_id: str) -> list[dict]:
    a = d.part(part_id)
    out = []
    for b in d.parts:
        if b.id == a.id:
            continue
        gaps = [max(a.at[k], b.at[k]) - min(a.max[k], b.max[k]) for k in range(3)]
        if all(g <= EPS for g in gaps):
            out.append({"id": b.id, "name": b.name, "material": b.material})
    return out


@mcp.tool()
def wp_list_designs() -> list[dict]:
    """List design files (name, title)."""
    return [{"name": x["name"], "title": x["title"]} for x in store.list_designs()]


@mcp.tool()
def wp_get_design(name: str) -> dict:
    """The whole design: params (value + expression), materials, resolved parts, joints,
    hardware, overall bounds and issues. Also returns `raw`, the file as written."""
    d = store.load(name)
    return {**d.to_dict(), "raw": d.raw}


@mcp.tool()
def wp_get_selection() -> dict:
    """What the human has selected in the viewer (click a part). Use for 'this' / 'that bracket'."""
    sel = store.get_selection()
    if not sel.get("design") or not sel.get("parts"):
        return {**sel, "note": "nothing selected; ask the human to click the part"}
    d = store.load(sel["design"])
    sel["details"] = [d.part(pid).to_dict() for pid in sel["parts"] if pid in {p.id for p in d.parts}]
    return sel


@mcp.tool()
def wp_explain_part(name: str, part_id: str) -> dict:
    """Everything needed to explain one part: its role and notes, material, size, the
    joints and fasteners it takes part in, and the parts it touches."""
    d = store.load(name)
    p = d.part(part_id)
    return {
        "part": p.to_dict(),
        "material": d.raw.get("materials", {}).get(p.material, {}),
        "raw": next(x for x in d.raw["parts"] if x.get("id") == part_id),
        "joints": d.joints_for(part_id),
        "touching": _touching(d, part_id),
        "mass_kg": round(cutlist.part_mass(p, d.raw.get("materials", {})), 2),
    }


@mcp.tool()
def wp_set_param(name: str, param: str, value: Any, label: str | None = None,
                 notes: str | None = None) -> dict:
    """Set (or add) a param. `value` is a number in mm or an expression over other params."""
    return _summary(store.set_param(name, param, value, label, notes))


@mcp.tool()
def wp_remove_param(name: str, param: str) -> dict:
    """Remove a param (refused if something still uses it)."""
    return _summary(store.remove_param(name, param))


@mcp.tool()
def wp_update_part(name: str, part_id: str, fields: dict) -> dict:
    """Merge fields into a part, e.g. {"size": ["base_w", 600, "ply"]} or {"role": "..."}.
    A field set to null is removed. Renaming `id` updates the joints that use it."""
    return _summary(store.update_part(name, part_id, fields))


@mcp.tool()
def wp_add_part(name: str, part: dict, after: str | None = None) -> dict:
    """Add a part: {id, name, group, material, shape?, leg?, size, at, role, notes?, mass_kg?}."""
    return _summary(store.add_part(name, part, after))


@mcp.tool()
def wp_remove_part(name: str, part_id: str) -> dict:
    """Remove a part (and drop it from joints)."""
    return _summary(store.remove_part(name, part_id))


@mcp.tool()
def wp_set_joint(name: str, joint: dict) -> dict:
    """Add or replace a joint by id: {id, type, parts: [...], fasteners, notes}."""
    return _summary(store.set_joint(name, joint))


@mcp.tool()
def wp_remove_joint(name: str, joint_id: str) -> dict:
    """Remove a joint by id."""
    return _summary(store.remove_joint(name, joint_id))


@mcp.tool()
def wp_set_material(name: str, material_id: str, spec: dict) -> dict:
    """Add or replace a material. Sheet: {name, kind:"sheet", thickness, stock:[l,w], density}.
    Lumber: {name, kind:"lumber", section:[a,b], stock_length, density}.
    Hardware/reference: {name, kind, mass_kg?, notes?}. Density is kg/m3."""
    return _summary(store.set_material(name, material_id, spec))


@mcp.tool()
def wp_set_hardware(name: str, items: list[dict]) -> dict:
    """Replace the loose hardware list (screws, bolts, glue): [{item, qty, notes?}]."""
    return _summary(store.set_hardware(name, items))


@mcp.tool()
def wp_set_meta(name: str, title: str | None = None, description: str | None = None) -> dict:
    """Change the design's title or description."""
    return _summary(store.set_meta(name, title, description))


@mcp.tool()
def wp_create_design(name: str, title: str, description: str = "", copy_from: str | None = None) -> dict:
    """Create a new design file (name: lowercase, digits, - and _). copy_from clones another."""
    return _summary(store.create(name, title, description, copy_from))


@mcp.tool()
def wp_undo(name: str) -> dict:
    """Revert the last change to a design (repeatable)."""
    return _summary(store.undo(name))


@mcp.tool()
def wp_check(name: str) -> dict:
    """Issues (overlaps, wrong stock sizes, parts below the floor) plus the tip check:
    centre of gravity, how far it can lean before it tips, and the push at the top that
    tips it, in each direction."""
    d = store.load(name)
    return {"issues": d.issues, "stability": cutlist.stability(d)}


@mcp.tool()
def wp_cut_list(name: str) -> dict:
    """Parts list: cut list grouped by identical pieces, stock to buy, and hardware.
    `text` is ready to show the human."""
    d = store.load(name)
    return {"text": format_cutlist(d), **cutlist.cut_list(d)}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
