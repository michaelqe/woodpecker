#!/usr/bin/env bash
# One-time (and re-runnable) system setup for Woodpecker on the droplet.
# Needs root, from a real terminal:
#
#   sudo ~/woodpecker/deploy/install.sh
#
# Idempotent: systemd unit, Caddy site block, sudoers restart rule.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
USER_NAME="${SUDO_USER:-michael}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
CADDYFILE=/etc/caddy/Caddyfile
MARKER="# --- woodpecker (deploy/Caddyfile.snippet) ---"
UNIT=woodpecker.service

[[ -x "$REPO/.venv/bin/woodpecker" ]] || { echo "missing $REPO/.venv; run deploy/deploy.sh from a dev machine first" >&2; exit 1; }

echo "== systemd unit"
install -m 644 "$HERE/$UNIT" "/etc/systemd/system/$UNIT"
systemctl daemon-reload
systemctl enable --now "$UNIT"
systemctl restart "$UNIT"
echo "  $UNIT"

echo "== caddy"
backup="$CADDYFILE.bak-pre-woodpecker-$(date +%Y%m%d-%H%M%S)"
cp -p "$CADDYFILE" "$backup"
python3 - "$CADDYFILE" "$HERE/Caddyfile.snippet" "$MARKER" <<'PY'
import sys
from pathlib import Path

caddy_path, snippet_path, marker = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
text = caddy_path.read_text(encoding="utf-8")
snippet = snippet_path.read_text(encoding="utf-8")
snippet = snippet[snippet.index(marker):].strip() + "\n"
if marker in text:
    start = text.index(marker)
    depth, end_rel = 0, None
    for i, ch in enumerate(text[start:]):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_rel = i + 1
                break
    if end_rel is None:
        raise SystemExit("could not find end of the Woodpecker Caddy site block")
    end = start + end_rel
    while end < len(text) and text[end] in "\r\n":
        end += 1
    new_text = text[:start] + snippet + text[end:]
else:
    new_text = text.rstrip() + "\n\n" + snippet
caddy_path.write_text(new_text, encoding="utf-8")
print("  wrote Woodpecker site block")
PY
if out="$(caddy validate --config "$CADDYFILE" --adapter caddyfile 2>&1)"; then
    systemctl reload caddy
    echo "  validated and reloaded (backup: $backup)"
else
    cp -p "$backup" "$CADDYFILE"
    echo "  validation FAILED; restored $backup. Output:" >&2
    echo "$out" | tail -8 >&2
    exit 1
fi

echo "== sudoers"
rule="/etc/sudoers.d/woodpecker"
tmp="$(mktemp)"
cat > "$tmp" <<RULE
# Installed by ~/woodpecker/deploy/install.sh: lets deploy.sh restart the service.
$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl restart woodpecker.service
RULE
if visudo -cf "$tmp" >/dev/null; then
    install -m 440 "$tmp" "$rule"
    echo "  $rule"
else
    echo "  sudoers rule failed to validate; not installed" >&2
fi
rm -f "$tmp"

echo "== state"
systemctl --no-pager --lines=0 status "$UNIT" | grep -E "^[^ ]|Active:" || true
sleep 1
curl -sf http://127.0.0.1:8514/api/health && echo
echo "  url:  https://woodpecker.app.kennedy.ee/"
