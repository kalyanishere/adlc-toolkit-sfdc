#!/bin/sh
# id-counter.sh — shortname-namespaced, per-project ADLC ID allocator.
#
# Replaces the legacy machine-global counters at ~/.claude/.global-next-{req,bug,lesson}
# with per-project counters at .adlc/.next-{req,bug,lesson}, namespaced by
# `project.shortname` from .adlc/config.yml. Allocated IDs use the format
# `<XYZ>-REQ-NNN`, `<XYZ>-BUG-NNN`, `<XYZ>-LESSON-NNN`.
#
# Source this file at the start of every fenced block that allocates an ID:
#
#   sh .adlc/partials/id-counter.sh 2>/dev/null || sh ~/.claude/skills/partials/id-counter.sh
#   . .adlc/partials/id-counter.sh 2>/dev/null || . ~/.claude/skills/partials/id-counter.sh
#   ID=$(allocate_req)        # → "SFC-REQ-001"
#
# Functions:
#   load_shortname           Echo `project.shortname` from .adlc/config.yml; hard-fail if missing.
#   allocate_req             Echo the next REQ id ("<XYZ>-REQ-NNN"); increment counter atomically.
#   allocate_bug             Echo the next BUG id ("<XYZ>-BUG-NNN"); increment counter atomically.
#   allocate_lesson          Echo the next LESSON id ("<XYZ>-LESSON-NNN"); increment counter atomically.
#
# All allocators use a POSIX `mkdir`-based lock with a `[ -L ]` symlink pre-check
# (LESSON-014), fail-loud guards on missing/empty counter inside the lock, and
# rely on the caller to guard `[ -n "$ID" ]` after `$(allocate_*)` because
# `exit 1` inside `$(...)` only terminates the subshell (LESSON-015).
#
# First-allocation bootstrap: when the counter file is absent, scan the project's
# .adlc/{specs,bugs,knowledge/lessons} for the highest existing ID — handling
# BOTH `<XYZ>-REQ-NNN` (new format) AND legacy `REQ-NNN` (un-namespaced) — and
# seed the counter at high-water + 1. Never reset to 1 if any artifact exists.

load_shortname() {
  if [ ! -f .adlc/config.yml ]; then
    echo "ERROR: .adlc/config.yml missing — run /init first." >&2
    return 1
  fi
  shortname=$(awk '
    /^project:/                  { in_project=1; next }
    in_project && /^[^[:space:]#]/ { in_project=0 }
    in_project && /^[[:space:]]+shortname:/ {
      sub(/^[[:space:]]+shortname:[[:space:]]*/, "")
      gsub(/["'\'']/, "")
      sub(/[[:space:]]*#.*$/, "")
      print
      exit
    }
  ' .adlc/config.yml)
  if [ -z "$shortname" ]; then
    echo "ERROR: project.shortname missing from .adlc/config.yml — required for ADLC ID allocation. Add a 3-uppercase-letter shortname under the 'project:' block (e.g., shortname: \"SFC\"). Run /init to set it interactively." >&2
    return 1
  fi
  case "$shortname" in
    [A-Z][A-Z][A-Z]) ;;
    *)
      echo "ERROR: project.shortname='$shortname' must be exactly 3 uppercase letters (^[A-Z]{3}\$)." >&2
      return 1
      ;;
  esac
  printf '%s' "$shortname"
}

# ---------------------------------------------------------------------------
# _allocate <kind> <counter-file> <scan-glob> <id-pattern>
# ---------------------------------------------------------------------------
# kind         — REQ | BUG | LESSON (used in the emitted id and error messages)
# counter-file — e.g., .adlc/.next-req
# scan-glob    — find expression for the artifact dir (used for first-run bootstrap)
# id-pattern   — grep -oE pattern that captures BOTH legacy `REQ-123` and
#                shortname-prefixed `XYZ-REQ-123` from artifact names
# ---------------------------------------------------------------------------
_allocate() {
  kind=$1
  counter=$2
  scan_path=$3
  id_pattern=$4

  shortname=$(load_shortname) || return 1

  lock="${counter}.lock.d"
  if [ -L "$lock" ]; then
    echo "ERROR: $lock is a symlink — refusing (TOCTOU risk). Inspect manually." >&2
    return 1
  fi

  # Acquire mkdir lock — atomic on POSIX, retries up to ~5s.
  i=0
  while [ "$i" -lt 50 ]; do
    if mkdir "$lock" 2>/dev/null; then
      break
    fi
    sleep 0.1
    i=$((i + 1))
  done
  if [ ! -d "$lock" ]; then
    echo "ERROR: failed to acquire $lock after 50 retries — aborting to avoid duplicate $kind id" >&2
    return 1
  fi

  # First-run bootstrap: counter file missing → seed from existing high-water.
  if [ ! -f "$counter" ]; then
    if [ -d "$scan_path" ]; then
      # Pick out the trailing 3+-digit number from every matching id, take max.
      highest=$(find "$scan_path" -maxdepth 4 \( -type d -o -type f \) 2>/dev/null \
        | grep -oE "$id_pattern" \
        | grep -oE '[0-9]+$' \
        | sort -n | tail -1)
    else
      highest=""
    fi
    seed=$(( ${highest:-0} + 1 ))
    # Write the SEED (next-to-allocate). Subsequent reads pick this up as NUM.
    if ! printf '%s\n' "$seed" > "$counter"; then
      echo "ERROR: failed to bootstrap $counter — aborting" >&2
      [ ! -L "$lock" ] && rmdir "$lock" 2>/dev/null
      return 1
    fi
  fi

  num=$(cat "$counter" 2>/dev/null)
  if [ -z "$num" ]; then
    echo "ERROR: counter $counter is empty inside lock — aborting (would reset to 1)" >&2
    [ ! -L "$lock" ] && rmdir "$lock" 2>/dev/null
    return 1
  fi

  # Atomically write back the incremented value, then release the lock.
  if ! printf '%s\n' "$((num + 1))" > "$counter"; then
    echo "ERROR: failed to write $counter inside lock — aborting" >&2
    [ ! -L "$lock" ] && rmdir "$lock" 2>/dev/null
    return 1
  fi
  [ ! -L "$lock" ] && rmdir "$lock" 2>/dev/null

  # Format as `<XYZ>-REQ-NNN` with at least 3-digit zero-padding.
  printf '%s-%s-%03d\n' "$shortname" "$kind" "$num"
}

allocate_req() {
  _allocate REQ .adlc/.next-req .adlc/specs '(REQ|[A-Z]{3}-REQ)-[0-9]+'
}

allocate_bug() {
  _allocate BUG .adlc/.next-bug .adlc/bugs '(BUG|[A-Z]{3}-BUG)-[0-9]+'
}

allocate_lesson() {
  _allocate LESSON .adlc/.next-lesson .adlc/knowledge/lessons '(LESSON|[A-Z]{3}-LESSON)-[0-9]+'
}
