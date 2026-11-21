"""Pictures (render.py) and Magpie pages (magpie.py), against a small fake Magpie."""
import io
import json
import re
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

from woodpecker import magpie, render, store

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def home(tmp_path, monkeypatch):
    shutil.copytree(REPO / "designs", tmp_path / "designs")
    shutil.copytree(REPO / "catalog", tmp_path / "catalog")
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "DESIGNS", tmp_path / "designs")
    monkeypatch.setattr(store, "STATE", tmp_path / ".woodpecker")
    return tmp_path


class FakeMagpie:
    def __init__(self):
        self.pages, self.files, self.calls = {}, [], []
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _out(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def _in(self):
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def do_GET(self):
                fake.calls.append(("GET", self.path))
                m = re.match(r"/api/pages/(\d+)$", self.path)
                if m and int(m.group(1)) in fake.pages:
                    return self._out(200, fake.pages[int(m.group(1))])
                self._out(404, {"detail": "not found"})

            def do_POST(self):
                fake.calls.append(("POST", self.path))
                assert self.headers["Authorization"] == "Bearer t0ken"
                body = self._in()
                if re.match(r"/api/projects/37/pages$", self.path):
                    b = json.loads(body)
                    pid = len(fake.pages) + 1
                    fake.pages[pid] = {"id": pid, "title": b["title"], "markdown": b["markdown"], "version": 1}
                    return self._out(201, fake.pages[pid])
                m = re.match(r"/api/pages/(\d+)/files$", self.path)
                if m:
                    assert b"\x89PNG" in body
                    fid = len(fake.files) + 1
                    fake.files.append(fid)
                    return self._out(201, {"id": fid, "url": f"/api/page-files/{fid}"})
                self._out(404, {})

            def do_PATCH(self):
                fake.calls.append(("PATCH", self.path))
                b = json.loads(self._in())
                pid = int(re.match(r"/api/pages/(\d+)$", self.path).group(1))
                p = fake.pages[pid]
                if b.get("base_version") is not None and b["base_version"] != p["version"]:
                    return self._out(409, {"detail": "conflict", "current": p})
                if "markdown" in b:
                    p["markdown"] = b["markdown"]
                if b.get("append_markdown"):
                    p["markdown"] += b["append_markdown"]
                p["title"] = b.get("title") or p["title"]
                p["version"] += 1
                self._out(200, p)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"


@pytest.fixture()
def fake_magpie(monkeypatch):
    f = FakeMagpie()
    monkeypatch.setenv("MAGPIE_API_BASE", f.base)
    monkeypatch.setenv("MAGPIE_API_TOKEN", "t0ken")
    monkeypatch.delenv("WOODPECKER_MAGPIE_PROJECT", raising=False)
    yield f
    f.httpd.shutdown()


def test_render_views(home):
    d = store.load("tv-cart")
    for v in render.VIEWS:
        img = Image.open(io.BytesIO(render.render(d, v)))
        assert img.size == (1200, 900)
        # something was drawn: not all background
        assert len(img.convert("RGB").resize((60, 45)).getcolors(10000)) > 5


def test_render_empty_design(home):
    store.create("blank", "Blank")
    img = Image.open(io.BytesIO(render.render(store.load("blank"), "3d")))
    assert img.size == (1200, 900)


def test_blank_design_has_starter_materials(home):
    d = store.create("blank", "Blank", created_by="hj")
    assert "ply18" in d.raw["materials"] and d.raw["created_by"] == "hj"


def test_publishing_off_without_token(home, monkeypatch):
    monkeypatch.delenv("MAGPIE_API_TOKEN", raising=False)
    assert not magpie.enabled()
    assert magpie.watch() is None


def test_publish_creates_page_and_keeps_notes(home, fake_magpie):
    info = magpie.publish("tv-cart", by="mk")
    assert info["page_id"] == 1 and info["url"].endswith("/#/pages/37/1")
    page = fake_magpie.pages[1]
    md = page["markdown"]
    assert page["title"] == store.load("tv-cart").title
    assert "## Cut list" in md and "## Shopping list" in md and "## Parameters" in md
    assert md.count("![") == len(render.VIEWS) and "/api/page-files/" in md
    assert "?design=tv-cart" in md and "by mk" in md
    assert len(fake_magpie.files) == len(render.VIEWS)

    # someone writes notes; a republish keeps them and re-uploads nothing unchanged
    page["markdown"] = md.replace("## Notes", "## Notes\n\nBought the casters at Bauhof.")
    page["version"] += 1
    magpie.publish("tv-cart")
    assert "Bought the casters at Bauhof." in page["markdown"]
    assert page["markdown"].count("## Notes") == 1
    assert len(fake_magpie.files) == len(render.VIEWS)

    # a change to the design re-renders and uploads new pictures
    store.set_param("tv-cart", "base_w", 700)
    magpie.publish("tv-cart")
    assert len(fake_magpie.files) > len(render.VIEWS)
    assert "700" in page["markdown"]


def test_publish_recreates_deleted_page(home, fake_magpie):
    magpie.publish("greenhouse")
    del fake_magpie.pages[1]
    info = magpie.publish("greenhouse")
    assert info["page_id"] == 1 and 1 in fake_magpie.pages  # fake reuses ids; a new page was made


def test_publish_error_is_recorded(home, monkeypatch):
    monkeypatch.setenv("MAGPIE_API_TOKEN", "x")
    monkeypatch.setenv("MAGPIE_API_BASE", "http://127.0.0.1:9")  # nothing listens
    with pytest.raises(Exception):
        magpie.publish("tv-cart")
    assert "unreachable" in magpie.info("tv-cart")["error"]


def test_material_color_and_anchored(home):
    import json
    from woodpecker import cutlist
    raw = json.loads((home / "designs/tv-cart.json").read_text())
    raw["anchored"] = "On ground screws."
    raw["materials"]["tv"]["color"] = "#ff0000"
    (home / "designs/tv-cart.json").write_text(json.dumps(raw))
    d = store.load("tv-cart")
    st = cutlist.stability(d)
    assert st["anchored"] == "On ground screws." and "tip" not in st
    tv = next(p for p in d.parts if p.material == "tv")
    assert list(render.part_color(tv, d)) == [255, 0, 0]
