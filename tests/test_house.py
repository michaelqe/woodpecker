"""The house model (scripts/house_model.py) stays in step with designs/house.json and the plan areas."""
import importlib.util
import json
from pathlib import Path

from woodpecker import model

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("house_model", REPO / "scripts" / "house_model.py")
house = importlib.util.module_from_spec(spec)
spec.loader.exec_module(house)


def test_design_file_is_generated_from_the_script():
    assert json.loads((REPO / "designs" / "house.json").read_text()) == json.loads(json.dumps(house.build()))


def test_traced_rooms_match_the_plan_areas():
    off = [line for line in house.area_report() if not line.startswith("ok")]
    assert not off, off


def test_house_loads_clean_and_pages_go_to_digital_twin():
    d = model.load(REPO / "designs" / "house.json")
    assert not d.issues
    assert d.magpie_project == 38
    assert all(p.kind == "reference" for p in d.parts)


def test_shell_is_exterior_only_and_fits_the_pad():
    shell = house.shell_parts()
    assert shell
    assert all("Interior wall" not in (p.get("role") or "") for p in shell)
    assert any(p["id"].startswith("g-e") for p in shell)  # long wall with the front door
    assert any(p["id"].startswith("g-s") for p in shell)  # short wall with the back door
    assert any(p["id"].startswith("porch-e") for p in shell)

    pad = house.shell_on_pad()
    assert all(p["id"].startswith("house-") for p in pad)
    # North-up site frame (Maps): +x east into the pad, +y north toward the road.
    # Short plan-south / back-door wall is the pad's west edge at x = 0.
    # Long plan-east / front-door wall faces the road at high y (not y = 0).
    short = [p for p in pad if p["id"].startswith("house-g-s")]
    assert short
    assert max(p["at"][0] + p["size"][0] for p in short) == 0
    long_north = [p for p in pad if p["id"].startswith("house-g-e")]
    assert long_north
    assert min(p["at"][1] for p in long_north) == house.NORTH_FACE - house.SOUTH_WEST - 284
    assert max(p["at"][1] + p["size"][1] for p in long_north) == house.NORTH_FACE - house.SOUTH_WEST
    # East face spans the short wall (~5.7 m), not the long facade
    assert max(p["at"][1] + p["size"][1] for p in short) < 7000
    # Living-room bay (plan west) sits south of y = 0, not north of the road wall
    bay = [p for p in pad if p["id"].startswith("house-g-bw")]
    assert bay and max(p["at"][1] + p["size"][1] for p in bay) <= 0


def test_garage_designs_embed_the_house_shell():
    for name in ("carport-2car", "carport-1car-20m2", "carport-office", "garage-2car"):
        raw = json.loads((REPO / "designs" / f"{name}.json").read_text())
        ids = {p["id"] for p in raw["parts"]}
        assert "house" not in ids  # old flat stub
        assert any(i.startswith("house-g-e") for i in ids)
        assert "wall" in raw["materials"]
        d = model.load(REPO / "designs" / f"{name}.json")
        assert not d.issues, (name, d.issues)


def test_garage_site_is_north_up_like_the_map():
    """Top view must match Google Maps: road/high y at the top, house west of the pad, cars nose north."""
    for name in ("carport-2car", "carport-1car-20m2", "carport-office", "garage-2car"):
        raw = json.loads((REPO / "designs" / f"{name}.json").read_text())
        pad = next(p for p in raw["parts"] if p["id"] == "pad")
        # Rectangular pad body sits below the road edge (PAD_N = 6100), not growing from y = 0 upward as garden
        assert pad["at"][1] > 0, name
        assert pad["at"][1] + pad["size"][1] == 6100, name
        long_n = [p for p in raw["parts"] if p["id"].startswith("house-g-e")]
        assert min(p["at"][1] for p in long_n) > 5000, name  # front-door wall faces the road
        for p in raw["parts"]:
            if p.get("group") == "Cars" and p.get("component"):
                assert p.get("rotate") == {"axis": "z", "deg": 180}, (name, p["id"])
                assert p["at"][1] > 5000, (name, p["id"])  # nose near the road
        d = model.load(REPO / "designs" / f"{name}.json")
        # House mass is west of the pad (x < 0); garage/carport structure is on the pad (x > 0)
        house_x = [pt.max[0] for pt in d.parts if pt.id.startswith("house-g-s")]
        assert house_x and max(house_x) <= 0, name
        frame = [pt for pt in d.parts if pt.id.startswith(("post_front", "beam_front", "g_front", "slab"))]
        assert frame and min(pt.at[0] for pt in frame) >= 0, name


# ---------------------------------------------------------------- electrical fixtures (HOUSE-2)
el = house.electrical


def test_fixture_ids_unique_and_circuits_known():
    ids = [fx[0] for fx in el.FIXTURES]
    assert len(ids) == len(set(ids))
    for fid, _, _, kind, *_rest in el.FIXTURES:
        circuit = _rest[3]
        if kind in ("data", "phone", "antenna"):
            assert circuit is None, fid
        else:
            assert circuit is None or circuit in el.CIRCUITS, fid


def test_every_fixture_sits_in_its_room_or_outside():
    rooms = {r[0]: r[5] for r in house.ROOMS}
    rooms["stairwell"] = [[5773, 4034, 8166, 6234]]
    indoor = {f: [rc for r in house.ROOMS if r[1] == f and r[6] != "outside" for rc in r[5]] for f in house.LEVEL}

    def inside(rects, x, y):
        return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in rects)

    for fx, x0, y0, z0, x1, y1, z1 in el.placed(house.WALLS, house.BLOCKS, house.ROOMS, house.LEVEL):
        fid, f, room = fx[:3]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if room == "OUT":
            assert not inside(indoor[f], cx, cy), fid
        else:
            assert inside(rooms[room], cx, cy), (fid, room, cx, cy)
        lv = house.LEVEL[f]
        assert lv["z"] <= z0 < z1 <= lv["z"] + el.CEILING, fid


def test_numbered_sockets_match_the_drawings():
    labels = [fx[9] for fx in el.FIXTURES]
    expected = ([f"9P{i}" for i in range(1, 7)] + [f"11P{i}" for i in range(1, 11)]
                + [f"12P{i}" for i in range(1, 11)] + [f"13P{i}" for i in range(1, 13)]
                + [f"27P{i}" for i in range(1, 4)] + ["5P", "6P", "7P", "8P"])
    for lab in expected:
        assert labels.count(lab) == 1, lab


def test_fixtures_are_in_the_design():
    raw = json.loads((REPO / "designs" / "house.json").read_text())
    parts = [p for p in raw["parts"] if p["id"].startswith("el-")]
    assert len(parts) == len(el.FIXTURES)
    assert all(p["material"] in el.MATERIALS for p in parts)
    assert all("2006" in p["role"] for p in parts)


# ---------------------------------------------------------------- full house beside the carport
_hc_spec = importlib.util.spec_from_file_location("house_carport", REPO / "scripts" / "house_carport.py")
hc = importlib.util.module_from_spec(_hc_spec)
_hc_spec.loader.exec_module(hc)


def _overlaps_xy(a, b):
    return all(a.at[i] < b.max[i] and b.at[i] < a.max[i] for i in range(2))


def test_house_carport_designs_are_generated_and_load_clean():
    for name, side in (("house-carport", False), ("house-carport-side-entrance", True)):
        assert json.loads((REPO / "designs" / f"{name}.json").read_text()) == json.loads(json.dumps(hc.design(side))), name
        d = model.load(REPO / "designs" / f"{name}.json")
        assert not d.issues, (name, d.issues)
        ids = {p["id"] for p in json.loads((REPO / "designs" / f"{name}.json").read_text())["parts"]}
        # whole house (interior walls, both floors, stair), not just the shell
        assert {"house-g-i3-1", "house-u-i1-1", "house-tread-1", "post_front"} <= ids, name
        assert not any(i.startswith("house-el-") for i in ids)


def test_side_entrance_route_is_clear():
    walls, rooms, _ = hc.side_entrance_layout()
    w = {x[0]: x for x in walls}
    # The sink-room door that opened out of the WC is gone; the corridor opens into the hall.
    assert not any("Sink room" in o["name"] for o in w["g-i3"][4])
    gap = next(o for o in w["g-i3"][4] if o["t"] == "o")
    assert hc.CORR_X0 <= gap["a"] and gap["b"] <= hc.CORR_X1
    assert gap["b"] - gap["a"] >= 900
    # Corridor at least 1 m clear; WC west wall sits east of it.
    assert hc.CORR_X1 - hc.CORR_X0 >= 1000 and w["g-i6"][3][0] >= hc.CORR_X1
    # The back door (x 6483-7383 on the south wall) opens into the back hall, not the plant cupboard.
    back = next(o for o in w["g-s"][4] if o["name"] == "Back door")
    assert back["b"] < hc.CUP_X0
    a = hc.area_report()
    assert a["wc0"] >= 1.5 and a["tagaesik"] > 5


def test_cars_clear_the_back_step_only_in_the_concept():
    for name, blocked in (("house-carport", True), ("house-carport-side-entrance", False)):
        d = model.load(REPO / "designs" / f"{name}.json")
        step = next(p for p in d.parts if p.id == "house-porch-s-floor")
        hit = any(_overlaps_xy(p, step) for p in d.parts if p.id.startswith(("multivan", "alltrack", "cargo")))
        assert hit is blocked, name
