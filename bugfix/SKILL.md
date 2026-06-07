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
   - Determine the next BUG ID using the canonical allocator partial. IDs are **per-project, namespaced by `project.shortname`** — `<XYZ>-BUG-NNN` (e.g., `SFC-BUG-014`). The counter lives at `<ARTIFACT_ROOT>/.adlc/.next-bug`. First allocation in a project bootstraps from the highest existing `<XYZ>-BUG-NNN` and legacy `BUG-NNN` under `.adlc/bugs/`, so re-running `/init` mid-project never resets to 1.
     ```bash
     cd "$ARTIFACT_ROOT"
     . .adlc/partials/id-counter.sh 2>/dev/null || . ~/.claude/skills/partials/id-counter.sh
     BUG_ID=$(allocate_bug)
     # `allocate_bug` runs in $(...). `return 1` from the partial only exits the
     # subshell — guard the parent context (LESSON-015):
     [ -n "$BUG_ID" ] || { echo "ERROR: failed to allocate BUG id — aborting before writing malformed bug report" >&2; exit 1; }
     # Extract the numeric suffix when you need BUG_NUM in templates / paths:
     BUG_NUM=${BUG_ID##*-}
     ```
     The partial enforces `project.shortname` (must match `^[A-Z]{3}$`), `mkdir`-based lock with symlink pre-check (LESSON-014), empty-counter fail-loud guards, and a first-run bootstrap that scans `.adlc/bugs/` for the high-water mark across BOTH legacy and namespaced ids. The legacy machine-global `~/.claude/.global-next-bug` is no longer read or written.
   - Create `<ARTIFACT_ROOT>/.adlc/bugs/<BUG_ID>-slug.md` (e.g., `SFC-BUG-014-account-merge-loses-tags.md`) — the primary repo for the bug, even when the fix lives in a sibling, the report stays here. Use the template from `<ARTIFACT_ROOT>/.adlc/templates/bug-template.md`
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

If yes, write a lesson to `<ARTIFACT_ROOT>/.adlc/knowledge/lessons/<LESSON_ID>-slug.md` using the canonical allocator partial. IDs are per-project, namespaced by `project.shortname` — `<XYZ>-LESSON-NNN`. The counter at `<ARTIFACT_ROOT>/.adlc/.next-lesson` and the lock at `.adlc/.next-lesson.lock.d` are shared with `/wrapup`'s lesson capture so concurrent `/bugfix` and `/wrapup` runs mutually exclude. First allocation in a project bootstraps from the highest existing `<XYZ>-LESSON-NNN` and legacy `LESSON-NNN`, never resets to 1.
```bash
cd "$ARTIFACT_ROOT"
. .adlc/partials/id-counter.sh 2>/dev/null || . ~/.claude/skills/partials/id-counter.sh
LESSON_ID=$(allocate_lesson)
[ -n "$LESSON_ID" ] || { echo "ERROR: failed to allocate LESSON id — aborting before writing malformed lesson" >&2; exit 1; }
LESSON_NUM=${LESSON_ID##*-}
```
The partial enforces `project.shortname` (`^[A-Z]{3}$`), `mkdir`-based lock with symlink pre-check (LESSON-014), empty-counter fail-loud guards (LESSON-015), and a first-run bootstrap that scans `.adlc/knowledge/lessons/` for the high-water mark across BOTH legacy and namespaced ids. The legacy machine-global `~/.claude/.global-next-lesson` is no longer read or written.

Use the lesson template (`<ARTIFACT_ROOT>/.adlc/templates/lesson-template.md`, fall back to `~/.claude/skills/templates/lesson-template.md`). Filename format is `<LESSON_ID>-slug.md` (e.g., `SFC-LESSON-014-static-vs-instance.md`). Slugs are lowercase kebab-case, ≤6 words. Include `domain`, `component`, and `tags` so future runs of `/spec`, `/architect`, `/reflect`, and `/review` can filter by relevance.

If the bug genuinely produced no useful lesson (one-line typo, etc.), say so explicitly in the final summary — don't silently skip.

**Step 4a — Back-update the parent REQ's spec and architecture docs.**

When a bug fixes shipped behavior, the REQ that originally shipped that code now describes a slightly inaccurate state. Append a "Post-ship corrections" section to the parent REQ's spec so the historical record stays accurate without rewriting the original.

1. **Identify the parent REQ.** Use the bug's frontmatter `parent_req:` field if set, OR derive it from `git log --diff-filter=AM <files-touched-by-fix>` and find the most recent REQ id mentioned in that history. If multiple REQs touched the file, pick the one that originally introduced the buggy behavior; if ambiguous, list all candidates and ask the user.

2. **Append a correction note** to `<ARTIFACT_ROOT>/.adlc/specs/<parent-req-spec-dir>/requirement.md`. **Append, do not rewrite** — the original spec is the historical record:
   ```markdown

   ## Post-ship corrections

   - **<BUG_ID>** (resolved <YYYY-MM-DD>): <one-line description of what was wrong>. Fix: <one-line description of what changed>. See `.adlc/bugs/<BUG_ID>-slug.md`.
   ```
   If the section already exists from a prior bug fix, append a new bullet — don't duplicate the heading.

3. **Update architecture documentation IF the fix changed an architectural decision.** Two places to consider:
   - `<ARTIFACT_ROOT>/.adlc/specs/<parent-req-spec-dir>/architecture-notes.md` (per-REQ architecture, if it exists for that REQ)
   - `<ARTIFACT_ROOT>/.adlc/context/architecture.md` (project-wide architecture, if the bug invalidated a documented pattern)

   Same rule — append a "Post-ship correction" section, don't silently rewrite the originals.

4. **Skip this step entirely** when:
   - The bug is purely a typo or comment fix (no shipped-behavior change)
   - The bug's parent REQ cannot be identified after honest investigation (note the gap in the bug report's "Notes" section instead)
   - The bug report explicitly opts out via `parent_req: none` in frontmatter (e.g., bugs filed against pre-ADLC legacy code)

These edits ALSO stay uncommitted on `main` until Step 4b's chore commit, which now stages the parent-REQ doc updates alongside the bug-report and lesson.

**Step 4b — Persist bug-report status update + lesson to `main`.**

The PRs were already merged in Step 1 of this Phase. Steps 3 and 4 wrote new content into `<ARTIFACT_ROOT>` (the primary repo's main checkout) but those edits are uncommitted. Land them as a **separate chore commit on `main`** — same model as `/wrapup`'s Step 4b:

```bash
git -C "$ARTIFACT_ROOT" status --short -- .adlc/bugs/ .adlc/knowledge/ .adlc/specs/ .adlc/context/ \
  | grep -qE '^\s*[?AM]' || { echo "bugfix: no bug-report / lesson / parent-spec edits to persist — skipping commit"; exit 0; }

git -C "$ARTIFACT_ROOT" checkout main
git -C "$ARTIFACT_ROOT" pull --ff-only origin main

# Stage the bug report, any new lesson, AND any parent-REQ / architecture
# back-update from Step 4a. Never blanket-add.
git -C "$ARTIFACT_ROOT" add \
  .adlc/bugs/BUG-xxx-slug.md \
  .adlc/knowledge/lessons/LESSON-*.md 2>/dev/null || true
# Parent REQ spec + architecture-notes (Step 4a back-update). Add only the
# specific files actually edited; never blanket-add .adlc/specs/.
# Substitute <parent-req-spec-dir> with the resolved value from Step 4a.
[ -n "${PARENT_REQ_DIR:-}" ] && git -C "$ARTIFACT_ROOT" add \
  ".adlc/specs/$PARENT_REQ_DIR/requirement.md" \
  ".adlc/specs/$PARENT_REQ_DIR/architecture-notes.md" 2>/dev/null || true
# Project-wide architecture (rare — only when a documented pattern was invalidated).
git -C "$ARTIFACT_ROOT" status --short -- .adlc/context/architecture.md 2>/dev/null \
  | grep -q . && git -C "$ARTIFACT_ROOT" add .adlc/context/architecture.md

git -C "$ARTIFACT_ROOT" diff --cached --quiet && {
  echo "bugfix: nothing staged — skipping commit"
  exit 0
}

# Commit message convention: include the parent REQ id so a future
# `git log --grep=REQ-xxx` surfaces the post-ship correction trail.
COMMIT_MSG="chore(BUG-xxx): mark resolved + capture lesson"
[ -n "${PARENT_REQ_ID:-}" ] && COMMIT_MSG="docs($PARENT_REQ_ID): post-ship correction from BUG-xxx + capture lesson"

git -C "$ARTIFACT_ROOT" commit -m "$COMMIT_MSG"
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
