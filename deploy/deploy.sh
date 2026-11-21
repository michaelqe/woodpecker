#!/usr/bin/env bash
# Deploy Woodpecker to the droplet from any host with SSH access.
#
#   deploy/deploy.sh
#
# Code: allowlist sync of woodpecker/, deploy/, pyproject.toml, docs.
# Data: ~/woodpecker/data (designs, catalog, chat, undo history, Magpie page ids) is the
# shared copy both users see. designs/ and catalog/ from the repo are copied in only
# where a file does not exist yet, so nothing edited on the site is overwritten.
# First time: also writes ~/woodpecker/.env (Magpie token read from ~/magpie/.env on the
# droplet itself) and asks you to run `sudo ~/woodpecker/deploy/install.sh` there.
#
# Optional env:
#   WOODPECKER_DEPLOY_HOST  override SSH target (default michael@running.app.kennedy.ee)
set -euo pipefail

HOST="${WOODPECKER_DEPLOY_HOST:-michael@running.app.kennedy.ee}"
SSH_OPTS=(-o BatchMode=yes)
if ! getent hosts running.app.kennedy.ee >/dev/null 2>&1 \
   && ! dig +short +time=2 +tries=1 running.app.kennedy.ee A >/dev/null 2>&1; then
  SSH_OPTS+=(-o HostName=142.93.133.110)
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE='~/woodpecker'
RSH="ssh ${SSH_OPTS[*]}"

cd "$ROOT"
SHA="$(git rev-parse HEAD)"
if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
  echo "deploy: warning: working tree is dirty; rsync sends local allowlisted files as-is" >&2
fi

echo "deploy: code → $HOST:$REMOTE"
rsync -az --delete -e "$RSH" \
  --exclude '__pycache__/' --exclude '*.pyc' --exclude '.DS_Store' --exclude '*.egg-info/' \
  --exclude '/woodpecker/BUILD_SHA' \
  --include '/woodpecker/' --include '/woodpecker/***' \
  --include '/deploy/' --include '/deploy/***' \
  --include '/pyproject.toml' --include '/README.md' --include '/AGENTS.md' \
  --exclude '*' \
  ./ "$HOST:$REMOTE/"

echo "deploy: new example designs and catalog items → $REMOTE/data (existing files untouched)"
ssh "${SSH_OPTS[@]}" "$HOST" "mkdir -p $REMOTE/data/designs $REMOTE/data/catalog"
rsync -az --ignore-existing -e "$RSH" --exclude '.DS_Store' designs/ "$HOST:$REMOTE/data/designs/"
rsync -az --ignore-existing -e "$RSH" --exclude '.DS_Store' catalog/ "$HOST:$REMOTE/data/catalog/"

ssh "${SSH_OPTS[@]}" "$HOST" "set -e
  cd $REMOTE
  if [[ ! -d .venv ]]; then python3.12 -m venv .venv; fi
  .venv/bin/pip install -q -e .
  echo '$SHA' > woodpecker/BUILD_SHA
  if [[ ! -f .env ]]; then
    token=\$(grep -E '^MAGPIE_API_TOKENS=' ~/magpie/.env | head -1 | cut -d= -f2- | cut -d, -f1 | tr -d '\"' || true)
    umask 077
    {
      echo 'WOODPECKER_HOME=/home/michael/woodpecker/data'
      echo 'WOODPECKER_PUBLIC_URL=https://woodpecker.app.kennedy.ee'
      echo 'MAGPIE_API_BASE=http://127.0.0.1:8509'
      echo 'MAGPIE_PUBLIC_URL=https://magpie.app.kennedy.ee'
      echo 'WOODPECKER_MAGPIE_PROJECT=37'
      echo \"MAGPIE_API_TOKEN=\$token\"
      echo '# Ask tab: claude CLI login to use (see README, Deploy)'
      echo 'WOODPECKER_CLAUDE_CONFIG_DIR=/home/michael/.claude-woodpecker'
    } > .env
    echo 'wrote .env (Magpie token taken from ~/magpie/.env)'
  fi
  if [[ ! -f /etc/systemd/system/woodpecker.service ]]; then
    echo 'code synced. FIRST-TIME SETUP still needed, in a real terminal on the droplet:'
    echo '  sudo ~/woodpecker/deploy/install.sh'
    exit 3
  fi
  if sudo -n systemctl restart woodpecker.service 2>/dev/null; then
    echo 'restarted woodpecker.service'
  else
    echo 'restart FAILED: old code is still running. Fix with: sudo ~/woodpecker/deploy/install.sh' >&2
    exit 1
  fi
  for i in \$(seq 1 30); do
    if curl -sf http://127.0.0.1:8514/api/health | grep -q '$SHA'; then
      echo 'health: ok ($SHA)'
      exit 0
    fi
    sleep 1
  done
  echo 'health: FAIL (expected $SHA)'
  exit 1
"
