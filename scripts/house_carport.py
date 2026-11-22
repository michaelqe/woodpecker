"""Generate the full house beside the two-car carport (run: python3 scripts/house_carport.py designs/).

Two designs, same site frame as scripts/garage_options.py (north up, origin = pad SW = house SE,
+x east into the pad, +y north toward the road):

- house-carport: the whole traced house (both floors, interior walls, floors, stair, built-ins;
  no electrical) next to option 1, the 6.6 x 6.0 m carport with the solar roof.
- house-carport-side-entrance: the same, with the ground floor at the back door reworked so the
  side (back) door on the pad is a real entrance instead of a way through the plant room, the
  sink room and the WC.

The side-entrance layout is a concept for the designer, in the drawing coordinates of
scripts/house_model.py (x along grid 1 -> 4, y down the drawing; the back door wall is y 14166).
Re-run this script after changing house_model.py or garage_options.py.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


house = _load("house_model")
garage = _load("garage_options")
G = house.GROUND

# ---------------------------------------------------------------- side-entrance concept (ground floor)
# Today: back door -> plant room (boiler, UFH manifold, main board) -> sink room (door drawn in the
# WC) -> WC -> hall. The concept, with the boiler, manifold and main board left where they are:
#   1. The plant room becomes a back hall (mudroom). The boiler and manifold on its east wall get a
#      full-height cupboard with doors; the main board stays on the west wall, in the open.
#   2. A 1.0 m corridor runs north from the back hall along the west side of the old sink room,
#      straight into the front hall beside the WC.
#   3. The rest of the sink room stays a utility room (sink, storage, the window), opened from the
#      back hall through the old plant-room door.
#   4. The WC moves its west wall 473 mm east (2.1 -> 1.6 m2) and loses the door to the sink room.
CORR_X0, CORR_X1 = 5626, 6626          # corridor clear width 1000
PART = 92                               # stud partition, as drawn elsewhere
CUP_X0 = 7520                           # plant cupboard front (back door ends at 7383)

CHANGED_WALLS = {
    "g-i3": ("g-i3", G, "Hall / office wall", [3034, 9866, 8166, 10060], [
        dict(t="d", a=4674, b=5474, name="Office door"),
        dict(t="o", a=5676, b=6576, name="Opening from the back corridor to the hall",
             note="CONCEPT: replaces the sink-room door that opened out of the WC")]),
    "g-i5": ("g-i5", G, "Utility room / back hall wall", [CORR_X1, 12052, 8166, 12144], [
        dict(t="d", a=6800, b=7400, name="Utility room door", note="CONCEPT: about where the plant-room door is today")]),
    "g-i6": ("g-i6", G, "WC west wall", [CORR_X1, 8766, CORR_X1 + PART, 9866], [
        dict(t="d", a=9100, b=9800, name="WC door", note="CONCEPT: wall moved 473 mm east")]),
}
NEW_WALLS = [
    ("g-c1", G, "Back corridor / utility room wall", [CORR_X1, 10060, CORR_X1 + PART, 12052], []),
    ("g-c2", G, "Plant cupboard front", [CUP_X0, 12144, CUP_X0 + PART, 14166], [
        dict(t="d", a=12250, b=14060, name="Plant cupboard doors",
             note="CONCEPT: bi-fold or two pairs of doors in front of the boiler and the manifold")]),
]
CHANGED_ROOMS = {
    "esik": ("esik", G, "Esik", "Hall", None,
             [[4279, 4034, 5773, 9866], [5773, 6400, 8166, 7874], [5773, 7874, 6153, 9866], [6153, 8766, CORR_X1, 9866]],
             "floor", "CONCEPT: gains the strip where the WC used to be; the back corridor joins it here. Was 12.8 m2."),
    "wc0": ("wc0", G, "WC", "WC", None, [[CORR_X1 + PART, 8766, 8166, 9866]], "tile",
            "CONCEPT: 1.45 x 1.10 m (was 2.1 m2 on the plan), about the size of the upstairs WC. The toilet stays on the east side."),
    "pesuruum": ("pesuruum", G, "Abiruum", "Utility room", None, [[CORR_X1 + PART, 10060, 8166, 12052]], "tile",
                 "CONCEPT: the east 1.45 m of the old sink room: sink, storage, the window. Room for a dryer or a dog wash."),
    "tehnoruum": ("tagaesik", G, "Tagaesik", "Back hall", None,
                  [[CORR_X0, 10060, CORR_X1, 12144], [CORR_X0, 12144, CUP_X0, 14166]], "tile",
                  "CONCEPT: the side entrance from the carport. Old plant room plus a 1.0 m corridor through the old sink room."),
}
NEW_ROOMS = [
    ("plant", G, "Tehnokapp", "Plant cupboard", None, [[CUP_X0 + PART, 12144, 8166, 14166]], "tile",
     "CONCEPT: 0.55 m deep, full height, round the gas boiler and the underfloor-heating manifold where they hang now. "
     "Check the boiler's depth, service clearance and air supply with the gas fitter."),
]
NEW_BLOCKS = [
    ("bench", G, "Bench with shoe shelf", [CORR_X0, 12900, CORR_X0 + 400, 14100], [0, 450], "fixture",
     "CONCEPT: boot bench along the back hall's west wall, shoes underneath."),
    ("coats", G, "Coat hooks", [CORR_X0, 12900, CORR_X0 + 60, 14100], [1650, 1750], "fixture",
     "CONCEPT: coat rail over the bench. The main board (PJK) stays on this wall, north of the bench, in the open."),
    ("utility-counter", G, "Sink and storage", [7566, 10150, 8166, 12000], [0, 900], "fixture",
     "CONCEPT: the sink and cupboards along the east wall, under the window."),
]


def side_entrance_layout():
    walls = []
    for w in house.WALLS:
        walls.append(CHANGED_WALLS.get(w[0], w))
    walls += NEW_WALLS
    rooms = []
    for r in house.ROOMS:
        rooms.append(CHANGED_ROOMS.get(r[0], r))
    rooms += NEW_ROOMS
    blocks = list(house.BLOCKS) + NEW_BLOCKS
    return walls, rooms, blocks


def house_on_pad(walls=None, rooms=None, blocks=None):
    parts = house.interior_parts(walls, rooms, blocks)
    for p in parts:
        p["size"] = [round(v, 1) for v in p["size"]]
        p["at"] = [round(v, 1) for v in p["at"]]
    out = house.to_site(parts, group=None)
    for q in out:
        q["group"] = "House: " + q["group"].lower() if q["group"] != "Site" else "House: outside"
    return out


# ---------------------------------------------------------------- the carport and cars
# Back step in site coordinates: x 0..1500 (it sticks 1.5 m into the pad), y 3283..5083.
STEP_X1 = 1500


def carport_site(side_entrance):
    p = garage.carport_params(W=6600, D=5950, bays=2, h_front=2900)
    parts = garage.carport_parts(batten_pieces=2, solar_rows=3, solar_cols=5)
    if side_entrance:
        # Cars moved east so the back step and a walking lane stay clear; the bike by the door.
        mv_x0 = STEP_X1 + 650
        at_x0 = mv_x0 + garage.MULTIVAN[2] + 700
        parts += garage.car("multivan", *garage.MULTIVAN, y_nose=garage.PAD_N - 450, cx=mv_x0 + garage.MULTIVAN[2] / 2)
        parts += garage.car("alltrack", *garage.ALLTRACK, y_nose=garage.PAD_N - 450, cx=at_x0 + garage.ALLTRACK[2] / 2)
        parts.append({"id": "cargo_bike", "name": "Cargo bike", "group": "Cars", "material": "car", "size": [650, 2700, 1100],
                      "at": [200, 350, 0],
                      "role": "Cargo bike along the house wall, south of the back step: in and out next to the side door."})
        parts.append({"id": "walk_lane", "name": "Walking lane to the side door", "group": "Site", "material": "lane",
                      "size": [STEP_X1 + 650 - 150, 4800, 5], "at": [150, 850, 20],
                      "role": "Kept clear: from both cars' doors to the back step, all under the carport roof."})
    else:
        # As option 1 (carport-2car).
        parts += garage.car("multivan", *garage.MULTIVAN, y_nose=garage.PAD_N - 450, cx=150 + 250 + 140 + 1450 - 140)
        parts += garage.car("alltrack", *garage.ALLTRACK, y_nose=garage.PAD_N - 450, cx=150 + 250 + 1585 + 3110 - 70 - 140)
        parts.append({"id": "cargo_bike", "name": "Cargo bike", "group": "Cars", "material": "car", "size": [2700, 650, 1100],
                      "at": [3900, garage.PAD_N - 5320 - 650, 0],
                      "role": "Cargo bike, about 2.7 m long, behind the Alltrack (which is shorter than the Multivan)."})
    parts += [q for q in garage.site_parts() if not q["id"].startswith("house-")]
    return p, parts


def design(side_entrance):
    params, parts = carport_site(side_entrance)
    layout = side_entrance_layout() if side_entrance else (None, None, None)
    parts += house_on_pad(*layout)
    materials = garage.mats("gl_post", "gl_beam", "c24_220", "c24_95", "batten", "roof_sheet", "solar", "site",
                            "boundary", "car", "zone")
    materials.update(copy.deepcopy(house.MATERIALS))
    if side_entrance:
        materials["lane"] = {"name": "Kept-clear walking lane (reference)", "kind": "reference", "color": "#c9b458"}
        title = "House + carport, side door as the entrance (concept)"
        description = (
            "The whole house next to option 1 (the 6.6 x 6.0 m two-car carport with the solar roof), with the ground floor "
            "reworked so the side door on the pad is a real entrance. Today it opens into the plant room, and the way on "
            "is through the sink room and the WC. In the concept the plant room becomes a back hall with a boot bench, the "
            "gas boiler and the underfloor-heating manifold stay where they hang behind a 0.55 m cupboard, and the main board "
            "stays on the back hall's west wall. A 1.0 m corridor runs north through the west side of the old sink room "
            "into the front hall beside the WC. The rest of the sink room stays a 2.9 m2 utility room with the sink and the "
            "window, opened from the back hall. The WC moves its west wall 473 mm east and shrinks from 2.1 to 1.6 m2 "
            "(the upstairs WC is 1.7). Outside, the cars move east so the back step and a walking lane stay clear, and the "
            "cargo bike stands by the door: car to front hall is about 9 m, all under a roof. "
            "A concept for the designer: plumbing, the boiler's clearances and the WC layout need checking on site.")
    else:
        title = "House + carport for 2 cars (6.6 x 6.0 m)"
        description = (
            "The whole house as traced (both floors: walls, windows, doors, floors, the stair, fireplace and built-ins; "
            "electrical fixtures left out) next to option 1, the 6.6 x 6.0 m two-car carport with the solar roof, on the "
            "real pad. North up like the map: the back-door wall faces the pad, the front-door wall faces the road. "
            "Cars parked as in option 1, where the Multivan stands over the back step.")
    return {
        "title": title, "description": description, "units": "mm",
        "anchored": "A house and a carport on ground screws: nothing to tip over.",
        "params": params, "materials": materials, "parts": parts,
        "joints": garage.carport_joints(2),
        "hardware": garage.carport_hardware(posts=6, rafters=13, roof_m2=6.6 * 5.97, panels=15),
    }


def area_report():
    """Areas of the side-entrance rooms that differ from the plan, for the page and the test."""
    walls, rooms, _ = side_entrance_layout()
    return {r[0]: round(house.area(r[5]), 2) for r in rooms if r[0] in ("esik", "wc0", "pesuruum", "tagaesik", "plant")}


def main(out):
    for name, side in (("house-carport", False), ("house-carport-side-entrance", True)):
        d = design(side)
        (out / f"{name}.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
        print("wrote", name, len(d["parts"]), "part specs")
    for k, v in area_report().items():
        print(f"  {k:<10} {v:5.2f} m2")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
