"""Local viewer server (stdlib only). `woodpecker serve` -> http://127.0.0.1:8790"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import cutlist, store
from .model import DesignError

STATIC = Path(__file__).resolve().parent / "static"
mimetypes.add_type("text/javascript", ".js")


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


class Handler(BaseHTTPRequestHandler):
    server_version = "Woodpecker/0.1"

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

    def _dispatch(self, method):
        path = urlparse(self.path).path
        for m, pat, fn in ROUTES:
            match = pat.match(path)
            if m == method and match:
                try:
                    return getattr(self, fn)(*match.groups())
                except DesignError as e:
                    return self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
                except json.JSONDecodeError as e:
                    return self._json({"error": f"invalid JSON: {e}"}, HTTPStatus.BAD_REQUEST)
        if method == "GET":
            return self.static(path)
        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/").removeprefix("static/")
        f = (STATIC / rel).resolve()
        if STATIC not in f.parents or not f.is_file():
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, f.read_bytes(), ctype)

    # ---- API
    @route("GET", r"/api/designs")
    def designs(self):
        self._json(store.list_designs())

    @route("GET", r"/api/designs/([\w-]+)")
    def design(self, name):
        self._json(design_payload(name))

    @route("GET", r"/api/designs/([\w-]+)/mtime")
    def design_mtime(self, name):
        self._json({"mtime": store.mtime(name)})

    @route("POST", r"/api/designs/([\w-]+)/params")
    def set_param(self, name):
        b = self._body()
        store.set_param(name, b["name"], b["value"])
        self._json(design_payload(name))

    @route("POST", r"/api/designs/([\w-]+)/undo")
    def undo(self, name):
        store.undo(name)
        self._json(design_payload(name))

    @route("GET", r"/api/selection")
    def get_selection(self):
        self._json(store.get_selection())

    @route("POST", r"/api/selection")
    def post_selection(self):
        b = self._body()
        self._json(store.set_selection(b.get("design"), list(b.get("parts", []))))


def serve(host="127.0.0.1", port=8790):
    httpd = ThreadingHTTPServer((host, port), Handler)
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
        print(json.dumps({k: v for k, v in cutlist.stability(d).items() if k != "mass_breakdown"}, indent=2))


def format_cutlist(d) -> str:
    c = cutlist.cut_list(d)
    lines = [f"# {d.title}", "", "## Cut list (mm)"]
    for r in c["rows"]:
        if r["kind"] == "lumber":
            dims = f"{r['length']:g} long, {r['section'][0]:g}x{r['section'][1]:g}"
        else:
            dims = f"{r['length']:g} x {r['width']:g} x {r['thickness']:g}"
        tri = " (triangle)" if r["shape"] == "triangle" else ""
        lines.append(f"{r['qty']:>3}  {r['label']}: {dims}{tri}  [{r['material_name']}]")
    lines += ["", "## Stock to buy"]
    for s in c["stock"]:
        lines.append(f"{s['count']:>3}  {s['name']} ({s['unit']}) - {s['method']}")
        for w in s.get("warnings", []):
            lines.append(f"     ! {w}")
    lines += ["", "## Hardware"]
    for h in c["hardware"]:
        note = f"  ({h['notes']})" if h.get("notes") else ""
        lines.append(f"{h['qty']:>3}  {h['item']}{note}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
