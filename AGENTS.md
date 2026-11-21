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
- `woodpecker/static/` — viewer: `app.js` (views, tools, panels, chat), `scene.js` (meshes, Manifold holes), `dims.js` (dimension lines), `units.js`, `layouts.js` (cut diagrams), `print.html/js` (build sheet). Vendored, no npm: three.js 0.170.0 (+ OrbitControls, TransformControls), manifold-3d 3.5.4 (WASM)
- `designs/` — design files (committed; they are the user's work)

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
