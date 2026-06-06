#!/bin/sh
# ADLC sprint dashboard launcher — idempotent, silent on success.
# Spawned by /spec, /proceed, /sprint at the top of each invocation.
#
# Behavior:
#   1. Upsert the current repo into ~/.adlc/dashboard-registry.json so the
#      running server picks it up on its next poll (~1.5s).
#   2. If a dashboard server is already running for this machine, print the
#      URL and exit. Otherwise start the Node server in the background.
#
# Runtime files (PID, URL, port, log) live under ~/.adlc/runtime/ — the
# server is shared across all projects on this host, not per-repo.
set -e

REPO_ROOT="${ADLC_ROOT:-$(pwd)}"
HOME_RUNTIME="$HOME/.adlc/runtime"
PID_FILE="$HOME_RUNTIME/sprint-dashboard.pid"
URL_FILE="$HOME_RUNTIME/sprint-dashboard.url"
LOG_FILE="$HOME_RUNTIME/sprint-dashboard.log"
REGISTRY_FILE="$HOME/.adlc/dashboard-registry.json"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_JS="$SCRIPT_DIR/server.js"
PORT="${ADLC_DASHBOARD_PORT:-5174}"

mkdir -p "$HOME_RUNTIME" "$HOME/.adlc"

# Upsert this repo into the dashboard registry. Done before any early-exit
# so an already-running server still picks up new projects.
if command -v node >/dev/null 2>&1; then
  REPO_ROOT="$REPO_ROOT" REGISTRY_FILE="$REGISTRY_FILE" node -e '
    const fs = require("fs");
    const path = require("path");
    const file = process.env.REGISTRY_FILE;
    const root = process.env.REPO_ROOT;
    if (!root) process.exit(0);
    let data = { roots: [] };
    try {
      const raw = fs.readFileSync(file, "utf8");
      const parsed = JSON.parse(raw);
      if (parsed && Array.isArray(parsed.roots)) data = parsed;
    } catch (_) {}
    const idx = data.roots.findIndex((r) => r && r.path === root);
    const entry = {
      path: root,
      name: path.basename(root),
      registeredAt: idx >= 0 && data.roots[idx].registeredAt
        ? data.roots[idx].registeredAt
        : new Date().toISOString(),
    };
    if (idx >= 0) data.roots[idx] = entry; else data.roots.push(entry);
    fs.writeFileSync(file, JSON.stringify(data, null, 2) + "\n");
  ' 2>/dev/null || true
fi

# Already running? Verify the PID is alive.
if [ -f "$PID_FILE" ]; then
  EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    if [ -f "$URL_FILE" ]; then
      echo "[sprint-dashboard] already running: $(cat "$URL_FILE")"
    else
      echo "[sprint-dashboard] already running (pid $EXISTING_PID)"
    fi
    exit 0
  fi
  rm -f "$PID_FILE" "$URL_FILE" 2>/dev/null || true
fi

if ! command -v node >/dev/null 2>&1; then
  echo "[sprint-dashboard] node not on PATH — skipping dashboard launch" >&2
  exit 0
fi

if [ ! -f "$SERVER_JS" ]; then
  echo "[sprint-dashboard] server.js not found at $SERVER_JS — skipping" >&2
  exit 0
fi

# Spawn detached. nohup + & so the server outlives the shell that launched it.
ADLC_DASHBOARD_PORT="$PORT" \
  nohup node "$SERVER_JS" >>"$LOG_FILE" 2>&1 &
LAUNCHED_PID=$!
disown "$LAUNCHED_PID" 2>/dev/null || true

# Wait briefly for the server to write its URL file (max ~3s).
i=0
while [ $i -lt 30 ]; do
  if [ -f "$URL_FILE" ]; then
    echo "[sprint-dashboard] launched: $(cat "$URL_FILE")"
    exit 0
  fi
  sleep 0.1
  i=$((i + 1))
done

# Fell through — server didn't come up. Don't fail the parent skill.
echo "[sprint-dashboard] launch attempted (pid $LAUNCHED_PID), URL not yet ready — see $LOG_FILE" >&2
exit 0
