# Woodpecker — agent instructions

Woodpecker is a woodworking / garage-building design tool built for talking to an agent.
A design is a JSON file of parametric parts (`designs/*.json`); the human watches it in a
3D viewer that reloads whenever the file changes, and asks you to change or explain it.
Magpie project: **Woodpecker** (`WOOD-n` tickets).

## Two kinds of work

**Designing** (the human wants a TV stand, a greenhouse, "make it wider", "explain this
bracket"): use the `woodpecker` MCP tools (`wp_*`, configured in `.mcp.json`). The server
sends its own rules as `instructions` (`INSTRUCTIONS` in `woodpecker/mcp_server.py`):
mm, x = width, y = depth (front y=0), z = up, `at` = minimum corner, every part has a
`role`, overlaps only where a joint says so. "This" means `wp_get_selection`. Always
`wp_check` after edits, and say so if stability changed. Do not hand-edit design JSON while
the human is looking; the tools validate and keep undo history.

**Coding** (changing Woodpecker itself): see below.

## Layout

- `woodpecker/model.py` — load + resolve a design (safe expression evaluator, params, parts, checks)
- `woodpecker/cutlist.py` — cut list, stock to buy (lumber: first-fit; sheets: area estimate), hardware, stability/tip check
- `woodpecker/store.py` — the only writer: validated edits, atomic writes, undo history in `.woodpecker/history/`, selection in `.woodpecker/selection.json`
- `woodpecker/server.py` — stdlib HTTP server + CLI (`woodpecker serve|cutlist|check`)
- `woodpecker/mcp_server.py` — MCP tools (mcp 2.x `MCPServer`)
- `woodpecker/static/` — viewer: vanilla JS + vendored three.js 0.170.0 (`vendor/`, no npm)
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
.venv/bin/woodpecker cutlist tv-cart
```
