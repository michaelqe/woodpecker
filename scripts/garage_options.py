"""Generate Woodpecker designs (run: python3 scripts/garage_options.py designs/) for the House > Garage (Proposed) options.

Site from the cadastral overlay on the Garage page (58.07 m2) and Google Maps (north up):
origin = pad SW = house SE corner, +x east into the pad, +y north toward Tiskre tee. House wall
at x = 0 (6.1 m along y). Road-side (north) edge is 10.29 m; garden-side (south) edge 11.72 m;
east edge 4.57 m. NE corner of the rectangular part of the pad is at (10290, 6100); the slanted
east/south corner is at (11593, 1720).

Top view is north-up (same as Maps). The house shell from scripts/house_model.py is placed by
shell_on_pad(): short back-door wall on the pad's west edge, long front-door wall facing the road.
Re-run this script after changing the house model.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("house_model", _REPO / "scripts" / "house_model.py")
_house = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_house)

PAD_N = 6100          # north (road) edge of the pad at the house, in site y
PAD_NE = (10290, 6100)  # north-east of the rectangular body
PAD_SE = (11593, 1720)  # south-east tip after the slant
DEG = math.degrees


# ---------------------------------------------------------------- materials
MATS = {
    "gl_post": {"name": "Glulam GL30c 140x140 (post)", "kind": "lumber", "section": [140, 140], "stock_length": 6000,
                "density": 460, "notes": "Glulam is ordered cut to length; 6 m is a common stock length."},
    "gl_beam": {"name": "Glulam GL30c 140x225 (beam)", "kind": "lumber", "section": [140, 225], "stock_length": 12000,
                "density": 460, "notes": "Ordered cut to length."},
    "gl_floor": {"name": "Glulam GL30c 90x225 (floor beam)", "kind": "lumber", "section": [90, 225], "stock_length": 6000,
                 "density": 460, "notes": "Ordered cut to length."},
    "c24_220": {"name": "Spruce C24 45x220", "kind": "lumber", "section": [45, 220], "stock_length": 6000, "density": 450},
    "c24_195": {"name": "Spruce C24 45x195", "kind": "lumber", "section": [45, 195], "stock_length": 6000, "density": 450},
    "c24_145": {"name": "Spruce C24 45x145", "kind": "lumber", "section": [45, 145], "stock_length": 5400, "density": 450},
    "c24_95": {"name": "Spruce C24 45x95", "kind": "lumber", "section": [45, 95], "stock_length": 3600, "density": 450},
    "batten": {"name": "Roof batten 32x100, planed", "kind": "lumber", "section": [32, 100], "stock_length": 4800, "density": 450},
    "osb22": {"name": "OSB/3 22 mm tongue and groove (floor)", "kind": "sheet", "thickness": 22, "stock": [2500, 1250], "density": 600},
    "osb12": {"name": "OSB/3 12 mm (ceiling deck)", "kind": "sheet", "thickness": 12, "stock": [2500, 1250], "density": 600},
    "roof_sheet": {"name": "Profiled steel roof sheet (reference)", "kind": "reference", "color": "#59636e"},
    "solar": {"name": "Solar panel about 430 W, 1722x1134 (reference)", "kind": "reference", "color": "#1d3557"},
    "boundary": {"name": "Plot boundary (reference)", "kind": "reference", "color": "#e3b505"},
    "site": {"name": "Site (reference, approximate)", "kind": "reference", "color": "#b9b4aa"},
    "car": {"name": "Car (reference)", "kind": "reference", "color": "#4f7cac"},
    "zone": {"name": "Cable protection zone (reference, approximate)", "kind": "reference", "color": "#d64541"},
    "opening": {"name": "Door / window (reference)", "kind": "reference", "color": "#8fbfe0"},
    "slab": {"name": "Concrete slab (reference)", "kind": "reference", "color": "#a7a7a2"},
    # House shell materials (from house_model; keys must not collide with the ones above)
    "wall": _house.MATERIALS["wall"],
    "glass": _house.MATERIALS["glass"],
    "outside": _house.MATERIALS["outside"],
    "masonry": _house.MATERIALS["masonry"],
}


def mats(*keys):
    return {k: MATS[k] for k in keys}


# ---------------------------------------------------------------- site and cars
def site_parts():
    # East edge from PAD_NE to PAD_SE (slanting south-east). Outward = away from the house.
    ex, ey = PAD_SE[0] - PAD_NE[0], PAD_SE[1] - PAD_NE[1]
    east_len = math.hypot(ex, ey)
    east_ang = DEG(math.atan2(ey, ex))
    nx, ny = -ey / east_len, ex / east_len       # outward normal (roughly east)
    bx = PAD_NE[0] + 2000 * nx
    by = PAD_NE[1] + 2000 * ny
    rect_h = PAD_N - PAD_SE[1]                   # 4380: rectangular body height
    P = []
    P.append({"id": "pad", "name": "Parking pad (pavers), main part", "group": "Site", "material": "site",
              "size": [10290, rect_h, 20], "at": [0, PAD_SE[1], 0],
              "role": "The existing paved pad, 58 m2 (Top view is north-up like the map: road at the top, garden at the bottom). Measured on the cadastral: 10.29 m along the road, 11.72 m along the garden, 6.1 m at the house, 4.57 m at the east end."})
    # Garden wedge: triangle (0,0)-(0, PAD_SE[1])-(PAD_SE[0], PAD_SE[1]) under the rectangular body
    P.append({"id": "pad_wedge", "name": "Parking pad, garden-side wedge", "group": "Site", "material": "site",
              "shape": "gusset", "leg": "left", "size": [PAD_SE[0], 20, PAD_SE[1]], "at": [0, 0, 20],
              "rotate": {"axis": "x", "deg": -90},
              "role": "Part of the pad: it is deeper at the house end (6.1 m) than at the east end (4.4-4.6 m)."})
    # East wedge: triangle PAD_NE-PAD_SE-(10290, PAD_SE[1]) east of the rectangular body
    P.append({"id": "pad_east", "name": "Parking pad, east wedge", "group": "Site", "material": "site",
              "shape": "gusset", "leg": "left", "size": [PAD_SE[0] - 10290, 20, rect_h],
              "at": [10290, PAD_SE[1], 20], "rotate": {"axis": "x", "deg": -90},
              "role": "Part of the pad: the east edge slants outward toward the garden."})
    for hp in _house.shell_on_pad():
        hp = dict(hp)
        hp["role"] = (
            (hp.get("role") or "")
            + " House shell from the digital twin (north-up): short back-door wall at x = 0,"
            " long front-door wall facing the road (north)."
        ).strip()
        P.append(hp)
    P.append({"id": "boundary_north", "name": "Plot boundary, road side (approx.)", "group": "Site", "material": "boundary",
              "size": [14000, 60, 100], "at": [-2000, PAD_N + 3500, 0],
              "role": "Boundary with the road-side strip, about 3.5 m north of the pad (measured on the map)."})
    P.append({"id": "boundary_east", "name": "Plot boundary with 0127 (approx.)", "group": "Site", "material": "boundary",
              "size": [9000, 60, 100],
              "at": [round(bx - 3500 * math.cos(math.radians(east_ang))),
                     round(by - 3500 * math.sin(math.radians(east_ang))), 0],
              "rotate": {"axis": "z", "deg": round(east_ang, 2)},
              "role": "Boundary with plot 0127, about 2 m from the east end of the pad. Under 4 m means EI60 walls and, in Tallinn, a written agreement with the neighbour."})
    P.append({"id": "cable_zone_front", "name": "Cable corridor protection zone (approx.)", "group": "Site", "material": "zone",
              "size": [16000, 2000, 15], "at": [-3000, PAD_N + 3500, 0],
              "role": "Low-voltage cables run 4-5 m north of the pad's front edge, with about 1 m protection zone each side. No digging or footings here without Elektrilevi's consent."})
    P.append({"id": "cable_zone_ne", "name": "Service cables from 1239, zone (approx.)", "group": "Site", "material": "zone",
              "size": [2000, 5500, 15], "at": [11300, PAD_N - 2000, 0],
              "role": "AXPK 4x25 service cables leave distribution point 1239 heading south then east, about 2 m from the pad's NE corner. Positions on utility maps can be off by a metre; order an on-site marking."})
    P.append({"id": "dist_1239", "name": "Distribution point 1239 (Haabersti)", "group": "Site", "material": "site",
              "size": [900, 500, 1400], "at": [11200, PAD_N + 1000, 0],
              "role": "Elektrilevi distribution point on the neighbouring land, just past the NE corner of the pad."})
    return P


def car(prefix, label, item, width, y_nose, cx, z=0):
    """A car from the catalog (published size, drawn with wheels and glass), backed in:
    nose toward the road (north, +y). Catalog vehicles face -y (nose at local y = 0), so they
    are rotated 180° about z; after that flip `at` is the nose / max-x corner, so use
    cx + width/2 (not cx - width/2) or the car lands a full width too far west."""
    return [{"id": prefix, "name": label, "group": "Cars", "component": item,
             "at": [round(cx + width / 2), round(y_nose), z],
             "rotate": {"axis": "z", "deg": 180},
             "role": f"{label}, to check the fit. Reference only: not in the cut list."}]


MULTIVAN = ("VW Multivan T6.1 (2021)", "vw-multivan-t61-2021", 1904)
ALLTRACK = ("VW Golf Alltrack (2017)", "vw-golf-alltrack-2017", 1799)


# ---------------------------------------------------------------- carport roof frame (parametric)
def carport_params(W, D, bays, h_front, pitch=5, x0=150, y0=None):
    """y0 is the garden (south) edge of the roof; +y is north toward the road. Default y0
    places the road edge of a depth-D roof on the pad's north edge (PAD_N)."""
    if y0 is None:
        y0 = PAD_N - D
    return {
        "x0": {"value": x0, "label": "Gap between house wall and roof edge"},
        "W": {"value": W, "label": "Roof width (along the house wall's side, x)"},
        "D": {"value": D, "label": "Roof depth, garden (south) to road (north)"},
        "y0": {"value": y0, "label": "Roof garden (south) edge"},
        "bays": {"value": bays, "label": "Bays between posts", "unit": "count"},
        "h_front": {"value": h_front, "label": "Top of the front (road / north) beam"},
        "pitch": {"value": pitch, "label": "Roof pitch (falls toward the garden / south)", "unit": "deg"},
        "oh_side": {"value": 250, "label": "Roof overhang past the end posts"},
        "oh_front": {"value": 300, "label": "Roof overhang north of the front posts"},
        "oh_back": {"value": 300, "label": "Roof overhang south of the back posts"},
        "post": {"value": 140, "label": "Post size (glulam, square)"},
        "beam_h": {"value": 225, "label": "Beam depth (glulam)"},
        "raf_h": {"value": 220, "label": "Rafter depth"},
        "raf_t": {"value": 45, "label": "Rafter thickness"},
        "raf_max": {"value": 600, "label": "Max rafter spacing"},
        "batten_max": {"value": 800, "label": "Max batten spacing (along the slope)"},
        "brace": {"value": 600, "label": "Knee brace leg"},
        "post_step": "(W - 2 * oh_side - post) / bays",
        "yb": "y0 + oh_back",
        "yf": "y0 + D - oh_front - post",
        "h_back": {"value": "h_front - (yf - yb) * tan(pitch)", "label": "Top of the back (garden) beam"},
        "raf_len": "D / cos(pitch)",
        "raf_n": "ceil((W - raf_t) / raf_max) + 1",
        "raf_step": "(W - raf_t) / (raf_n - 1)",
        # Rafter sits on the low (garden) end and rises toward the road (+pitch about x)
        "raf_z": "h_back + (yb + post / 2 - y0) * tan(pitch)",
        "top_z": "raf_z + raf_h / cos(pitch)",
        "bat_n": "ceil((raf_len - 100) / batten_max) + 1",
        "bat_step": "(raf_len - 100) / (bat_n - 1)",
        "roof_area_m2": {"value": "W * D / 1000000", "label": "Roofed area (counts as footprint)", "unit": "m2"},
        "height_max": {"value": "h_front + raf_h / cos(pitch) + 32 + 25", "label": "Highest point (roof sheet at the road edge)"},
    }


def carport_parts(batten_pieces=2, solar_rows=3, solar_cols=5):
    P = []
    P.append({"id": "post_front", "name": "Post, front (road)", "group": "Frame", "material": "gl_post",
              "size": ["post", "post", "h_front - beam_h"], "at": ["x0 + oh_side", "yf", 0],
              "repeat": {"count": "bays + 1", "axis": "x", "spacing": "post_step"},
              "role": "Carries the front (road / north) beam down to a ground screw. Sized and spaced so walls and a door can be added later."})
    P.append({"id": "post_back", "name": "Post, back (garden)", "group": "Frame", "material": "gl_post",
              "size": ["post", "post", "h_back - beam_h"], "at": ["x0 + oh_side", "yb", 0],
              "repeat": {"count": "bays + 1", "axis": "x", "spacing": "post_step"},
              "role": "Carries the back (low / garden) beam. Shorter than the front posts because the roof falls toward the garden."})
    P.append({"id": "beam_front", "name": "Beam, front (road)", "group": "Frame", "material": "gl_beam",
              "size": ["W - 200", "post", "beam_h"], "at": ["x0 + 100", "yf", "h_front - beam_h"],
              "role": "Front (high / road) beam on top of the front posts; the rafters sit on it."})
    P.append({"id": "beam_back", "name": "Beam, back (garden)", "group": "Frame", "material": "gl_beam",
              "size": ["W - 200", "post", "beam_h"], "at": ["x0 + 100", "yb", "h_back - beam_h"],
              "role": "Back (low / garden) beam on top of the back posts."})
    for row, y, top in (("front", "yf", "h_front"), ("back", "yb", "h_back")):
        P.append({"id": f"brace_{row}", "name": f"Knee brace, {row}", "group": "Frame", "material": "c24_95",
                  "size": ["brace / cos(45)", 45, 95],
                  "at": ["x0 + oh_side + post", f"{y} + post / 2 - 22.5", f"{top} - beam_h - brace - 95 * sqrt(2) + 2"],
                  "rotate": {"axis": "y", "deg": -45}, "ends": {"start": 45, "end": -45},
                  "repeat": {"count": "bays", "axis": "x", "spacing": "post_step"},
                  "mirror": {"axis": "x", "about": "x0 + W / 2"},
                  "role": "Diagonal between post and beam. Stops the frame racking sideways along its length (wind, a nudge from a car)."})
    P.append({"id": "rafter", "name": "Rafter", "group": "Roof", "material": "c24_220",
              "size": ["raf_t", "raf_len", "raf_h"], "at": ["x0", "y0", "raf_z"],
              "rotate": {"axis": "x", "deg": "pitch"},
              "repeat": {"count": "raf_n", "axis": "x", "spacing": "raf_step"},
              "role": "Spans from the back beam to the front beam, rising toward the road so rain and snow run off to the garden. Fixed with a rafter tie at each beam.",
              "notes": "About 5.3 m between the beams: check the span against the snow load in the design project (45x220 at 600 c/c is at the limit; 400 c/c or 45x245 if needed)."})
    for k in range(batten_pieces):
        P.append({"id": f"batten_{k + 1}", "name": f"Roof batten, piece {k + 1}", "group": "Roof", "material": "batten",
                  "size": [f"W / {batten_pieces}", 100, 32],
                  "at": [f"x0 + {k} * W / {batten_pieces}", "y0 + 50 * cos(pitch)", "top_z + 50 * sin(pitch)"],
                  "rotate": {"axis": "x", "deg": "pitch"},
                  "repeat": {"count": "bat_n", "step": [0, "bat_step * cos(pitch)", "bat_step * sin(pitch)"]},
                  "role": "Across the rafters; the steel roof sheets are screwed to these. Joints fall on a rafter."})
    P.append({"id": "roof", "name": "Roof sheet", "group": "Roof", "material": "roof_sheet",
              "size": ["W", "raf_len", 25], "at": ["x0", "y0", "top_z + 32"], "rotate": {"axis": "x", "deg": "pitch"},
              "role": "Profiled steel sheet with anti-condensation felt (so it does not drip on the cars)."})
    for r in range(solar_rows):
        P.append({"id": f"solar_{r + 1}", "name": f"Solar panel, row {r + 1}", "group": "Solar", "material": "solar",
                  "size": [1134, 1722, 35],
                  "at": ["x0 + (W - %d * 1150) / 2" % solar_cols,
                         f"y0 + (150 + {r} * 1740) * cos(pitch)",
                         f"top_z + 32 + 25 + 60 + (150 + {r} * 1740) * sin(pitch)"],
                  "rotate": {"axis": "x", "deg": "pitch"},
                  "repeat": {"count": solar_cols, "axis": "x", "spacing": 1150},
                  "role": "Solar panels on rails over the roof sheet. The roof falls to the south (garden), so the panels face south."})
    return P


def carport_joints(batten_pieces=2):
    return [
        {"id": "post_beam", "type": "bolted", "parts": ["post_front", "beam_front", "post_back", "beam_back"],
         "fasteners": "Post-to-beam steel brackets, 2x M12 bolts each, or a slotted post with 2x M12"},
        {"id": "braces", "type": "screwed", "parts": ["brace_front", "brace_back", "post_front", "post_back", "beam_front", "beam_back"],
         "fasteners": "2x 8x160 construction screws at each end"},
        {"id": "rafters_on_beams", "type": "screwed", "parts": ["rafter", "beam_front", "beam_back"],
         "fasteners": "Rafter tie (hurricane clip) each side of each rafter at both beams"},
        {"id": "battens", "type": "screwed",
         "parts": ["rafter", "roof"] + [f"batten_{k + 1}" for k in range(batten_pieces)],
         "fasteners": "2x 5x90 screws per crossing"},
        {"id": "solar_on_roof", "type": "clamped", "parts": ["roof", "solar_1", "solar_2", "solar_3"],
         "fasteners": "Panel rails on roof hooks into the battens"},
    ]


def carport_hardware(posts, rafters, roof_m2, panels):
    return [
        {"item": "Ground screw 76x1000 with adjustable post plate", "qty": posts,
         "notes": "One per post. Lift the pavers locally, screw in, re-lay. Keep clear of cable zones."},
        {"item": "Post-to-beam steel bracket + 2x M12x200 bolts", "qty": posts},
        {"item": "Rafter tie / hurricane clip", "qty": rafters * 4},
        {"item": f"Profiled steel roof sheet with anti-condensation felt, about {roof_m2:.0f} m2", "qty": 1},
        {"item": "Gutter along the back (low) edge, with downpipe to a soakaway", "qty": 1},
        {"item": "8x160 construction screws (braces)", "qty": 40},
        {"item": "5x90 screws (battens), box of 250", "qty": 2},
        {"item": f"Solar panel about 430 W ({panels} = about {panels * 0.43:.1f} kWp) + rails, inverter, small-producer connection", "qty": panels},
    ]


# ---------------------------------------------------------------- framed walls (for the box and the garage)
def wall(prefix, label, axis, origin, length, height, openings=(), stud=145, t=45, step=600, sloped=None):
    """Stud wall. axis 'x' or 'y' = the direction it runs. origin = (x, y, z) of its outer corner.
    openings: (offset, width, height, sill, name) measured along the wall from its start.
    sloped: (z_at_start, drop_per_mm) for walls whose top follows a mono-pitch roof (axis y only)."""
    X, Y, Z = origin
    parts, ids = [], []

    def put(pid, name, along, across, up, size_along, size_up, mat="c24_145", role=""):
        if axis == "x":
            at, size = [X + along, Y + across, Z + up], [size_along, stud, size_up]
        else:
            at, size = [X + across, Y + along, Z + up], [stud, size_along, size_up]
        parts.append({"id": pid, "name": name, "group": label, "material": mat,
                      "size": [round(s, 1) for s in size], "at": [round(a, 1) for a in at], "role": role})
        ids.append(pid)

    def top_at(a):
        return height if not sloped else sloped[0] - sloped[1] * a

    npieces = math.ceil(length / 5400)
    seg = length / npieces
    for i in range(npieces):
        sfx = "" if npieces == 1 else f"_{i + 1}"
        put(f"{prefix}_sole{sfx}", f"{label}: bottom plate", i * seg, 0, 0, seg, t,
            role="Bottom plate, on the floor or slab (on a damp-proof strip).")
        if not sloped:
            put(f"{prefix}_top{sfx}", f"{label}: top plate", i * seg, 0, height - 2 * t, seg, t,
                role="Top plate, doubled: carries the roof and ties the wall together.")
            put(f"{prefix}_cap{sfx}", f"{label}: top plate, cap", i * seg, 0, height - t, seg, t,
                role="Second top plate. Shift its joint at least one stud bay from the joint below when you build it.")
    if sloped:
        z0, drop = sloped
        ang = DEG(math.atan(drop))
        plen = seg / math.cos(math.atan(drop))
        for i in range(npieces):
            sfx = "" if npieces == 1 else f"_{i + 1}"
            parts.append({"id": f"{prefix}_top{sfx}", "name": f"{label}: sloping top plate", "group": label, "material": "c24_145",
                          "size": [stud, round(plen, 1), t],
                          "at": [X, Y + round(i * seg, 1), round(Z + z0 - drop * i * seg - t / math.cos(math.atan(drop)), 1)],
                          "rotate": {"axis": "x", "deg": round(-ang, 3)},
                          "role": "Top plate following the roof slope."})
            ids.append(f"{prefix}_top{sfx}")
    # stud positions: every `step`, plus both ends, skipping openings; kings and jacks at openings
    cuts = []
    for (off, w, h, sill, name) in openings:
        cuts.append((off - 2 * t, off + w + 2 * t))
    pos = [0.0] + [k * step - t / 2 for k in range(1, int(length // step) + 1) if k * step < length - t] + [length - t]
    pos = sorted(set(round(p, 1) for p in pos if not any(a - 1 < p < b + 1 - t for a, b in cuts)))
    n = 0
    for p in pos:
        n += 1
        top = top_at(p + t / 2) - (2 * t if not sloped else t / math.cos(math.atan(sloped[1])))
        put(f"{prefix}_stud{n}", f"{label}: stud", p, 0, t, t, top - t, role="Stud.")
    for k, (off, w, h, sill, name) in enumerate(openings, 1):
        under_top = top_at(off) - (2 * t if not sloped else t)
        # kings and jacks both sides
        put(f"{prefix}_o{k}_king_l", f"{label}: king stud ({name})", off - 2 * t, 0, t, t, under_top - t - 5, role=f"Full-height stud beside the {name}.")
        put(f"{prefix}_o{k}_king_r", f"{label}: king stud ({name})", off + w + t, 0, t, t, under_top - t - 5, role=f"Full-height stud beside the {name}.")
        put(f"{prefix}_o{k}_jack_l", f"{label}: jack stud ({name})", off - t, 0, t, t, sill + h - t, role=f"Carries the header over the {name}.")
        put(f"{prefix}_o{k}_jack_r", f"{label}: jack stud ({name})", off + w, 0, t, t, sill + h - t, role=f"Carries the header over the {name}.")
        hmat = "c24_195" if w < 2000 else "c24_220"
        hdr = 195 if w < 2000 else 220
        for side, across in (("a", 0), ("b", stud - t)):
            hid = f"{prefix}_o{k}_header{side}"
            if axis == "x":
                at, size = [X + off - t, Y + across, Z + sill + h], [w + 2 * t, t, hdr]
            else:
                at, size = [X + across, Y + off - t, Z + sill + h], [t, w + 2 * t, hdr]
            parts.append({"id": hid, "name": f"{label}: header ({name})", "group": label, "material": hmat,
                          "size": [round(v, 1) for v in size], "at": [round(v, 1) for v in at],
                          "role": f"Lintel over the {name}, two boards on edge with insulation between: takes the roof load around the opening."})
            ids.append(hid)
        if sill > 0:
            put(f"{prefix}_o{k}_sill", f"{label}: sill ({name})", off, 0, sill - t, w, t, role=f"Sill under the {name}.")
        ref = {"id": f"{prefix}_o{k}", "name": f"{label}: {name}", "group": label, "material": "opening",
               "size": [w, 60, h] if axis == "x" else [60, w, h],
               "at": [X + off, Y + stud / 2 - 30, Z + sill] if axis == "x" else [X + stud / 2 - 30, Y + off, Z + sill],
               "role": f"{name.capitalize()} (bought, {w} x {h} mm rough opening)."}
        parts.append(ref)
    return parts, ids


def main():
    designs = {}

    # ---------- 1. two-car carport with solar
    p = carport_params(W=6600, D=5950, bays=2, h_front=2900)
    parts = carport_parts(batten_pieces=2, solar_rows=3, solar_cols=5)
    parts += car("multivan", *MULTIVAN, y_nose=PAD_N - 450, cx=150 + 250 + 140 + 1450 - 140)
    parts += car("alltrack", *ALLTRACK, y_nose=PAD_N - 450, cx=150 + 250 + 1585 + 3110 - 70 - 140)
    parts.append({"id": "cargo_bike", "name": "Cargo bike", "group": "Cars", "material": "car", "size": [2700, 650, 1100],
                  "at": [3900, PAD_N - 5320 - 650, 0],
                  "role": "Cargo bike, about 2.7 m long, behind the Alltrack (which is shorter than the Multivan)."})
    parts += site_parts()
    designs["carport-2car"] = {
        "title": "Carport for 2 cars with solar roof (6.6 x 6.0 m)",
        "description": ("Option 1 for House > Garage (Proposed). Open timber carport at the house end of the pad, where it is deepest. "
                        "Glulam posts on ground screws (no slab, pavers re-laid around them), glulam beams, 45x220 rafters, "
                        "mono-pitch roof falling 5 degrees toward the garden, with room for about 15 solar panels (about 6.5 kWp). "
                        "Roofed area about 39 m2: 20-60 m2 needs a building notice and design project, and the detailed plan "
                        "(one building, 100 m2, realised) is the real hurdle. Posts and clear height are sized so walls and doors can be "
                        "added later. Free-standing, 150 mm off the house wall. Sizes are a starting point for the designer, not a calculation."),
        "units": "mm", "anchored": "Stands on ground screws, so there is no tip check; the designer checks wind uplift and snow.",
        "params": p, "materials": mats("gl_post", "gl_beam", "c24_220", "c24_95", "batten", "roof_sheet", "solar", "site", "wall", "glass", "outside", "masonry", "boundary", "car", "zone"),
        "parts": parts, "joints": carport_joints(2),
        "hardware": carport_hardware(posts=6, rafters=13, roof_m2=6.6 * 5.97, panels=15),
    }

    # ---------- 2. one-car carport under 20 m2
    p = carport_params(W=3600, D=5450, bays=1, h_front=2800)
    p["oh_side"]["value"] = 200
    parts = carport_parts(batten_pieces=1, solar_rows=3, solar_cols=3)
    parts += car("multivan", *MULTIVAN, y_nose=PAD_N - 300, cx=150 + 1800)
    parts += site_parts()
    j = carport_joints(1)
    designs["carport-1car-20m2"] = {
        "title": "Carport for the Multivan, under 20 m2 (3.6 x 5.45 m)",
        "description": ("Option 2 for House > Garage (Proposed). The smallest useful roof: one car (the Multivan) at the house end, "
                        "roofed area 19.6 m2 (19.8 m2 measured over the roof sheet edge) and under 5 m high, which the building code exempts from notice and permit "
                        "(EhS Annex 1: 0-20 m2). It must still be allowed by the detailed plan, so ask the city question (c) first. "
                        "Same construction as option 1, so a second bay can be added later (but that makes it 20-60 m2). "
                        "Room for 9 solar panels (about 3.9 kWp)."),
        "units": "mm", "anchored": "Stands on ground screws, so there is no tip check.",
        "params": p, "materials": mats("gl_post", "gl_beam", "c24_220", "c24_95", "batten", "roof_sheet", "solar", "site", "wall", "glass", "outside", "masonry", "boundary", "car", "zone"),
        "parts": parts, "joints": j,
        "hardware": carport_hardware(posts=4, rafters=7, roof_m2=3.6 * 5.47, panels=9),
    }

    # ---------- 3. carport + office and bike box, just under 60 m2
    p = carport_params(W=9950, D=5950, bays=3, h_front=3500)
    parts = carport_parts(batten_pieces=3, solar_rows=3, solar_cols=8)
    parts += car("multivan", *MULTIVAN, y_nose=PAD_N - 450, cx=150 + 250 + 70 + 1551)
    parts += car("alltrack", *ALLTRACK, y_nose=PAD_N - 450, cx=150 + 250 + 70 + 3103 + 1551)
    # the box: x 6780..9950; y garden 1700 .. road 5580 (flipped from the old 520..4400)
    bx0, bx1, by0, by1 = 6780, 9950, PAD_N - 4400, PAD_N - 520
    bw, bd = bx1 - bx0, by1 - by0
    fz = 100  # underside of floor beams
    for i, x in enumerate((bx0, bx0 + (bw - 90) / 2, bx1 - 90)):
        parts.append({"id": f"box_beam{i + 1}", "name": "Office box: floor beam", "group": "Office box: floor",
                      "material": "gl_floor", "size": [90, bd, 225], "at": [round(x, 1), by0, fz],
                      "role": "Glulam beam on three ground screws; carries the floor joists."})
    jn = math.ceil((bd - 45) / 600) + 1
    parts.append({"id": "box_joist", "name": "Office box: floor joist", "group": "Office box: floor", "material": "c24_145",
                  "size": [bw, 45, 145], "at": [bx0, by0, fz + 225],
                  "repeat": {"count": jn, "axis": "y", "spacing": round((bd - 45) / (jn - 1), 1)},
                  "role": "Floor joist across the three beams, with 150 mm insulation between and a wind barrier underneath."})
    floor_top = fz + 225 + 145 + 22
    k = 0
    for xi, (fx, fw) in enumerate(((bx0, 1250), (bx0 + 1250, 1250), (bx0 + 2500, bw - 2500))):
        for yi, (fy, fl) in enumerate(((by0, 2500), (by0 + 2500, bd - 2500))):
            k += 1
            parts.append({"id": f"box_floor{k}", "name": "Office box: floor board", "group": "Office box: floor",
                          "material": "osb22", "size": [fw, fl, 22], "at": [fx, fy, fz + 225 + 145],
                          "role": "Floor deck, glued and screwed to the joists."})
    wall_h = 2480
    wz = floor_top
    walls, wall_ids = [], []
    w, ids = wall("box_n", "Office box: road wall", "x", (bx0, by1 - 145, wz), bw, wall_h)
    walls += w; wall_ids += ids
    w, ids = wall("box_s", "Office box: garden wall", "x", (bx0, by0, wz), bw, wall_h,
                  openings=[(900, 1300, 1300, 900, "window")])
    walls += w; wall_ids += ids
    w, ids = wall("box_w", "Office box: carport-side wall", "y", (bx0, by0 + 145, wz), bd - 290, wall_h,
                  openings=[(150, 900, 2100, 0, "office door"), (2050, 1000, 2100, 0, "bike-room door")])
    walls += w; wall_ids += ids
    w, ids = wall("box_e", "Office box: east wall (EI60)", "y", (bx1 - 145, by0 + 145, wz), bd - 290, wall_h)
    walls += w; wall_ids += ids
    w, ids = wall("box_p", "Office box: partition", "x", (bx0 + 145, by1 - 145 - 1350, wz), bw - 290, wall_h, stud=95,
                  openings=[])
    for q in w:
        if q.get("material") == "c24_145":
            q["material"] = "c24_95"
    walls += w; wall_ids += ids
    parts += walls
    cj_n = math.ceil((bd - 45) / 600) + 1
    parts.append({"id": "box_ceiling", "name": "Office box: ceiling joist", "group": "Office box: roof",
                  "material": "c24_145", "size": [bw, 45, 145], "at": [bx0, by0, wz + wall_h],
                  "repeat": {"count": cj_n, "axis": "y", "spacing": round((bd - 45) / (cj_n - 1), 1)},
                  "role": "Ceiling joist on the top plates, with 150 mm insulation. The big carport roof keeps the rain off, so the box only needs a sealed deck on top."})
    k = 0
    for fx, fw in ((bx0, 1250), (bx0 + 1250, 1250), (bx0 + 2500, bw - 2500)):
        for fy, fl in ((by0, 2500), (by0 + 2500, bd - 2500)):
            k += 1
            parts.append({"id": f"box_deck{k}", "name": "Office box: ceiling deck", "group": "Office box: roof",
                          "material": "osb12", "size": [fw, fl, 12], "at": [fx, fy, wz + wall_h + 145],
                          "role": "Deck over the ceiling joists, under the carport roof."})
    parts.append({"id": "cargo_bike", "name": "Cargo bike", "group": "Cars", "material": "car", "size": [2700, 650, 1100],
                  "at": [bx0 + 220, by1 - 145 - 330 - 650, floor_top],
                  "role": "Cargo bike in the bike room (road end), in and out through the side door."})
    parts.append({"id": "desk", "name": "Sit/stand desk", "group": "Office box: inside", "material": "car", "size": [1600, 800, 740],
                  "at": [bx0 + 800, by0 + 145 + 50, floor_top], "role": "Desk under the garden window."})
    parts += site_parts()
    joints = carport_joints(3)
    floor_ids = ["box_beam1", "box_beam2", "box_beam3", "box_joist"] + [f"box_floor{i}" for i in range(1, 7)]
    joints.append({"id": "box_floor", "type": "screwed", "parts": floor_ids, "fasteners": "Joist hangers or 2x 5x100 screws; floor glued and screwed"})
    joints.append({"id": "box_walls", "type": "nailed", "parts": wall_ids + [i for i in floor_ids if "floor" in i] + ["box_ceiling"] + [f"box_deck{i}" for i in range(1, 7)],
                   "fasteners": "2x 90 mm ring-shank nails per stud end; corners with 6x120 screws"})
    designs["carport-office"] = {
        "title": "Carport for 2 cars + office and bike room (9.95 x 6.0 m)",
        "description": ("Option 3 for House > Garage (Proposed), the 'design for the final state' idea. One mono-pitch roof over "
                        "two car bays at the house end and an insulated 3.2 x 3.9 m box at the east end: a bike and storage room "
                        "toward the road and an office of about 2.9 x 2.3 m with a window to the garden. The box has a timber floor on "
                        "ground screws, so there is no slab. The roofed area is 59.2 m2 (59.7 m2 over the roof sheet edge): just under the 60 m2 line, so it needs a "
                        "building notice and design project, not a permit (the detailed plan still applies). "
                        "The box's east wall is about 2-3 m from the boundary with 0127, so it must be EI60 (fire-rated board) with "
                        "no window, plus a written agreement with the neighbour. The roof takes about 24 panels (about 10 kWp)."),
        "units": "mm", "anchored": "Stands on ground screws, so there is no tip check.",
        "params": p, "materials": mats("gl_post", "gl_beam", "gl_floor", "c24_220", "c24_195", "c24_145", "c24_95", "batten", "osb22", "osb12",
                                       "roof_sheet", "solar", "site", "wall", "glass", "outside", "masonry", "boundary", "car", "zone", "opening"),
        "parts": parts, "joints": joints,
        "hardware": carport_hardware(posts=8, rafters=18, roof_m2=9.95 * 5.97, panels=24) + [
            {"item": "Ground screw 76x1000 for the box floor beams", "qty": 9},
            {"item": "Mineral wool 150 mm (walls, floor, ceiling), about 45 m2", "qty": 1},
            {"item": "Vapour barrier, wind barrier, interior boards, about 45 m2 each", "qty": 1},
            {"item": "Fire-rated board EI60 for the east wall, about 10 m2 (both faces per the fire design)", "qty": 1},
            {"item": "Exterior cladding (horizontal boards) with battens, about 40 m2", "qty": 1},
            {"item": "Triple-glazed window 1300x1300", "qty": 1},
            {"item": "Insulated exterior door 900x2100 (office) and 1000x2100 (bike room)", "qty": 2},
            {"item": "Air-to-air heat pump (heats and cools)", "qty": 1},
        ],
    }

    # ---------- 4. insulated two-car garage on a slab
    GW, GD, hf, pitch = 6600, 6200, 2900, 5
    gx0 = 150
    gy0 = PAD_N - GD  # garden (south) edge of the garage footprint; front/road at gy0 + GD
    drop = math.tan(math.radians(pitch))
    t = 45
    gparams = {
        "GW": {"value": GW, "label": "Garage width (outside of the frame)"},
        "GD": {"value": GD, "label": "Garage depth (outside of the frame)"},
        "pitch": {"value": pitch, "label": "Roof pitch (falls toward the garden / south)", "unit": "deg"},
        "h_front": {"value": hf, "label": "Front (road) wall height (top of the plates)"},
        "slab": {"value": 100, "label": "Slab thickness above the pad"},
        "footprint_m2": {"value": "GW * GD / 1000000", "label": "Footprint of the walls", "unit": "m2"},
        "roof_area_m2": {"value": "(GW + 400) * (GD + 600) / 1000000", "label": "Roofed area with eaves", "unit": "m2"},
    }
    parts = []
    parts.append({"id": "slab", "name": "Insulated slab", "group": "Slab", "material": "slab",
                  "size": [GW + 200, GD + 200, 100], "at": [gx0 - 100, gy0 - 100, 0],
                  "role": "Frost-protected insulated slab (hire this). Floor falls to the door, with a channel drain outside it; no floor drain inside."})
    z0 = 100
    walls, wall_ids = [], []
    # front (road / north): two 2500 doors with a pier between
    w, ids = wall("g_front", "Garage: front wall", "x", (gx0, gy0 + GD - 145, z0), GW, hf,
                  openings=[(300, 2500, 2125, 0, "sectional door 1"), (3800, 2500, 2125, 0, "sectional door 2")])
    walls += w; wall_ids += ids
    hb = hf - (GD - 145) * drop
    w, ids = wall("g_back", "Garage: garden wall", "x", (gx0, gy0, z0), GW, round(hb, 1),
                  openings=[(2700, 1200, 1000, 1100, "window")])
    walls += w; wall_ids += ids
    # Side walls run from garden toward road; roof slopes down toward garden, so height rises with y
    w, ids = wall("g_west", "Garage: house-side wall", "y", (gx0, gy0 + 145, z0), GD - 290, hf,
                  sloped=(hb + 145 * drop, -drop))
    walls += w; wall_ids += ids
    w, ids = wall("g_east", "Garage: east wall", "y", (gx0 + GW - 145, gy0 + 145, z0), GD - 290, hf,
                  sloped=(hb + 145 * drop, -drop),
                  openings=[(GD - 290 - 3600 - 900, 900, 2100, 0, "side door")])
    walls += w; wall_ids += ids
    parts += walls
    # mid beam on a post between the bays
    ym = gy0 + GD / 2 - 70
    # Height under the rafter line: high at the road, falling toward the garden
    dist_from_front = (gy0 + GD) - (ym + 70)
    zm = z0 + hf - (dist_from_front - 72.5) * drop
    parts.append({"id": "g_midpost", "name": "Garage: middle post", "group": "Garage: roof", "material": "gl_post",
                  "size": [140, 140, round(zm - 225 - z0, 1)], "at": [gx0 + GW / 2 - 70, ym, z0],
                  "role": "Post between the two bays, under the middle beam. Halves the rafter span."})
    parts.append({"id": "g_midbeam", "name": "Garage: middle beam", "group": "Garage: roof", "material": "gl_beam",
                  "size": [GW - 290, 140, 225], "at": [gx0 + 145, ym, round(zm - 225, 1)],
                  "role": "Glulam beam across the garage at mid-depth, from side wall to side wall, with the post in the middle."})
    rn = math.ceil((GW + 400 - 45) / 600) + 1
    # Rafters rise toward the road (+pitch); sit on the garden eave and run north
    cosp = math.cos(math.radians(pitch))
    back_len = (GD / 2 + 300) / cosp
    front_len = (GD / 2 + 300) / cosp
    rstep = round((GW + 400 - 90) / (rn - 1), 1)
    raf_z_garden = z0 + hb + 300 * drop
    parts.append({"id": "g_rafter_b", "name": "Garage: rafter, garden half", "group": "Garage: roof", "material": "c24_195",
                  "size": [45, round(back_len, 1), 195],
                  "at": [gx0 - 200, gy0 - 300, round(raf_z_garden, 1)],
                  "rotate": {"axis": "x", "deg": pitch},
                  "repeat": {"count": rn, "axis": "x", "spacing": rstep},
                  "role": "Garden half of a rafter pair: from the 300 mm garden eave over the garden wall to the middle beam."})
    parts.append({"id": "g_rafter", "name": "Garage: rafter, road half", "group": "Garage: roof", "material": "c24_195",
                  "size": [45, round(front_len, 1), 195],
                  "at": [gx0 - 200 + 45, ym, round(raf_z_garden + (ym - (gy0 - 300)) * drop, 1)],
                  "rotate": {"axis": "x", "deg": pitch},
                  "repeat": {"count": rn, "axis": "x", "spacing": rstep},
                  "role": "Road half: lapped beside the garden half over the middle beam and bolted to it, then over the front wall to a 300 mm eave."})
    parts.append({"id": "g_roof", "name": "Garage: roof sheet", "group": "Garage: roof", "material": "roof_sheet",
                  "size": [GW + 400, round((GD + 600) / math.cos(math.radians(pitch)), 1), 25],
                  "at": [gx0 - 200, gy0 - 300, round(raf_z_garden + 195 / math.cos(math.radians(pitch)) + 50, 1)],
                  "rotate": {"axis": "x", "deg": pitch},
                  "role": "Profiled steel roof on counter-battens (ventilated). Falls toward the garden."})
    parts += car("multivan", *MULTIVAN, y_nose=PAD_N - 400, cx=gx0 + 300 + 1250)
    parts += car("alltrack", *ALLTRACK, y_nose=PAD_N - 400, cx=gx0 + 3800 + 1250)
    for q in parts:
        if q.get("group") == "Cars":
            q["at"][2] = 100
    parts += site_parts()
    designs["garage-2car"] = {
        "title": "Insulated garage for 2 cars (6.6 x 6.2 m)",
        "description": ("Option 4 for House > Garage (Proposed). A closed timber-frame garage at the house end on an insulated slab, "
                        "with two 2.5 m sectional doors toward the road, a side door to the east and a window to the garden. "
                        "Inside it is about 6.3 x 5.9 m, enough for the Multivan with room to walk around it. The mono-pitch roof "
                        "falls toward the garden on a middle beam and post between the bays. Footprint 41 m2 to the walls, 48 m2 including the eaves; either way it needs a building notice "
                        "and design project, and the detailed plan still applies. It is the most expensive option for the smallest "
                        "gain over a carport (page section 8). The slab runs about 1 m past the pad on the garden side at the east end."),
        "units": "mm", "anchored": "Bolted to the slab, so there is no tip check.",
        "params": gparams, "materials": mats("gl_post", "gl_beam", "c24_220", "c24_195", "c24_145", "roof_sheet", "site", "wall", "glass", "outside", "masonry", "boundary", "car", "zone", "opening", "slab"),
        "parts": parts,
        "joints": [
            {"id": "g_walls", "type": "nailed", "parts": wall_ids + ["g_rafter", "g_rafter_b", "g_midbeam", "g_midpost", "slab"],
             "fasteners": "Studs nailed through the plates; bottom plates anchored to the slab; rafter ties at each wall"},
            {"id": "g_roofing", "type": "screwed", "parts": ["g_rafter", "g_rafter_b", "g_roof"], "fasteners": "Counter-battens and battens screwed to the rafters"},
        ],
        "hardware": [
            {"item": "Insulated sectional door 2500x2125, with motor", "qty": 2},
            {"item": "Insulated side door 900x2100", "qty": 1},
            {"item": "Triple-glazed window 1200x1000", "qty": 1},
            {"item": "Insulated slab with edge insulation, about 46 m2 (hire)", "qty": 1},
            {"item": "Anchor bolts for the bottom plates", "qty": 24},
            {"item": "Rafter ties", "qty": rn * 6},
            {"item": "Mineral wool 145/195 mm, about 120 m2", "qty": 1},
            {"item": "OSB 12 mm wall sheathing and wind barrier, about 70 m2", "qty": 1},
            {"item": "Exterior cladding with battens, about 70 m2", "qty": 1},
            {"item": f"Profiled steel roof with counter-battens, about {(GW + 400) * (GD + 600) / 1e6:.0f} m2", "qty": 1},
            {"item": "Channel drain outside the doors, to a soakaway", "qty": 1},
        ],
    }

    for name, d in designs.items():
        (OUT / f"{name}.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
        print("wrote", name, len(d["parts"]), "part specs")


main()
