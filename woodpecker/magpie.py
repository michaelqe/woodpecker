"""One Magpie page per design: pictures, shopping list, cut list, parameters, tip check.

Woodpecker owns everything above the page's "Notes" heading and rewrites it when the
design changes; people write under "## Notes" and that part is kept. Pictures come from
render.py and are uploaded as page files (only when they changed).

Off unless MAGPIE_API_TOKEN is set (so a dev copy on the laptop never makes pages).
Env:
  MAGPIE_API_BASE           default http://127.0.0.1:8509 (Magpie on the same droplet)
  MAGPIE_API_TOKEN          an agent token from Magpie's MAGPIE_API_TOKENS
  WOODPECKER_MAGPIE_PROJECT Magpie project id for the pages (default 37, "Woodpecker");
                            a design's own "magpie_project" wins (the house model lives in House > Digital Twin)
  WOODPECKER_PUBLIC_URL     link back to the viewer (default https://woodpecker.app.kennedy.ee)
  MAGPIE_PUBLIC_URL         link to the page (default https://magpie.app.kennedy.ee)
"""
from __future__ import annotations

import datetime as _dt
import fcntl
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager

from . import cutlist, render, store
from .model_errors import DesignError

NOTES = "## Notes"
DEBOUNCE_S = 20


def enabled() -> bool:
    return bool(os.environ.get("MAGPIE_API_TOKEN"))


def _base() -> str:
    return os.environ.get("MAGPIE_API_BASE", "http://127.0.0.1:8509").rstrip("/")


def project_id() -> int:
    return int(os.environ.get("WOODPECKER_MAGPIE_PROJECT", "37"))


def viewer_url(name: str) -> str:
    return f"{os.environ.get('WOODPECKER_PUBLIC_URL', 'https://woodpecker.app.kennedy.ee').rstrip('/')}/?design={name}"


def page_url(page_id: int, project: int | None = None) -> str:
    return f"{os.environ.get('MAGPIE_PUBLIC_URL', 'https://magpie.app.kennedy.ee').rstrip('/')}/#/pages/{project or project_id()}/{page_id}"


# ---------------------------------------------------------------- HTTP

def _req(method: str, path: str, body=None, *, raw: bytes | None = None, ctype: str | None = None):
    headers = {"Authorization": f"Bearer {os.environ.get('MAGPIE_API_TOKEN', '')}"}
    data = None
    if raw is not None:
        data, headers["Content-Type"] = raw, ctype
    elif body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    req = urllib.request.Request(_base() + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read() or b"null")
        except json.JSONDecodeError:
            payload = None
        if e.code == 409:
            return 409, payload
        raise DesignError(f"Magpie {method} {path}: {e.code} {payload}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise DesignError(f"Magpie unreachable at {_base()}: {e}") from e


def _upload(page_id: int, filename: str, content: bytes, ctype: str = "image/png") -> dict:
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    _, f = _req("POST", f"/api/pages/{page_id}/files", raw=body, ctype=f"multipart/form-data; boundary={boundary}")
    return f


# ---------------------------------------------------------------- state

def _state_path():
    store.STATE.mkdir(parents=True, exist_ok=True)
    return store.STATE / "magpie.json"


def _load_state() -> dict:
    p = _state_path()
    return json.loads(p.read_text()) if p.exists() else {}


def _save_state(s: dict) -> None:
    p = _state_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, indent=1))
    tmp.replace(p)


@contextmanager
def _lock():
    """One publisher at a time across processes (viewer server and MCP server)."""
    store.STATE.mkdir(parents=True, exist_ok=True)
    with open(store.STATE / "magpie.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def info(name: str) -> dict:
    s = _load_state().get(name) or {}
    out = {"enabled": enabled(), **{k: s.get(k) for k in ("page_id", "published_at", "error", "by")}}
    if s.get("page_id"):
        out["url"] = page_url(s["page_id"], s.get("project_id"))
    return out


# ---------------------------------------------------------------- page body

def _fmt(n, d=0):
    return f"{n:,.{d}f}".replace(",", " ")


def _cell(s) -> str:
    return str(s).replace("|", "/").replace("\n", " ")


def body_markdown(design, images: dict[str, str], by: str | None) -> str:
    c = cutlist.cut_list(design)
    st = cutlist.stability(design)
    b = design.bounds(include_reference=False)
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"[Open in Woodpecker]({viewer_url(design.name)}) · design `{design.name}` · "
         f"updated {now}{f' by {by}' if by else ''}", ""]
    if design.raw.get("description"):
        L += [design.raw["description"], ""]
    L += ["*Everything above **Notes** is rewritten by Woodpecker when the design changes. "
          "Write under Notes; that part is kept.*", ""]

    labels = {v: render.VIEWS[v][2] for v in render.VIEWS}
    if images:
        L += ["## Drawings", ""]
        for v, url in images.items():
            L += [f"![{labels.get(v, v)}]({url})", ""]

    L += ["## Size and weight", ""]
    if b.get("size"):
        s = b["size"]
        L.append(f"Overall **{_fmt(s[0])} x {_fmt(s[1])} x {_fmt(s[2])} mm** (W x D x H).")
    if st.get("total_mass_kg") is not None:
        L.append(f"Weight about **{st['total_mass_kg']} kg** (parts with a known weight).")
    if st.get("anchored"):
        L.append(st["anchored"])
    tips = st.get("tip") or {}
    if tips:
        L += ["", "| Tips | at tilt | push at the top |", "|---|---|---|"]
        for k, t in tips.items():
            L.append(f"| {k} | {t['tip_angle_deg']}° | {t['push_at_top_kg']} kg |")
    L.append("")

    L += ["## Shopping list", ""]
    if c["stock"]:
        L += ["| Qty | Stock | Unit | How it was worked out |", "|---|---|---|---|"]
        for s in c["stock"]:
            warn = ("; " + "; ".join(s["warnings"])) if s.get("warnings") else ""
            L.append(f"| {s['count']} | {_cell(s['name'])} | {_cell(s['unit'])} | {_cell(s['method'])}{_cell(warn)} |")
        L.append("")
    if c["bought"]:
        L += ["| Qty | Bought item | Article | Price |", "|---|---|---|---|"]
        for it in c["bought"]:
            p = it.get("price") or {}
            price = f"{p['amount']:g} {p.get('currency', '')}" if p.get("amount") is not None else "-"
            L.append(f"| {it['qty']} | {_cell(it['item'])} | {it.get('article') or '-'} | {price} |")
        L.append("")
    if c["hardware"]:
        L += ["| Qty | Hardware | Notes |", "|---|---|---|"]
        for h in c["hardware"]:
            L.append(f"| {h['qty']} | {_cell(h['item'])} | {_cell(h.get('notes') or '')} |")
        L.append("")
    cost = c["cost"]
    if cost["lines"]:
        missing = f" ({len(cost['missing'])} items have no price yet)" if cost["missing"] else ""
        L += [f"Cost of priced items: **{cost['total_eur']:.2f} EUR**{missing}.", ""]

    L += ["## Cut list", ""]
    if c["rows"]:
        L += ["| Qty | Part | Size (mm) | Material | Notes |", "|---|---|---|---|---|"]
        for r in c["rows"]:
            if r["kind"] == "lumber":
                dims = f"{r['length']:g} long, {r['section'][0]:g} x {r['section'][1]:g}"
            else:
                dims = f"{r['length']:g} x {r['width']:g} x {r['thickness']:g}"
            notes = []
            if r["shape"] != "rect":
                notes.append(r["shape"])
            if r.get("ends"):
                notes.append(f"ends cut at {r['ends'][0]:g}° / {r['ends'][1]:g}°")
            notes += r.get("cut_notes", [])
            L.append(f"| {r['qty']} | {_cell(r['label'])} | {dims} | {_cell(r['material_name'])} | {_cell('; '.join(notes))} |")
        L.append("")
    else:
        L += ["Nothing to cut yet.", ""]

    params = design.raw.get("params") or {}
    if params:
        L += ["## Parameters", "", "| Name | Value | What it is |", "|---|---|---|"]
        for k, v in params.items():
            val = v.get("value") if isinstance(v, dict) else v
            label = v.get("label", "") if isinstance(v, dict) else ""
            resolved = design.params.get(k)
            shown = f"`{val}` = {resolved:g}" if isinstance(val, str) and resolved is not None else f"{val}"
            L.append(f"| {k} | {_cell(shown)} | {_cell(label)} |")
        L.append("")

    L += ["## Check", ""]
    if design.issues:
        L += [f"- **{i['level']}**: {_cell(i['message'])}" for i in design.issues]
    else:
        L.append("No overlaps or stock problems found.")
    L.append("")
    return "\n".join(L)


def _split_notes(markdown: str) -> str:
    m = re.search(r"^#{1,3}\s*Notes\s*$", markdown or "", re.M | re.I)
    return markdown[m.start():].strip() if m else f"{NOTES}\n"


# ---------------------------------------------------------------- publish

def publish(name: str, by: str | None = None, force: bool = False) -> dict:
    """Create or refresh the design's Magpie page. Returns info(name)."""
    if not enabled():
        raise DesignError("Magpie publishing is off here (no MAGPIE_API_TOKEN)")
    with _lock():
        state = _load_state()
        s = state.setdefault(name, {})
        try:
            design = store.load(name)
            pid = s.get("page_id")
            if pid:
                try:
                    _, page = _req("GET", f"/api/pages/{pid}")
                except DesignError as e:
                    if ": 404 " not in str(e):
                        raise
                    pid = None  # someone deleted the page in Magpie: make a new one
            if not pid:
                proj = design.magpie_project or project_id()
                _, page = _req("POST", f"/api/projects/{proj}/pages",
                               {"title": design.title, "markdown": f"Drawing it…\n\n{NOTES}\n", "author": "woodpecker"})
                pid = s["page_id"] = page["id"]
                s["project_id"] = proj
                s["images"] = {}
            # pictures: upload only the ones that changed
            imgs = s.setdefault("images", {})
            for view, png in render.render_all(design).items():
                sha = hashlib.sha256(png).hexdigest()[:16]
                if force or (imgs.get(view) or {}).get("sha") != sha:
                    f = _upload(pid, f"{name}-{view}.png", png)
                    imgs[view] = {"sha": sha, "url": f["url"]}
            urls = {v: imgs[v]["url"] for v in render.VIEWS if v in imgs}
            gen = body_markdown(design, urls, by or s.get("by"))
            for _attempt in range(3):
                notes = _split_notes(page.get("markdown") or "")
                status, res = _req("PATCH", f"/api/pages/{pid}", {
                    "title": design.title, "markdown": f"{gen}\n{notes}\n",
                    "base_version": page.get("version"), "author": "woodpecker"})
                if status != 409:
                    break
                page = (res or {}).get("current") or _req("GET", f"/api/pages/{pid}")[1]
            s.update(published_at=time.time(), mtime=store.mtime(name), error=None)
            if by:
                s["by"] = by
        except DesignError as e:
            s["error"] = str(e)
            _save_state(state)
            raise
        _save_state(state)
    return info(name)


def delete_page(name: str) -> None:
    """The design was deleted: delete its Magpie page too, and forget it."""
    with _lock():
        st = _load_state()
        s = st.pop(name, None) or {}
        if enabled() and s.get("page_id"):
            try:
                _req("DELETE", f"/api/pages/{s['page_id']}")
            except DesignError:
                st[name] = s   # Magpie unreachable: keep the id so it can be retried
        _save_state(st)


# ---------------------------------------------------------------- background sync

def watch(interval: float = 5.0) -> threading.Thread | None:
    """Republish designs whose file changed and then sat still for DEBOUNCE_S seconds."""
    if not enabled():
        return None

    def loop():
        while True:
            try:
                state = _load_state()
                for d in store.list_designs():
                    name = d["name"] if isinstance(d, dict) else d
                    m = store.mtime(name)
                    s = state.get(name) or {}
                    if s.get("mtime") != m and time.time() - m >= DEBOUNCE_S:
                        try:
                            publish(name)
                        except DesignError as e:
                            print(f"magpie: {name}: {e}", flush=True)
                            # remember so a broken design is not retried every 5 s
                            st = _load_state()
                            st.setdefault(name, {})["mtime"] = m
                            _save_state(st)
            except Exception as e:  # keep the thread alive
                print(f"magpie watcher: {e}", flush=True)
            time.sleep(interval)

    t = threading.Thread(target=loop, name="magpie-sync", daemon=True)
    t.start()
    return t
