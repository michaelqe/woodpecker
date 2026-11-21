"""Load a design file and resolve it into plain numbers.

A design is JSON (see designs/tv-cart.json). Every length is in millimetres.
Sizes and positions may be numbers or expressions over `params`, so changing
one param moves every part that depends on it.

Axes: x = width (left -> right), y = depth (front -> back), z = up. `at` is the
part's minimum corner; `size` is its extent along x, y, z.
"""
from __future__ import annotations

import ast
import json
import math
import operator
from dataclasses import dataclass, field
from pathlib import Path

SHAPES = {"box", "gusset"}
GUSSET_LEGS = {"front", "back", "left", "right"}
MATERIAL_KINDS = {"sheet", "lumber", "hardware", "reference"}
EPS = 0.01  # mm; overlaps thinner than this are treated as touching


class DesignError(ValueError):
    pass


# ---------------------------------------------------------------- expressions

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_FUNCS = {
    "min": min, "max": max, "round": round, "abs": abs,
    "sqrt": math.sqrt, "ceil": math.ceil, "floor": math.floor,
    "sin": lambda d: math.sin(math.radians(d)),
    "cos": lambda d: math.cos(math.radians(d)),
    "tan": lambda d: math.tan(math.radians(d)),
}


def evaluate(expr, names: dict[str, float]) -> float:
    """Evaluate a number or arithmetic string against `names`. No other Python."""
    if isinstance(expr, bool):
        raise DesignError(f"expected a number, got {expr!r}")
    if isinstance(expr, (int, float)):
        return float(expr)
    if not isinstance(expr, str):
        raise DesignError(f"expected a number or expression, got {expr!r}")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise DesignError(f"bad expression {expr!r}: {e.msg}") from None

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in names:
                raise DesignError(f"unknown name {node.id!r} in {expr!r}")
            return names[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in _FUNCS and not node.keywords:
            return float(_FUNCS[node.func.id](*[ev(a) for a in node.args]))
        raise DesignError(f"unsupported syntax in {expr!r}")

    try:
        return ev(tree)
    except ZeroDivisionError:
        raise DesignError(f"division by zero in {expr!r}") from None


def _param_names(expr) -> set[str]:
    if not isinstance(expr, str):
        return set()
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in _FUNCS}


def resolve_params(raw: dict) -> dict[str, float]:
    """Params may reference each other in any order; cycles are an error."""
    out: dict[str, float] = {}
    visiting: set[str] = set()

    def get(name: str) -> float:
        if name in out:
            return out[name]
        if name not in raw:
            raise DesignError(f"unknown param {name!r}")
        if name in visiting:
            raise DesignError(f"param cycle through {name!r}")
        visiting.add(name)
        spec = raw[name]
        value = spec["value"] if isinstance(spec, dict) else spec
        for dep in _param_names(value):
            if dep in raw:
                get(dep)
        out[name] = evaluate(value, out)
        visiting.discard(name)
        return out[name]

    for name in raw:
        get(name)
    return out


# ---------------------------------------------------------------- resolved model

@dataclass
class Part:
    id: str
    name: str
    material: str
    kind: str          # material kind
    shape: str
    size: tuple[float, float, float]
    at: tuple[float, float, float]
    group: str = ""
    role: str = ""
    notes: str = ""
    leg: str = ""
    mass_kg: float | None = None

    @property
    def max(self) -> tuple[float, float, float]:
        return tuple(a + s for a, s in zip(self.at, self.size))

    @property
    def volume_mm3(self) -> float:
        v = self.size[0] * self.size[1] * self.size[2]
        return v / 2 if self.shape == "gusset" else v

    def centroid(self) -> tuple[float, float, float]:
        cx, cy, cz = (a + s / 2 for a, s in zip(self.at, self.size))
        if self.shape != "gusset":
            return (cx, cy, cz)
        # right-triangle profile: centroid sits 1/3 in from the right-angle corner
        x0, y0, z0 = self.at
        sx, sy, sz = self.size
        cz = z0 + sz / 3
        if self.leg == "back":
            cy = y0 + sy * 2 / 3
        elif self.leg == "front":
            cy = y0 + sy / 3
        elif self.leg == "right":
            cx = x0 + sx * 2 / 3
        elif self.leg == "left":
            cx = x0 + sx / 3
        return (cx, cy, cz)

    def to_dict(self) -> dict:
        d = {
            "id": self.id, "name": self.name, "group": self.group,
            "material": self.material, "kind": self.kind, "shape": self.shape,
            "size": list(self.size), "at": list(self.at),
            "role": self.role, "notes": self.notes,
        }
        if self.shape == "gusset":
            d["leg"] = self.leg
        return d


@dataclass
class Design:
    path: Path
    raw: dict
    params: dict[str, float]
    parts: list[Part]
    issues: list[dict] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def title(self) -> str:
        return self.raw.get("title", self.name)

    def part(self, part_id: str) -> Part:
        for p in self.parts:
            if p.id == part_id:
                return p
        raise DesignError(f"no part {part_id!r}")

    def joints_for(self, part_id: str) -> list[dict]:
        return [j for j in self.raw.get("joints", []) if part_id in j.get("parts", [])]

    def bounds(self, include_reference: bool = True) -> dict:
        ps = [p for p in self.parts if include_reference or p.kind != "reference"]
        if not ps:
            return {"min": [0, 0, 0], "max": [0, 0, 0], "size": [0, 0, 0]}
        lo = [min(p.at[i] for p in ps) for i in range(3)]
        hi = [max(p.max[i] for p in ps) for i in range(3)]
        return {"min": lo, "max": hi, "size": [h - l for l, h in zip(lo, hi)]}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.raw.get("description", ""),
            "units": "mm",
            "params": [
                {"name": k, "value": v, "expr": _param_expr(self.raw["params"][k]),
                 "label": _param_meta(self.raw["params"][k], "label"),
                 "notes": _param_meta(self.raw["params"][k], "notes")}
                for k, v in self.params.items()
            ],
            "materials": self.raw.get("materials", {}),
            "parts": [p.to_dict() for p in self.parts],
            "joints": self.raw.get("joints", []),
            "hardware": self.raw.get("hardware", []),
            "bounds": self.bounds(include_reference=False),
            "issues": self.issues,
        }


def _param_expr(spec):
    return spec["value"] if isinstance(spec, dict) else spec


def _param_meta(spec, key):
    return spec.get(key, "") if isinstance(spec, dict) else ""


def load(path: str | Path) -> Design:
    path = Path(path)
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise DesignError(f"{path.name} is not valid JSON: {e}") from None
    return resolve(raw, path)


def resolve(raw: dict, path: Path | None = None) -> Design:
    path = path or Path("untitled.json")
    params = resolve_params(raw.get("params", {}))
    materials = raw.get("materials", {})
    parts: list[Part] = []
    issues: list[dict] = []
    seen: set[str] = set()

    for i, sp in enumerate(raw.get("parts", [])):
        pid = sp.get("id") or f"part_{i}"
        where = f"part {pid!r}"
        if pid in seen:
            issues.append(_issue("error", pid, f"duplicate part id {pid!r}"))
            continue
        seen.add(pid)
        mat = sp.get("material", "")
        if mat not in materials:
            issues.append(_issue("error", pid, f"{where}: unknown material {mat!r}"))
            continue
        kind = materials[mat].get("kind", "sheet")
        shape = sp.get("shape", "box")
        if shape not in SHAPES:
            issues.append(_issue("error", pid, f"{where}: unknown shape {shape!r}"))
            continue
        try:
            size = tuple(evaluate(e, params) for e in sp["size"])
            at = tuple(evaluate(e, params) for e in sp.get("at", [0, 0, 0]))
            mass = evaluate(sp["mass_kg"], params) if "mass_kg" in sp else None
        except (DesignError, KeyError, TypeError) as e:
            issues.append(_issue("error", pid, f"{where}: {e}"))
            continue
        if len(size) != 3 or len(at) != 3:
            issues.append(_issue("error", pid, f"{where}: size and at need 3 values"))
            continue
        if min(size) <= 0:
            issues.append(_issue("error", pid, f"{where}: size must be positive, got {size}"))
            continue
        leg = sp.get("leg", "")
        if shape == "gusset" and leg not in GUSSET_LEGS:
            issues.append(_issue("error", pid, f"{where}: gusset needs leg front/back/left/right"))
            continue
        parts.append(Part(
            id=pid, name=sp.get("name", pid), material=mat, kind=kind, shape=shape,
            size=_r(size), at=_r(at), group=sp.get("group", ""), role=sp.get("role", ""),
            notes=sp.get("notes", ""), leg=leg, mass_kg=mass,
        ))

    design = Design(path=path, raw=raw, params=params, parts=parts, issues=issues)
    design.issues.extend(check(design))
    return design


def _r(v):
    return tuple(round(x, 3) + 0.0 for x in v)


def _issue(level, part, message):
    return {"level": level, "part": part, "message": message}


# ---------------------------------------------------------------- checks

def check(design: Design) -> list[dict]:
    issues = []
    materials = design.raw.get("materials", {})
    for p in design.parts:
        m = materials[p.material]
        dims = sorted(p.size)
        if p.kind == "sheet" and "thickness" in m and abs(dims[0] - m["thickness"]) > EPS:
            issues.append(_issue("warning", p.id,
                f"{p.name}: thinnest side is {dims[0]:g} mm but {p.material} is {m['thickness']:g} mm"))
        if p.kind == "lumber" and "section" in m:
            sec = sorted(m["section"])
            if abs(dims[0] - sec[0]) > EPS or abs(dims[1] - sec[1]) > EPS:
                issues.append(_issue("warning", p.id,
                    f"{p.name}: section {dims[0]:g}x{dims[1]:g} does not match "
                    f"{p.material} {sec[0]:g}x{sec[1]:g}"))
        if p.at[2] < -EPS:
            issues.append(_issue("warning", p.id, f"{p.name}: goes below the floor (z={p.at[2]:g})"))

    joined = set()
    for j in design.raw.get("joints", []):
        ps = j.get("parts", [])
        for a in ps:
            for b in ps:
                joined.add((a, b))
        for pid in ps:
            if pid not in {p.id for p in design.parts}:
                issues.append(_issue("warning", pid, f"joint {j.get('id', '?')!r} names unknown part {pid!r}"))

    solid = [p for p in design.parts if p.kind != "reference"]
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            if (a.id, b.id) in joined:
                continue
            ov = [min(a.max[k], b.max[k]) - max(a.at[k], b.at[k]) for k in range(3)]
            if all(o > EPS for o in ov):
                issues.append(_issue("warning", a.id,
                    f"{a.name} and {b.name} overlap by {ov[0]:g}x{ov[1]:g}x{ov[2]:g} mm "
                    f"with no joint between them"))
    return issues
