"""Load a design file and resolve it into solids.

A design is JSON (see designs/*.json). Every length is in millimetres and every
angle in degrees. Sizes and positions may be numbers or expressions over `params`.

Axes: x = width (left -> right), y = depth (front -> back), z = up.

A part spec is resolved like this:
  local solid   box `size` from the origin (optional angled `ends`), or a gusset,
                or every panel of a catalog `component`
  rotate        about world-aligned axes through the local origin, in listed order
  at            then moved so the local origin sits at `at`
  repeat        copies offset by i * step   (ids  stud[0], stud[1], ...)
  mirror        plus mirrored copies        (ids  rafter~m, rafter[2]~m, ...)
Python is the single source of geometry: the viewer draws the solids sent to it.
"""
from __future__ import annotations

import ast
import json
import math
import operator
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog
from . import geometry as g
from .model_errors import DesignError

__all__ = ["DesignError", "Design", "Part", "evaluate", "resolve_params", "load", "resolve", "EPS"]

SHAPES = {"box", "gusset", "cylinder", "sphere", "prism"}
GUSSET_LEGS = {"front", "back", "left", "right"}
MATERIAL_KINDS = {"sheet", "lumber", "hardware", "reference"}
EPS = 0.01  # mm; overlaps thinner than this are treated as touching
MAX_COPIES = 500


# ---------------------------------------------------------------- expressions

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_FUNCS = {
    "min": min, "max": max, "round": round, "abs": abs,
    "sqrt": math.sqrt, "ceil": math.ceil, "floor": math.floor,
    "sin": lambda d: math.sin(math.radians(d)),
    "cos": lambda d: math.cos(math.radians(d)),
    "tan": lambda d: math.tan(math.radians(d)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
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
    except (ZeroDivisionError, ValueError, OverflowError) as e:
        raise DesignError(f"cannot evaluate {expr!r}: {e}") from None


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
    source: str          # the spec id this came from (joints may name it)
    instance: str        # copy id (e.g. "stud[2]"); equals id except for component panels
    name: str
    material: str
    kind: str            # sheet | lumber | hardware | reference | component
    shape: str
    size: tuple[float, float, float]   # local size, before rotation
    solid: g.Solid                     # world geometry
    group: str = ""
    role: str = ""
    notes: str = ""
    leg: str = ""
    ends: tuple[float, float] = (0.0, 0.0)
    mass_kg: float | None = None
    component: str | None = None
    aligned: bool = True               # no tilt (drag handles allowed)
    axis_map: list[int] | None = None  # world axis of each local axis (aligned parts)
    mirrored: bool = False
    cutouts: list[g.Solid] = field(default_factory=list)
    subtract: list[str] = field(default_factory=list)
    cut_notes: list[str] = field(default_factory=list)
    base_name: str = ""                # the spec's name, without copy numbers
    axis: str = ""                     # cylinder / prism axis (local)
    color: str | None = None           # own display colour (catalog panels, e.g. tyres)
    exact_volume: float | None = None  # true volume for curved shapes (facets run a little small)

    def __post_init__(self):
        self.base_name = self.base_name or self.name
        lo, hi = self.solid.bounds()
        self.at = tuple(round(v, 3) + 0.0 for v in lo)
        self.max = tuple(round(v, 3) + 0.0 for v in hi)
        self._vc = None

    @property
    def bsize(self):
        return tuple(h - l for l, h in zip(self.at, self.max))

    def _volc(self):
        if self._vc is None:
            self._vc = self.solid.volume_and_centroid()
        return self._vc

    @property
    def volume_mm3(self) -> float:
        return self.exact_volume if self.exact_volume is not None else self._volc()[0]

    def centroid(self):
        return self._volc()[1]

    def to_dict(self, geometry: bool = True) -> dict:
        d = {
            "id": self.id, "source": self.source, "name": self.name, "group": self.group,
            "material": self.material, "kind": self.kind, "shape": self.shape,
            "size": list(self.size), "at": list(self.at), "max": list(self.max),
            "role": self.role, "notes": self.notes, "aligned": self.aligned,
        }
        if self.axis_map:
            d["axis_map"] = self.axis_map
        if self.shape == "gusset":
            d["leg"] = self.leg
        if self.axis:
            d["axis"] = self.axis
        if self.shape == "cylinder":
            k = "xyz".index(self.axis or "z")
            cross_ = [self.size[i] for i in range(3) if i != k]
            d["dia"] = cross_[0] if abs(cross_[0] - cross_[1]) < 0.01 else cross_
            d["length"] = self.size[k]
        if self.color:
            d["color"] = self.color
        if any(self.ends):
            d["ends"] = list(self.ends)
        if self.component:
            d["component"] = self.component
        if self.mirrored:
            d["mirrored"] = True
        if self.cut_notes:
            d["cut_notes"] = self.cut_notes
        if geometry:
            d["mesh"] = self.solid.to_json()
            if self.cutouts:
                d["cutouts"] = [c.to_json() for c in self.cutouts]
            if self.subtract:
                d["subtract"] = self.subtract
        return d


@dataclass
class Design:
    path: Path
    raw: dict
    params: dict[str, float]
    parts: list[Part]
    issues: list[dict] = field(default_factory=list)
    components: dict[str, dict] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def title(self) -> str:
        return self.raw.get("title", self.name)

    @property
    def magpie_project(self) -> int | None:
        """Magpie project id for this design's page, when it is not the default Woodpecker one."""
        v = self.raw.get("magpie_project")
        return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None

    def part(self, part_id: str) -> Part:
        for p in self.parts:
            if p.id == part_id:
                return p
        raise DesignError(f"no part {part_id!r}")

    def expand(self, ref: str) -> list[Part]:
        """A joint/selection reference: an exact part id, a spec id (all its copies),
        or a component instance (all its panels)."""
        return [p for p in self.parts if p.id == ref or p.source == ref or p.instance == ref
                or p.id.startswith(ref + "/")]

    def joints_for(self, part_id: str) -> list[dict]:
        p = self.part(part_id)
        keys = {p.id, p.source, p.instance}
        return [j for j in self.raw.get("joints", []) if keys & set(j.get("parts", []))]

    def bounds(self, include_reference: bool = True) -> dict:
        ps = [p for p in self.parts if include_reference or p.kind != "reference"]
        if not ps:
            return {"min": [0, 0, 0], "max": [0, 0, 0], "size": [0, 0, 0]}
        lo = [min(p.at[i] for p in ps) for i in range(3)]
        hi = [max(p.max[i] for p in ps) for i in range(3)]
        return {"min": lo, "max": hi, "size": [round(h - l, 3) for l, h in zip(lo, hi)]}

    def to_dict(self, geometry: bool = True) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.raw.get("description", ""),
            "units": "mm",
            "params": [
                {"name": k, "value": v, "expr": _param_expr(self.raw["params"][k]),
                 "label": _param_meta(self.raw["params"][k], "label"),
                 "notes": _param_meta(self.raw["params"][k], "notes"),
                 "unit": _param_meta(self.raw["params"][k], "unit") or "mm"}
                for k, v in self.params.items()
            ],
            "materials": self.raw.get("materials", {}),
            "components": self.components,
            "parts": [p.to_dict(geometry) for p in self.parts],
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


# ---------------------------------------------------------------- resolving

def _vec(v, params, what):
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise DesignError(f"{what} needs 3 values")
    return tuple(evaluate(e, params) for e in v)


def _rotations(spec, params) -> g.Mat:
    rots = spec.get("rotate") or []
    if isinstance(rots, dict):
        rots = [rots]
    m = g.identity()
    for r in rots:
        if not isinstance(r, dict) or r.get("axis") not in ("x", "y", "z"):
            raise DesignError('rotate needs {"axis": "x|y|z", "deg": ...}')
        m = g.mul(g.rotate(r["axis"], evaluate(r.get("deg", 0), params)), m)
    return m


def _copies(spec, params) -> list[tuple[str, str, g.Mat, bool]]:
    """(suffix, name suffix, world transform applied after placement, mirrored)."""
    out = [("", "", g.identity(), False)]
    rep = spec.get("repeat")
    if rep:
        count = int(round(evaluate(rep.get("count", 1), params)))
        if count < 1 or count > MAX_COPIES:
            raise DesignError(f"repeat count must be 1..{MAX_COPIES}, got {count}")
        if "step" in rep:
            step = _vec(rep["step"], params, "repeat.step")
        else:
            axis = rep.get("axis", "x")
            if axis not in ("x", "y", "z"):
                raise DesignError("repeat.axis must be x, y or z")
            s = evaluate(rep.get("spacing", 0), params)
            step = tuple(s if a == axis else 0.0 for a in "xyz")
        out = [(f"[{i}]", f" {i + 1}", g.translate(*(i * s for s in step)), False) for i in range(count)]
    mir = spec.get("mirror")
    if mir:
        axis = mir.get("axis")
        if axis not in ("x", "y", "z"):
            raise DesignError("mirror.axis must be x, y or z")
        about = evaluate(mir.get("about", 0), params)
        mm = g.mirror(axis, about)
        out += [(s + "~m", n + " (mirrored)", g.mul(mm, t), True) for s, n, t, _ in out]
    return out


def resolve(raw: dict, path: Path | None = None) -> Design:
    path = path or Path("untitled.json")
    params = resolve_params(raw.get("params", {}))
    materials = raw.get("materials", {})
    parts: list[Part] = []
    issues: list[dict] = []
    seen: set[str] = set()
    components: dict[str, dict] = {}

    for i, sp in enumerate(raw.get("parts", [])):
        sid = sp.get("id") or f"part_{i}"
        where = f"part {sid!r}"
        if sid in seen:
            issues.append(_issue("error", sid, f"duplicate part id {sid!r}"))
            continue
        seen.add(sid)
        try:
            parts.extend(_resolve_spec(sid, sp, params, materials, components))
        except (DesignError, KeyError, TypeError, ValueError) as e:
            msg = str(e) if isinstance(e, DesignError) else f"{type(e).__name__}: {e}"
            issues.append(_issue("error", sid, f"{where}: {msg}"))

    ids = [p.id for p in parts]
    if len(ids) != len(set(ids)):
        dup = sorted({x for x in ids if ids.count(x) > 1})
        issues.append(_issue("error", dup[0], f"copies produce duplicate ids: {', '.join(dup[:5])}"))

    design = Design(path=path, raw=raw, params=params, parts=parts, issues=issues, components=components)
    _apply_joint_cuts(design)
    design.issues.extend(check(design))
    return design


def _shape_solid(sp: dict, params: dict, size=None):
    """Local solid for a spec (or a catalog panel). Returns (solid, size, extras)."""
    shape = sp.get("shape", "box")
    if shape not in SHAPES:
        raise DesignError(f"unknown shape {shape!r}; use one of {', '.join(sorted(SHAPES))}")
    extra = {"shape": shape, "leg": "", "ends": (0.0, 0.0), "axis": "", "exact_volume": None}
    if shape == "prism":
        axis = sp.get("axis", "x")
        if axis not in g.AXES:
            raise DesignError("prism axis must be x, y or z")
        prof = sp.get("profile") or []
        if len(prof) < 3:
            raise DesignError("prism needs a profile of at least 3 [u, v] points")
        pts = [(evaluate(u, params), evaluate(v, params)) for u, v in prof]
        length = evaluate(sp.get("length", size[g.AXES[axis]] if size else 0), params)
        if length <= 0:
            raise DesignError("prism needs a positive length")
        try:
            solid = g.prism_solid(pts, length, axis)
        except ValueError as e:
            raise DesignError(str(e)) from None
        lo, hi = solid.bounds()
        area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2
        extra.update(axis=axis, exact_volume=area * length)
        return solid, tuple(h - l for l, h in zip(lo, hi)), extra
    if size is None:
        size = _vec(sp["size"], params, "size")
    if min(size) <= 0:
        raise DesignError(f"size must be positive, got {tuple(round(s, 2) for s in size)}")
    if shape == "gusset":
        leg = sp.get("leg", "")
        if leg not in GUSSET_LEGS:
            raise DesignError("gusset needs leg front/back/left/right")
        extra["leg"] = leg
        return g.gusset_solid(size, leg), size, extra
    if shape == "cylinder":
        axis = sp.get("axis", "z")
        if axis not in g.AXES:
            raise DesignError("cylinder axis must be x, y or z")
        k = g.AXES[axis]
        a, b = [size[i] for i in range(3) if i != k]
        extra.update(axis=axis, exact_volume=math.pi * a * b / 4 * size[k])
        return g.cylinder_solid(size, axis), size, extra
    if shape == "sphere":
        extra["exact_volume"] = math.pi / 6 * size[0] * size[1] * size[2]
        return g.sphere_solid(size), size, extra
    e = sp.get("ends") or {}
    ends = (evaluate(e.get("start", 0), params), evaluate(e.get("end", 0), params))
    if any(abs(a) >= 80 for a in ends):
        raise DesignError("end cut angles must be between -80 and 80 degrees")
    if size[2] * (math.tan(math.radians(ends[0])) + math.tan(math.radians(ends[1]))) >= size[0]:
        raise DesignError("end cuts meet: the board is too short for those angles")
    extra["ends"] = ends
    return g.box_solid(size, *ends), size, extra


def _resolve_spec(sid, sp, params, materials, components) -> list[Part]:
    rot = _rotations(sp, params)
    at = _vec(sp.get("at", [0, 0, 0]), params, "at")
    place = g.mul(g.translate(*at), rot)
    aligned = g.is_axis_aligned(rot)
    axis_map = [max(range(3), key=lambda r: abs(rot[r][c])) for c in range(3)] if aligned else None
    name = sp.get("name", sid)
    common = dict(group=sp.get("group", ""), role=sp.get("role", ""), notes=sp.get("notes", ""))

    if "component" in sp:
        item = catalog.get(sp["component"])
        panels = catalog.generate(item, sp.get("options", {}))
        components[item["id"]] = {
            **catalog.summary(item),
            "assumed": item.get("assumed", []),
            "construction": item.get("construction", ""),
            "material": item.get("material", ""),
            "color": item.get("color", "#e9e7e2"),
        }
        is_ref = bool(item.get("reference"))
        total_mass = None if is_ref else catalog.mass_kg(item)[0]
        locals_ = []
        for pn in panels:
            solid, psize, extra = _shape_solid(pn, {}, tuple(pn["size"]) if "size" in pn else None)
            locals_.append((pn, solid.transformed(g.translate(*pn.get("at", (0, 0, 0)))), psize, extra))
        vol = sum(s.volume_and_centroid()[0] for _, s, _, _ in locals_) or 1.0
        out = []
        for suffix, nsuffix, copy, mirrored in _copies(sp, params):
            tf = g.mul(copy, place)
            inst = sid + suffix
            for pn, ls, psize, extra in locals_:
                share = None if total_mass is None else total_mass * ls.volume_and_centroid()[0] / vol
                out.append(Part(
                    id=f"{inst}/{pn['sub']}", source=sid, instance=inst,
                    name=f"{name}{nsuffix}: {pn['name']}", material="@" + item["id"],
                    kind="reference" if is_ref else "component",
                    shape=extra["shape"], size=tuple(psize), solid=ls.transformed(tf), mass_kg=share,
                    component=item["id"], aligned=aligned, axis_map=axis_map, mirrored=mirrored,
                    axis=extra["axis"], color=pn.get("color"), **common,
                ))
        return out

    mat = sp.get("material", "")
    if mat not in materials:
        raise DesignError(f"unknown material {mat!r}")
    kind = materials[mat].get("kind", "sheet")
    local, size, extra = _shape_solid(sp, params)
    shape, leg, ends = extra["shape"], extra["leg"], extra["ends"]
    mass = evaluate(sp["mass_kg"], params) if "mass_kg" in sp else None
    cut_locals = []
    for c in sp.get("cutouts", []) or []:
        cs = _vec(c["size"], params, "cutout size")
        ca = _vec(c.get("at", [0, 0, 0]), params, "cutout at")
        cut_locals.append((c.get("label", "cutout"), cs, g.box_solid(cs).transformed(g.translate(*ca))))

    out = []
    for suffix, nsuffix, copy, mirrored in _copies(sp, params):
        tf = g.mul(copy, place)
        p = Part(
            id=sid + suffix, source=sid, instance=sid + suffix, name=name + nsuffix, base_name=name,
            material=mat, kind=kind, shape=shape, size=tuple(round(s, 3) for s in size),
            solid=local.transformed(tf), leg=leg, ends=ends, mass_kg=mass,
            aligned=aligned, axis_map=axis_map, mirrored=mirrored, axis=extra["axis"],
            exact_volume=None if extra["exact_volume"] is None else extra["exact_volume"] * abs(_det3(tf)),
            **common,
        )
        for label, cs, csol in cut_locals:
            p.cutouts.append(csol.transformed(tf))
            p.cut_notes.append(f"{label}: {cs[0]:g} x {cs[1]:g} x {cs[2]:g}")
        out.append(p)
    return out


def _apply_joint_cuts(design: Design) -> None:
    """A joint with `cut_into: [hosts]` cuts the other joint parts out of the hosts
    (a through-mortise, a dado, a birdsmouth notch)."""
    for j in design.raw.get("joints", []):
        hosts_ref = j.get("cut_into") or []
        if not hosts_ref:
            continue
        hosts = [p for r in hosts_ref for p in design.expand(r)]
        host_ids = {p.id for p in hosts}
        guests = [p for r in j.get("parts", []) if r not in hosts_ref for p in design.expand(r)
                  if p.id not in host_ids]
        for h in hosts:
            cut = [gp for gp in guests if g.aabb_overlap(h.solid.bounds(), gp.solid.bounds(), EPS)
                   and g.penetration(h.solid, gp.solid) > EPS]
            if not cut:
                continue
            h.subtract.extend(gp.id for gp in cut)
            lo = [max(h.at[k], min(gp.at[k] for gp in cut)) for k in range(3)]
            hi = [min(h.max[k], max(gp.max[k] for gp in cut)) for k in range(3)]
            dims = " x ".join(f"{v:g}" for v in sorted((round(b - a, 1) for a, b in zip(lo, hi)), reverse=True))
            names = sorted({gp.name.split(",")[0].split(" (mirrored)")[0] for gp in cut})
            exact = h.aligned and all(gp.aligned for gp in cut)
            h.cut_notes.append(f"{j.get('type', 'cut')} for {', '.join(names)}"
                               + (f" ({dims})" if exact else " (angled: mark it from the drawing or the mating part)"))


def _issue(level, part, message):
    return {"level": level, "part": part, "message": message}


# ---------------------------------------------------------------- checks

def check(design: Design) -> list[dict]:
    issues = []
    materials = design.raw.get("materials", {})
    for p in design.parts:
        if p.kind == "component" or p.component:
            continue
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
    for p in design.parts:
        if p.at[2] < -0.5:
            issues.append(_issue("warning", p.id, f"{p.name}: goes below the floor (z={p.at[2]:g})"))

    all_ids = {p.id for p in design.parts}
    joined: set[frozenset] = set()
    for j in design.raw.get("joints", []):
        members = []
        for ref in j.get("parts", []):
            ex = design.expand(ref)
            if not ex and ref not in all_ids:
                issues.append(_issue("warning", ref, f"joint {j.get('id', '?')!r} names unknown part {ref!r}"))
            members.extend(p.id for p in ex)
        for a in members:
            for b in members:
                if a != b:
                    joined.add(frozenset((a, b)))

    solid = [p for p in design.parts if p.kind != "reference"]
    boxes = [(p, p.solid.bounds()) for p in solid]
    for i, (a, ab) in enumerate(boxes):
        for b, bb in boxes[i + 1:]:
            if not g.aabb_overlap(ab, bb, EPS):
                continue
            if frozenset((a.id, b.id)) in joined:
                continue
            if a.kind == "component" and a.instance == b.instance:
                continue
            simple = a.aligned and b.aligned and a.shape == b.shape == "box" and not any(a.ends + b.ends)
            if simple:
                ov = [min(a.max[k], b.max[k]) - max(a.at[k], b.at[k]) for k in range(3)]
                issues.append(_issue("warning", a.id,
                    f"{a.name} and {b.name} overlap by {ov[0]:g}x{ov[1]:g}x{ov[2]:g} mm "
                    f"with no joint between them"))
            else:
                d = g.penetration(a.solid, b.solid)
                if d > 0.5:
                    issues.append(_issue("warning", a.id,
                        f"{a.name} and {b.name} overlap by {d:.1f} mm with no joint between them"))
    return issues


def _det3(m) -> float:
    """Volume scale of a transform (1 for rotations and mirrors; kept for safety)."""
    a = [row[:3] for row in m[:3]]
    return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
            + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
