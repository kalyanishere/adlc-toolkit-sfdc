#!/bin/sh
# ADLC sprint dashboard launcher — idempotent, silent on success.
# Spawned by /spec, /proceed, /sprint at the top of each invocation. If a
# dashboard is already running for this repo, prints the URL and exits.
# Otherwise starts the Node server in the background, writes a PID file,
# and prints the URL once.
set -e

REPO_ROOT="${ADLC_ROOT:-$(pwd)}"
RUNTIME_DIR="$REPO_ROOT/.adlc/runtime"
PID_FILE="$RUNTIME_DIR/sprint-dashboard.pid"
URL_FILE="$RUNTIME_DIR/sprint-dashboard.url"
LOG_FILE="$RUNTIME_DIR/sprint-dashboard.log"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_JS="$SCRIPT_DIR/server.js"
PORT="${ADLC_DASHBOARD_PORT:-5174}"

mkdir -p "$RUNTIME_DIR"

# Already running? Verify the PID is alive AND owns the port.
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
ADLC_ROOT="$REPO_ROOT" ADLC_DASHBOARD_PORT="$PORT" \
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
