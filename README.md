# Woodpecker

Design furniture and garage builds by talking to an agent, and watch the 3D model change.

```bash
.venv/bin/woodpecker serve      # open http://127.0.0.1:8790
```

Then either use the **Ask** tab in the viewer, or run `claude-home` in this folder (the
`woodpecker` MCP tools load from `.mcp.json`). Things to try: "make the base 650 deep",
click a part and ask "explain this", "give me the cut list", "will it tip if a kid pulls on
the TV?", "swap the base for a KALLAX".

## Viewer

| | |
|---|---|
| Views | 1–4 = 3D / Front / Side / Top (front, side and top are flat scale views with dimensions). Drag to orbit, right-drag to pan, scroll to zoom, F re-fits. |
| Select (V) | Click a part. Shift-click for several. Esc clears. The agent sees what you selected. |
| Move (G) | Drag an arrow. Snaps to the step chosen in the toolbar (1/10/50 mm). Copies move together. |
| Size (S) | Drag a handle to make a part longer, wider or thicker. Expressions are kept ("base_d" becomes "base_d + 60"). |
| Board (B) | Pick a material and orientation, click on the floor or a top face, click again. Snaps to nearby edges. Upright boards take one click and the height box. |
| + Product | Drop in a catalog product (IKEA KALLAX, BILLY, EKET, BESTÅ…). |
| Units | mm / cm / inches. Files stay in mm. Params accept `18`, `3/4"`, `1' 6"`, `45cm`. |
| Undo | ⌘Z. Reverts the last change, yours or the agent's. Delete key removes the selected part. |

Tabs: **Part** (what it does, joints, product info), **Params**, **Cut list** (cut list,
sheet and board layouts, bought items, hardware, cost), **Check** (overlaps, stock sizes,
tip stability, published load limits), **Ask** (chat with Claude). The cut list tab links to
a printable build sheet (`/print/<design>`).

## Catalog

`catalog/<brand>/*.json` holds bought products with the maker's published dimensions,
price, load limits and source URL. Anything the maker doesn't publish (usually panel
thickness) is listed under `assumed`, and the viewer shows it. Ask the agent to add a
product; it looks it up on the maker's site and adds it with `wp_catalog_add`.

## Tests

```bash
.venv/bin/pytest                 # model, cut list, catalog, edits
node tests/ui_smoke.mjs          # drives the viewer in headless Chrome (server must be running)
```

## Chat settings

The Ask tab runs `claude -p` with only the woodpecker tools plus web lookup. It finds
`~/.local/bin/claude` and uses `CLAUDE_CONFIG_DIR=~/.claude-home` when that exists.
Override with `WOODPECKER_CLAUDE`, `WOODPECKER_CLAUDE_CONFIG_DIR`, `WOODPECKER_CHAT_MODEL`.

See `AGENTS.md` for the design-file model and the code layout.
