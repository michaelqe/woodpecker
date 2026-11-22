"""Generate the house model (run: python3 scripts/house_model.py designs/).

Magpie: House > Digital Twin (project 38). Source: the two floor-plan photos of 25 Jun 2025
(ground and upper floor, grid lines 1-4), traced by hand. Every room area printed on the plans
is checked against the traced walls when this script runs.

Coordinates below are the drawing's: x = left -> right along grid 1 -> 4 (0 = outer face of the
bay wall), y = down the drawing (0 = outer face of the kitchen wall). box() turns them into
Woodpecker's axes (y grows toward the back, so y_wp = DEPTH - y), which keeps the top view the
same way round as the plan instead of mirrored. z = up (0 = ground-floor floor).

Site orientation (from the cadastral / Google Maps, north up): the long wall with the front door
(plan "east") faces north toward Tiskre tee; the short wall with the back door (plan "south")
faces east onto the parking pad. The living-room bay (plan "west") faces south. shell_on_pad()
rotates the shell into the garage site frame (origin at the house's SE / pad's SW, +x east,
+y north) so Top view matches the map.

Change the house here and re-run; do not edit designs/house.json with the tools, the next run
overwrites it. Everything is a reference part: nothing here is built, so there is no cut list.

Assumed until measured: ceilings 2700, floor between storeys 300, window sills 900, window and
door heads 2100. Positions marked GUESS in a note are read off the photo without a dimension.
"""
import json
import sys
from pathlib import Path

GROUND, UPPER = 0, 1
LEVEL = {GROUND: {"z": 0, "h": 3000, "name": "Ground floor"},
         UPPER: {"z": 3000, "h": 2700, "name": "Upper floor"}}
W_SILL, W_HEAD, D_HEAD = 900, 2100, 2100
DEPTH = 14450  # outer face to outer face, top to bottom of the drawing

MATERIALS = {
    "wall": {"name": "Wall (reference)", "kind": "reference", "color": "#d6d4ce"},
    "glass": {"name": "Window glass (reference)", "kind": "reference", "color": "#8fbfe0"},
    "floor": {"name": "Floor, wood (reference)", "kind": "reference", "color": "#b8946a"},
    "tile": {"name": "Floor, tiles (reference)", "kind": "reference", "color": "#8fa3ad"},
    "slab": {"name": "Floor between storeys (reference)", "kind": "reference", "color": "#a7a7a2"},
    "outside": {"name": "Terrace and steps (reference)", "kind": "reference", "color": "#8a8f7a"},
    "masonry": {"name": "Fireplace and chimney (reference)", "kind": "reference", "color": "#9c8576"},
    "fixture": {"name": "Built-in fixture (reference)", "kind": "reference", "color": "#a59e90"},
    "appliance": {"name": "Appliance (reference)", "kind": "reference", "color": "#e8e8e8"},
    "stair": {"name": "Stair treads (reference)", "kind": "reference", "color": "#a07850"},
    "rail": {"name": "Railing (reference)", "kind": "reference", "color": "#555a60"},
}

# ---------------------------------------------------------------- walls
# r = [x0, y0, x1, y1]; openings run along the wall's long side, in drawing coordinates.
# t: w = window, d = door, o = opening without a door.
WALLS = [
    # Ground floor, exterior (284)
    ("g-n", GROUND, "North wall by the kitchen", [2750, 0, 8450, 284], [
        dict(t="w", a=3634, b=4634, name="Kitchen window")]),
    ("g-e", GROUND, "East wall", [8166, 0, 8450, 14450], [
        dict(t="w", a=891, b=2891, name="Kitchen window"),
        dict(t="w", a=4382, b=5282, name="Hall window"),
        dict(t="d", a=6683, b=7687, name="Front door"),
        dict(t="w", a=10147, b=11059, name="Sink room window")]),
    ("g-s", GROUND, "South wall", [2750, 14166, 8450, 14450], [
        dict(t="w", a=3216, b=4616, name="Office window"),
        dict(t="d", a=6483, b=7383, name="Back door")]),
    ("g-wk", GROUND, "West wall by the kitchen", [2750, 0, 3034, 4034], [
        dict(t="w", a=500, b=1400, sill=300, name="Tall kitchen window", note="GUESS: position and width"),
        dict(t="d", a=1600, b=2450, name="Terrace door 1", note="GUESS: two doors side by side, widths not on the plan"),
        dict(t="d", a=2550, b=3400, name="Terrace door 2", note="GUESS: two doors side by side, widths not on the plan")]),
    ("g-wl", GROUND, "West wall by the office", [2750, 9866, 3034, 14450], [
        dict(t="w", a=11400, b=12800, name="Office west window", note="GUESS: position and width")]),
    ("g-bn", GROUND, "Bay north wall", [0, 3750, 2750, 4034], [
        dict(t="w", a=595, b=1595, name="Living room north window")]),
    ("g-bw", GROUND, "Bay west wall", [0, 3750, 284, 10150], [
        dict(t="w", a=4459, b=6900, sill=500, head=2300, name="Living room window 1", note="GUESS: one window or two, sill height"),
        dict(t="w", a=7000, b=9441, sill=500, head=2300, name="Living room window 2", note="GUESS: one window or two, sill height")]),
    ("g-bs", GROUND, "Bay south wall", [0, 9866, 2750, 10150], []),
    # Ground floor, interior
    ("g-i1", GROUND, "Kitchen / stair wall", [5766, 3840, 8166, 4034], []),
    ("g-i2", GROUND, "Stair side wall", [5766, 4034, 5858, 5150], []),
    ("g-i3", GROUND, "Hall / office wall", [3034, 9866, 8166, 10060], [
        dict(t="d", a=4674, b=5474, name="Office door"),
        dict(t="d", a=6308, b=7208, name="Sink room door",
             note="Drawn opening out of the WC; the real way in is not confirmed")]),
    ("g-i4", GROUND, "Office / sink room wall", [5534, 10060, 5626, 14166], []),
    ("g-i5", GROUND, "Sink room / plant room wall", [5626, 12052, 8166, 12144], [
        dict(t="d", a=6705, b=7405, name="Plant room door")]),
    ("g-i6", GROUND, "WC west wall", [6153, 8766, 6245, 9866], [
        dict(t="d", a=9100, b=9800, name="WC door")]),
    ("g-i7", GROUND, "WC / wardrobe wall", [6153, 8674, 8166, 8766], []),
    ("g-i8", GROUND, "Wardrobe end wall", [6153, 7874, 6245, 8674], []),
    # Upper floor, exterior
    ("u-n", UPPER, "North wall by bedroom 1", [2750, 0, 8450, 284], [
        dict(t="w", a=3634, b=4634, name="Bedroom 1 north window")]),
    ("u-e", UPPER, "East wall", [8166, 0, 8450, 14450], [
        dict(t="w", a=4382, b=5282, name="Landing window", note="Other east windows upstairs not clear on the photo")]),
    ("u-s", UPPER, "South wall", [2750, 14166, 8450, 14450], [
        dict(t="w", a=3216, b=4616, name="Bedroom 4 south window")]),
    ("u-wm", UPPER, "West wall by bedroom 1", [2750, 0, 3034, 4034], [
        dict(t="w", a=594, b=1894, name="Bedroom 1 west window"),
        dict(t="d", a=2700, b=3460, name="Bedroom 1 west door", note="GUESS: balcony or French window")]),
    ("u-wl", UPPER, "West wall by bedroom 4", [2750, 9866, 3034, 14450], [
        dict(t="w", a=11000, b=12400, name="Bedroom 4 west window", note="GUESS: position and width")]),
    ("u-bn", UPPER, "Bay north wall", [0, 3750, 2750, 4034], [
        dict(t="w", a=595, b=1595, name="Bedroom 2 north window")]),
    ("u-bw", UPPER, "Bay west wall", [0, 3750, 284, 10150], [
        dict(t="w", a=4459, b=6459, name="Bedroom 2 west window"),
        dict(t="w", a=7458, b=9458, name="Bedroom 3 west window")]),
    ("u-bs", UPPER, "Bay south wall", [0, 9866, 2750, 10150], []),
    # Upper floor, interior
    ("u-i1", UPPER, "Bedroom 1 south wall", [3034, 3840, 8166, 4034], [
        dict(t="d", a=4700, b=5600, name="Bedroom 1 door")]),
    ("u-i2", UPPER, "Walk-in wardrobe partition", [7266, 284, 7358, 3840], [
        dict(t="o", a=3000, b=3700, name="Wardrobe opening", note="GUESS: the plan shows no way in")]),
    ("u-i3", UPPER, "Bedrooms 2-3 / landing wall", [4456, 4034, 4650, 9866], [
        dict(t="d", a=6050, b=6850, name="Bedroom 2 door"),
        dict(t="d", a=8950, b=9750, name="Bedroom 3 door")]),
    ("u-i4", UPPER, "Bedroom 2 / 3 wall", [284, 6904, 4456, 6996], []),
    ("u-i5", UPPER, "Bedroom 4 north wall", [3034, 9866, 5766, 10060], [
        dict(t="d", a=4850, b=5650, name="Bedroom 4 door")]),
    ("u-i6", UPPER, "Bathroom west wall", [5766, 7742, 5858, 12134], []),
    ("u-i7", UPPER, "Bathroom north wall", [5858, 7742, 8166, 7834], [
        dict(t="d", a=5950, b=6750, name="Bathroom door", note="GUESS: position")]),
    ("u-i8", UPPER, "WC west wall", [6874, 6234, 6966, 7742], [
        dict(t="d", a=7000, b=7700, name="WC door")]),
    ("u-i9", UPPER, "WC north wall", [6874, 6234, 8166, 6326], []),
    ("u-i10", UPPER, "Basin room / bath room wall", [5858, 9866, 8166, 10060], [
        dict(t="o", a=5960, b=6960, name="Opening between the bathroom halves")]),
    ("u-i11", UPPER, "Bath / sauna wall", [5858, 12042, 8166, 12134], [
        dict(t="d", a=6790, b=7390, name="Sauna door")]),
    ("u-i12", UPPER, "Closet / sauna wall", [6566, 12134, 6658, 14166], []),
    ("u-i13", UPPER, "Bedroom 4 closet wall", [5766, 12681, 5858, 14166], []),
]

# ---------------------------------------------------------------- rooms
# (id, floor, plan name, English name, plan area m2 or None, rects, kind, note)
ROOMS = [
    ("kook", GROUND, "Köök", "Kitchen", 18.1, [[3034, 284, 8166, 3840]], "floor", ""),
    ("elutuba", GROUND, "Elutuba", "Living room", 23.3, [[284, 4034, 2750, 9866], [2750, 4034, 4279, 9866]], "floor",
     "Open to the hall. Split at x 4279, where both rooms match the plan areas."),
    ("esik", GROUND, "Esik", "Hall", 12.8, [[4279, 4034, 5773, 9866], [5773, 6400, 8166, 7874], [5773, 7874, 6153, 9866]],
     "floor", "Open to the living room. Split at x 4279, where both rooms match the plan areas."),
    ("stair-floor", GROUND, "Trepi alune", "Under the stair", None, [[5773, 4034, 8166, 6400]], "floor",
     "Floating stair: the space under it is usable."),
    ("wc0", GROUND, "WC", "WC", 2.1, [[6245, 8766, 8166, 9866]], "tile", ""),
    ("kabinet", GROUND, "Kabinet", "Office", 10.2, [[3034, 10060, 5534, 14166]], "floor", ""),
    ("pesuruum", GROUND, "Pesuruum", "Sink and storage", 5.2, [[5626, 10060, 8166, 12052]], "tile",
     "Drawn as the laundry; now a sink and built-in storage. The laundry moved upstairs."),
    ("tehnoruum", GROUND, "Tehnoruum", "Plant room", 5.0, [[5626, 12144, 8166, 14166]], "tile", ""),
    ("terrass", GROUND, "Terrass", "Terrace", None, [[300, 120, 2750, 3750]], "outside", "Outline only; no dimensions on the plan."),
    ("porch-e", GROUND, "Välisuks", "Entrance step", None, [[8450, 5900, 9950, 8600]], "outside", "2700 x 1200 + 300 step."),
    ("porch-s", GROUND, "Tagauks", "Back step", None, [[6033, 14450, 7833, 15950]], "outside", "1800 x 1200 + 300 step."),
    ("mag1", UPPER, "Magamistuba 1", "Bedroom 1", 15.1, [[3034, 284, 7266, 3840]], "floor", ""),
    ("garderoob", UPPER, "Garderoob", "Walk-in wardrobe", 2.9, [[7358, 284, 8166, 3840]], "floor", ""),
    ("mag2", UPPER, "Magamistuba 2", "Bedroom 2", 12.0, [[284, 4034, 4456, 6904]], "floor", ""),
    ("mag3", UPPER, "Magamistuba 3", "Bedroom 3", 12.0, [[284, 6996, 4456, 9866]], "floor", ""),
    ("trepihall", UPPER, "Trepihall", "Landing", 8.2,
     [[4650, 4034, 5773, 6234], [4650, 6234, 6874, 7742], [4650, 7742, 5766, 9866]], "floor", ""),
    ("wc1", UPPER, "WC", "WC", 1.7, [[6966, 6326, 8166, 7742]], "tile", ""),
    ("vann1", UPPER, "Vannituba", "Bathroom, basins", 4.7, [[5858, 7834, 8166, 9866]], "tile", ""),
    ("vann2", UPPER, "Vannituba", "Bathroom, bath and laundry", 4.6, [[5858, 10060, 8166, 12042]], "tile",
     "The washing machine is here, across from the bath."),
    ("leil", UPPER, "Leil", "Sauna", 3.1, [[6658, 12134, 8166, 14166]], "tile", ""),
    ("mag4", UPPER, "Magamistuba 4", "Bedroom 4", 12.8, [[3034, 10060, 5766, 14166], [5858, 12134, 6566, 14166]], "floor",
     "Includes the 708 mm closet beside the sauna."),
]

# (id, floor, name, [x0, y0, x1, y1], [z0, z1] above the floor, material, role)
BLOCKS = [
    ("fireplace", GROUND, "Fireplace", [3977, 6047, 4735, 8798], [0, 3000], "masonry",
     "Fireplace between the living room and the hall. Size read off the photo, about +-50 mm."),
    ("chimney-up", UPPER, "Chimney", [4031, 7174, 4456, 7608], [0, 2700], "masonry",
     "Chimney through bedroom 3, from the plan symbol."),
    ("hall-wardrobe", GROUND, "Hall wardrobe", [6245, 7874, 8166, 8674], [0, 2400], "fixture",
     "Built-in wardrobe by the front door, 1921 x 800."),
    ("washer", UPPER, "Washing machine", [5870, 10700, 6470, 11300], [0, 850], "appliance",
     "Laundry across from the bath. GUESS: exact position."),
]


# ---------------------------------------------------------------- build
def area(rects):
    return sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rects) / 1e6


def fmt(n):
    return f"{round(n):,}".replace(",", " ")


def box(pid, name, group, material, x0, y0, z0, x1, y1, z1, role, notes=""):
    p = {"id": pid, "name": name, "group": group, "material": material,
         "size": [x1 - x0, y1 - y0, z1 - z0], "at": [x0, DEPTH - y1, z0], "role": role}
    if notes:
        p["notes"] = notes
    return p


def wall_parts(wid, f, name, r, openings):
    x0, y0, x1, y1 = r
    lv = LEVEL[f]
    z, H = lv["z"], lv["h"]
    group = lv["name"]
    along_x = (x1 - x0) >= (y1 - y0)
    thick = (y1 - y0) if along_x else (x1 - x0)
    kind = "Exterior" if thick >= 280 else "Interior"
    length = (x1 - x0) if along_x else (y1 - y0)
    base_role = f"{kind} wall, {thick} mm thick, {fmt(length)} mm long ({group.lower()})."
    out, n = [], 0

    def piece(a, b, h0, h1, what, note=""):
        nonlocal n
        if b <= a or h1 <= h0:
            return
        n += 1
        rx = (a, y0, b, y1) if along_x else (x0, a, x1, b)
        out.append(box(f"{wid}-{n}", f"{name} ({group.lower()})", group, "wall",
                       rx[0], rx[1], z + h0, rx[2], rx[3], z + h1, f"{base_role} {what}", note))

    c = x0 if along_x else y0
    end = x1 if along_x else y1
    for o in sorted(openings, key=lambda o: o["a"]):
        piece(c, o["a"], 0, H, "Solid section.")
        sill = o.get("sill", W_SILL) if o["t"] == "w" else 0
        head = o.get("head", W_HEAD if o["t"] == "w" else D_HEAD)
        w = o["b"] - o["a"]
        desc = f"{o['name']}, {w} mm wide at {fmt(o['a'])}-{fmt(o['b'])}"
        piece(o["a"], o["b"], 0, sill, f"Below the {o['name'].lower()} (sill {sill}).", o.get("note", ""))
        piece(o["a"], o["b"], head, H, f"Above the {o['name'].lower()} (head {head}). {desc}.", o.get("note", ""))
        if o["t"] == "w":
            n += 1
            mid = (y0 + y1) / 2 if along_x else (x0 + x1) / 2
            rx = (o["a"], mid - 12, o["b"], mid + 12) if along_x else (mid - 12, o["a"], mid + 12, o["b"])
            out.append(box(f"{wid}-{n}", o["name"], group, "glass", rx[0], rx[1], z + sill, rx[2], rx[3], z + head,
                           f"{desc}, sill {sill}, head {head} ({name.lower()}).", o.get("note", "")))
        c = o["b"]
    piece(c, end, 0, H, "Solid section.")
    return out


def room_parts(rid, f, plan_name, en, plan_area, rects, kind, note):
    lv = LEVEL[f]
    group = "Site" if kind == "outside" else lv["name"]
    a = area(rects)
    check = f"; plan says {plan_area} m2" if plan_area else ""
    out = []
    for i, (x0, y0, x1, y1) in enumerate(rects):
        if kind == "outside":
            z0, z1 = (0, 150) if rid.startswith("porch") else (0, 20)
        elif f == UPPER:
            z0, z1 = lv["z"] - 300, lv["z"]
        else:
            z0, z1 = 0, 20
        mat = kind
        size = f"{fmt(x1 - x0)} x {fmt(y1 - y0)} mm"
        role = (f"{en} ({plan_name}), {lv['name'].lower()}. This piece {size}; the room is {a:.2f} m2 as traced{check}."
                if kind != "outside" else f"{en} ({plan_name}), {size}.")
        out.append(box(f"{rid}-floor{'' if len(rects) == 1 else '-' + str(i + 1)}", f"{en} floor", group, mat,
                       x0, y0, z0, x1, y1, z1, role, note))
    return out


def stair_parts():
    """Floating U-stair: 17 risers, up toward the east wall, round, back to the bedroom 1 door. GUESS: direction."""
    rise = 3000 / 17
    P, g = [], "Stair"
    role = "Floating stair tread (no risers, space under it is usable). Layout guessed from the tread lines on the plan."
    for i in range(1, 8):
        x = 5800 + (i - 1) * 214
        P.append(box(f"tread-{i}", f"Stair tread {i}", g, "stair", x, 5300, i * rise - 40, x + 214, 6400, i * rise, role))
    P.append(box("tread-landing", "Stair landing", g, "stair", 7298, 4034, 8 * rise - 40, 8166, 6400, 8 * rise,
                 "Stair landing or winders at the east wall (drawn as winders; simplified to a landing)."))
    for i in range(9, 17):
        j = i - 9
        xa = round(7298 - (j + 1) * 187.25)
        P.append(box(f"tread-{i}", f"Stair tread {i}", g, "stair", xa, 4034, i * rise - 40, round(xa + 187.25), 5134, i * rise, role))
    P.append(box("rail-west", "Landing railing", g, "rail", 5753, 5134, 3000, 5793, 6234, 3900, "Railing round the stairwell upstairs."))
    P.append(box("rail-south", "Landing railing", g, "rail", 5793, 6214, 3000, 6874, 6254, 3900, "Railing round the stairwell upstairs."))
    return P


def _wall_thickness(r):
    x0, y0, x1, y1 = r
    return (y1 - y0) if (x1 - x0) >= (y1 - y0) else (x1 - x0)


def shell_parts():
    """Exterior walls, glass, terrace/steps and the chimney — the massing for other designs.

    No interior walls, floors, stairs or fixtures. Used by scripts/garage_options.py so the
    carport/garage drawings show the real house instead of a flat stub.
    """
    parts = []
    for w in WALLS:
        if _wall_thickness(w[3]) < 280:
            continue
        parts += wall_parts(*w)
    for r in ROOMS:
        if r[6] == "outside":
            parts += room_parts(*r)
    for bid, f, name, (x0, y0, x1, y1), (h0, h1), mat, role in BLOCKS:
        if bid != "chimney-up":
            continue
        z = LEVEL[f]["z"]
        parts.append(box(bid, name, LEVEL[f]["name"], mat, x0, y0, z + h0, x1, y1, z + h1, role))
    for p in parts:
        p["size"] = [round(v, 1) for v in p["size"]]
        p["at"] = [round(v, 1) for v in p["at"]]
    return parts


# Plan-south wall runs twin x = SOUTH_WEST .. NORTH_FACE (geo east face of the house).
# SOUTH_WEST is the geo-SE corner (pad SW); NORTH_FACE is the geo-NE corner (pad NW on the road).
SOUTH_WEST = 2750
NORTH_FACE = 8450


def shell_on_pad():
    """Shell parts in garage/carport site coordinates (north up, matching Google Maps).

    Origin = house SE = pad SW corner. +x = east (into the pad), +y = north (toward the road).
    The short plan-south / back-door wall is the pad's west edge; the long plan-east / front-door
    wall faces the road. Part ids are prefixed with `house-`.
    """
    out = []
    for p in shell_parts():
        hx, hy, hz = p["at"]
        sx, sy, sz = p["size"]
        q = dict(p)
        q["id"] = f"house-{p['id']}"
        q["group"] = "House"
        # 90° CCW in plan: south → +x (east), east → +y (north)
        q["at"] = [round(-(hy + sy), 1), round(hx - SOUTH_WEST, 1), round(hz, 1)]
        q["size"] = [round(sy, 1), round(sx, 1), round(sz, 1)]
        out.append(q)
    return out


def build():
    parts = []
    for w in WALLS:
        parts += wall_parts(*w)
    for r in ROOMS:
        parts += room_parts(*r)
    for bid, f, name, (x0, y0, x1, y1), (h0, h1), mat, role in BLOCKS:
        z = LEVEL[f]["z"]
        parts.append(box(bid, name, LEVEL[f]["name"], mat, x0, y0, z + h0, x1, y1, z + h1, role))
    parts += stair_parts()
    for p in parts:
        p["size"] = [round(v, 1) for v in p["size"]]
        p["at"] = [round(v, 1) for v in p["at"]]
    return {
        "title": "Our house (digital twin)",
        "description": (
            "Both floors traced from the floor-plan photos of 25 Jun 2025, as walls, windows, doors and floors. "
            "Generated by scripts/house_model.py; tracked in Magpie under House > Digital Twin. "
            "Heights are assumed (2.7 m ceilings, 0.3 m floor between storeys) until measured; no roof yet."),
        "units": "mm",
        "anchored": "A house: nothing to tip over.",
        "magpie_project": 38,
        "params": {},
        "materials": MATERIALS,
        "parts": parts,
        "joints": [],
        "hardware": [],
    }


def area_report():
    lines = []
    for rid, f, plan_name, en, plan_area, rects, kind, _ in ROOMS:
        if plan_area is None:
            continue
        a = area(rects)
        ok = abs(a - plan_area) <= max(0.15, 0.03 * plan_area)
        lines.append(f"{'ok  ' if ok else 'OFF '} {LEVEL[f]['name']:<13} {en:<28} plan {plan_area:5.1f}  traced {a:6.2f}")
    return lines


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "designs")
    d = build()
    (out / "house.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out / 'house.json'}: {len(d['parts'])} parts")
    print("\n".join(area_report()))
