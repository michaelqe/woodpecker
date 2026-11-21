"""Rotation, end cuts, repeat/mirror, joint cuts, catalog components, layouts, edits."""
import json
import math
import shutil
from pathlib import Path

import pytest

from woodpecker import catalog, cutlist, geometry as g, model, store
from woodpecker.model import DesignError

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def home(tmp_path, monkeypatch):
    shutil.copytree(REPO / "designs", tmp_path / "designs")
    shutil.copytree(REPO / "catalog", tmp_path / "catalog")
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "DESIGNS", tmp_path / "designs")
    monkeypatch.setattr(store, "STATE", tmp_path / ".woodpecker")
    return tmp_path


def base(parts, joints=(), params=None):
    return {
        "params": params or {},
        "materials": {
            "ply": {"kind": "sheet", "thickness": 18, "stock": [2500, 1250], "density": 600},
            "pine": {"kind": "lumber", "section": [45, 95], "stock_length": 3000, "density": 450},
        },
        "parts": parts, "joints": list(joints),
    }


# ---------------------------------------------------------------- geometry

def test_box_volume_and_centroid():
    s = g.box_solid((100, 50, 20))
    vol, c = s.volume_and_centroid()
    assert vol == pytest.approx(100 * 50 * 20)
    assert c == pytest.approx((50, 25, 10))


def test_gusset_volume_is_half():
    vol, _ = g.gusset_solid((18, 250, 250), "back").volume_and_centroid()
    assert vol == pytest.approx(18 * 250 * 250 / 2)


def test_penetration():
    a = g.box_solid((100, 100, 100))
    b = g.box_solid((100, 100, 100)).transformed(g.translate(90, 0, 0))
    c = g.box_solid((100, 100, 100)).transformed(g.translate(100, 0, 0))
    assert g.penetration(a, b) == pytest.approx(10)
    assert g.penetration(a, c) <= 0


def test_mirror_keeps_faces_outward():
    s = g.box_solid((10, 20, 30)).transformed(g.mirror("x", 0))
    vol, _ = s.volume_and_centroid()
    assert vol == pytest.approx(6000)


# ---------------------------------------------------------------- model features

def test_repeat_and_mirror_ids_and_positions():
    d = model.resolve(base([{
        "id": "stud", "material": "pine", "size": [95, 45, 1000], "at": [0, 0, 0],
        "repeat": {"count": 3, "axis": "y", "spacing": 600}, "mirror": {"axis": "x", "about": 1000},
    }]))
    ids = [p.id for p in d.parts]
    assert ids == ["stud[0]", "stud[1]", "stud[2]", "stud[0]~m", "stud[1]~m", "stud[2]~m"]
    assert d.part("stud[2]").at == (0, 1200, 0)
    assert d.part("stud[1]~m").at[0] == pytest.approx(2000 - 95)
    assert d.issues == []


def test_rotated_rafter_with_plumb_cuts_is_vertical_at_both_ends():
    p = 30
    d = model.resolve(base([{
        "id": "rafter", "material": "pine", "size": [1500, 45, 95],
        "rotate": {"axis": "y", "deg": -p}, "ends": {"start": p, "end": -p},
    }]))
    r = d.part("rafter")
    assert not r.aligned
    vs = r.solid.verts
    # local corners 0/4 are the start bottom/top, 1/5 the end bottom/top
    assert vs[0][0] == pytest.approx(vs[4][0], abs=1e-6)
    assert vs[1][0] == pytest.approx(vs[5][0], abs=1e-6)
    assert vs[1][2] > vs[0][2]  # it rises along +x
    assert r.ends == (30, -30)


def test_end_cuts_that_meet_are_refused():
    d = model.resolve(base([{"id": "x", "material": "pine", "size": [100, 45, 95], "ends": {"start": 60, "end": 60}}]))
    assert any(i["level"] == "error" for i in d.issues)


def test_joint_cut_into_makes_a_hole_and_allows_overlap():
    d = model.resolve(base([
        {"id": "top", "material": "ply", "size": [500, 500, 18], "at": [0, 0, 100]},
        {"id": "post", "material": "pine", "size": [95, 45, 300], "at": [200, 200, 0]},
    ], joints=[{"id": "m", "type": "through-mortise", "parts": ["post", "top"], "cut_into": ["top"]}]))
    top = d.part("top")
    assert top.subtract == ["post"]
    assert "95 x 45 x 18" in top.cut_notes[0]
    assert d.issues == []


def test_overlap_without_joint_still_flagged_for_rotated_parts():
    d = model.resolve(base([
        {"id": "a", "material": "pine", "size": [1000, 45, 95], "rotate": {"axis": "y", "deg": -20}},
        {"id": "b", "material": "pine", "size": [95, 45, 1000], "at": [400, 0, 0]},
    ]))
    assert any("overlap" in i["message"] for i in d.issues)


def test_explicit_cutouts():
    d = model.resolve(base([{"id": "panel", "material": "ply", "size": [600, 400, 18],
                             "cutouts": [{"label": "cable hole", "at": [280, 180, 0], "size": [40, 40, 18]}]}]))
    p = d.part("panel")
    assert len(p.cutouts) == 1 and p.cut_notes == ["cable hole: 40 x 40 x 18"]


# ---------------------------------------------------------------- catalog

def test_catalog_generators_fill_the_published_size(home):
    for item in catalog.all_items().values():
        panels = catalog.generate(item, {})
        lo = [min(p["at"][k] for p in panels) for k in range(3)]
        hi = [max(p["at"][k] + p["size"][k] for p in panels) for k in range(3)]
        assert lo == [0, 0, 0], item["id"]
        assert hi == pytest.approx(item["size"]), item["id"]


def test_catalog_panels_do_not_overlap(home):
    for item in catalog.all_items().values():
        solids = [g.box_solid(tuple(p["size"])).transformed(g.translate(*p["at"])) for p in catalog.generate(item, {})]
        for i, a in enumerate(solids):
            for b in solids[i + 1:]:
                assert g.penetration(a, b) <= 0.01, item["id"]


def test_catalog_entries_cite_their_source(home):
    for item in catalog.all_items().values():
        assert item["url"].startswith("https://www.ikea.com/")
        assert item["retrieved"] and item["assumed"]


def test_component_in_design(home):
    d = store.load("tv-cart-kallax")
    panels = d.expand("kallax")
    assert panels and all(p.kind == "component" for p in panels)
    assert d.issues == []
    c = cutlist.cut_list(d)
    assert c["bought"][0]["qty"] == 1 and c["bought"][0]["article"] == "903.015.55"
    assert c["cost"]["lines"][0]["total_eur"] == 27.99


def test_catalog_add_validates(home):
    with pytest.raises(DesignError):
        catalog.add({"id": "x"})
    catalog.add({"id": "test-block", "brand": "Test", "name": "Block", "size": [100, 100, 100],
                 "geometry": {"generator": "block"}, "url": "https://example.com", "retrieved": "2026-11-21"})
    assert catalog.get("test-block")["name"] == "Block"
    assert catalog.search("block")[0]["id"] == "test-block"


# ---------------------------------------------------------------- cut list

def test_guillotine_layout_has_no_overlaps_and_fits():
    parts = [{"id": f"p{i}", "material": "ply", "size": [600, 400, 18], "at": [i * 700, 0, 0]} for i in range(13)]
    d = model.resolve(base(parts))
    st = cutlist.cut_list(d)["stock"][0]
    assert st["count"] == 2
    for sheet in st["layouts"]:
        rs = sheet["rects"]
        for r in rs:
            assert r["x"] + r["w"] <= 2500 + 1e-6 and r["y"] + r["h"] <= 1250 + 1e-6
        for i, a in enumerate(rs):
            for b in rs[i + 1:]:
                assert (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or
                        a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def test_triangles_pair_up_on_the_sheet():
    d = store_free_triangles()
    st = cutlist.cut_list(d)["stock"][0]
    assert sum(len(s["rects"]) for s in st["layouts"]) == 1


def store_free_triangles():
    return model.resolve(base([
        {"id": "g1", "material": "ply", "shape": "gusset", "leg": "back", "size": [18, 200, 200], "at": [0, 0, 0]},
        {"id": "g2", "material": "ply", "shape": "gusset", "leg": "back", "size": [18, 200, 200], "at": [100, 0, 0]},
    ]))


def test_greenhouse_is_clean_and_buys_whole_boards(home):
    d = store.load("greenhouse")
    assert d.issues == []
    c = cutlist.cut_list(d)
    rafters = next(r for r in c["rows"] if r["label"] == "Rafter")
    assert rafters["qty"] == 12 and rafters["ends"] == [30, -30]
    assert "birdsmouth" in rafters["cut_notes"][0]
    assert all(not s["warnings"] for s in c["stock"])


def test_cost_uses_only_given_prices(home):
    store.set_material("tv-cart", "ply18", {**store.read_raw("tv-cart")["materials"]["ply18"], "price_eur": 80})
    c = cutlist.cut_list(store.load("tv-cart"))["cost"]
    assert c["total_eur"] == 80
    assert any("Spruce" in m for m in c["missing"])


# ---------------------------------------------------------------- edits

@pytest.mark.parametrize("expr,delta,out", [
    (100, 40, 140), ("post_x", 40, "post_x + 40"), ("post_x + 40", -40, "post_x"),
    ("post_x - 10", 25, "post_x + 15"), ("(a + b) / 2", 10, "(a + b) / 2 + 10"), ("x", 0, "x"),
])
def test_offset_expr(expr, delta, out):
    assert store.offset_expr(expr, delta) == out


def test_move_and_resize_keep_expressions(home):
    store.move_part("tv-cart", "bracket", [0, 0, 50])
    raw = store.read_raw("tv-cart")
    assert next(p for p in raw["parts"] if p["id"] == "bracket")["at"][2] == "screen_center - 75"
    store.resize_part("tv-cart", "base_top", [0, 20, 0])
    assert next(p for p in raw["parts"] if p["id"] == "base_top")  # unchanged copy
    raw = store.read_raw("tv-cart")
    assert next(p for p in raw["parts"] if p["id"] == "base_top")["size"][1] == "base_d + 20"


def test_param_units_reach_the_viewer(home):
    d = store.load("tv-cart").to_dict(geometry=False)
    units = {p["name"]: p["unit"] for p in d["params"]}
    assert units["tv_mass"] == "kg" and units["base_w"] == "mm"


def test_viewer_payload_has_meshes(home):
    from woodpecker.server import design_payload
    p = design_payload("greenhouse")
    rafter = next(x for x in p["design"]["parts"] if x["id"] == "rafter[0]")
    assert len(rafter["mesh"]["verts"]) == 8 and rafter["subtract"]
    json.dumps(p)  # serialisable
