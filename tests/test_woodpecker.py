import json
import shutil
from pathlib import Path

import pytest

from woodpecker import cutlist, model, store
from woodpecker.model import DesignError, evaluate, resolve_params

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def home(tmp_path, monkeypatch):
    (tmp_path / "designs").mkdir()
    shutil.copy(REPO / "designs" / "tv-cart.json", tmp_path / "designs" / "tv-cart.json")
    monkeypatch.setattr(store, "DESIGNS", tmp_path / "designs")
    monkeypatch.setattr(store, "STATE", tmp_path / ".woodpecker")
    return tmp_path


def test_expressions():
    assert evaluate("a * 2 + 1", {"a": 3}) == 7
    assert evaluate(18, {}) == 18
    assert evaluate("max(a, 10)", {"a": 3}) == 10
    for bad in ["__import__('os')", "a.b", "[1]", "unknown + 1", "1/0"]:
        with pytest.raises(DesignError):
            evaluate(bad, {"a": 1})


def test_params_any_order_and_cycles():
    assert resolve_params({"b": "a + 1", "a": 2}) == {"b": 3, "a": 2}
    with pytest.raises(DesignError):
        resolve_params({"a": "b", "b": "a"})


def test_tv_cart_is_clean():
    d = model.load(REPO / "designs" / "tv-cart.json")
    assert d.issues == []
    assert d.bounds(include_reference=False)["size"] == [560, 600, 1150]


def test_cut_list_groups_and_stock():
    d = model.load(REPO / "designs" / "tv-cart.json")
    c = cutlist.cut_list(d)
    posts = [r for r in c["rows"] if r["kind"] == "lumber"]
    assert len(posts) == 1 and posts[0]["qty"] == 2 and posts[0]["length"] == 1057
    spruce = next(s for s in c["stock"] if s["material"] == "spruce45x95")
    assert spruce["count"] == 1  # two 1057 pieces fit one 3 m board
    assert any(h["item"].startswith("Braked swivel caster") and h["qty"] == 4 for h in c["hardware"])


def test_stability_matches_hand_estimate():
    s = cutlist.stability(model.load(REPO / "designs" / "tv-cart.json"))
    assert 40 < s["total_mass_kg"] < 55
    assert 300 < s["cog_mm"][2] < 450
    assert s["weakest"] in ("forward", "left", "right")
    assert 25 < s["tip"][s["weakest"]]["tip_angle_deg"] < 45


def test_deeper_base_is_more_stable(home):
    before = cutlist.stability(store.load("tv-cart"))["tip"]["forward"]["tip_angle_deg"]
    store.set_param("tv-cart", "base_d", 700)
    after = cutlist.stability(store.load("tv-cart"))["tip"]["forward"]["tip_angle_deg"]
    assert after > before


def test_overlap_without_joint_is_flagged(home):
    d = store.add_part("tv-cart", {
        "id": "shelf", "name": "Shelf", "material": "ply18",
        "size": [200, 200, "ply"], "at": ["post_x", "post_y", 600],
    })
    assert any("overlap" in i["message"] and i["part"] in ("post_front", "shelf") for i in d.issues)


def test_bad_edit_refused_and_file_untouched(home):
    before = (home / "designs" / "tv-cart.json").read_text()
    with pytest.raises(DesignError):
        store.update_part("tv-cart", "base_top", {"size": ["nope", 1, 1]})
    assert (home / "designs" / "tv-cart.json").read_text() == before


def test_undo(home):
    store.set_param("tv-cart", "base_w", 700)
    assert store.load("tv-cart").params["base_w"] == 700
    store.undo("tv-cart")
    assert store.load("tv-cart").params["base_w"] == 560


def test_remove_part_cleans_joints(home):
    store.remove_part("tv-cart", "brace_left")
    raw = json.loads((home / "designs" / "tv-cart.json").read_text())
    assert all("brace_left" not in j["parts"] for j in raw["joints"])


def test_rename_part_updates_joints(home):
    store.update_part("tv-cart", "bracket", {"id": "vesa"})
    raw = json.loads((home / "designs" / "tv-cart.json").read_text())
    assert any("vesa" in j["parts"] for j in raw["joints"])


def test_wrong_stock_size_warns(home):
    d = store.update_part("tv-cart", "post_front", {"size": ["post_w", 40, "post_len"]})
    assert any("does not match" in i["message"] for i in d.issues)


def test_selection_roundtrip(home):
    store.set_selection("tv-cart", ["bracket"])
    assert store.get_selection()["parts"] == ["bracket"]


def test_design_name_validation(home):
    with pytest.raises(DesignError):
        store.design_path("../etc/passwd")
