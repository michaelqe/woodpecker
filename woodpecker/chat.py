"""Chat with Claude from the viewer: runs `claude -p` with only the woodpecker tools
(plus web lookup for catalog products), resuming one session per design.

Configure with env vars:
  WOODPECKER_CLAUDE             path to the claude binary (default ~/.local/bin/claude, else PATH)
  WOODPECKER_CLAUDE_CONFIG_DIR  CLAUDE_CONFIG_DIR for it (default ~/.claude-home if it exists)
  WOODPECKER_CHAT_MODEL         optional --model
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import store

CHAT_PROMPT = """\
You are the design assistant inside the Woodpecker viewer. The human is looking at the 3D
model, which reloads after each of your edits, so do not describe what they can already
see. Use the woodpecker tools (their instructions explain the model). Keep replies short and
plain: a few sentences or a short list. Give measurements in mm, adding inches in brackets
when the human uses inches. "This"/"that" means the selected parts named in the viewer
context line. For IKEA or other bought products use wp_catalog_search; if a product is
missing, look it up on the maker's own site (WebSearch/WebFetch) and add it with
wp_catalog_add using only published numbers, listing whatever you had to assume.
"""

_locks: dict[str, threading.Lock] = {}


def claude_bin() -> str | None:
    env = os.environ.get("WOODPECKER_CLAUDE")
    if env:
        return env
    local = Path.home() / ".local" / "bin" / "claude"
    if local.exists():
        return str(local)
    return shutil.which("claude")


def _env() -> dict:
    env = dict(os.environ)
    cfg = os.environ.get("WOODPECKER_CLAUDE_CONFIG_DIR")
    if not cfg:
        home = Path.home() / ".claude-home"
        cfg = str(home) if home.exists() else None
    if cfg:
        env["CLAUDE_CONFIG_DIR"] = cfg
    return env


def _state_file(design: str) -> Path:
    d = store.STATE / "chat"
    d.mkdir(parents=True, exist_ok=True)
    store.design_path(design)  # validates the name
    return d / f"{design}.json"


def history(design: str) -> dict:
    f = _state_file(design)
    if not f.exists():
        return {"session_id": None, "messages": []}
    return json.loads(f.read_text())


def _save(design: str, h: dict) -> None:
    _state_file(design).write_text(json.dumps(h, indent=1))


def reset(design: str) -> dict:
    f = _state_file(design)
    if f.exists():
        f.unlink()
    return {"ok": True}


def status() -> dict:
    b = claude_bin()
    return {"available": bool(b and Path(b).exists()), "binary": b}


def context_line(design: str, selection: list[str]) -> str:
    sel = ", ".join(selection) if selection else "nothing"
    return f"[Viewer context: design={design}; selected parts: {sel}]"


def stream(design: str, message: str, selection: list[str]):
    """Yield events: {"type": "text"|"tool"|"error"|"done", ...}."""
    b = claude_bin()
    if not b:
        yield {"type": "error", "text": "claude CLI not found (set WOODPECKER_CLAUDE)"}
        return
    lock = _locks.setdefault(design, threading.Lock())
    if not lock.acquire(blocking=False):
        yield {"type": "error", "text": "Still answering the previous message."}
        return
    try:
        h = history(design)
        h["messages"].append({"role": "user", "text": message, "at": time.time()})
        _save(design, h)
        cmd = [b, "-p", f"{context_line(design, selection)}\n{message}",
               "--output-format", "stream-json", "--verbose",
               "--mcp-config", str(store.ROOT / ".mcp.json"), "--strict-mcp-config",
               "--allowedTools", "mcp__woodpecker", "WebSearch", "WebFetch",
               "--append-system-prompt", CHAT_PROMPT]
        if os.environ.get("WOODPECKER_CHAT_MODEL"):
            cmd += ["--model", os.environ["WOODPECKER_CHAT_MODEL"]]
        if h.get("session_id"):
            cmd += ["--resume", h["session_id"]]
        proc = subprocess.Popen(cmd, cwd=store.ROOT, env=_env(), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, bufsize=1)
        reply = []
        for line in proc.stdout:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t == "system" and ev.get("session_id"):
                h["session_id"] = ev["session_id"]
            elif t == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if block.get("type") == "text" and block.get("text", "").strip():
                        reply.append(block["text"])
                        yield {"type": "text", "text": block["text"]}
                    elif block.get("type") == "tool_use":
                        yield {"type": "tool", "name": block.get("name", "").replace("mcp__woodpecker__", "")}
            elif t == "result":
                if ev.get("session_id"):
                    h["session_id"] = ev["session_id"]
                if ev.get("is_error"):
                    yield {"type": "error", "text": str(ev.get("result") or "error")}
        proc.wait(timeout=10)
        if proc.returncode and not reply:
            err = (proc.stderr.read() or "").strip()[-500:]
            yield {"type": "error", "text": err or f"claude exited with {proc.returncode}"}
        h["messages"].append({"role": "assistant", "text": "\n\n".join(reply), "at": time.time()})
        _save(design, h)
        yield {"type": "done"}
    finally:
        lock.release()
