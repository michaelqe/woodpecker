"""A part spec {"design": "<name>"} places another design inside this one, live."""
import json

from woodpecker import cutlist, model

BOARD = {"title": "Stand", "materials": {"ply": {"name": "Plywood 18", "kind": "sheet", "thickness": 18, "density": 600}},
         "parts": [{"id": "top", "material": "ply", "size": [800, 400, 18], "at": [100, 50, 500]},
                   {"id": "tv", "material": "ref", "size": [1200, 60, 700], "at": [100, 200, 518]}]}
BOARD["materials"]["ref"] = {"name": "TV (reference)", "kind": "reference", "color": "#111111"}


def _write(tmp, name, raw):
    (tmp / f"{name}.json").write_text(json.dumps(raw))
    return tmp / f"{name}.json"


def test_placed_design_lands_at_its_min_corner_and_follows_edits(tmp_path):
    _write(tmp_path, "stand", BOARD)
    room = {"title": "Room", "materials": {}, "parts": [
        {"id": "stand", "name": "TV stand", "design": "stand", "at": [2000, 1000, 0],
         "rotate": {"axis": "z", "deg": 90}}]}
    d = model.load(_write(tmp_path, "room", room))
    assert not [i for i in d.issues if i["level"] == "error"], d.issues
    ids = {p.id for p in d.parts}
    assert ids == {"stand/top", "stand/tv"}
    top = d.part("stand/top")
    assert top.kind == "component" and top.component == "design:stand"
    assert d.part("stand/tv").kind == "reference"
    assert top.color  # keeps the colour it has in its own design
    assert d.components["design:stand"]["name"] == "Stand"
    # rotated 90° about z at (2000, 1000): the 1200 wide TV now runs along y
    assert abs(d.part("stand/tv").bsize[1] - 1200) < 1e-6
    # listed once as a placed design, with the plywood's mass carried over
    assert [b["item"] for b in cutlist.bought_items(d)] == ["Design Stand"]
    assert abs(cutlist.part_mass(top, {}) - 0.8 * 0.4 * 0.018 * 600) < 0.01

    BOARD2 = json.loads(json.dumps(BOARD))
    BOARD2["parts"][0]["size"] = [1000, 400, 18]
    _write(tmp_path, "stand", BOARD2)
    d = model.load(tmp_path / "room.json")
    assert abs(d.part("stand/top").bsize[1] - 1000) < 1e-6


def test_placing_repeats_and_missing_and_cycles(tmp_path):
    _write(tmp_path, "stand", BOARD)
    room = {"title": "Room", "materials": {}, "parts": [
        {"id": "s", "design": "stand", "at": [0, 0, 0], "repeat": {"count": 2, "axis": "x", "spacing": 2000}},
        {"id": "gone", "design": "nope", "at": [0, 0, 0]}]}
    d = model.load(_write(tmp_path, "room", room))
    assert {p.instance for p in d.parts} == {"s[0]", "s[1]"}
    assert any("no design 'nope'" in i["message"] for i in d.issues)

    a = {"title": "A", "materials": {}, "parts": [{"id": "b", "design": "b", "at": [0, 0, 0]}]}
    b = {"title": "B", "materials": {}, "parts": [{"id": "a", "design": "a", "at": [0, 0, 0]}]}
    _write(tmp_path, "b", b)
    d = model.load(_write(tmp_path, "a", a))
    assert any("contain itself" in i["message"] for i in d.issues), d.issues
    selfish = {"title": "S", "materials": {}, "parts": [{"id": "me", "design": "selfish", "at": [0, 0, 0]}]}
    d = model.load(_write(tmp_path, "selfish", selfish))
    assert any("contain itself" in i["message"] for i in d.issues), d.issues
