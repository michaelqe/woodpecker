"""Live IKEA product lookups through IKEA's own (unofficial, undocumented) web endpoints.

Documented by the community at https://ingmar.dels.ink/ikea-openapi/ . Two calls:

- search:  https://sik.search.blue.cdtapps.com/{cc}/{lang}/search-result-page?q=...&types=PRODUCT
           name, type, "147x39x78 cm" size text, price, item number, product page URL.
- details: the product page (www.ikea.com/{cc}/{lang}/p/...) embeds its data as JSON in
           <script type="text/hydrate">: width/depth/height, load limits, package weights,
           materials and the "good to know" notes.

`import_product` turns the details into a catalog item and saves it under catalog/ikea/,
so a design never depends on IKEA staying up. Only published numbers go in; the internal
structure (panel thickness, shelf count) is a guess by product type and is listed in
`assumed`. These endpoints are not a supported API and can change without notice.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import json
import os
import re
import time
import urllib.parse
import urllib.request

from . import catalog
from .model_errors import DesignError

SEARCH = "https://sik.search.blue.cdtapps.com/{cc}/{lang}/search-result-page"
PRODUCT_JSON = "https://www.ikea.com/{cc}/{lang}/products/{suffix}/{item}.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
TIMEOUT = 15
_cache: dict[str, tuple[float, object]] = {}
CACHE_S = 600


def market() -> tuple[str, str]:
    return (os.environ.get("WOODPECKER_IKEA_COUNTRY", "ee").lower(),
            os.environ.get("WOODPECKER_IKEA_LANGUAGE", "en").lower())


def _get(url: str) -> bytes:
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1]
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip",
                                               "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
    except urllib.error.HTTPError as e:
        raise DesignError(f"IKEA returned {e.code} for {url}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise DesignError(f"could not reach IKEA ({e}); the local catalog still works") from e
    _cache[url] = (time.time(), body)
    return body


def item_no(s: str) -> str:
    """'202.758.14', '20275814', 's99552177' or a product URL -> '20275814' / '99552177'."""
    s = s.strip()
    m = re.search(r"-s?(\d{8})/?(?:\?.*)?$", s) if "/" in s else None
    digits = m.group(1) if m else re.sub(r"[^\d]", "", s)
    if len(digits) != 8:
        raise DesignError(f"not an IKEA article number: {s!r} (expected 8 digits, like 202.758.14)")
    return digits


def article(no: str) -> str:
    return f"{no[:3]}.{no[3:6]}.{no[6:]}"


# ---------------------------------------------------------------- search

def search(q: str, size: int = 24) -> list[dict]:
    q = q.strip()
    if not q:
        return []
    cc, lang = market()
    url = SEARCH.format(cc=cc, lang=lang) + "?" + urllib.parse.urlencode(
        {"q": q, "types": "PRODUCT", "size": size, "c": "sr", "v": "20240110"})
    return parse_search(json.loads(_get(url)))


def parse_search(data: dict) -> list[dict]:
    items = (((data.get("searchResultPage") or {}).get("products") or {}).get("main") or {}).get("items") or []
    out = []
    for it in items:
        p = it.get("product") or {}
        if not p.get("itemNo"):
            continue
        price = p.get("salesPrice") or {}
        no = p["itemNo"]
        out.append({
            "item_no": no,
            "article": article(no),
            "combination": p.get("itemType") == "SPR",
            "name": p.get("name"),
            "type": p.get("typeName"),
            "variant": p.get("validDesignText"),
            "size_text": p.get("itemMeasureReferenceText"),
            "size_mm": size_from_text(p.get("itemMeasureReferenceText") or ""),
            "price": {"amount": price["numeral"], "currency": price.get("currencyCode", "EUR")}
                     if price.get("numeral") is not None else None,
            "url": p.get("pipUrl"),
            "image": p.get("mainImageUrl"),
            "category": p.get("filterClass"),
            "in_catalog": catalog.by_article(article(no)),
        })
    return out


def size_from_text(text: str) -> list[float] | None:
    """'147x39x78 cm' -> [1470, 390, 780] (IKEA's order is width x depth x height).
    Two numbers ('147x77 cm', width x height) give no depth, so None."""
    m = re.match(r"\s*([\d.,]+)x([\d.,]+)x([\d.,]+)\s*(cm|mm)", text)
    if not m:
        return None
    k = 10 if m.group(4) == "cm" else 1
    return [round(float(v.replace(",", ".")) * k, 1) for v in m.groups()[:3]]


# ---------------------------------------------------------------- product details

# Markets tried, in English, when the home market's page gives no assembled size for an article
# (IKEA Estonia lists none for some combinations, e.g. KIVIK 994.405.85, that Finland publishes).
OTHER_MARKETS = ("fi", "se", "nl", "gb")


def details(ref: str) -> dict:
    """Published facts for one product: measurements, loads, packages, materials, notes.
    When the home market's page has no width/depth/height, the same article's page in a
    neighbouring market fills in the measurements (`measurements_from` says which page)."""
    no = item_no(ref)
    url = ref if ref.startswith("http") else _pip_url(no)
    page = _get(url).decode("utf-8", "replace")
    d = parse_product_page(page, url, no)
    if wdh(d["measurements"]) is None:
        home = market()[0]
        for cc in OTHER_MARKETS:
            if cc == home:
                continue
            try:
                other_url = _pip_url(no, cc, "en", search_fallback=False)
                other = parse_product_page(_get(other_url).decode("utf-8", "replace"), other_url, no)
            except DesignError:
                continue
            if wdh(other["measurements"]) is not None:
                d["measurements"] = other["measurements"]
                for k in ("loads", "packages", "notes", "materials"):
                    d[k] = d[k] or other[k]
                d["measurements_from"] = other_url
                break
    return d


def wdh(meas: dict) -> tuple[float, float, float] | None:
    """Width, depth, height from IKEA's measurement names, or None. Sofas and corner units give
    "Max. width" / "Min. depth" / "Max. depth": the max values are the bounding box."""
    m: dict[str, float] = {}
    for k, v in meas.items():
        low = k.lower().strip()
        if low.startswith("min."):
            continue
        low = low.removeprefix("max.").strip()
        if low not in m or k.lower().startswith("max."):
            m[low] = v
    if "depth" in m:
        W, D = m.get("width") or m.get("length"), m["depth"]
    else:  # tables: length x width
        W, D = m.get("length"), m.get("width")
    H = m.get("height") or m.get("thickness")
    return (W, D, H) if W and D and H else None


def _pip_url(no: str, cc: str | None = None, lang: str | None = None, search_fallback: bool = True) -> str:
    if cc is None:
        cc, lang = market()
    for candidate in (no, f"s{no}"):  # plain articles, then combinations (SPR)
        try:
            data = json.loads(_get(PRODUCT_JSON.format(cc=cc, lang=lang, suffix=candidate[-3:], item=candidate)))
            if data.get("pipUrl"):
                return data["pipUrl"]
        except DesignError:
            continue
    found = [r for r in search(no, 5) if r["item_no"] == no] if search_fallback else []
    if found and found[0]["url"]:
        return found[0]["url"]
    raise DesignError(f"IKEA {cc.upper()} has no product {article(no)}")


def _hydrate(page: str, no: str) -> dict:
    """The page's embedded product data, or {} when it is missing or about another product
    (IKEA's combination pages sometimes embed an unrelated product's data)."""
    for m in re.finditer(r'<script type="text/hydrate"[^>]*>(.*?)</script>', page, re.S):
        if "productInformationSectionProps" in m.group(1):
            props = next(iter(json.loads(m.group(1)).values()))["loaderData"]["pageProps"]
            got = str((props.get("product") or {}).get("itemNo", "")).lstrip("s")
            return props if got == no else {}
    return {}


_CM = re.compile(r"([\d.,]+)\s*(cm|mm|m|kg)\b")


def _measure(text: str) -> tuple[float, str] | None:
    m = _CM.search(text or "")
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    unit = m.group(2)
    if unit == "cm":
        return v * 10, "mm"
    if unit == "m":
        return v * 1000, "mm"
    return v, unit


def parse_product_page(page: str, url: str, no: str) -> dict:
    props = _hydrate(page, no)
    info = props.get("productInformationSectionProps") or {}
    meas = info.get("measurementsProps") or {}
    out: dict = {"item_no": no, "article": article(no), "url": url, "measurements": {}, "loads": {},
                 "packages": [], "notes": [], "materials": [], "page_data": bool(props)}

    for m in meas.get("measurements") or []:
        name = (m.get("name") or "").strip()
        val = _measure(m.get("measure") or "")
        if not val:
            continue
        out["measurements"][name] = round(val[0], 1)
        low = name.lower()
        if "load" in low and val[1] == "kg":
            out["loads"][name] = val[0]

    pk = ((meas.get("packaging") or {}).get("contentProps") or {}).get("packages") or []
    for p in pk:
        vals = {}
        for g in p.get("measurementGroups") or []:
            for m in g.get("measurements") or []:
                if m.get("value") is not None:
                    vals[m.get("type")] = m["value"]
        qty = int((p.get("quantity") or {}).get("value") or 1)
        out["packages"].append({"name": p.get("name"), "item_no": p.get("itemNo"), "qty": qty, **vals})

    acc = ((info.get("productDetailsProps") or {}).get("accordionObject")) or {}
    for g in ((acc.get("goodToKnow") or {}).get("contentProps") or {}).get("goodToKnow") or []:
        if g.get("text"):
            out["notes"].append(g["text"])
    for grp in ((acc.get("materialsAndCare") or {}).get("contentProps") or {}).get("materials") or []:
        for m in grp.get("materials") or []:
            text = ": ".join(x for x in (m.get("ptype"), m.get("material")) if x)
            if text:
                out["materials"].append(text)

    prod = props.get("product") or {}
    out["name"] = prod.get("name") or ""
    typ, _, variant = (prod.get("description") or "").partition(",")  # "Shelving unit, white"
    out["type"], out["variant"] = typ.strip(), variant.strip()
    out["size_text"] = prod.get("itemMeasureReferenceText")
    price = prod.get("price")
    out["price"] = {"amount": float(price), "currency": prod.get("currencyCode") or "EUR"} \
        if isinstance(price, (int, float)) else None
    return out


# ---------------------------------------------------------------- catalog item

_STORAGE = ("bookcase", "shelving unit", "shelf unit", "cabinet", "tv bench", "tv unit", "chest",
            "sideboard", "storage", "wardrobe", "dresser", "drawer", "bench")


def to_catalog_item(d: dict, search_hit: dict | None = None) -> dict:
    """Catalog entry from published details. Raises if IKEA gives no W/D/H."""
    W, D, H = wdh(d["measurements"]) or (None, None, None)
    fallback = False
    if not (W and D and H):
        hint = size_from_text(d.get("size_text") or "") or (search_hit or {}).get("size_mm")
        if hint:
            W, D, H = hint
            fallback = True
        else:
            label = d.get("size_text") or (search_hit or {}).get("size_text")
            raise DesignError(
                f"IKEA publishes no width/depth/height for {d['article']} "
                f"(got {', '.join(d['measurements']) or label or 'nothing'}). Combinations often only "
                "have a 2-number label; add the plain unit(s) it is made of instead, or add it by hand")
    name = d.get("name") or (search_hit or {}).get("name") or "IKEA product"
    typ = d.get("type") or (search_hit or {}).get("type") or ""
    variant = d.get("variant") or (search_hit or {}).get("variant") or ""
    full = ", ".join(x for x in (f"{name} {typ.lower()}".strip(), variant,
                                 f"{_cm(W)}x{_cm(D)}x{_cm(H)} cm") if x)

    loads = {}
    for k, v in d["loads"].items():
        low = k.lower()
        key = "per_shelf_kg" if "shelf" in low else "per_drawer_kg" if "drawer" in low else \
            "top_kg" if "top" in low else \
            (re.sub(r"[^a-z]+", "_", low.replace("max. load", "")).strip("_") or "max_load") + "_kg"
        loads[key] = v
    for n in d["notes"]:
        t = re.search(r"max(?:imum)? load of ([\d.,]+) kg on the top", n, re.I)
        if t:
            loads.setdefault("top_kg", float(t.group(1).replace(",", ".")))

    pkg = [p for p in d["packages"] if p.get("weight") is not None]
    package_kg = round(sum(p["weight"] * p.get("qty", 1) for p in pkg), 2) if pkg else None
    material = "; ".join(d["materials"])

    geometry, assumed = guess_geometry(name, typ, d.get("url", ""), W, D, H)
    if fallback:
        assumed.append("size from IKEA's size label only (the product page had no detailed "
                       "measurements); loads and weight not read")
    if d.get("measurements_from"):
        assumed.append(f"measurements from IKEA's page in another country ({d['measurements_from']}): "
                       "the home market's page publishes none for this article")
    if d.get("blocked"):
        assumed.append("IKEA refused the product page to this server, so only its search result was used: "
                       "name, price and size label; no loads, materials or weight")
    if package_kg is None:
        assumed.append("weight unknown (IKEA lists no package weight)")
    item = {
        "id": f"ikea-{_slug(name)}-{_slug(typ)}-{d['item_no']}".replace("--", "-"),
        "brand": "IKEA",
        "category": (search_hit or {}).get("category") or typ.lower(),
        "name": full,
        "article": d["article"],
        "url": d["url"],
        "retrieved": _dt.date.today().isoformat(),
        "source": "ikea.com product page (unofficial endpoints)",
        "price": d.get("price") or (search_hit or {}).get("price"),
        "size": [W, D, H],
        "load": loads,
        "package_kg": package_kg,
        "material": material,
        "measurements": d["measurements"],
        "notes": d["notes"],
        "geometry": geometry,
        "assumed": assumed,
        "color": _color(variant),
    }
    if "honeycomb" in material.lower():
        item["construction"] = ("Panels have a paper honeycomb core. Screws into the panel faces barely "
                                "hold: bolt right through with large washers, or sandwich the unit "
                                "between plywood plates and fasten to those.")
    return {k: v for k, v in item.items() if v not in (None, "", [], {})}


def guess_geometry(name: str, typ: str, url: str, W, D, H) -> tuple[dict, list[str]]:
    n, t = name.upper(), typ.lower()
    if n == "KALLAX" and "shelving unit" in t and "underframe" not in url:
        cols, rows = max(1, round(W / 375)), max(1, round(H / 375))
        return ({"generator": "cube_grid", "cols": cols, "rows": rows, "panel": 38},
                [f"{cols}x{rows} cubes worked out from the size", "panel thickness 38 mm (not published; measure yours)",
                 "inserts, drawers and doors are not drawn"])
    if "table" in t or t == "desk":
        return ({"generator": "table", "top": 40, "leg": 50},
                ["drawn as a top on 4 legs: 40 mm top, 50 mm square legs (not published)"])
    if any(k in t for k in _STORAGE):
        return ({"generator": "carcass", "panel": 16, "back": 3, "shelves": 0},
                ["drawn as a plain box: 16 mm panels, 3 mm back, no shelves (IKEA does not publish "
                 "the inside; check the assembly instructions)"])
    return ({"generator": "block"}, ["drawn as a solid block of the published size"])


def import_product(ref: str) -> dict:
    """Fetch, convert and save one product. Returns the catalog summary.
    An article that is already in the catalog is kept as it is (it may hold measured numbers)."""
    no = item_no(ref)
    existing = catalog.by_article(article(no))
    if existing:
        return {**catalog.summary(catalog.get(existing)), "already_in_catalog": True}
    hit = next((h for h in _safe_search(no) if h["item_no"] == no), None)
    try:
        d = details(ref)
    except DesignError as e:
        if "returned 403" not in str(e):
            raise
        # IKEA blocks product pages from data-centre addresses (the droplet); its search still answers.
        if not (hit and hit.get("size_mm")):
            what = f"{hit['name']} {hit.get('type') or ''}".strip() if hit else article(no)
            raise DesignError(
                f"IKEA blocks its product pages from this server, and its search gives no size for {what}. "
                "Import it from Woodpecker on the Mac (IKEA answers there), or ask in the Ask tab: "
                "\"add IKEA " + article(no) + " to the catalog, W x D x H cm\" with the size from the IKEA page.") from None
        d = {"item_no": no, "article": article(no), "url": hit.get("url") or ref, "measurements": {}, "loads": {},
             "packages": [], "notes": [], "materials": [], "page_data": False, "name": "", "type": "",
             "variant": "", "size_text": hit.get("size_text"), "price": None, "blocked": True}
    item = to_catalog_item(d, hit)
    return catalog.add(item)


def _safe_search(q):
    try:
        return search(q, 5)
    except DesignError:
        return []


def _cm(mm) -> str:
    return f"{mm / 10:g}"


def _slug(s: str) -> str:
    s = s.lower().translate(str.maketrans("åäöüéè", "aaouee"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40]


_COLORS = {"white": "#e9e7e2", "black": "#3a3633", "brown": "#5a4636", "oak": "#c8a77a", "birch": "#d9c3a0",
           "grey": "#9a9a96", "gray": "#9a9a96", "beige": "#d8cbb4", "green": "#7d8f73", "blue": "#6f86a0",
           "pine": "#d6b98a", "walnut": "#6b4c35"}


def _color(variant: str) -> str:
    v = variant.lower()
    for k, c in _COLORS.items():
        if k in v:
            return c
    return "#d9d4cc"
