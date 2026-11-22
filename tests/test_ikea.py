"""IKEA lookups, offline: fixtures are trimmed copies of real ikea.com/ee responses (2026-11-21).
Set WOODPECKER_LIVE=1 to also run one real search and import."""
import json
import os
import shutil
from pathlib import Path

import pytest

from woodpecker import catalog, ikea, store
from woodpecker.model import DesignError

REPO = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
PIP_URL = "https://www.ikea.com/ee/en/p/kallax-shelving-unit-white-20275814/"


@pytest.fixture()
def home(tmp_path, monkeypatch):
    shutil.copytree(REPO / "designs", tmp_path / "designs")
    shutil.copytree(REPO / "catalog", tmp_path / "catalog")
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "DESIGNS", tmp_path / "designs")
    monkeypatch.setattr(store, "STATE", tmp_path / ".woodpecker")
    return tmp_path


@pytest.fixture()
def offline(monkeypatch):
    """Serve fixtures instead of the network; anything else fails the test."""
    pages = {PIP_URL: (FIX / "ikea_pip_kallax_202.758.14.html").read_bytes()}

    def fake_get(url):
        if url in pages:
            return pages[url]
        if "search-result-page" in url:
            return (FIX / "ikea_search.json").read_bytes()
        if url.endswith("/products/814/20275814.json"):
            return json.dumps({"pipUrl": PIP_URL}).encode()
        raise DesignError(f"IKEA returned 404 for {url}")

    monkeypatch.setattr(ikea, "_get", fake_get)


def test_item_numbers():
    assert ikea.item_no("202.758.14") == "20275814"
    assert ikea.item_no("s99552177") == "99552177"
    assert ikea.item_no(PIP_URL) == "20275814"
    assert ikea.item_no("https://www.ikea.com/ee/en/p/kallax-tv-bench-white-s99552177/") == "99552177"
    assert ikea.article("20275814") == "202.758.14"
    with pytest.raises(DesignError):
        ikea.item_no("kallax")


def test_size_label():
    assert ikea.size_from_text("147x39x78 cm") == [1470, 390, 780]
    assert ikea.size_from_text("147x77 cm") is None  # no depth


def test_search_parses(home, offline):
    hits = ikea.search("kallax")
    assert hits[0]["article"] == "995.521.77" and hits[0]["combination"]
    assert hits[0]["size_mm"] == [1470, 390, 780]
    assert hits[0]["price"] == {"amount": 84.99, "currency": "EUR"}


def test_product_page_parses(offline):
    d = ikea.details("202.758.14")
    assert d["page_data"] and d["name"] == "KALLAX" and d["type"] == "Shelving unit" and d["variant"] == "white"
    assert d["measurements"]["Width"] == 765 and d["measurements"]["Depth"] == 390
    assert d["loads"]["Max. load/shelf"] == 13
    assert d["packages"][0]["weight"] == 11.78
    assert any("25 kg on the top" in n for n in d["notes"])


def test_mismatched_page_data_is_ignored():
    """IKEA's combination pages sometimes embed another product's data."""
    page = (FIX / "ikea_pip_kallax_202.758.14.html").read_text()
    d = ikea.parse_product_page(page, "x", "99552177")
    assert not d["page_data"] and d["measurements"] == {}


def test_to_catalog_item_keeps_published_and_lists_guesses(offline):
    it = ikea.to_catalog_item(ikea.details("202.758.14"))
    assert it["size"] == [765, 390, 765]
    assert it["load"] == {"per_shelf_kg": 13, "wall_cabinet_kg": 20, "top_kg": 25}
    assert it["package_kg"] == 11.78 and it["price"]["amount"] == 34.99
    assert it["geometry"] == {"generator": "cube_grid", "cols": 2, "rows": 2, "panel": 38}
    assert any("38 mm" in a for a in it["assumed"])
    assert "honeycomb" in it["construction"]
    assert len(catalog.generate(it, {})) == 7


def test_import_keeps_existing_article(home, offline):
    r = ikea.import_product("202.758.14")  # already curated as ikea-kallax-77x77
    assert r["id"] == "ikea-kallax-77x77" and r["already_in_catalog"]


def test_import_saves_new_item(home, offline):
    (home / "catalog/ikea/ikea-kallax-77x77.json").unlink()
    r = ikea.import_product("202.758.14")
    assert r["id"] == "ikea-kallax-shelving-unit-20275814"
    assert (home / "catalog/ikea/ikea-kallax-shelving-unit-20275814.json").exists()
    store.add_part("tv-cart", {"id": "k2", "name": "KALLAX", "component": r["id"], "at": [2000, 0, 0], "role": "test"})
    assert store.load("tv-cart").part("k2/top")


def test_table_and_shelf_measurements():
    table = {"item_no": "30514791", "article": "305.147.91", "url": "u", "name": "LACK", "type": "Side table",
             "variant": "white", "measurements": {"Length": 550, "Width": 550, "Height": 450},
             "loads": {"Max. load": 10}, "packages": [], "notes": [], "materials": []}
    it = ikea.to_catalog_item(table)
    assert it["size"] == [550, 550, 450] and it["geometry"]["generator"] == "table"
    assert it["load"] == {"max_load_kg": 10}
    assert len(catalog.generate(it, {})) == 5
    shelf = {**table, "type": "Shelf", "measurements": {"Width": 830, "Depth": 300, "Thickness": 18}}
    assert ikea.to_catalog_item(shelf)["size"] == [830, 300, 18]


def test_no_depth_is_an_error_not_a_guess():
    d = {"item_no": "69552942", "article": "695.529.42", "url": "u", "name": "KALLAX", "type": "Shelving unit",
         "measurements": {}, "loads": {}, "packages": [], "notes": [], "materials": [], "size_text": "147x77 cm"}
    with pytest.raises(DesignError, match="plain unit"):
        ikea.to_catalog_item(d)


@pytest.mark.skipif(not os.environ.get("WOODPECKER_LIVE"), reason="set WOODPECKER_LIVE=1 to hit ikea.com")
def test_live(home):
    assert ikea.search("billy bookcase")
    (home / "catalog/ikea/ikea-billy-80x28x106.json").unlink()
    r = ikea.import_product("302.638.44")
    assert catalog.get(r["id"])["size"] == [800, 280, 1060]


def test_sofa_max_measurements_give_the_bounding_box():
    kivik = {"Max. width": 3180.0, "Height": 830.0, "Min. depth": 950.0, "Max. depth": 1630.0,
             "Min. seat depth": 600.0, "Seat height": 450.0}
    assert ikea.wdh(kivik) == (3180.0, 1630.0, 830.0)
    assert ikea.wdh({"Width": 770, "Depth": 390, "Height": 1470}) == (770, 390, 1470)
    assert ikea.wdh({"Height": 830.0, "Seat height": 450.0}) is None


def _blank(no, url, meas=None):
    return {"item_no": no, "article": ikea.article(no), "url": url, "measurements": meas or {}, "loads": {},
            "packages": [], "notes": [], "materials": [], "page_data": True, "name": "KIVIK",
            "type": "4-seat sofa with chaise longue", "variant": "Tibbleby beige/grey", "size_text": None,
            "price": {"amount": 619.0, "currency": "EUR"}}


def test_measurements_come_from_another_market_when_home_has_none(monkeypatch):
    ee, fi = "https://www.ikea.com/ee/en/p/kivik-s99440585/", "https://www.ikea.com/fi/en/p/kivik-s99440585/"
    monkeypatch.setattr(ikea, "_get", lambda url: url.encode())
    monkeypatch.setattr(ikea, "_pip_url", lambda no, cc=None, lang=None, search_fallback=True:
                        {None: ee, "fi": fi}.get(cc) or (_ for _ in ()).throw(DesignError("IKEA returned 404")))
    pages = {ee: _blank("99440585", ee), fi: _blank("99440585", fi, {"Max. width": 3180.0, "Height": 830.0, "Max. depth": 1630.0})}
    monkeypatch.setattr(ikea, "parse_product_page", lambda page, url, no: json.loads(json.dumps(pages[url])))
    d = ikea.details("99440585")
    assert d["measurements_from"] == fi and ikea.wdh(d["measurements"]) == (3180.0, 1630.0, 830.0)
    item = ikea.to_catalog_item(d)
    assert item["size"] == [3180.0, 1630.0, 830.0] and item["url"] == ee
    assert any("another country" in a for a in item["assumed"])


def test_blocked_server_imports_from_search_or_explains(home, monkeypatch):
    hit = {"item_no": "20275814", "name": "KALLAX", "type": "Shelving unit", "variant": "white",
           "size_text": "77x39x147 cm", "size_mm": [770, 390, 1470], "price": {"amount": 39.99, "currency": "EUR"},
           "url": PIP_URL, "category": "shelving", "combination": False}
    monkeypatch.setattr(ikea, "_safe_search", lambda q: [hit])

    def blocked(ref):
        raise DesignError("IKEA returned 403 for https://www.ikea.com/...")
    monkeypatch.setattr(ikea, "details", blocked)
    monkeypatch.setattr(catalog, "by_article", lambda a: None)
    r = ikea.import_product("202.758.14")
    item = catalog.get(r["id"])
    assert item["size"] == [770, 390, 1470]
    assert any("refused the product page" in a for a in item["assumed"])

    monkeypatch.setattr(ikea, "_safe_search", lambda q: [{**hit, "size_text": "", "size_mm": None}])
    with pytest.raises(DesignError, match="blocks its product pages from this server"):
        ikea.import_product("202.758.14")
