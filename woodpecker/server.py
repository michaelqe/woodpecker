"""Local viewer server (stdlib only). `woodpecker serve` -> http://127.0.0.1:8790"""
from __future__ import annotations

import argparse
import json
import threading
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import catalog, chat, cutlist, ikea, magpie, store
from .model import DesignError

STATIC = Path(__file__).resolve().parent / "static"
BUILD_SHA_FILE = Path(__file__).resolve().parent / "BUILD_SHA"
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")


def design_payload(name: str) -> dict:
    d = store.load(name)
    return {
        "design": d.to_dict(),
        "mtime": store.mtime(name),
        "cutlist": cutlist.cut_list(d),
        "stability": cutlist.stability(d),
    }


ROUTES: list[tuple[str, re.Pattern, str]] = []


def route(method, pattern):
    def deco(fn):
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn.__name__))
        return fn
    return deco


NAME = r"([\w-]+)"
PART = r"([^/]+)"


class Handler(BaseHTTPRequestHandler):
    server_version = "Woodpecker/0.2"

    def log_message(self, fmt, *args):  # quieter: skip the 1 s mtime polls
        if "/mtime" not in self.path:
            super().log_message(fmt, *args)

    # ---- plumbing
    def _send(self, status, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=HTTPStatus.OK):
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _user(self) -> str | None:
        """Login name from Caddy forward-auth (absent when run locally)."""
        u = (self.headers.get("X-Remote-User") or "").strip()
        return u or None

    def _query(self) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def _dispatch(self, method):
        path = urlparse(self.path).path
        for m, pat, fn in ROUTES:
            match = pat.match(path)
            if m == method and match:
                try:
                    return getattr(self, fn)(*(unquote(g) for g in match.groups()))
                except DesignError as e:
                    return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                except json.JSONDecodeError as e:
                    return self._json({"error": f"invalid JSON: {e}"}, HTTPStatus.BAD_REQUEST)
                except FileNotFoundError as e:
                    return self._json({"error": str(e)}, HTTPStatus.NOT_FOUND)
        if method == "GET":
            return self.static(path)
        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def static(self, path):
        if path.startswith("/print/"):
            path = "/print.html"
        rel = "index.html" if path in ("", "/") else path.lstrip("/").removeprefix("static/")
        f = (STATIC / rel).resolve()
        if STATIC not in f.parents or not f.is_file():
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, f.read_bytes(), ctype)

    # ---- health / who
    @route("GET", r"/api/health")
    def health(self):
        sha = BUILD_SHA_FILE.read_text().strip() if BUILD_SHA_FILE.exists() else "dev"
        self._json({"ok": True, "git_sha": sha, "magpie": magpie.enabled()})

    @route("GET", r"/api/me")
    def me(self):
        self._json({"user": self._user(), "magpie": magpie.enabled()})

    # ---- designs
    @route("GET", r"/api/designs")
    def designs(self):
        self._json(store.list_designs())

    @route("POST", r"/api/designs")
    def create_design(self):
        b = self._body()
        store.create(b["name"], b.get("title") or b["name"], b.get("description", ""), b.get("copy_from"),
                     created_by=self._user())
        _publish_soon(b["name"], self._user())
        self._json(design_payload(b["name"]))

    @route("GET", rf"/api/designs/{NAME}")
    def design(self, name):
        self._json(design_payload(name))

    @route("GET", rf"/api/designs/{NAME}/mtime")
    def design_mtime(self, name):
        self._json({"mtime": store.mtime(name)})

    @route("POST", rf"/api/designs/{NAME}/params")
    def set_param(self, name):
        b = self._body()
        store.set_param(name, b["name"], b["value"])
        self._json(design_payload(name))

    @route("POST", rf"/api/designs/{NAME}/delete")
    def delete_design(self, name):
        out = store.delete_design(name)
        threading.Thread(target=magpie.mark_deleted, args=(name,), daemon=True).start()
        self._json(out)

    @route("GET", rf"/api/designs/{NAME}/page")
    def design_page(self, name):
        self._json(magpie.info(name))

    @route("POST", rf"/api/designs/{NAME}/publish")
    def publish(self, name):
        self._json(magpie.publish(name, by=self._user(), force=bool(self._body().get("force"))))

    @route("GET", rf"/api/designs/{NAME}/render/([a-z0-9-]+)")
    def render_png(self, name, view):
        from . import render
        if view not in render.VIEWS:
            raise DesignError(f"view must be one of {', '.join(render.VIEWS)}")
        self._send(HTTPStatus.OK, render.render(store.load(name), view), "image/png")

    @route("POST", rf"/api/designs/{NAME}/undo")
    def undo(self, name):
        store.undo(name)
        self._json(design_payload(name))

    # ---- parts (the viewer's drawing tools)
    def _source(self, name, part_id):
        return store.load(name).part(part_id).source

    @route("POST", rf"/api/designs/{NAME}/parts")
    def add_part(self, name):
        b = self._body()
        store.add_part(name, b["part"], b.get("after"))
        self._json(design_payload(name))

    @route("POST", rf"/api/designs/{NAME}/parts/{PART}/move")
    def move_part(self, name, part_id):
        store.move_part(name, self._source(name, part_id), self._body()["delta"])
        self._json(design_payload(name))

    @route("POST", rf"/api/designs/{NAME}/parts/{PART}/resize")
    def resize_part(self, name, part_id):
        store.resize_part(name, self._source(name, part_id), self._body()["delta"])
        self._json(design_payload(name))

    @route("POST", rf"/api/designs/{NAME}/parts/{PART}/update")
    def update_part(self, name, part_id):
        store.update_part(name, self._source(name, part_id), self._body()["fields"])
        self._json(design_payload(name))

    @route("POST", rf"/api/designs/{NAME}/parts/{PART}/delete")
    def delete_part(self, name, part_id):
        store.remove_part(name, self._source(name, part_id))
        self._json(design_payload(name))

    # ---- catalog
    @route("GET", r"/api/catalog")
    def catalog_search(self):
        self._json(catalog.search(self._query().get("q", "")))

    @route("GET", r"/api/catalog/([a-z0-9-]+)")
    def catalog_item(self, item_id):
        self._json(catalog.get(item_id))

    @route("GET", r"/api/ikea")
    def ikea_search(self):
        cc, lang = ikea.market()
        self._json({"market": f"{cc}/{lang}", "results": ikea.search(self._query().get("q", ""))})

    @route("POST", r"/api/ikea/import")
    def ikea_import(self):
        self._json(ikea.import_product(str(self._body()["ref"])))

    # ---- selection
    @route("GET", r"/api/selection")
    def get_selection(self):
        self._json(store.get_selection())

    @route("POST", r"/api/selection")
    def post_selection(self):
        b = self._body()
        self._json(store.set_selection(b.get("design"), list(b.get("parts", []))))

    # ---- chat
    @route("GET", r"/api/chat")
    def chat_status(self):
        self._json(chat.status())

    @route("GET", rf"/api/chat/{NAME}")
    def chat_history(self, name):
        self._json(chat.history(name))

    @route("POST", rf"/api/chat/{NAME}/reset")
    def chat_reset(self, name):
        self._json(chat.reset(name))

    @route("POST", rf"/api/chat/{NAME}")
    def chat_send(self, name):
        b = self._body()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        for ev in chat.stream(name, b.get("message", ""), list(b.get("selection", []))):
            try:
                self.wfile.write((json.dumps(ev) + "\n").encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # keep draining so the session and history are saved
        self.close_connection = True


def _publish_soon(name: str, by: str | None) -> None:
    if not magpie.enabled():
        return

    def run():
        try:
            magpie.publish(name, by=by)
        except DesignError as e:
            print(f"magpie: {name}: {e}", flush=True)
    threading.Thread(target=run, daemon=True).start()


def serve(host="127.0.0.1", port=8790):
    httpd = ThreadingHTTPServer((host, port), Handler)
    if magpie.watch():
        print("Magpie pages: on (project %s at %s)" % (magpie.project_id(), magpie._base()))
    print(f"Woodpecker on http://{host}:{port}  (designs in {store.DESIGNS})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="woodpecker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the viewer")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8790)
    c = sub.add_parser("cutlist", help="print the cut list for a design")
    c.add_argument("name")
    k = sub.add_parser("check", help="print issues and the tip check")
    k.add_argument("name")
    args = ap.parse_args(argv)
    if args.cmd == "serve":
        serve(args.host, args.port)
    elif args.cmd == "cutlist":
        print(format_cutlist(store.load(args.name)))
    elif args.cmd == "check":
        d = store.load(args.name)
        for i in d.issues:
            print(f"{i['level']}: {i['message']}")
        if not d.issues:
            print("no issues")
        st = cutlist.stability(d)
        print(f"mass {st.get('total_mass_kg')} kg, centre of gravity {st.get('cog_mm')}")
        for k_, t in st.get("tip", {}).items():
            print(f"  tips {k_:<8} at {t['tip_angle_deg']:>5}°  push at top {t['push_at_top_kg']} kg")


def format_cutlist(d) -> str:
    c = cutlist.cut_list(d)
    lines = [f"# {d.title}", "", "## Cut list (mm)"]
    for r in c["rows"]:
        if r["kind"] == "lumber":
            dims = f"{r['length']:g} long, {r['section'][0]:g}x{r['section'][1]:g}"
        else:
            dims = f"{r['length']:g} x {r['width']:g} x {r['thickness']:g}"
        extra = f" ({r['shape']})" if r["shape"] != "rect" else ""
        if r.get("ends"):
            extra += f", ends cut at {r['ends'][0]:g}° / {r['ends'][1]:g}°"
        lines.append(f"{r['qty']:>3}  {r['label']}: {dims}{extra}  [{r['material_name']}]")
        for n in r.get("cut_notes", []):
            lines.append(f"       - {n}")
    lines += ["", "## Stock to buy"]
    for s in c["stock"]:
        lines.append(f"{s['count']:>3}  {s['name']} ({s['unit']}) - {s['method']}")
        for w in s.get("warnings", []):
            lines.append(f"     ! {w}")
    if c["bought"]:
        lines += ["", "## Bought items"]
        for b in c["bought"]:
            price = b.get("price") or {}
            p = f"  {price['amount']:g} {price.get('currency', '')}" if price.get("amount") is not None else ""
            lines.append(f"{b['qty']:>3}  {b['item']} ({b.get('article') or 'no article no.'}){p}")
    lines += ["", "## Hardware"]
    for h in c["hardware"]:
        note = f"  ({h['notes']})" if h.get("notes") else ""
        lines.append(f"{h['qty']:>3}  {h['item']}{note}")
    cost = c["cost"]
    if cost["lines"]:
        lines += ["", f"## Cost: {cost['total_eur']:.2f} EUR for priced items"]
        if cost["missing"]:
            lines.append(f"   ({len(cost['missing'])} items have no price yet)")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
