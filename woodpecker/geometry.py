"""Small 3D helpers: 4x4 matrices, convex solids, volume, centroid, overlap (SAT).

Solids are convex polyhedra: a list of vertices and a list of faces (vertex index
lists, wound counter-clockwise seen from outside).
"""
from __future__ import annotations

import math

Vec = tuple[float, float, float]
Mat = list[list[float]]


# ---------------------------------------------------------------- matrices

def identity() -> Mat:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def mul(a: Mat, b: Mat) -> Mat:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def translate(x, y, z) -> Mat:
    m = identity()
    m[0][3], m[1][3], m[2][3] = x, y, z
    return m


def rotate(axis: str, deg: float) -> Mat:
    """Right-handed rotation about a world axis through the origin."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    m = identity()
    if axis == "x":
        m[1][1], m[1][2], m[2][1], m[2][2] = c, -s, s, c
    elif axis == "y":
        m[0][0], m[0][2], m[2][0], m[2][2] = c, s, -s, c
    elif axis == "z":
        m[0][0], m[0][1], m[1][0], m[1][1] = c, -s, s, c
    else:
        raise ValueError(f"axis must be x, y or z, got {axis!r}")
    return m


def mirror(axis: str, about: float) -> Mat:
    i = "xyz".index(axis)
    m = identity()
    m[i][i] = -1.0
    m[i][3] = 2.0 * about
    return m


def apply(m: Mat, p: Vec) -> Vec:
    x, y, z = p
    return (
        m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
        m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
        m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3],
    )


def is_axis_aligned(m: Mat) -> bool:
    """True when the rotation part only permutes/flips axes (no tilt)."""
    for i in range(3):
        nz = [abs(m[i][j]) for j in range(3) if abs(m[i][j]) > 1e-9]
        if len(nz) != 1 or abs(nz[0] - 1) > 1e-9:
            return False
    return True


# ---------------------------------------------------------------- vectors

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


# ---------------------------------------------------------------- solids

class Solid:
    """Convex polyhedron. `smooth` (optional, one entry per face) groups the facets of one
    curved surface (a cylinder's side, a sphere): drawings shade and outline them as one."""
    __slots__ = ("verts", "faces", "smooth")

    def __init__(self, verts: list[Vec], faces: list[list[int]], smooth: list[int] | None = None):
        self.verts = verts
        self.faces = faces
        self.smooth = smooth
        self._orient()

    def _orient(self):
        """Wind every face outward (works for any convex solid, mirrored or not)."""
        c = self.vertex_mean()
        out = []
        for f in self.faces:
            n = self._face_normal(f)
            fc = tuple(sum(self.verts[i][k] for i in f) / len(f) for k in range(3))
            out.append(list(reversed(f)) if dot(n, sub(fc, c)) < 0 else f)
        self.faces = out

    def _face_normal(self, f):
        # Newell's method: robust for any planar polygon
        n = [0.0, 0.0, 0.0]
        for i in range(len(f)):
            a, b = self.verts[f[i]], self.verts[f[(i + 1) % len(f)]]
            n[0] += (a[1] - b[1]) * (a[2] + b[2])
            n[1] += (a[2] - b[2]) * (a[0] + b[0])
            n[2] += (a[0] - b[0]) * (a[1] + b[1])
        return tuple(n)

    def vertex_mean(self) -> Vec:
        n = len(self.verts)
        return tuple(sum(v[k] for v in self.verts) / n for k in range(3))

    def transformed(self, m: Mat) -> "Solid":
        return Solid([apply(m, v) for v in self.verts], [list(f) for f in self.faces],
                     list(self.smooth) if self.smooth else None)

    def triangles(self):
        for f in self.faces:
            for i in range(1, len(f) - 1):
                yield (f[0], f[i], f[i + 1])

    def volume_and_centroid(self) -> tuple[float, Vec]:
        o = self.vertex_mean()
        vol = 0.0
        cx = cy = cz = 0.0
        for a, b, c in self.triangles():
            pa, pb, pc = (sub(self.verts[i], o) for i in (a, b, c))
            v = dot(pa, cross(pb, pc)) / 6.0
            vol += v
            cx += v * (pa[0] + pb[0] + pc[0]) / 4
            cy += v * (pa[1] + pb[1] + pc[1]) / 4
            cz += v * (pa[2] + pb[2] + pc[2]) / 4
        if abs(vol) < 1e-12:
            return 0.0, o
        return abs(vol), (o[0] + cx / vol, o[1] + cy / vol, o[2] + cz / vol)

    def bounds(self) -> tuple[Vec, Vec]:
        lo = tuple(min(v[k] for v in self.verts) for k in range(3))
        hi = tuple(max(v[k] for v in self.verts) for k in range(3))
        return lo, hi

    def normals(self):
        return [unit(self._face_normal(f)) for f in self.faces]

    def edge_dirs(self):
        seen = []
        for f in self.faces:
            for i in range(len(f)):
                d = unit(sub(self.verts[f[(i + 1) % len(f)]], self.verts[f[i]]))
                if not any(abs(abs(dot(d, s)) - 1) < 1e-6 for s in seen):
                    seen.append(d)
        return seen

    def to_json(self, nd=2):
        out = {"verts": [[round(c, nd) for c in v] for v in self.verts], "faces": self.faces}
        if self.smooth:
            out["smooth"] = self.smooth
        return out


def box_solid(size: Vec, start_deg: float = 0.0, end_deg: float = 0.0) -> Solid:
    """Box from the origin along +x, +y, +z. End cuts tilt the x-ends in the x-z plane:
    a positive angle makes the top edge shorter than the bottom at that end."""
    L, w, h = size
    x0t = h * math.tan(math.radians(start_deg))
    x1t = L - h * math.tan(math.radians(end_deg))
    v = [(0, 0, 0), (L, 0, 0), (L, w, 0), (0, w, 0),
         (x0t, 0, h), (x1t, 0, h), (x1t, w, h), (x0t, w, h)]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [3, 7, 6, 2], [0, 4, 7, 3], [1, 2, 6, 5]]
    return Solid([tuple(float(c) for c in p) for p in v], f)


# ---------------------------------------------------------------- curved shapes (faceted)

AXES = {"x": 0, "y": 1, "z": 2}


def segments_for(radius: float, max_err: float = 0.5, lo: int = 12, hi: int = 48) -> int:
    """Facets so the flat sides stray at most max_err mm from the true circle (multiple of 4,
    so the extremes sit exactly on the bounding box)."""
    if radius <= max_err:
        return lo
    n = math.ceil(math.pi / math.acos(1 - max_err / radius))
    return max(lo, min(hi, (n + 3) // 4 * 4))


def _place(axis: str, u: float, v: float, t: float) -> Vec:
    """Profile coordinates (u, v) across the axis and t along it -> x, y, z."""
    return {"x": (t, u, v), "y": (u, t, v), "z": (u, v, t)}[axis]


def is_convex(profile) -> bool:
    n = len(profile)
    if n < 3:
        return False
    sign = 0
    for i in range(n):
        (ax, ay), (bx, by), (cx, cy) = profile[i], profile[(i + 1) % n], profile[(i + 2) % n]
        z = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
        if abs(z) < 1e-9:
            continue
        if sign == 0:
            sign = 1 if z > 0 else -1
        elif (z > 0) != (sign > 0):
            return False
    return sign != 0


def prism_solid(profile, length: float, axis: str = "x", smooth_sides: bool = False) -> Solid:
    """Convex 2D profile extruded from 0 to `length` along `axis`. Profile points are
    (u, v) in the other two axes in order: axis x -> (y, z), y -> (x, z), z -> (x, y)."""
    pts = [(float(u), float(v)) for u, v in profile]
    if not is_convex(pts):
        raise ValueError("profile must be a convex polygon (split the shape into convex pieces)")
    n = len(pts)
    verts = [_place(axis, u, v, 0.0) for u, v in pts] + [_place(axis, u, v, float(length)) for u, v in pts]
    faces = [list(range(n)), list(range(n, 2 * n))]
    smooth = [0, 0] if smooth_sides else None
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
        if smooth is not None:
            smooth.append(1)
    return Solid(verts, faces, smooth)


def cylinder_solid(size: Vec, axis: str = "z") -> Solid:
    """Cylinder (elliptic if the two cross sizes differ) filling the box [0, size] along axis."""
    k = AXES[axis]
    cross_ = [size[i] for i in range(3) if i != k]
    ru, rv = cross_[0] / 2, cross_[1] / 2
    n = segments_for(max(ru, rv))
    prof = [(ru + ru * math.cos(2 * math.pi * i / n), rv + rv * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return prism_solid(prof, size[k], axis, smooth_sides=True)


def sphere_solid(size: Vec) -> Solid:
    """Sphere (ellipsoid if sizes differ) filling the box [0, size]. Fewer facets than a
    cylinder: spheres make the overlap check slow, and 24 around reads as round."""
    rx, ry, rz = size[0] / 2, size[1] / 2, size[2] / 2
    n_lon = min(24, segments_for(max(rx, ry), max_err=1.5))
    n_lat = max(6, n_lon // 2)
    verts = [(rx, ry, 0.0)]
    for i in range(1, n_lat):
        th = math.pi * i / n_lat
        for j in range(n_lon):
            ph = 2 * math.pi * j / n_lon
            verts.append((rx + rx * math.sin(th) * math.cos(ph), ry + ry * math.sin(th) * math.sin(ph),
                          rz - rz * math.cos(th)))
    verts.append((rx, ry, 2 * rz))
    top = len(verts) - 1
    faces = []

    def ring(i, j):
        return 1 + (i - 1) * n_lon + (j % n_lon)
    for j in range(n_lon):
        faces.append([0, ring(1, j + 1), ring(1, j)])
    for i in range(1, n_lat - 1):
        for j in range(n_lon):
            faces.append([ring(i, j), ring(i, j + 1), ring(i + 1, j + 1), ring(i + 1, j)])
    for j in range(n_lon):
        faces.append([top, ring(n_lat - 1, j), ring(n_lat - 1, j + 1)])
    return Solid(verts, faces, [1] * len(faces))


def gusset_solid(size: Vec, leg: str) -> Solid:
    """Right-triangle prism in its bounding box [0,size]. `leg` = side of the vertical leg."""
    sx, sy, sz = size
    along_y = leg in ("front", "back")
    su, st = (sy, sx) if along_y else (sx, sy)
    tri = [(0, 0), (su, 0), (su, sz)] if leg in ("back", "right") else [(0, 0), (su, 0), (0, sz)]

    def P(u, v, t):
        return (t, u, v) if along_y else (u, t, v)

    v = [P(u, w, 0) for u, w in tri] + [P(u, w, st) for u, w in tri]
    f = [[0, 1, 2], [3, 5, 4], [0, 3, 4, 1], [1, 4, 5, 2], [2, 5, 3, 0]]
    return Solid([tuple(float(c) for c in p) for p in v], f)


# ---------------------------------------------------------------- overlap

def aabb_overlap(a: tuple[Vec, Vec], b: tuple[Vec, Vec], eps: float) -> bool:
    return all(min(a[1][k], b[1][k]) - max(a[0][k], b[0][k]) > eps for k in range(3))


def penetration(a: Solid, b: Solid) -> float:
    """Depth of overlap between two convex solids (<= 0 means separate or touching)."""
    axes = a.normals() + b.normals()
    for ea in a.edge_dirs():
        for eb in b.edge_dirs():
            c = cross(ea, eb)
            if norm(c) > 1e-9:
                axes.append(unit(c))
    depth = math.inf
    for ax in axes:
        if norm(ax) < 1e-9:
            continue
        pa = [dot(v, ax) for v in a.verts]
        pb = [dot(v, ax) for v in b.verts]
        o = min(max(pa), max(pb)) - max(min(pa), min(pb))
        if o <= 0:
            return o
        depth = min(depth, o)
    return depth
