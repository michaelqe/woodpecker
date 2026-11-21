# Woodpecker

Design furniture and garage builds by talking to an agent, and watch the 3D model change.

```bash
.venv/bin/woodpecker serve      # open http://127.0.0.1:8790
claude                          # in this folder; the woodpecker MCP tools load from .mcp.json
```

Then: "make the base 650 deep", click a part and ask "explain this", "give me the cut
list", "will it tip if a kid pulls on the TV?".

In the viewer: drag to orbit, right-drag to pan, scroll to zoom. 1–4 switch 3D / Front /
Side / Top, Esc clears the selection, F re-fits. Edit params in the Params tab (numbers or
expressions, Enter to apply). Undo reverts the last change, yours or the agent's.

See `AGENTS.md` for the design-file model and the code layout.
