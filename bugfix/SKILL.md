---
name: bugfix
description: End-to-end bug fix workflow — report, analyze, fix, verify, ship (PR + merge + deploy + knowledge capture)
argument-hint: Bug description or BUG-xxx ID
---

# /bugfix — Bug Fix Workflow

You are fixing a bug using a streamlined workflow that skips the full spec ceremony but follows the **same deployment strategy as a feature**: changes land via PR, ride the project's CI/CD pipeline (staging-first if the project has one), and aren't marked resolved until every declared deploy target is confirmed.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Project config: !`cat .adlc/config.yml 2>/dev/null || echo "No config — single-repo legacy mode"`
- Bug template: !`cat .adlc/templates/bug-template.md 2>/dev/null || cat ~/.claude/skills/templates/bug-template.md 2>/dev/null || echo "No bug template found"`
- Conventions: !`cat .adlc/context/conventions.md 2>/dev/null || echo "No conventions found"`
- Existing bugs: !`ls .adlc/bugs/ 2>/dev/null || echo "No bugs directory found"`

## Input

Bug report: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `<ARTIFACT_ROOT>/.adlc/bugs/` exists (after Phase 0 has resolved `<ARTIFACT_ROOT>`). If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized in the main checkout. Run `/init` first."

## Instructions

### Phase 0: Pin `<ARTIFACT_ROOT>` (do this FIRST)

Resolve and freeze the absolute path of the **main checkout** for the repo this `/bugfix` was invoked from. Every `.adlc/...` write later in this skill — bug report file, lesson, BUG/LESSON counter scans — resolves against `<ARTIFACT_ROOT>`, never against cwd. cwd may be a Claude Code skill-isolation worktree (`.claude/worktrees/<slug>`) or, after Phase 6 Step 5, a directory that has been removed.

Resolve in this order, stopping at the first that succeeds:

1. **Explicit caller arg**: if the invoker passed `--main-root <abs-path>`, use it verbatim.
2. **From `git worktree list`**:
   ```bash
   ARTIFACT_ROOT=$(git worktree list --porcelain | awk '
     /^worktree /{p=$2}
     /^branch refs\/heads\/(main|master)$/{print p; exit}
   ')
   ```
3. **Fallback**: if `git rev-parse --abbrev-ref HEAD` reports `main` or `master`, use `git rev-parse --show-toplevel`. Otherwise stop with: "ERROR: cannot resolve `<ARTIFACT_ROOT>` — pass `--main-root` explicitly or run from the main checkout."

Verify it:
```bash
git -C "$ARTIFACT_ROOT" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "ERROR: ARTIFACT_ROOT=$ARTIFACT_ROOT is not a git repo — aborting" >&2
  exit 1
}
[ -d "$ARTIFACT_ROOT/.adlc/bugs" ] || {
  echo "ERROR: $ARTIFACT_ROOT/.adlc/bugs missing — wrong checkout? Run /init there first." >&2
  exit 1
}
```

Treat `<ARTIFACT_ROOT>` as **immutable** for the rest of the run. In cross-repo mode, this `<ARTIFACT_ROOT>` is the primary (the repo `/bugfix` was invoked from — where the bug report lives). Sibling-repo writes (the actual code fix) target their own checkouts via `.adlc/config.yml`'s `path:` entries — those paths are read on demand in Phase 3, not pinned here.

### Phase 1: Report
1. If given a bug description (not a BUG ID), create a bug report:
   - Determine the next BUG ID using the **global** atomic counter file `~/.claude/.global-next-bug` (shared across all repos for unique IDs, mirroring the REQ counter — see LESSON-004). Read the number, use it, and immediately write the incremented value back — using a POSIX `mkdir`-based lock to prevent concurrent collisions (works on macOS and Linux; `flock` is not available by default on macOS):
     ```bash
     BUG_NUM=$(
       LOCK=~/.claude/.global-next-bug.lock.d
       COUNTER=~/.claude/.global-next-bug
       if [ -L "$LOCK" ]; then
         echo "ERROR: $LOCK is a symlink — refusing (TOCTOU risk). Inspect manually." >&2
         exit 1
       fi
       for _ in $(seq 50); do mkdir "$LOCK" 2>/dev/null && break; sleep 0.1; done
       # Hard-fail if we never acquired the lock (50 retries × 0.1s = ~5s budget).
       # Without this guard, a contended lock would silently fall through to the
       # critical section unguarded — defeating mutual exclusion (REQ-416 verify C1).
       [ -d "$LOCK" ] || { echo "ERROR: failed to acquire $LOCK after 50 retries — aborting to avoid duplicate BUG id" >&2; exit 1; }
       # Counter read inside lock — fail hard if the file disappears mid-critical-section
       # rather than silently treating empty-as-zero and resetting the global counter (REQ-416 verify M2).
       NUM=$(cat "$COUNTER" 2>/dev/null) || { echo "ERROR: counter $COUNTER unreadable inside lock — aborting" >&2; rmdir "$LOCK" 2>/dev/null; exit 1; }
       [ -n "$NUM" ] || { echo "ERROR: counter $COUNTER is empty — aborting (would reset to 1)" >&2; rmdir "$LOCK" 2>/dev/null; exit 1; }
       echo $((NUM + 1)) > "$COUNTER"
       # rmdir is guarded by the same symlink check (residual TOCTOU window between
       # check and rmdir is accepted risk per ADR-4 — see LESSON-014).
       if [ ! -L "$LOCK" ]; then rmdir "$LOCK" 2>/dev/null; fi
       echo $NUM
     )
     # `exit 1` inside the $(...) subshell terminates only the subshell — BUG_NUM
     # would be silently empty. Guard the parent context (REQ-416 verify D-pass).
     [ -n "$BUG_NUM" ] || { echo "ERROR: failed to allocate BUG number — aborting before writing malformed bug report" >&2; exit 1; }
     ```
     If `~/.claude/.global-next-bug` doesn't exist, create it by scanning all `.adlc/bugs/` directories under the user's repos root for the highest `BUG-xxx` number, use the next one, and write the number after that. The scan root is `$ADLC_REPOS_ROOT` if set, otherwise the parent of the **main checkout** (use `$ARTIFACT_ROOT`, not cwd — a skill-isolation worktree's parent points at `.claude/worktrees/` and silently misses every actual repo):
     ```bash
     SCAN_ROOT="${ADLC_REPOS_ROOT:-$(cd "$ARTIFACT_ROOT/.." && pwd)}"
     HIGHEST=$(find "$SCAN_ROOT" -path '*/.adlc/bugs/BUG-*' -type f 2>/dev/null \
       | grep -oE 'BUG-[0-9]+' | sed 's/BUG-//' | sort -n | tail -1)
     BUG_NUM=$(( ${HIGHEST:-0} + 1 ))
     echo $((BUG_NUM + 1)) > ~/.claude/.global-next-bug
     ```
     If the scan finds nothing (genuinely first BUG across all repos), `HIGHEST` is empty — `BUG_NUM` defaults to 1. Bug reports are `.md` files so the scan uses `-type f`; the analogous REQ-counter scan in `/spec` uses `-type d` because REQ specs are directories (deliberate, do not "correct" to `-type d`).
     Note: the legacy per-repo `.adlc/.next-bug` counter is **deprecated** and no longer consulted — existing files can be left in place but should not be read or written.
   - Create `<ARTIFACT_ROOT>/.adlc/bugs/BUG-xxx-slug.md` (the primary repo for the bug — even when the fix lives in a sibling, the report stays here) using the template from `<ARTIFACT_ROOT>/.adlc/templates/bug-template.md`
   - Fill in: description, reproduction steps (if known), expected vs actual behavior, environment
   - Set status to `open`, severity based on impact
   - **Cross-repo**: if `<ARTIFACT_ROOT>/.adlc/config.yml` declares siblings AND the bug's fix likely lives in a sibling (e.g., a frontend symptom whose root cause is in a backend repo), add a `repo: <sibling-id>` field to the bug frontmatter. If the fix spans multiple repos, add a `touched_repos: [<id>, <id>]` field. The `repo:` field determines where Phase 3's commit and Phase 4's PR land.
   - **Commit the bug report on `main` immediately** — the fix may take hours, the report should not sit uncommitted in the working tree:
     ```bash
     git -C "$ARTIFACT_ROOT" checkout main
     git -C "$ARTIFACT_ROOT" pull --ff-only origin main
     git -C "$ARTIFACT_ROOT" add .adlc/bugs/BUG-xxx-slug.md
     git -C "$ARTIFACT_ROOT" commit -m "chore(BUG-xxx): file bug report"
     git -C "$ARTIFACT_ROOT" push origin main
     ```
     Substitute the concrete BUG id. If branch protection rejects the push, surface it to the user — they will need to land the report via a tiny PR; do **not** silently leave it uncommitted, or Phase 6's status update will write into a file that's never been seen by the repo's history.
2. If given a BUG ID, read the existing bug report at `<ARTIFACT_ROOT>/.adlc/bugs/BUG-xxx-slug.md` — note any `repo:` or `touched_repos:` field for routing.

### Phase 2: Analyze
1. Launch Explore agents to trace the bug:
   - Search for relevant code paths based on the bug description
   - Trace the execution flow that triggers the bug
   - Identify the root cause (not just symptoms)
2. Read the identified files to understand the context
3. Document the root cause in the bug report's "Root Cause" section
4. Validate the analysis:
   - Re-read the affected code paths to confirm the root cause is correct
   - Check for secondary issues or edge cases related to the bug
   - Adjust the root cause and fix approach if validation reveals inaccuracies
5. Update the bug report with the validated findings

### Phase 3: Fix
1. **Determine target repo**: if the bug's frontmatter has `repo:` and it names a sibling (not this repo), cd into that sibling's path from `.adlc/config.yml` and do all fix work there. For `touched_repos: [...]`, cd into each in turn — one commit per repo, on a shared branch name. Otherwise fix in the current repo.
2. Proceed directly with the validated fix approach — do not pause for user confirmation
3. Implement the fix following project conventions
4. Ensure the fix addresses the root cause, not just symptoms
5. Update related test files if the fix changes behavior
6. Track progress with TodoWrite

### Phase 4: Verify
1. Run the test suite: `npm test` (or appropriate test command)
2. If tests fail, fix and re-run
3. Update the bug report at `<ARTIFACT_ROOT>/.adlc/bugs/BUG-xxx-slug.md` (do NOT mark `resolved` yet — that happens in Phase 6 after the fix is merged and deployed). The report lives on `main` in the main checkout — write directly there; do NOT touch a copy inside a fix worktree:
   - Leave status as `open` (or set to `in-review` if your project uses that value)
   - Fill in "Resolution" section with what was changed and why
   - Fill in "Files Changed" section with specific file paths
   - Update the `updated` date
   - These edits will be committed in Phase 6 Step 4 (chore-on-main alongside the lesson capture). Do NOT commit them now — leaving them as uncommitted main-checkout edits during Phase 5 is intentional, so that Phase 4's interim summary can still be revised if Phase 5's PR review surfaces additional context.
4. Present an interim summary:
   - Root cause
   - What was fixed
   - Files changed
   - Test results
   - Then continue to Phase 5

### Phase 5: Ship — Create Pull Request(s)

For each touched repo (just the current repo in single-repo mode; each entry in `touched_repos:` in cross-repo mode):

1. Push the fix branch: `git -C <worktree> push -u origin fix/bug-xxx-slug`
2. Create the PR with `gh pr create` (run from inside the worktree, or use `gh -R <owner/repo>`). In cross-repo mode, create the **primary** repo's PR **last** so its body can link every sibling.
   - **Title**: `fix(BUG-xxx): short description` — when cross-repo, scope to the repo (e.g., `fix(api): null deref in user serializer [BUG-042]`).
   - **Body**:
     ```
     ## Summary
     [1-2 lines describing what broke and what was fixed in THIS repo]

     ## Bug
     BUG-xxx: [bug title]
     Severity: [critical | high | medium | low]
     Primary repo: <primary-repo-id>

     ## Root Cause
     [Pulled from the bug report's Root Cause section]

     ## Files Changed (this repo)
     - `path/to/file.ts` — what changed and why

     ## Related PRs (cross-repo)
     [Omit in single-repo mode. Otherwise list each sibling PR URL — back-fill
      sibling bodies via `gh pr edit` once every URL is known.]

     ## Test Plan
     - [ ] Unit/integration tests pass locally
     - [ ] CI green on this PR
     - [ ] Staging deploy succeeded (verified in Phase 6)
     - [ ] Production deploy succeeded (verified in Phase 6)
     ```
3. After all sibling PRs exist, edit each one (`gh pr edit <prUrl> --body ...`) to fill in the Related PRs section.
4. Wait for CI to pass on every PR: `gh pr checks <prUrl>`. If CI fails, diagnose and re-push — never bypass with `--no-verify` or admin-merge.
5. Report all PR URLs to the user, grouped by repo.

### Phase 6: Wrapup — Merge, Deploy, Knowledge Capture

This is the equivalent of `/proceed`'s Phase 8 / `/wrapup` steps, condensed for bugs.

**Step 1 — Merge each PR.**
1. Verify the PR is mergeable: `gh pr view <prUrl> --json mergeable,mergeStateStatus` should report `MERGEABLE`. If main has advanced, rebase the fix branch onto `origin/main`, force-push with lease, and wait for CI to re-pass.
2. Merge with squash + branch delete: `gh pr merge <prUrl> --squash --delete-branch`. In cross-repo mode, walk `touched_repos:` order (or `merge_order:` from `.adlc/config.yml` if not specified on the bug).

**Step 2 — Confirm deploys** (this is the staging-first gate when the project has one — same model as features).

Skip this step entirely if the project doesn't deploy via Cloud Run (i.e., `stack.backends` in `.adlc/config.yml` doesn't include `cloud-run` and there's no `gcp:` block).

Otherwise, for each touched service that has a `services:` entry in `.adlc/config.yml`, look up `gcp.staging_project` and `gcp.production_project` from the config and confirm both:

```bash
# Staging
gcloud run services describe <service> \
  --project=<gcp.staging_project from config> \
  --region=<services[<id>].region or gcp.default_region> \
  --format="value(status.latestReadyRevisionName,status.traffic[0].revisionName)"

# Production
gcloud run services describe <service> \
  --project=<gcp.production_project from config> \
  --region=<services[<id>].region or gcp.default_region> \
  --format="value(status.latestReadyRevisionName,status.traffic[0].revisionName)"
```

Confirm the merge SHA's revision is serving 100% traffic in each. If `gcp.production_project` is omitted (no separate prod project), only confirm staging.

If staging deployed but production has NOT yet been promoted, wait — the pipeline runs them sequentially. If either fails, surface to the user with the failed deploy log link before claiming the bug resolved.

**iOS deploy** (only when `stack.frontends` in `.adlc/config.yml` includes `ios` AND the fix touched the iOS repo):
1. Read `ios.deploy_targets`, `ios.derived_data_clean`, and `ios.deploy_command` from `.adlc/config.yml`.
2. If `ios.derived_data_clean` is true: `rm -rf ~/Library/Developer/Xcode/DerivedData/*`
3. From the iOS repo's worktree, run `<ios.deploy_command>` and deploy to **every** device in `ios.deploy_targets` — never skip one. Don't leave this as a follow-up for the user.

If `stack.frontends` doesn't include `ios`, skip this section entirely.

**Step 3 — Update the bug report** (write into `<ARTIFACT_ROOT>/.adlc/bugs/BUG-xxx-slug.md` — the main checkout, NOT a fix worktree which may already be removed):
- Set status to `resolved`
- Update the `updated` date
- Confirm Resolution and Files Changed sections are filled in (from Phase 4)
- Add a Deployment section noting the staging + production revisions

These edits stay uncommitted on `main` for now — they will be staged together with the lesson in Step 4's chore commit.

**Step 4 — Capture knowledge** (NEVER skip — per memory `feedback_wrapup_knowledge_capture.md`).

Evaluate honestly: did this bug reveal something a future implementer should know?
- A surprising failure mode (race condition, schema mismatch, mocked-vs-real divergence, etc.)?
- A pattern or anti-pattern worth recording?
- A check that would have caught this earlier?
- An assumption from a prior REQ that turned out false?

If yes, write a lesson to `<ARTIFACT_ROOT>/.adlc/knowledge/lessons/LESSON-xxx-slug.md` using the **global** atomic counter `~/.claude/.global-next-lesson` (shared across all repos for unique IDs, mirroring the REQ/BUG counters — see LESSON-004), wrapped in a POSIX `mkdir`-lock with a symlink pre-check (LESSON-014). The lock path `~/.claude/.global-next-lesson.lock.d` is shared with `/wrapup` so a concurrent `/bugfix` and `/wrapup` mutually exclude and cannot double-allocate the same LESSON id:
```bash
LESSON_NUM=$(
  LOCK=~/.claude/.global-next-lesson.lock.d
  COUNTER=~/.claude/.global-next-lesson
  if [ -L "$LOCK" ]; then
    echo "ERROR: $LOCK is a symlink — refusing (TOCTOU risk). Inspect manually." >&2
    exit 1
  fi
  for _ in $(seq 50); do mkdir "$LOCK" 2>/dev/null && break; sleep 0.1; done
  # Hard-fail if we never acquired the lock (50 retries × 0.1s = ~5s budget).
  # Without this guard, a contended lock would silently fall through to the
  # critical section unguarded — defeating mutual exclusion (REQ-416 verify C1).
  [ -d "$LOCK" ] || { echo "ERROR: failed to acquire $LOCK after 50 retries — aborting to avoid duplicate LESSON id" >&2; exit 1; }
  # Counter read inside lock — fail hard if the file disappears mid-critical-section
  # rather than silently treating empty-as-zero and resetting the global counter (REQ-416 verify M2).
  NUM=$(cat "$COUNTER" 2>/dev/null) || { echo "ERROR: counter $COUNTER unreadable inside lock — aborting" >&2; rmdir "$LOCK" 2>/dev/null; exit 1; }
  [ -n "$NUM" ] || { echo "ERROR: counter $COUNTER is empty — aborting (would reset to 1)" >&2; rmdir "$LOCK" 2>/dev/null; exit 1; }
  echo $((NUM + 1)) > "$COUNTER"
  # rmdir is guarded by the same symlink check (residual TOCTOU window between
  # check and rmdir is accepted risk per ADR-4 — see LESSON-014).
  if [ ! -L "$LOCK" ]; then rmdir "$LOCK" 2>/dev/null; fi
  echo $NUM
)
# `exit 1` inside the $(...) subshell terminates only the subshell — LESSON_NUM
# would be silently empty. Guard the parent context (REQ-416 verify D-pass).
[ -n "$LESSON_NUM" ] || { echo "ERROR: failed to allocate LESSON number — aborting before writing malformed lesson" >&2; exit 1; }
```
If `~/.claude/.global-next-lesson` doesn't exist, create it by scanning all `.adlc/knowledge/lessons/` directories under the user's repos root for the highest `LESSON-xxx` number, use the next one, and write the number after that. The scan root is `$ADLC_REPOS_ROOT` if set, otherwise the parent of the **main checkout** (use `$ARTIFACT_ROOT`, not cwd):
```bash
SCAN_ROOT="${ADLC_REPOS_ROOT:-$(cd "$ARTIFACT_ROOT/.." && pwd)}"
HIGHEST=$(find "$SCAN_ROOT" -path '*/.adlc/knowledge/lessons/LESSON-*' -type f 2>/dev/null \
  | grep -oE 'LESSON-[0-9]+' | sed 's/LESSON-//' | sort -n | tail -1)
LESSON_NUM=$(( ${HIGHEST:-0} + 1 ))
echo $((LESSON_NUM + 1)) > ~/.claude/.global-next-lesson
```
Lessons are `.md` files so the scan uses `-type f` (the `/spec` REQ-counter scan uses `-type d` because specs are directories — a deliberate sibling-substitution, do not "correct" to `-type d`). Use the counter ONLY thereafter — never re-scan after it exists. Note: the legacy per-repo `.adlc/.next-lesson` counter is **deprecated** and no longer consulted — existing files can be left in place but should not be read or written.

Use the lesson template (`<ARTIFACT_ROOT>/.adlc/templates/lesson-template.md`, fall back to `~/.claude/skills/templates/lesson-template.md`). Filename format is `LESSON-xxx-slug.md` only — no date prefixes, no bare-numeric prefixes. Include `domain`, `component`, and `tags` so future runs of `/spec`, `/architect`, `/reflect`, and `/review` can filter by relevance.

If the bug genuinely produced no useful lesson (one-line typo, etc.), say so explicitly in the final summary — don't silently skip.

**Step 4b — Persist bug-report status update + lesson to `main`.**

The PRs were already merged in Step 1 of this Phase. Steps 3 and 4 wrote new content into `<ARTIFACT_ROOT>` (the primary repo's main checkout) but those edits are uncommitted. Land them as a **separate chore commit on `main`** — same model as `/wrapup`'s Step 4b:

```bash
git -C "$ARTIFACT_ROOT" status --short -- .adlc/bugs/ .adlc/knowledge/ \
  | grep -qE '^\s*[?AM]' || { echo "bugfix: no bug-report or lesson edits to persist — skipping commit"; exit 0; }

git -C "$ARTIFACT_ROOT" checkout main
git -C "$ARTIFACT_ROOT" pull --ff-only origin main

# Stage only the bug report and any new lesson — never blanket-add.
git -C "$ARTIFACT_ROOT" add \
  .adlc/bugs/BUG-xxx-slug.md \
  .adlc/knowledge/lessons/LESSON-*.md 2>/dev/null || true

git -C "$ARTIFACT_ROOT" diff --cached --quiet && {
  echo "bugfix: nothing staged — skipping commit"
  exit 0
}

git -C "$ARTIFACT_ROOT" commit -m "chore(BUG-xxx): mark resolved + capture lesson"
git -C "$ARTIFACT_ROOT" push origin main
```

Substitute the concrete BUG id in the path glob and commit message. If branch protection blocks the push, surface to the user — they will need to land the chore via a small PR. Do **not** swallow the failure: the bug stays in `open` state in the repo's history if this commit doesn't land.

**Step 5 — Clean up.**
1. Switch the local checkout to main and pull: `git -C <main-worktree> checkout main && git -C <main-worktree> pull`
2. If the fix was done in a separate worktree, remove it: `git -C <main-worktree> worktree remove <fix-worktree-path>`
3. If the fix branch still exists locally after squash-merge, delete it: `git branch -D fix/bug-xxx-slug`
4. Prune remote-tracking refs: `git fetch --prune`

**Step 6 — Final ship summary.**

```
## BUG-xxx: Bug Title — Resolved

**Severity**: <severity>
**PR(s)**: #nn (and siblings if cross-repo)
**Merged**: YYYY-MM-DD

### Root cause
- 1-2 lines

### Fix
- 1-2 lines

### Deployment
- Staging: <service> revision <hash> @ 100% traffic
- Production: <service> revision <hash> @ 100% traffic
- iOS: deployed to <list of ios.deploy_targets from config> (or "n/a — backend-only fix")

### Lessons captured
- `<ARTIFACT_ROOT>/.adlc/knowledge/lessons/LESSON-xxx-slug.md` — one-line hook
  (or "None — fix was straightforward and revealed no new pattern")
```

## Branch Naming
Use `fix/bug-xxx-slug` for the branch name. In cross-repo bugs, use the same branch name in every touched repo so PRs can be linked visually.

## Commit Message Format
```
fix(BUG-xxx): short description of the fix
```

## Cross-Repo Bugs (brief)
When a bug's fix spans repos (via `touched_repos:` in the bug frontmatter):
- The bug report itself always lives in the repo `/bugfix` was invoked from (the "primary" for this bug).
- Phase 3 makes one commit per touched repo, each on a branch with the same name (`fix/bug-xxx-slug`).
- Phase 5 opens one PR per touched repo and cross-links them (primary PR's body is created last so it can reference every sibling URL).
- Phase 6 merges in the order the repos are listed in `touched_repos:`. If the bug report doesn't specify an order, use the `merge_order` from `.adlc/config.yml`.
- If this gets complicated (more than 2 touched repos, or ordering matters), consider promoting the bug into a full REQ and using `/proceed` instead.
