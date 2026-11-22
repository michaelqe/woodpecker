# Woodpecker — agent instructions

Woodpecker is a woodworking / garage-building design tool built for talking to an agent.
A design is a JSON file of parametric parts (`designs/*.json`); the human watches it in a
3D viewer that reloads whenever the file changes, and asks you to change or explain it.
Magpie project: **Woodpecker** (`WOOD-n` tickets).

## Two kinds of work

**Designing** (the human wants a TV stand, a greenhouse, "make it wider", "explain this
bracket"): use the `woodpecker` MCP tools (`wp_*`, configured in `.mcp.json`). The server
sends its own rules as `instructions` (`INSTRUCTIONS` in `woodpecker/mcp_server.py`):
mm, x = width, y = depth (front y=0), z = up, `at` = where the part's local origin goes,
rotate/ends/repeat/mirror/cutouts, catalog `component`s, every part has a `role`, overlaps
only where a joint says so (`cut_into` makes the hole). "This" means `wp_get_selection`. Always
`wp_check` after edits, and say so if stability changed. Do not hand-edit design JSON while
the human is looking; the tools validate and keep undo history.

**Coding** (changing Woodpecker itself): see below.

## Layout

- `woodpecker/model.py` — load + resolve a design into world-space convex solids (safe expression evaluator, params, rotate/ends/repeat/mirror, components, joint cuts, checks). Python is the single source of geometry; the viewer draws `mesh` as sent.
- `woodpecker/geometry.py` — matrices, convex solids, volume/centroid, SAT overlap
- Placed designs: a part spec `{"design": "<name>"}` puts a whole other design in this one, live (`_resolve_design` in `model.py`; parts become `component` `design:<name>`, colours carried over, `at` = its min corner, cycles refused). `store.mtime` includes placed designs so the viewer reloads. Viewer: `+ Add` → Your designs; Duplicate = New with `copy_from`.
- `woodpecker/catalog.py` + `catalog/<brand>/*.json` — bought products (published dims + `assumed`), panel generators (`cube_grid`, `carcass`, `table`, `block`)
- `woodpecker/render.py` — server-side PNG drawings (numpy z-buffer, 5 views)
- `woodpecker/magpie.py` — one Magpie page per design, rewritten above `## Notes`; background sync in the server; off without `MAGPIE_API_TOKEN`
- `deploy/` — droplet deploy (port 8514, data in `~/woodpecker/data`, `deploy/deploy.sh`)
- `woodpecker/ikea.py` — live IKEA search/import through IKEA's unofficial web endpoints (see https://ingmar.dels.ink/ikea-openapi/); imports are saved to `catalog/ikea/`
- `woodpecker/cutlist.py` — cut list, stock (lumber first-fit, sheets guillotine layouts), bought items, hardware, cost (only given prices), tip check (floor hull)
- `woodpecker/chat.py` — the viewer's Ask tab: `claude -p` with only the woodpecker tools + web lookup, one resumed session per design
- `woodpecker/store.py` — the only writer: validated edits, atomic writes, undo history in `.woodpecker/history/`, selection in `.woodpecker/selection.json`
- `woodpecker/server.py` — stdlib HTTP server + CLI (`woodpecker serve|cutlist|check`)
- `woodpecker/mcp_server.py` — MCP tools (mcp 2.x `MCPServer`)
- `woodpecker/static/` — viewer: `app.js` (views, tools, panels, chat; Layers panel = part groups × materials, remembered per design in localStorage; nav pad, arrow/+/−/F/H keys and double-click focus move the camera and OrbitControls target together), `scene.js` (meshes, Manifold holes), `dims.js` (dimension lines), `units.js`, `layouts.js` (cut diagrams), `print.html/js` (build sheet). Vendored, no npm: three.js 0.170.0 (+ OrbitControls, TransformControls), manifold-3d 3.5.4 (WASM)
- `designs/` — design files (committed; they are the user's work)
- `scripts/house_model.py` → `designs/house.json` — our house (Magpie: House > Digital Twin, project 38), traced from the floor-plan photos. Generated: change the script and re-run it (`python3 scripts/house_model.py designs/`), never edit the design with the tools. `tests/test_house.py` checks the file is current and every room matches the plan's area. Electrical fixtures (sockets, switches, lights, outlets, thermostats, each with its circuit row from House > Electricity) are data in `scripts/house_electrical.py`, traced from the 2006 wiring drawings; `placed()` snaps wall items to the nearest real wall face of their room, clear of doors and windows. A design's `magpie_project` sends its page to that project instead of Woodpecker's. `shell_on_pad()` is the exterior massing for the garage/carport designs; after changing the house, also re-run `python3 scripts/garage_options.py designs/`
- `scripts/garage_options.py` → `designs/carport-*.json`, `garage-2car.json` — the four House > Garage (Proposed) options, including the house shell and the pad. Site frame is north-up like Google Maps: origin = pad SW = house SE, +x east, +y north (road at the top of Top view). Catalog cars are rotated 180° so noses point north; after that flip `at` is `cx + width/2`.
- `scripts/house_carport.py` → `designs/house-carport.json`, `house-carport-side-entrance.json` — the whole house (`interior_parts()`, no electrical, rotated by `to_site()`) beside option 1. The side-entrance design is a ground-floor concept (back hall, corridor, plant cupboard, smaller WC) passed in as a changed layout; `house_model.WALLS/ROOMS` stay the traced house. Re-run after changing either other script.

## Rules

- Keep deps minimal: Python stdlib + `mcp`. No npm, no bundler. Vendor JS files by URL with an exact version.
- UI is restrained dark Metro (black canvas, charcoal panels, cyan `#1ba1e2` only for selection/actions, no rounded corners, shadows or gradients).
- The viewer, the MCP server and the CLI all go through `store.py`; never write design files any other way.
- New design-file features must be reflected in: `model.py` (resolve + checks), the viewer (render), `INSTRUCTIONS`, and a test.

## Run

```bash
cd ~/Personal/Woodpecker
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/woodpecker serve          # http://127.0.0.1:8790
.venv/bin/pytest
node tests/ui_smoke.mjs             # with the server running; drives the viewer in headless Chrome
.venv/bin/woodpecker cutlist tv-cart
```

Restart `woodpecker serve` after Python changes (no auto-reload). The user's shell aliases
`claude` to a warning; the real command is `claude-home` (CLAUDE_CONFIG_DIR=~/.claude-home).

## Catalog rule

Only the maker's published numbers go in `catalog/`, with `url` and `retrieved`. Anything
else (panel thickness, shelf positions) goes in `assumed`. Never invent prices.
