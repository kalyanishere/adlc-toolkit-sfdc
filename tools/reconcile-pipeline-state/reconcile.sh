#!/bin/sh
# tools/reconcile-pipeline-state/reconcile.sh
#
# Heal "ghost" REQs whose pipeline-runner died after the merge landed but
# before writing the final pipeline-state.json. Walks every spec dir under
# the project root and, for each spec where requirement.md says status:
# complete AND a merged PR matches the feature branch convention AND
# pipeline-state.json is missing or has completed=false, synthesizes a
# minimal state file with terminalState=merged, completed=true,
# repos[*].merged=true.
#
# Pure POSIX shell + jq + git + gh. No LLM. Deterministic. Idempotent.
# Safe to run as a startup step in /sprint and /proceed — a project with
# no ghosts is a no-op.
#
# Usage:
#   sh reconcile.sh [--root <project-path>] [--dry-run] [--verbose]
#
# Exit codes:
#   0  no ghosts found, or all ghosts healed
#   1  one or more ghosts could not be healed (still ghost on exit) —
#      e.g., merged PR could not be located, gh unauthenticated for the
#      hosted remote, malformed requirement.md frontmatter. The script
#      surfaces a per-ghost reason on stderr and continues; exit 1 only
#      reflects "did anything fail to heal."
#   2  user error (bad arg, no spec dir, etc.)

set -eu

ROOT=""
DRY_RUN=0
VERBOSE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --dry-run|-n) DRY_RUN=1; shift ;;
    --verbose|-v) VERBOSE=1; shift ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//' >&2
      exit 0
      ;;
    *) echo "ERROR: unknown arg '$1' (use --help)" >&2; exit 2 ;;
  esac
done

[ -n "$ROOT" ] || ROOT=$(pwd)
[ -d "$ROOT/.adlc/specs" ] || {
  log_v "no .adlc/specs under $ROOT — nothing to reconcile"
  exit 0
}

log_v() { [ "$VERBOSE" -eq 1 ] && printf '[reconcile] %s\n' "$*" >&2 || true; }
log()   { printf '[reconcile] %s\n' "$*" >&2; }
warn()  { printf '[reconcile] WARN: %s\n' "$*" >&2; }
err()   { printf '[reconcile] ERROR: %s\n' "$*" >&2; }

# Capture an ISO-8601 UTC timestamp once per run so all synthesized state
# files share a consistent "reconciled at" mark.
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

command -v jq  >/dev/null 2>&1 || { err "jq is required";  exit 2; }
command -v git >/dev/null 2>&1 || { err "git is required"; exit 2; }

# Try to detect whether gh is usable against the project's origin. We don't
# require it — local-bare projects (and offline runs) reconcile via git
# alone. We just record availability so the per-spec heal can prefer gh.
GH_OK=0
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  GH_OK=1
fi
log_v "gh available + authenticated: $GH_OK"

# Resolve the gh repo slug for `gh pr list` calls. Falls back gracefully if
# origin is a local bare path (no slug — gh queries are skipped).
ORIGIN_URL=$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)
GH_SLUG=""
case "$ORIGIN_URL" in
  https://github.com/*/*.git) GH_SLUG=${ORIGIN_URL#https://github.com/}; GH_SLUG=${GH_SLUG%.git} ;;
  https://github.com/*/*)     GH_SLUG=${ORIGIN_URL#https://github.com/} ;;
  git@github.com:*/*.git)     GH_SLUG=${ORIGIN_URL#git@github.com:};     GH_SLUG=${GH_SLUG%.git} ;;
  git@github.com:*/*)         GH_SLUG=${ORIGIN_URL#git@github.com:} ;;
esac
log_v "origin URL: $ORIGIN_URL  slug: ${GH_SLUG:-<none>}"

healed=0
failed=0
total=0

# Walk every spec dir matching the canonical REQ pattern. We accept both
# the prefixed form (SAP-REQ-001) and the bare form (REQ-001) so projects
# that haven't adopted shortname namespacing still reconcile.
for SPEC_DIR in "$ROOT"/.adlc/specs/*/ ; do
  SPEC_NAME=$(basename "$SPEC_DIR")
  case "$SPEC_NAME" in
    [A-Z]*-REQ-*|REQ-*) ;;
    *) continue ;;
  esac

  REQ_ID=$(printf '%s' "$SPEC_NAME" | sed -E 's/^([A-Z]+-REQ-[0-9]+|REQ-[0-9]+).*/\1/')
  [ -n "$REQ_ID" ] || continue
  total=$((total + 1))

  REQ_FILE="$SPEC_DIR/requirement.md"
  STATE_FILE="$SPEC_DIR/pipeline-state.json"

  [ -f "$REQ_FILE" ] || { log_v "$REQ_ID: no requirement.md, skipping"; continue; }

  # Only consider specs whose requirement.md status is 'complete'. A spec
  # in draft / approved / in-progress is either pre-pipeline or live; we
  # don't touch it.
  REQ_STATUS=$(awk '
    /^---[[:space:]]*$/ { fm = !fm; next }
    fm && $1 == "status:" { print $2; exit }
  ' "$REQ_FILE" | tr -d '"')
  [ "$REQ_STATUS" = "complete" ] || {
    log_v "$REQ_ID: status=$REQ_STATUS, skipping"
    continue
  }

  # Already-healthy state file? If completed=true and terminalState is set,
  # this REQ is already fine.
  if [ -f "$STATE_FILE" ]; then
    DONE=$(jq -r '.completed // false' "$STATE_FILE" 2>/dev/null || echo "false")
    TERM=$(jq -r '.terminalState // ""' "$STATE_FILE" 2>/dev/null || echo "")
    if [ "$DONE" = "true" ] && [ -n "$TERM" ] && [ "$TERM" != "null" ]; then
      log_v "$REQ_ID: state file already complete (terminalState=$TERM), skipping"
      continue
    fi
  fi

  log "$REQ_ID: ghost detected — requirement complete but state file missing/incomplete"

  # Look up the merged PR. Two paths:
  #   (a) gh available + hosted slug — query gh pr list by head ref.
  #   (b) fallback: parse `git log --grep` on main for the squash-merge
  #       commit message format `<REQ-ID>: ... (#<N>)` produced by gh.
  PR_NUMBER=""
  PR_URL=""
  PR_MERGED_AT=""
  PR_MERGE_SHA=""

  if [ "$GH_OK" -eq 1 ] && [ -n "$GH_SLUG" ]; then
    # Branch convention is feat/<REQ-ID>-... — match by prefix to be robust
    # to slug variations between the spec dir name and the actual branch.
    PR_JSON=$(gh -R "$GH_SLUG" pr list \
      --state merged \
      --search "head:feat/${REQ_ID}-" \
      --limit 1 \
      --json number,url,mergedAt,mergeCommit,headRefName 2>/dev/null || true)
    if [ -n "$PR_JSON" ] && [ "$PR_JSON" != "[]" ]; then
      PR_NUMBER=$(printf '%s' "$PR_JSON" | jq -r '.[0].number // empty')
      PR_URL=$(printf '%s'    "$PR_JSON" | jq -r '.[0].url // empty')
      PR_MERGED_AT=$(printf '%s' "$PR_JSON" | jq -r '.[0].mergedAt // empty')
      PR_MERGE_SHA=$(printf '%s' "$PR_JSON" | jq -r '.[0].mergeCommit.oid // empty')
    fi
  fi

  # Fallback path: scan main for the squash-merge commit by REQ id. Try
  # origin/main first (the canonical authority), then local main, then any
  # branch — covers fresh clones, local-bare repos, and odd default-branch
  # names without hardcoding 'main' more than necessary.
  if [ -z "$PR_NUMBER" ]; then
    LOG_REF=""
    for cand in origin/main origin/master main master HEAD; do
      if git -C "$ROOT" rev-parse --verify "$cand" >/dev/null 2>&1; then
        LOG_REF="$cand"; break
      fi
    done
    SHA=""
    if [ -n "$LOG_REF" ]; then
      SHA=$(git -C "$ROOT" log "$LOG_REF" --pretty=format:"%H %s" 2>/dev/null \
              | grep -E "^[a-f0-9]+ ${REQ_ID}[: ]" \
              | head -1 \
              | awk '{print $1}')
    fi
    if [ -n "$SHA" ]; then
      PR_MERGE_SHA="$SHA"
      # Pull merged-at from the commit's author date (close enough for a
      # synthesized state file's purposes; stamped in notes that this is
      # post-hoc).
      # `%cI` returns a timezone-aware ISO timestamp like
      # `2026-06-06T19:42:34+05:30`. We need a UTC ISO-8601 string ending
      # in Z so the dashboard sorts it lexicographically. Use python3 since
      # it's universally present on macOS/Linux toolkit hosts; falls back
      # to the raw value if python3 is missing.
      RAW=$(git -C "$ROOT" log -1 --pretty=format:"%cI" "$SHA")
      if command -v python3 >/dev/null 2>&1; then
        PR_MERGED_AT=$(python3 -c '
import sys, datetime
raw = sys.argv[1]
dt = datetime.datetime.fromisoformat(raw)
print(dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
' "$RAW" 2>/dev/null || printf '%s' "$RAW")
      else
        PR_MERGED_AT="$RAW"
      fi
      # Squash commits include "(#N)" at the end. Pick out the number if
      # present so we still get a clickable PR url.
      MSG=$(git -C "$ROOT" log -1 --pretty=format:"%s" "$SHA")
      PR_NUMBER=$(printf '%s' "$MSG" | sed -nE 's/.*\(#([0-9]+)\)$/\1/p')
      if [ -n "$PR_NUMBER" ] && [ -n "$GH_SLUG" ]; then
        PR_URL="https://github.com/$GH_SLUG/pull/$PR_NUMBER"
      fi
    fi
  fi

  if [ -z "$PR_MERGE_SHA" ] && [ -z "$PR_NUMBER" ]; then
    warn "$REQ_ID: cannot locate a merged PR or merge commit — skipping (manual recovery required)"
    failed=$((failed + 1))
    continue
  fi

  # Resolve repo id and branch. Spec frontmatter doesn't carry these
  # reliably; we use convention defaults that match /proceed Phase 0:
  #   - repo id = basename of project root (single-repo default)
  #   - branch  = feat/<REQ-ID>-<slug>  (read from PR if we have it,
  #                                     else from local branch list)
  REPO_ID=$(basename "$ROOT")
  BRANCH=""
  if [ "$GH_OK" -eq 1 ] && [ -n "$PR_NUMBER" ] && [ -n "$GH_SLUG" ]; then
    BRANCH=$(gh -R "$GH_SLUG" pr view "$PR_NUMBER" --json headRefName --jq .headRefName 2>/dev/null || true)
  fi
  if [ -z "$BRANCH" ]; then
    # Fallback: scan local refs for any branch starting feat/<REQ-ID>-
    BRANCH=$(git -C "$ROOT" for-each-ref --format='%(refname:short)' \
             "refs/heads/feat/${REQ_ID}-*" "refs/remotes/origin/feat/${REQ_ID}-*" 2>/dev/null \
             | head -1 | sed 's|^origin/||')
  fi
  [ -n "$BRANCH" ] || BRANCH="feat/${REQ_ID}-unknown-slug"

  # Worktree path is the standard convention. If the worktree doesn't
  # exist on disk anymore (the runner removed it before exiting), the
  # path is still recorded in state so audit trails point to where the
  # work happened.
  WORKTREE="$ROOT/.worktrees/${REQ_ID}"

  # Existing state file (partial)? Preserve startedAt and phaseHistory if
  # present so reconciliation doesn't erase what the runner did capture.
  STARTED_AT=""
  if [ -f "$STATE_FILE" ]; then
    STARTED_AT=$(jq -r '.startedAt // empty' "$STATE_FILE" 2>/dev/null || echo "")
  fi
  [ -n "$STARTED_AT" ] || STARTED_AT="$NOW"

  if [ "$DRY_RUN" -eq 1 ]; then
    log "$REQ_ID: WOULD heal -> prUrl=${PR_URL:-<none>} mergeSha=$PR_MERGE_SHA branch=$BRANCH (dry-run)"
    healed=$((healed + 1))
    continue
  fi

  # Synthesize the state file via jq (safer than hand-templating JSON).
  # If a partial state file existed we merge over it; otherwise we
  # construct a fresh minimal record.
  TMP=$(mktemp)
  if [ -f "$STATE_FILE" ]; then
    BASE_INPUT="$STATE_FILE"
  else
    BASE_INPUT=/dev/null
    printf '{}' > "$TMP.base"
    BASE_INPUT="$TMP.base"
  fi

  jq \
    --arg req       "$REQ_ID" \
    --arg branch    "$BRANCH" \
    --arg now       "$NOW" \
    --arg started   "$STARTED_AT" \
    --arg repoId    "$REPO_ID" \
    --arg root      "$ROOT" \
    --arg worktree  "$WORKTREE" \
    --arg prUrl     "$PR_URL" \
    --arg mergedAt  "$PR_MERGED_AT" \
    --arg mergeSha  "$PR_MERGE_SHA" \
    '
    . as $base |
    $base + {
      req:                ($base.req                // $req),
      branch:             ($base.branch             // $branch),
      complexity:         ($base.complexity         // "small"),
      startedAt:          ($base.startedAt          // $started),
      completed:          true,
      terminalState:      "merged",
      currentPhase:       8,
      currentPhaseStartedAt: null,
      completedPhases:    ([0,1,2,3,4,5,6,7,8]),
      integrationBranch:  ($base.integrationBranch  // "main"),
      mergeOrder:         ($base.mergeOrder         // [$repoId]),
      phase4:             ($base.phase4             // {currentTask:null, completedTasks:["TASK-001"], failedTasks:[]}),
      repos:              (
        ($base.repos // {}) as $r |
        ($r[$repoId] // {}) as $rr |
        $r + {
          ($repoId): ($rr + {
            primary:    ($rr.primary    // true),
            path:       ($rr.path       // $root),
            worktree:   ($rr.worktree   // $worktree),
            branch:     ($rr.branch     // $branch),
            touched:    true,
            merged:     true,
            prUrl:      (if $prUrl   != "" then $prUrl   else $rr.prUrl // null end),
            mergedAt:   (if $mergedAt!= "" then $mergedAt else $rr.mergedAt // null end),
            mergeCommit:(if $mergeSha!= "" then $mergeSha else $rr.mergeCommit // null end),
          })
        }
      ),
      phaseHistory: (
        ($base.phaseHistory // []) +
        [{phase: 8, name: "Reconciled by tools/reconcile-pipeline-state",
          startedAt: $now, completedAt: $now}]
      ),
      reconciledAt:       $now,
      reconciledNotes: (
        ($base.reconciledNotes // "") +
        "Healed by reconcile.sh: pipeline-runner exited without finalizing this state file. " +
        "Merge of \(.req // $req) confirmed via " +
        (if $prUrl != "" then "PR " + $prUrl else "merge commit " + $mergeSha end) +
        ". Phase boundaries before this entry are whatever the runner had recorded; " +
        "they may be incomplete. The merge itself is real (verifiable with " +
        "`git merge-base --is-ancestor \($mergeSha) origin/main`)."
      ),
    }
    ' "$BASE_INPUT" > "$TMP"

  mv "$TMP" "$STATE_FILE"
  rm -f "$TMP.base"
  log "$REQ_ID: healed -> $STATE_FILE  (PR ${PR_URL:-#$PR_NUMBER}, sha $PR_MERGE_SHA)"
  healed=$((healed + 1))
done

if [ "$total" -eq 0 ]; then
  log_v "no REQ specs found under $ROOT/.adlc/specs"
fi

if [ "$healed" -gt 0 ] || [ "$failed" -gt 0 ]; then
  log "summary: $healed healed, $failed failed (out of $total scanned)"
fi

[ "$failed" -eq 0 ] && exit 0 || exit 1
