---
name: wrapup
description: Close out a completed feature — update ADLC artifacts, log knowledge, and summarize
argument-hint: REQ-xxx ID to wrap up
---

# /wrapup — Feature Completion Wrap-Up

You are closing out a completed feature after it has been merged. This skill ensures ADLC artifacts are finalized, knowledge is captured, and the team has a clear summary of what shipped.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Active specs: !`grep -rl 'status: approved\|status: in-progress\|status: complete' .adlc/specs/*/requirement.md 2>/dev/null | tail -20 || echo "No specs found"`
- Knowledge directory: !`ls .adlc/knowledge/ 2>/dev/null || echo "No knowledge directory"`
- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- Recent merges: !`git log --oneline --merges -10 2>/dev/null || echo "No merge history"`
- SF quality checklist: !`cat .adlc/partials/sf-quality-checklist.md 2>/dev/null || cat ~/.claude/skills/partials/sf-quality-checklist.md 2>/dev/null || echo "No sf-quality-checklist found"`

## Input

Target: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `<ARTIFACT_ROOT>/.adlc/context/architecture.md` and `<ARTIFACT_ROOT>/.adlc/context/conventions.md` exist (after Step 0 has resolved `<ARTIFACT_ROOT>`). If any of these files are missing, stop and tell the user: "The `.adlc/` structure hasn't been initialized in the main checkout. Run `/init` first to set up the project context."

## Instructions

### Step 0: Pin `<ARTIFACT_ROOT>` (do this FIRST)

Every later step that writes under `.adlc/` (status updates, lessons, assumptions, conventions, architecture notes, the assume/lesson counters) MUST resolve its path against `<ARTIFACT_ROOT>` — the **absolute path of the primary repo's main checkout** — never against the current working directory. Otherwise, when `/wrapup` runs inside a feature worktree (the common case under `/proceed`) the writes land in the worktree and disappear when Step 2's `git worktree remove` runs.

Resolve in this order, stopping at the first that succeeds:

1. **From `pipeline-state.json`** (preferred under `/proceed`): if `<spec-dir>/pipeline-state.json` exists, read `repos[<primary-id>].path`. Pick the entry whose `primary` flag is true.
2. **From an explicit caller arg**: if the invoker passed `--main-root <abs-path>` (e.g., `/proceed` Phase 8 in a future revision), use it verbatim.
3. **Derived from `git worktree list`**: parse the worktree list and pick the worktree on `refs/heads/main` (or `master`):
   ```bash
   ARTIFACT_ROOT=$(git worktree list --porcelain | awk '
     /^worktree /{p=$2}
     /^branch refs\/heads\/(main|master)$/{print p; exit}
   ')
   ```
4. **Fallback**: if none of the above produced a path AND `git rev-parse --abbrev-ref HEAD` reports `main` or `master`, use `git rev-parse --show-toplevel`. Otherwise stop with: "ERROR: cannot resolve `<ARTIFACT_ROOT>` — pass `--main-root` explicitly or run from the main checkout."

Verify it:
```bash
git -C "$ARTIFACT_ROOT" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "ERROR: ARTIFACT_ROOT=$ARTIFACT_ROOT is not a git repo — aborting" >&2
  exit 1
}
[ -d "$ARTIFACT_ROOT/.adlc" ] || {
  echo "ERROR: $ARTIFACT_ROOT/.adlc missing — wrong checkout? Run /init there first." >&2
  exit 1
}
```

Substitute the resolved value everywhere later steps reference `<ARTIFACT_ROOT>`. Treat it as **immutable** for the rest of the run — once frozen, never re-derive (the worktree may be removed mid-run).

In cross-repo mode you will resolve a `<ARTIFACT_ROOT>` per touched repo using the same rules — `repos[<id>].path` from `pipeline-state.json` is the canonical source. The PRIMARY repo's `<ARTIFACT_ROOT>` is the one used for ADLC spec/knowledge writes (specs and knowledge always live in the primary). Sibling-repo `<ARTIFACT_ROOT>` values are only needed when sibling-specific artifacts (e.g., `Permissions.md` in a Salesforce sibling — Step 3a) need to land on that sibling's main checkout.

### Step 1: Identify the Feature
1. If given a REQ ID, locate all artifacts under `<ARTIFACT_ROOT>/.adlc/specs/REQ-xxx-*/`
2. If no REQ ID given, infer from the current branch name or recent merge commits
3. Read the requirement spec, architecture doc, and all task files
4. **Detect repository mode** — read `<ARTIFACT_ROOT>/.adlc/config.yml` in the primary repo. If it declares more than one entry under `repos:`, this is **cross-repo mode**; otherwise **single-repo mode**. In cross-repo mode also read `pipeline-state.json` from the spec directory — it holds the per-repo branch/worktree/PR/merge state.

### Step 2: Commit, Push, and Merge

**Determine the repo set to operate on**:
- **Single-repo mode**: operate on the current repo only. Skip to the single-repo steps below.
- **Cross-repo mode from `/proceed`**: `pipeline-state.json` already lists touched repos; each `repos[<id>].merged` reflects whether `/proceed` Phase 8 already merged that PR. Walk `mergeOrder` and for each repo either confirm it's merged (no-op) or run the single-repo merge sequence inside that repo's worktree.
- **Cross-repo mode standalone**: no `pipeline-state.json` — fall back to detecting touched repos from the config and checking for feature branches/open PRs in each. Proceed with the single-repo merge sequence in each repo that has pending work, in `merge_order` from the config.

**Single-repo merge sequence** — run this block inside each target repo's worktree (same mechanics as before):

1. **Branch check FIRST** — never commit on `main`. Run `git -C <worktree> branch --show-current`. If it reports `main` (or `master`), stop: create a feature branch (e.g., `agent/REQ-xxx-slug` or `feat/REQ-xxx-slug`) and switch to it with `git checkout -b <branch>` BEFORE touching any files. If you're already on a worktree branch from `/proceed` Phase 0, continue.
2. Check `git -C <worktree> status` and `git -C <worktree> diff` for any uncommitted changes related to the feature
3. If there are uncommitted changes:
   - Stage all relevant files (avoid secrets, `.env`, credentials)
   - Create a commit with message: `feat(REQ-xxx): <summary of changes>`
   - Include `Co-Authored-By: Claude <noreply@anthropic.com>`
4. Push the branch to remote with `git -C <worktree> push -u origin <branch>`
5. If no PR exists for this branch, create one using `gh pr create` (from inside the worktree, or with `gh -R <owner/repo>`) with a summary of what shipped
6. If CI checks exist, monitor the pipeline with `gh run watch` and report the result
7. **Rebase onto current main before merging** — in a sprint or long-running pipeline, upstream `main` may have advanced since the branch was cut. Run `git -C <worktree> fetch origin main` and check whether the branch is behind: `git -C <worktree> merge-base --is-ancestor origin/main HEAD`. If that command fails (exit 1), the branch is behind main and must be updated:
   - `git -C <worktree> rebase origin/main`
   - If there are conflicts, STOP and surface them to the user — do not try to resolve semantic conflicts blindly
   - On clean rebase, force-push with lease: `git -C <worktree> push --force-with-lease`
   - Re-run `gh pr checks <prUrl>` and wait for CI to re-pass before merging
8. Verify PR status is mergeable: `gh pr view <prUrl> --json mergeable,mergeStateStatus` should report `MERGEABLE` and a clean merge state. If not, stop and surface the reason.
9. Merge the PR using `gh pr merge <prUrl> --squash --delete-branch`. In cross-repo mode, update `pipeline-state.json` — set `repos[<id>].merged = true`.
10. **Capture cleanup state BEFORE leaving the branch**. You must record three things while you are still on the feature branch in the feature worktree, because the subsequent `git checkout main` may only work in the main worktree and you will lose the ability to look these up afterwards:
    - Branch name: `BRANCH=$(git -C <worktree> branch --show-current)`
    - Current working-tree path: `WT_PATH=<worktree>`
    - Main worktree path: `MAIN_WT=$(git -C <worktree> worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}')`
11. Move to the main worktree and update it: `git -C "$MAIN_WT" checkout main && git -C "$MAIN_WT" pull`
12. **Clean up local branch and worktree** (run from `$MAIN_WT`):
    - If `"$WT_PATH"` differs from `"$MAIN_WT"` (i.e., the work happened in a separate worktree), remove it: `git -C "$MAIN_WT" worktree remove "$WT_PATH"`. This handles BOTH the `/proceed` pattern (`.worktrees/REQ-xxx`) and the Claude Code harness pattern (`.claude/worktrees/<slug>`) without hardcoding either path.
    - If the feature branch still exists locally after the squash-merge (git does not recognize squash-merges as merged, so `git branch --merged` will miss it), delete it: `git -C "$MAIN_WT" branch -D "$BRANCH"`. Squash-merge is the default, so expect this to be the common case.
    - Prune any lingering remote-tracking refs: `git -C "$MAIN_WT" fetch --prune`
13. Verify cleanup: `git -C "$MAIN_WT" worktree list` should no longer include `$WT_PATH`, and `git -C "$MAIN_WT" branch` should no longer include `$BRANCH`. If either is still present, stop and surface the reason rather than silently moving on.

**Cross-repo aggregate log**: after walking every touched repo, emit a one-line summary per repo: `<repo-id>: merged <prUrl>, worktree cleaned` or `<repo-id>: already merged (from /proceed Phase 8)`.

### Step 3: Update ADLC Artifact Statuses

**All file paths in this step resolve under `<ARTIFACT_ROOT>/.adlc/...` — never against cwd.** The work-tree may already have been removed by Step 2.12 by the time `/proceed` invokes Phase 8 wrapup.

1. Set the requirement's frontmatter status to `complete` in `<ARTIFACT_ROOT>/.adlc/specs/REQ-xxx-*/requirement.md`
2. Set all task statuses to `complete` in `<ARTIFACT_ROOT>/.adlc/specs/REQ-xxx-*/tasks/*.md`
3. Update the `updated` date on all modified artifacts to today's date
4. If any tasks were deferred or descoped, note them in the requirement file under a "Deferred" section
5. If `<ARTIFACT_ROOT>/.adlc/specs/REQ-xxx-*/pipeline-state.json` exists, update it: set `"completed": true`, add a final entry to `phaseHistory` with `{phase, name, startedAt: <currentPhaseStartedAt>, completedAt: <now>}`, and clear `currentPhaseStartedAt` (set it to `null`) since no phase is in flight after wrapup

### Step 3a: Salesforce — Permissions.md gate

Skip this step in cross-repo mode for any sibling that did NOT touch Salesforce metadata.

For every Salesforce repo touched by this REQ that introduced or modified metadata (custom objects, custom fields, Apex classes, Apex triggers, LWC bundles, Flows, custom tabs, custom permissions), verify that a `Permissions.md` file exists and is current. Salesforce-rules.md mandates this file per feature, with assignment matrix and dependency mapping.

Search order:

1. `.adlc/specs/REQ-xxx-*/Permissions.md` — preferred (lives with the spec)
2. `force-app/main/default/permissionsets/<feature>/Permissions.md` — alternative
3. `Permissions.md` at the repo root with frontmatter `req: REQ-xxx`

If the file is **absent**, generate it from `templates/permissions-template.md` (or fall back to `~/.claude/skills/templates/permissions-template.md`). Populate:

- `id` field as `PERMS-<REQ-id>`
- `req` field as the current REQ id
- `app_prefix` from `.adlc/config.yml` `salesforce.app_prefix`
- The **Permission sets generated** table — list every `*.permissionset-meta.xml` file under `force-app/main/default/permissionsets/` that has a frontmatter `req: REQ-xxx` OR was created in this REQ's commits (`git log --diff-filter=A`)
- The **Dependency mapping** table — for each set, list which Apex class / SObject / field / flow it grants access to (read the permission set XML)
- Leave the **Assignment matrix** rows as placeholder personas — surface this to the user so they can fill in real persona names

If the file is **present but stale** (lists permission sets that no longer exist in the worktree, OR is missing permission sets that DO exist), regenerate the affected rows.

If the file is **present and current**, walk its anti-pattern checklist:

- ✅ No `View All Data` / `Modify All Data` granted in any permission set
- ✅ Object-level access split per field where possible (FLS-first)
- ✅ No permission set grants Read AND Delete on the same object
- ✅ No permission set lists more than 10 object permissions
- ✅ Sensitive data sits in a dedicated set, not bundled with general feature access

Run `python3 tools/sf-lint/check.py` over the touched permset files; surface any `perm-set-naming` or `perm-set-anti-pattern` finding as a wrapup blocker. The user must acknowledge before proceeding to Step 4.

If sf-lint flags permset findings, **STOP** — the merge in Step 2 has already happened, but knowledge capture and deploy in Step 4–6 should not proceed until the permission posture is corrected. Surface the findings and wait.

### Step 3b: Salesforce — Agentforce deploy-order gate

Skip this step unless `.adlc/config.yml` `salesforce.industries:` includes `agentforce`.

Salesforce-rules.md mandates the deploy order for Agentforce features:

```
fields/metadata → Apex → Flow → GenAiPromptTemplate / GenAiFunction / GenAiPlugin → publish → sf agent activate
```

If this REQ touched Agentforce metadata (any `.agent` file, `.genAiFunction-meta.xml`, `.genAiPlugin-meta.xml`, `.genAiPromptTemplate-meta.xml`), confirm:

1. **API version**: every touched Agentforce metadata file declares `<apiVersion>` ≥ `66.0`. Grep for `<apiVersion>` and reject anything below 66.0:
   ```sh
   find force-app -path '*/genAi*-meta.xml' -o -name '*.agent' | xargs grep -hE '<apiVersion>([0-9.]+)' | awk -F'[<>]' '{ if ($3 < 66.0) print $0 }'
   ```
2. **Deploy order**: walk the deploy log for the most recent staging/prod deploy (from Step 6, OR `sf project deploy report --target-org <staging-alias>`) and confirm the dependency-order:
   - Custom fields and metadata files appear in the deploy result before Apex
   - Apex appears before Flow
   - Flow appears before GenAi* (`GenAiFunction`, `GenAiPlugin`, `GenAiPromptTemplate`)
   - `sf agent activate` is the last step
3. **Variant-correct user**: read `.adlc/config.yml` `salesforce.agentforce_variant`. If `Service`, confirm a dedicated Einstein Agent User + system permission set was deployed; if `Employee`, confirm `default_agent_user` is omitted from the agent definition. Surface a finding if mismatched.
4. **`@InvocableVariable` wrappers**: every `@InvocableMethod` referenced by an Agent Script `apex://` target uses an `@InvocableVariable` wrapper class with named fields — never a bare `List<T>`. Grep `force-app/main/default/classes/*.cls` for `@InvocableMethod` and confirm.

If any check fails, surface as a wrapup blocker. The corrective action is a forward-fix deploy (Salesforce has no rollback) — recommend the user open a follow-up REQ if the deploy already shipped, OR re-run `/canary` against staging after fixing.

### Step 4: Capture Knowledge
Evaluate whether any decisions, patterns, or lessons should be persisted:

#### Architectural Decisions
- Were any new patterns introduced? If so, propose an update to `<ARTIFACT_ROOT>/.adlc/context/architecture.md`
- Were any existing patterns modified or deprecated?

#### Assumptions Validated or Invalidated
- Review assumptions from the requirement spec
- Log any that were validated, invalidated, or still unresolved to `<ARTIFACT_ROOT>/.adlc/knowledge/assumptions/` (NEVER `./...` — cwd may be a worktree that's about to be removed)
- Use the assumption template (check `<ARTIFACT_ROOT>/.adlc/templates/assumption-template.md` first, fall back to `~/.claude/skills/templates/assumption-template.md`)
- Name files: `ASSUME-xxx-slug.md`. Determine the next ID using the atomic counter at `<ARTIFACT_ROOT>/.adlc/.next-assume` (LESSON-110), wrapped in a POSIX `mkdir`-lock with a symlink pre-check (LESSON-014) so concurrent `/sprint` wrapups can't lose updates and a swapped-in symlink can't redirect the counter. **The counter and its lock live under the main checkout — not the worktree** (otherwise concurrent worktrees each see their own counter and collide):
  ```bash
  # ARTIFACT_ROOT was pinned in Step 0 — pass through, never re-derive.
  ASSUME_NUM=$(
    [ -n "$ARTIFACT_ROOT" ] || { echo "ERROR: ARTIFACT_ROOT not set — Step 0 must run first" >&2; exit 1; }
    LOCK="$ARTIFACT_ROOT/.adlc/.next-assume.lock.d"
    COUNTER="$ARTIFACT_ROOT/.adlc/.next-assume"
    if [ -L "$LOCK" ]; then
      echo "ERROR: $LOCK is a symlink — refusing (TOCTOU risk). Inspect manually." >&2
      exit 1
    fi
    for _ in $(seq 50); do mkdir "$LOCK" 2>/dev/null && break; sleep 0.1; done
    # Hard-fail if we never acquired the lock (REQ-416 verify C1).
    [ -d "$LOCK" ] || { echo "ERROR: failed to acquire $LOCK after 50 retries — aborting to avoid duplicate ASSUME id" >&2; exit 1; }
    NUM=$(cat "$COUNTER" 2>/dev/null || echo "1")
    echo $((NUM + 1)) > "$COUNTER"
    # rmdir guarded by symlink check; residual TOCTOU window accepted per ADR-4 / LESSON-014.
    if [ ! -L "$LOCK" ]; then rmdir "$LOCK" 2>/dev/null; fi
    echo $NUM
  )
  # `exit 1` inside the subshell terminates only the subshell — guard parent context.
  [ -n "$ASSUME_NUM" ] || { echo "ERROR: failed to allocate ASSUME number — aborting" >&2; exit 1; }
  ```
  If `.adlc/.next-assume` doesn't exist, scan `.adlc/knowledge/assumptions/` for the highest existing `ASSUME-xxx-` file, use the next one, and write the value after that to the counter. Use the counter ONLY — never re-scan after the counter exists. The counter prevents collisions when concurrent `/sprint` pipelines wrap up at the same time.

#### Lessons Learned

Claude drafts the lesson directly from in-context conversation memory. Consider:
  - Any surprises during implementation?
  - Approaches that didn't work and why?
  - Things that worked particularly well?
- Log notable lessons to `<ARTIFACT_ROOT>/.adlc/knowledge/lessons/` if they'd help future work (NEVER `./.adlc/knowledge/lessons/` — cwd may be a worktree that's about to be removed)
- Use the lesson template (check `<ARTIFACT_ROOT>/.adlc/templates/lesson-template.md` first, fall back to `~/.claude/skills/templates/lesson-template.md`)
- **Filename format is `<XYZ>-LESSON-NNN-slug.md`** (e.g., `SFC-LESSON-041-signed-url-ttl-mismatch.md`). The `<XYZ>` prefix comes from `project.shortname` in `.adlc/config.yml`. Legacy un-namespaced files (`LESSON-NNN-slug.md`) are still valid history; only **new** allocations get the prefix. Slugs are lowercase kebab-case, ≤6 words. Do not use date-prefixed names (`2026-MM-DD-…md`) or bare numeric prefixes (`034-…md`).
- **Allocate the next ID via the canonical allocator partial.** IDs are per-project, namespaced by `project.shortname`. The counter lives at `<ARTIFACT_ROOT>/.adlc/.next-lesson`. First allocation in a project bootstraps from the highest existing `<XYZ>-LESSON-NNN` and legacy `LESSON-NNN` under `.adlc/knowledge/lessons/`, so re-running `/init` mid-project never resets to 1. The lock at `.adlc/.next-lesson.lock.d` is shared with `/bugfix`'s lesson capture so concurrent runs mutually exclude.
  ```bash
  cd "$ARTIFACT_ROOT"
  . .adlc/partials/id-counter.sh 2>/dev/null || . ~/.claude/skills/partials/id-counter.sh
  LESSON_ID=$(allocate_lesson)
  # `allocate_lesson` runs in $(...). `return 1` from the partial only exits the
  # subshell — guard the parent context (LESSON-015):
  [ -n "$LESSON_ID" ] || { echo "ERROR: failed to allocate LESSON id — aborting before writing malformed lesson" >&2; exit 1; }
  # Extract the numeric suffix when you need LESSON_NUM in templates / paths:
  LESSON_NUM=${LESSON_ID##*-}
  ```
  The partial enforces: `project.shortname` (`^[A-Z]{3}$`), `mkdir`-based lock with symlink pre-check (LESSON-014), empty-counter fail-loud guards (LESSON-015), and a first-run bootstrap that scans `.adlc/knowledge/lessons/` for the high-water mark across BOTH legacy and namespaced ids. The legacy machine-global `~/.claude/.global-next-lesson` is no longer read or written.
- **Legacy files**: older projects may still have date-prefixed or bare-numeric lessons from before this convention was locked. Do not rename them in a wrapup PR — migration is a separate, dedicated operation. When scanning for the next ID, only count files matching `LESSON-*.md`; treat the legacy files as read-only history.
- Include `domain`, `component`, and `tags` so that `/spec`, `/architect`, `/reflect`, and `/review` can filter by relevance. The `component` field should be more specific than `domain` (e.g., `domain: API`, `component: API/auth` or `domain: iOS`, `component: iOS/SwiftUI`)

#### Convention Updates
- Were any new conventions established? Propose updates to `<ARTIFACT_ROOT>/.adlc/context/conventions.md`
- Were any existing conventions found to be problematic?

### Step 4b: Persist Knowledge to `main`

The Phase 2 squash-merge already shipped the feature commits to `main`. Step 4 just wrote new artifacts (lessons, assumptions, status updates, conventions) into `<ARTIFACT_ROOT>` — the **main checkout**, NOT the now-deleted feature worktree. Those files are uncommitted local changes on `main` and will sit there forever unless this step lands them.

This step is intentionally a **separate commit on `main`** (not part of the feature PR) because:
- The feature PR is already merged — there is no PR to amend.
- These artifacts capture knowledge **about** the merged change; they are not part of the change itself.
- A standalone commit makes the captured knowledge attributable and revertible without disturbing the feature commit.

Run inside `<ARTIFACT_ROOT>`:

```bash
git -C "$ARTIFACT_ROOT" status --short -- .adlc/ \
  | grep -qE '^\s*[?AM]' || { echo "wrapup: no knowledge artifacts to persist — skipping commit"; exit 0; }

# Pull first in case main moved while the feature was being merged.
git -C "$ARTIFACT_ROOT" checkout main
git -C "$ARTIFACT_ROOT" pull --ff-only origin main

# Stage only ADLC artifacts — never blanket-add (LESSON-110: don't sweep up
# stray files an interrupted earlier run may have left in the main checkout).
git -C "$ARTIFACT_ROOT" add \
  .adlc/specs/REQ-xxx-*/requirement.md \
  .adlc/specs/REQ-xxx-*/tasks/*.md \
  .adlc/specs/REQ-xxx-*/pipeline-state.json \
  .adlc/knowledge/lessons/LESSON-*.md \
  .adlc/knowledge/assumptions/ASSUME-*.md \
  .adlc/context/architecture.md \
  .adlc/context/conventions.md 2>/dev/null || true

# Bail cleanly if nothing was actually staged (all globs missed).
git -C "$ARTIFACT_ROOT" diff --cached --quiet && {
  echo "wrapup: nothing staged — skipping commit"
  exit 0
}

git -C "$ARTIFACT_ROOT" commit -m "chore(REQ-xxx): capture knowledge from completed feature

- requirement + tasks → status: complete
- new lessons / assumptions / convention updates from /wrapup
" || { echo "ERROR: knowledge commit failed — surface to user, do not retry blindly" >&2; exit 1; }

git -C "$ARTIFACT_ROOT" push origin main
```

Substitute the concrete REQ id for `REQ-xxx`. If `git push` is blocked by branch protection on `main`, surface that to the user — they will need to land the chore commit via a small PR (`chore/req-xxx-knowledge-capture` branch). Do **not** silently swallow a push failure: if knowledge isn't persisted upstream, the next `/wrapup` may re-allocate the same LESSON id from a stale counter view.

### Step 5: Generate Ship Summary
Create a concise summary suitable for sharing with the team. In cross-repo mode, list each repo/PR under a Repos section.

**Single-repo template**:
```
## REQ-xxx: Feature Title

**Status**: Shipped
**Branch**: agent/REQ-xxx-slug
**PR**: #nn
**Merged**: YYYY-MM-DD

### What shipped
- Bullet points of user-facing or developer-facing changes

### Key decisions
- Notable architectural or design decisions made during implementation

### Metrics
- Files changed: N
- Lines added/removed: +N / -N
- Tests added: N
- Coverage impact: X% -> Y% (if measurable)

### Deferred items
- Any work explicitly postponed for future

### Follow-up needed
- Any remaining work, monitoring, or verification required
```

**Cross-repo template** (replace the single `PR`/`Branch` lines with a Repos table):
```
## REQ-xxx: Feature Title

**Status**: Shipped
**Merged**: YYYY-MM-DD

### Repos
| Repo | Branch | PR | Files | +/- |
|------|--------|----|-------|-----|
| api    | feat/REQ-xxx-... | #12 | 7 | +320 / -15 |
| web    | feat/REQ-xxx-... | #45 | 3 | +88 / -2  |
| mobile | feat/REQ-xxx-... | #31 | 5 | +210 / -40 |

### What shipped
- Bullet points (call out cross-repo changes like new API contracts explicitly)

### Key decisions
### Metrics (aggregate across repos)
### Deferred items
### Follow-up needed
```

### Step 6: Deploy

Walk the touched Salesforce repos and promote the change set through `/canary`. Read `.adlc/config.yml` `orgs:` for environment aliases — every step below is conditional on what the project actually declares.

1. **Skip if no deployable Salesforce changes** (e.g., only ADLC docs / spec edits). The wrapup may complete with the merge alone.
2. **Promote to staging** via `/canary staging` (delegates to `sf project deploy validate` then `sf project deploy start` against the staging org alias). The `sf project deploy start:*` permission is on the `ask` list — Claude Code surfaces an ask-prompt; the user confirms once.
3. **Smoke gate**: when `salesforce.industries:` includes `agentforce`, `/canary` automatically runs `sf agent test run` against the test specs at `agentforce_test_specs:`. On any failure, STOP — recommend a forward-fix; do NOT auto-promote to prod.
4. **Confirm**: read `sf project deploy report --target-org <staging-alias> --json` and confirm the deploy id matches the run from `/canary staging`. Surface succeeded/failed component counts.
5. **Promote to production**: NEVER auto. Emit a one-line summary: "Staging deploy ✓ — run `/canary prod` to deploy to production." Do not auto-continue. The user runs `/canary prod` as a deliberate, separate invocation, and `.claude/settings.json` ask-gates `sf project deploy start --target-org prod*` and `sf agent activate` so even the explicit invocation surfaces a final confirmation.
6. **Vlocity / OmniStudio DataPacks**: when `industries:` includes `omnistudio`, after the standard sf deploy, confirm any DataPack pack deploys via `vlocity packDeploy` (the `Bash(vlocity packDeploy:*)` permission is also on `ask`). Run `vlocity packGetDiffs` first to confirm the pack manifest matches the deploy plan.
7. In cross-repo mode, emit a one-line deploy status per touched repo in the ship summary. External (non-SFDC) sibling repos use their own deploy mechanism — surface a TODO if their deploy is outside this skill's scope.

### Step 7: Clean Up
1. Check for any temporary files, debug logging, or feature flags that should be removed
2. Verify CLAUDE.md or other docs don't need updates based on what shipped

### Step 8: Recommend Next Steps
- If deferred items exist: "Consider creating `/spec` for deferred items: [list]"
- If follow-up monitoring is needed: "Monitor [what] for [how long]"
- If conventions were updated: "Review `.adlc/context/conventions.md` changes"
- Otherwise: "Feature complete. No follow-up needed."
