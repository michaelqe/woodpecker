# Woodpecker

Design furniture and garage builds by talking to an agent, and watch the 3D model change.

Live at **https://woodpecker.app.kennedy.ee** (shared login; both users see the same designs
and product catalog). Each design has a page in Magpie (project Woodpecker) with drawings
from 5 angles, the shopping list, cut list, parameters and tip check, kept up to date.

```bash
.venv/bin/woodpecker serve      # open http://127.0.0.1:8790
```

Then either use the **Ask** tab in the viewer, or run `claude-home` in this folder (the
`woodpecker` MCP tools load from `.mcp.json`). Things to try: "make the base 650 deep",
click a part and ask "explain this", "give me the cut list", "will it tip if a kid pulls on
the TV?", "swap the base for a KALLAX".

## New designs

**New** (next to the design list) starts a blank design, already stocked with common plywood
and timber, or a copy of an existing one. Describe what you want to build and the agent
starts on it in the Ask tab. A Magpie page is made for it straight away.

## Magpie pages

Woodpecker rewrites everything above the page's **Notes** heading about 20 seconds after a
design stops changing (or at once with **Publish to Magpie now** in the Cut list tab, or the
agent's `wp_publish`). Write under Notes; that part is kept. Pictures are drawn on the server
(`woodpecker/render.py`, numpy + Pillow; holes from joints are not shown there) and are also
at `/api/designs/<name>/render/<3d|3d-back|front|side|top>`. The agent can save them with
`wp_export_images`. Publishing is on only where `MAGPIE_API_TOKEN` is set (the droplet), so a
laptop copy never makes duplicate pages.

## Viewer

| | |
|---|---|
| Views | 1–4 = 3D / Front / Side / Top (front, side and top are flat scale views with dimensions). Drag to orbit, right-drag to pan, scroll to zoom, F re-fits. |
| Select (V) | Click a part. Shift-click for several. Esc clears. The agent sees what you selected. |
| Move (G) | Drag an arrow. Snaps to the step chosen in the toolbar (1/10/50 mm). Copies move together. |
| Size (S) | Drag a handle to make a part longer, wider or thicker. Expressions are kept ("base_d" becomes "base_d + 60"). |
| Board (B) | Pick a material and orientation, click on the floor or a top face, click again. Snaps to nearby edges. Upright boards take one click and the height box. |
| + Product | Drop in a bought product. Searches your catalog and, live, IKEA's shop; picking an IKEA result imports it. |
| Units | mm / cm / inches. Files stay in mm. Params accept `18`, `3/4"`, `1' 6"`, `45cm`. |
| Undo | ⌘Z. Reverts the last change, yours or the agent's. Delete key removes the selected part. |

Tabs: **Part** (what it does, joints, product info), **Params**, **Cut list** (cut list,
sheet and board layouts, bought items, hardware, cost), **Check** (overlaps, stock sizes,
tip stability, published load limits), **Ask** (chat with Claude). The cut list tab links to
a printable build sheet (`/print/<design>`).

## Catalog

`catalog/<brand>/*.json` holds bought products with the maker's published dimensions,
price, load limits and source URL. Anything the maker doesn't publish (usually panel
thickness) is listed under `assumed`, and the viewer shows it.

**IKEA, live.** The product picker and the agent (`wp_ikea_search`, `wp_ikea_import`) search
IKEA's shop through its unofficial web endpoints (documented at
https://ingmar.dels.ink/ikea-openapi/). Importing reads the product page: width, depth,
height, load limits, package weights, materials, price and notes. It saves them as a catalog
file, so designs keep working if IKEA changes its site. What IKEA does not publish (panel
thickness, the inside layout) is guessed from the product type and listed in `assumed`;
edit the file if you measure. Combinations whose label has only two numbers ("147x77 cm")
are refused: add the plain units instead. The market is Estonia in English; change it with
`WOODPECKER_IKEA_COUNTRY` / `WOODPECKER_IKEA_LANGUAGE` (e.g. `us` / `en`). These endpoints
are not a supported API and can break.

For other makers, ask the agent to add the product from the maker's page (`wp_catalog_add`).

## Tests

```bash
.venv/bin/pytest                 # model, cut list, catalog, edits, IKEA parsing (offline)
WOODPECKER_LIVE=1 .venv/bin/pytest tests/test_ikea.py   # one real IKEA search and import
node tests/ui_smoke.mjs          # drives the viewer in headless Chrome (server must be running)
```

## Chat settings

The Ask tab runs `claude -p` with only the woodpecker tools plus web lookup. It finds
`~/.local/bin/claude` and uses `CLAUDE_CONFIG_DIR=~/.claude-home` when that exists.
Override with `WOODPECKER_CLAUDE`, `WOODPECKER_CLAUDE_CONFIG_DIR`, `WOODPECKER_CHAT_MODEL`.

See `AGENTS.md` for the design-file model and the code layout.

## Deploy

```bash
deploy/deploy.sh      # from the Mac: code to ~/woodpecker, restart, health check
```

The droplet runs `woodpecker serve` on 127.0.0.1:8514 behind Caddy forward-auth
(`deploy/Caddyfile.snippet`). Shared data lives in `~/woodpecker/data` (designs, catalog, chat,
undo history, page ids). Deploys add new example designs and catalog files there but never
overwrite ones edited on the site. First time only, in a real terminal on the droplet:
`sudo ~/woodpecker/deploy/install.sh` (unit, Caddy block, restart rule).

The Ask tab needs a working `claude` login on the droplet, kept separate from the droplet's
default one: `CLAUDE_CONFIG_DIR=~/.claude-woodpecker ~/.local/bin/claude` then `/login`
(or put `ANTHROPIC_API_KEY=...` in `~/woodpecker/.env`). Both users' chats run on that login.
