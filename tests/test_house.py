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
