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
OPEN_BROWSER="${ADLC_DASHBOARD_OPEN:-0}"

mkdir -p "$HOME_RUNTIME" "$HOME/.adlc"

# Open the dashboard URL in the user's default browser (Chrome preferred on macOS).
# Best-effort, silent on failure — never fails the parent skill.
open_in_browser() {
  url="$1"
  [ -z "$url" ] && return 0
  case "$(uname -s)" in
    Darwin)
      # Try Chrome first; fall back to system default.
      open -a "Google Chrome" "$url" 2>/dev/null || open "$url" 2>/dev/null || true
      ;;
    Linux)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 || true
      fi
      ;;
    MINGW*|MSYS*|CYGWIN*)
      cmd.exe /c start "" "$url" >/dev/null 2>&1 || true
      ;;
  esac
}

# Skip registering the toolkit repo itself — it's the development surface
# (also symlinked at ~/.claude/skills), not a "project" that hosts REQs.
# The check: a project repo never contains tools/sprint-dashboard/launch.sh,
# but the toolkit always does. Honor explicit override via ADLC_FORCE_REGISTER=1.
SKIP_REGISTER=0
if [ "${ADLC_FORCE_REGISTER:-0}" != "1" ] && [ -f "$REPO_ROOT/tools/sprint-dashboard/launch.sh" ]; then
  SKIP_REGISTER=1
fi

# Upsert this repo into the dashboard registry. Done before any early-exit
# so an already-running server still picks up new projects.
if [ "$SKIP_REGISTER" = "0" ] && command -v node >/dev/null 2>&1; then
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

# Compute the URL suffix used when opening the browser. Defaults to the
# project just registered above (the launching repo is the natural focus
# of attention) so the dashboard lands on it instead of whichever project
# happened to be selected last in localStorage. Skipped when registration
# was skipped (e.g. running from inside the toolkit repo) or when the
# repo basename isn't usable.
PROJECT_QS=""
if [ "$SKIP_REGISTER" = "0" ]; then
  PROJECT_NAME="$(basename "$REPO_ROOT")"
  if [ -n "$PROJECT_NAME" ]; then
    # urlencode just spaces — the % sign and most other shell-safe chars
    # are tolerable in URLSearchParams. If a project name contains ?, &,
    # or #, the user has bigger problems than dashboard linking.
    PROJECT_QS="?project=$(printf '%s' "$PROJECT_NAME" | sed 's/ /%20/g')"
  fi
fi

# Already running? Verify the PID is alive.
if [ -f "$PID_FILE" ]; then
  EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    if [ -f "$URL_FILE" ]; then
      RUNNING_URL="$(cat "$URL_FILE")"
      echo "[sprint-dashboard] already running: ${RUNNING_URL}${PROJECT_QS}"
      [ "$OPEN_BROWSER" = "1" ] && open_in_browser "${RUNNING_URL}${PROJECT_QS}"
    else
      echo "[sprint-dashboard] already running (pid $EXISTING_PID)"
    fi
    exit 0
  fi
  rm -f "$PID_FILE" "$URL_FILE" 2>/dev/null || true
fi

if ! command -v node >/dev/null 2>&1; then
  cat >&2 <<EOF
[sprint-dashboard] FAILED: node not found on PATH.
  Install Node.js (v18+) to run the dashboard server. The skill registry
  was still updated, so the project will appear once a dashboard is
  running on this host.
EOF
  exit 0   # never fail the parent skill
fi

if [ ! -f "$SERVER_JS" ]; then
  cat >&2 <<EOF
[sprint-dashboard] FAILED: server.js not found at $SERVER_JS.
  This usually means ~/.claude/skills is not symlinked to your toolkit
  clone (run-from-anywhere expects it to be a symlink to adlc-toolkit-sfdc).
  Verify with:
    readlink ~/.claude/skills
  If empty or pointing somewhere unexpected, re-run the symlink step
  from the toolkit README ('Setup → 2. Symlink to Claude Code').
EOF
  exit 0
fi

# Pre-flight port check — emit a clear message if the configured port is
# already in use by something OTHER than our dashboard. (If our own dashboard
# is the user, the PID-file check above would have caught it; this catches
# port collisions with unrelated processes — e.g., another dev tool on 5174.)
if command -v lsof >/dev/null 2>&1; then
  PORT_HOG="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  if [ -n "$PORT_HOG" ]; then
    PORT_HOG_CMD="$(ps -p "$PORT_HOG" -o command= 2>/dev/null || echo unknown)"
    cat >&2 <<EOF
[sprint-dashboard] FAILED: port $PORT already in use by pid $PORT_HOG ($PORT_HOG_CMD).
  Either stop that process, or pick a different port:
    ADLC_DASHBOARD_PORT=5175 sh \$0
EOF
    exit 0
  fi
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
    LAUNCHED_URL="$(cat "$URL_FILE")"
    echo "[sprint-dashboard] launched: ${LAUNCHED_URL}${PROJECT_QS}"
    [ "$OPEN_BROWSER" = "1" ] && open_in_browser "${LAUNCHED_URL}${PROJECT_QS}"
    exit 0
  fi
  sleep 0.1
  i=$((i + 1))
done

# Fell through — server didn't come up in 3s. Differentiate "still booting"
# from "crashed on boot": if the spawned PID is dead, the server crashed and
# the user needs to see the log tail; if it's alive, the server is just slow
# and the URL file will appear shortly (rare but possible on cold-boot).
if ! kill -0 "$LAUNCHED_PID" 2>/dev/null; then
  cat >&2 <<EOF
[sprint-dashboard] FAILED: server crashed on boot (pid $LAUNCHED_PID is dead).
  Last few lines of $LOG_FILE:
EOF
  tail -20 "$LOG_FILE" 2>/dev/null | sed 's/^/  | /' >&2 || true
  cat >&2 <<EOF
  Common causes:
    • Port $PORT taken by another process — set ADLC_DASHBOARD_PORT
    • node version too old — server.js requires Node 18+
    • server.js syntax error — pull the latest toolkit
EOF
else
  echo "[sprint-dashboard] launch attempted (pid $LAUNCHED_PID), URL not yet ready — server may still be booting; check $LOG_FILE if no URL appears in a few seconds." >&2
fi
exit 0
