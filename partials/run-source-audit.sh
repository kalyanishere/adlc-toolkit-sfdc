#!/bin/sh
# run-source-audit.sh — invoke the source-only Salesforce code audit and
# return its exit code. Sourced by /reflect Phase 5a and the /proceed gate.
#
# Reads policy from .adlc/config.yml under the `audit:` block:
#   audit.enabled       (true|false; default true)
#   audit.fail_on       (severity list, default CRITICAL,HIGH; NONE = advise-only)
#   audit.scope         (diff|full; default diff)
#   audit.skip_paths    (YAML list; default empty)
#   audit.report_dir    (default .adlc/runtime/audit)
#
# Resolves the audit tool from (in order):
#   1) $ADLC_AUDIT_TOOL_DIR (env override)
#   2) .adlc/tools/sf-code-audit/  (consumer-local copy)
#   3) $TOOLKIT_HOME/tools/sf-code-audit/  (toolkit fallback)
#
# Exit codes mirror audit_source.py:
#   0 — gate passed (or disabled)
#   1 — gate failed (one or more fail_on severities had findings)
#   2 — config / tool resolution error

set -e

CFG=".adlc/config.yml"
if [ ! -f "$CFG" ]; then
  echo "[audit] $CFG not found — skipping (run /init first)."
  exit 0
fi

# YAML reader (single-line scalars under audit:).
yaml_get() {
  key="$1"
  awk -v key="$key" '
    /^audit:/                      { in_audit=1; next }
    in_audit && /^[^[:space:]#]/   { in_audit=0 }
    in_audit && $0 ~ "^[[:space:]]+" key ":" {
      sub("^[[:space:]]+" key ":[[:space:]]*", "")
      gsub(/^["'\'']/, ""); gsub(/["'\'']$/, "")
      sub(/[[:space:]]*#.*$/, "")
      print
      exit
    }
  ' "$CFG"
}

ENABLED=$(yaml_get enabled)
[ -z "$ENABLED" ] && ENABLED="true"
case "$ENABLED" in
  false|False|FALSE|no|No|NO|0)
    echo "[audit] disabled in $CFG (audit.enabled=false) — skipping."
    exit 0
    ;;
esac

FAIL_ON=$(yaml_get fail_on)
[ -z "$FAIL_ON" ] && FAIL_ON="CRITICAL,HIGH"

SCOPE=$(yaml_get scope)
[ -z "$SCOPE" ] && SCOPE="diff"

REPORT_DIR=$(yaml_get report_dir)
[ -z "$REPORT_DIR" ] && REPORT_DIR=".adlc/runtime/audit"
mkdir -p "$REPORT_DIR"

# Resolve the audit tool dir.
if [ -n "${ADLC_AUDIT_TOOL_DIR:-}" ] && [ -f "$ADLC_AUDIT_TOOL_DIR/audit_source.py" ]; then
  AUDIT_DIR="$ADLC_AUDIT_TOOL_DIR"
elif [ -f ".adlc/tools/sf-code-audit/audit_source.py" ]; then
  AUDIT_DIR=".adlc/tools/sf-code-audit"
elif [ -n "${TOOLKIT_HOME:-}" ] && [ -f "$TOOLKIT_HOME/tools/sf-code-audit/audit_source.py" ]; then
  AUDIT_DIR="$TOOLKIT_HOME/tools/sf-code-audit"
else
  echo "[audit] ERROR: cannot locate audit_source.py."
  echo "  Looked under \$ADLC_AUDIT_TOOL_DIR, .adlc/tools/sf-code-audit/, and \$TOOLKIT_HOME/tools/sf-code-audit/."
  echo "  Re-run /init to copy the audit tool into .adlc/tools/sf-code-audit/."
  exit 2
fi

# Build the diff list when scope=diff.
DIFF_FLAG=""
if [ "$SCOPE" = "diff" ]; then
  if git rev-parse --git-dir >/dev/null 2>&1; then
    BASE=$(git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD main 2>/dev/null || true)
    DIFF_FILE="$REPORT_DIR/diff-files.txt"
    if [ -n "$BASE" ]; then
      git diff --name-only --diff-filter=ACMR "$BASE"...HEAD > "$DIFF_FILE" 2>/dev/null || true
      # Add unstaged + staged work-tree changes too.
      git diff --name-only --diff-filter=ACMR >> "$DIFF_FILE" 2>/dev/null || true
      git diff --name-only --diff-filter=ACMR --cached >> "$DIFF_FILE" 2>/dev/null || true
    else
      git diff --name-only --diff-filter=ACMR HEAD > "$DIFF_FILE" 2>/dev/null || true
    fi
    # Dedupe.
    if [ -s "$DIFF_FILE" ]; then
      sort -u "$DIFF_FILE" -o "$DIFF_FILE"
      DIFF_FLAG="--files-from $DIFF_FILE"
      echo "[audit] scope=diff ($(wc -l < "$DIFF_FILE" | tr -d ' ') changed files)"
    else
      echo "[audit] scope=diff but no changed files — skipping."
      exit 0
    fi
  else
    echo "[audit] scope=diff but not in a git repo — falling back to full scan."
  fi
fi

JSON_OUT="$REPORT_DIR/source-audit.json"
MD_OUT="$REPORT_DIR/source-audit.md"

# Prefer the project-local venv (created by /init Step 7.8 — has all org-mode
# deps). Falls back to system python3 when the venv is missing or stale. The
# source-only audit_source.py is stdlib-only so either Python works.
PY_BIN=""
for cand in "$AUDIT_DIR/.venv/bin/python" ".adlc/tools/sf-code-audit/.venv/bin/python" "python3"; do
  if [ -x "$cand" ] || command -v "$cand" >/dev/null 2>&1; then
    PY_BIN="$cand"
    break
  fi
done
if [ -z "$PY_BIN" ]; then
  echo "[audit] ERROR: no python3 interpreter available."
  echo "  Install Python 3.8+ and re-run /init to provision the audit tool venv."
  exit 2
fi

echo "[audit] running source-only audit (fail_on=$FAIL_ON, scope=$SCOPE, py=$PY_BIN)..."
set +e
"$PY_BIN" "$AUDIT_DIR/audit_source.py" \
  --root . \
  --fail-on "$FAIL_ON" \
  --json-out "$JSON_OUT" \
  --md-out "$MD_OUT" \
  $DIFF_FLAG
RC=$?
set -e

if [ "$RC" -eq 0 ]; then
  echo "[audit] PASS — report: $MD_OUT"
elif [ "$RC" -eq 1 ]; then
  echo "[audit] FAIL — $FAIL_ON-severity findings present. See $MD_OUT for details."
else
  echo "[audit] ERROR (rc=$RC). See output above."
fi

exit $RC
