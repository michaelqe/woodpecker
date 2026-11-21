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
