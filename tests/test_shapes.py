"""Round and profiled shapes, and reference vehicles from the catalog."""
import json
import math
import shutil
from pathlib import Path

import pytest

from woodpecker import catalog, cutlist, geometry as g, render, store
from woodpecker.model import DesignError

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def home(tmp_path, monkeypatch):
    shutil.copytree(REPO / "designs", tmp_path / "designs")
    shutil.copytree(REPO / "catalog", tmp_path / "catalog")
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "DESIGNS", tmp_path / "designs")
    monkeypatch.setattr(store, "STATE", tmp_path / ".woodpecker")
    return tmp_path


def blank(home, parts, materials=None, name="s"):
    store.create(name, "Shapes")
    raw = store.read_raw(name)
    raw["materials"].update(materials or {})
    raw["parts"] = parts
    (home / f"designs/{name}.json").write_text(json.dumps(raw))
    return store.load(name)


def test_segments_keep_the_error_small():
    for r in (10, 20, 100, 345, 1000):
        n = g.segments_for(r)
        assert n % 4 == 0 and 12 <= n <= 48
        if n < 48:
            assert r * (1 - math.cos(math.pi / n)) <= 0.5


def test_cylinder_dowel_exact_volume_and_cut_list(home):
    d = blank(home, [{"id": "leg", "name": "Leg", "material": "dowel", "shape": "cylinder", "axis": "z",
                      "size": [45, 45, 720], "at": [0, 0, 0], "role": "leg"}],
              {"dowel": {"name": "Round pine 45", "kind": "lumber", "section": [45, 45], "stock_length": 2400,
                         "density": 500}})
    leg = d.part("leg")
    assert leg.volume_mm3 == pytest.approx(math.pi * 22.5 ** 2 * 720)
    assert leg.to_dict()["dia"] == 45 and leg.to_dict()["length"] == 720
    assert "smooth" in leg.to_dict()["mesh"]
    row = cutlist.cut_list(d)["rows"][0]
    assert row["shape"] == "round" and row["length"] == 720
    assert d.issues == []


def test_sphere_and_overlap_with_a_box(home):
    d = blank(home, [
        {"id": "ball", "name": "Ball", "material": "ply18", "shape": "sphere", "size": [100, 100, 100], "at": [0, 0, 0], "role": "x"},
        {"id": "board", "name": "Board", "material": "ply18", "size": [200, 200, 18], "at": [-50, -50, 90], "role": "x"},
    ])
    assert d.part("ball").volume_mm3 == pytest.approx(math.pi / 6 * 100 ** 3)
    assert any("overlap" in i["message"] for i in d.issues)


def test_prism_profile_must_be_convex(home):
    bad = blank(home, [{"id": "p", "name": "P", "material": "ply18", "shape": "prism", "axis": "x", "length": 18,
                        "profile": [[0, 0], [100, 0], [50, 20], [100, 100], [0, 100]], "role": "x"}])
    assert any("convex" in i["message"] and i["level"] == "error" for i in bad.issues)
    with pytest.raises(DesignError, match="convex"):
        store.write("s", store.read_raw("s"))  # and an edit that makes one is refused
    d = blank(home, [{"id": "p", "name": "Bracket", "material": "ply18", "shape": "prism", "axis": "x", "length": 18,
                      "profile": [[0, 0], [300, 0], [300, 60], [60, 300], [0, 300]], "at": [0, 0, 0], "role": "x"}],
              name="s2")
    p = d.part("p")
    assert p.size == (18, 300, 300)
    assert p.volume_mm3 == pytest.approx((300 * 300 - 240 * 240 / 2) * 18)


def test_vehicles_are_reference_parts(home):
    d = blank(home, [
        {"id": "van", "name": "Van", "component": "vw-multivan-t61-2021", "at": [0, 0, 0]},
        {"id": "golf", "name": "Golf", "component": "vw-golf-alltrack-2017", "at": [2500, 0, 0]},
    ])
    van = [p for p in d.parts if p.instance == "van"]
    assert van and all(p.kind == "reference" for p in van)
    lo = [min(p.at[k] for p in van) for k in range(3)]
    hi = [max(p.max[k] for p in van) for k in range(3)]
    # published: 4904 long, 1970 high, 2297 over the mirrors
    assert hi[1] - lo[1] == pytest.approx(4904, abs=1)
    assert hi[2] - lo[2] == pytest.approx(1970, abs=1)
    assert hi[0] - lo[0] == pytest.approx(2297, abs=20)
    assert any(p.shape == "cylinder" and p.color == "#1d1f21" for p in van)  # tyres
    c = cutlist.cut_list(d)
    assert c["bought"] == [] and c["rows"] == [] and d.issues == []
    assert render.render(d, "side")[:4] == b"\x89PNG"


def test_vehicle_catalog_items_cite_sources():
    for i in ("vw-multivan-t61-2021", "vw-golf-alltrack-2017"):
        it = catalog.get(i)
        assert it["reference"] and it["url"].startswith("https://") and it["assumed"]
        assert len(catalog.generate(it, {})) == 15
