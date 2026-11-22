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


def test_delete_reports_where_a_design_was_placed(tmp_path, monkeypatch):
    from woodpecker import store
    (tmp_path / "designs").mkdir()
    monkeypatch.setattr(store, "DESIGNS", tmp_path / "designs")
    monkeypatch.setattr(store, "STATE", tmp_path / ".woodpecker")
    _write(tmp_path / "designs", "stand", BOARD)
    _write(tmp_path / "designs", "room", {"title": "Room", "materials": {}, "parts": [{"id": "s", "design": "stand", "at": [0, 0, 0]}]})
    assert store.placed_in("stand") == [{"name": "room", "title": "Room"}]
    out = store.delete_design("stand")
    assert out["was_placed_in"] == [{"name": "room", "title": "Room"}]
    assert not (tmp_path / "designs" / "stand.json").exists()
    assert not (tmp_path / ".woodpecker" / "history" / "stand").exists()  # gone for good


def test_move_several_and_group_are_one_undo_step(tmp_path, monkeypatch):
    from woodpecker import store
    (tmp_path / "designs").mkdir()
    monkeypatch.setattr(store, "DESIGNS", tmp_path / "designs")
    monkeypatch.setattr(store, "STATE", tmp_path / ".woodpecker")
    raw = json.loads(json.dumps(BOARD))
    raw["parts"][1]["at"] = ["100 + 5", 200, 518]
    _write(tmp_path / "designs", "stand", raw)
    store.move_parts("stand", ["top", "tv", "top"], [10, 0, -5])
    parts = store.read_raw("stand")["parts"]
    assert parts[0]["at"] == [110, 50, 495]
    assert parts[1]["at"] == ["100 + 15", 200, 513]   # expression kept readable, moved once
    store.set_group("stand", ["top", "tv"], " TV stand ")
    assert {p["group"] for p in store.read_raw("stand")["parts"]} == {"TV stand"}
    store.undo("stand")
    assert "group" not in store.read_raw("stand")["parts"][0]
    store.undo("stand")
    assert store.read_raw("stand")["parts"][0]["at"] == [100, 50, 500]


def test_deleting_a_design_deletes_its_magpie_page(tmp_path, monkeypatch):
    from woodpecker import magpie, store
    monkeypatch.setattr(store, "STATE", tmp_path / ".woodpecker")
    monkeypatch.setenv("MAGPIE_API_TOKEN", "t")
    magpie._save_state({"stand": {"page_id": 42}, "other": {"page_id": 7}})
    calls = []
    monkeypatch.setattr(magpie, "_req", lambda method, path, body=None, **kw: calls.append((method, path)) or (204, None))
    magpie.delete_page("stand")
    assert calls == [("DELETE", "/api/pages/42")]
    assert magpie._load_state() == {"other": {"page_id": 7}}


def test_turning_parts_keeps_their_middle_and_merges_z_turns(tmp_path, monkeypatch):
    from woodpecker import store
    (tmp_path / "designs").mkdir()
    monkeypatch.setattr(store, "DESIGNS", tmp_path / "designs")
    monkeypatch.setattr(store, "STATE", tmp_path / ".woodpecker")
    _write(tmp_path / "designs", "stand", BOARD)

    def mid(d, sid):
        ps = [p for p in d.parts if p.source == sid]
        return [(min(p.at[k] for p in ps) + max(p.max[k] for p in ps)) / 2 for k in range(3)]

    d0 = store.load("stand")
    m0 = mid(d0, "top")
    d = store.rotate_parts("stand", ["top"], 90)
    assert all(abs(a - b) < 1e-6 for a, b in zip(mid(d, "top"), m0))       # turned in place
    assert abs(d.part("top").bsize[0] - 400) < 1e-6                        # 800 x 400 is now 400 x 800
    assert store.read_raw("stand")["parts"][0]["rotate"] == {"axis": "z", "deg": 90.0}
    d = store.rotate_parts("stand", ["top"], -90)
    assert "rotate" not in store.read_raw("stand")["parts"][0]             # back to square, no clutter
    assert all(abs(a - b) < 1e-6 for a, b in zip(d.part("top").at, d0.part("top").at))

    # two parts turn as one piece about their shared middle
    both = [(min(p.at[k] for p in d0.parts) + max(p.max[k] for p in d0.parts)) / 2 for k in range(2)]
    d = store.rotate_parts("stand", ["top", "tv"], 180)
    after = [(min(p.at[k] for p in d.parts) + max(p.max[k] for p in d.parts)) / 2 for k in range(2)]
    assert all(abs(a - b) < 1e-6 for a, b in zip(after, both))
    # the TV was behind the top's front edge; after a half turn it is mirrored about the middle
    assert abs((d.part("tv").at[1] + d.part("tv").max[1]) / 2 - (2 * both[1] - (200 + 60 / 2))) < 1e-6
    store.undo("stand")
    assert store.read_raw("stand")["parts"][1]["at"] == [100, 200, 518]
