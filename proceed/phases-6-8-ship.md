---
parent: proceed
phases: "6-8"
---

# /proceed — Phases 6–8: Ship

Companion to `proceed/SKILL.md`. These three phases package verified work
into PRs (one per touched repo), sanity-check each PR, then merge in
configured order, deploy, and capture knowledge via `/wrapup`. SKILL.md
keeps a one-paragraph summary of each; the per-step PR body templates,
merge sequencing, and terminal-state contract live here.

---

### Phase 6: Create Pull Request(s)

**Gate**: `currentPhase` must be `6`. After completion: append `6`, set `currentPhase=7`.

**Goal**: Package the work into reviewable PRs — one PR per touched repo.

1. For each touched repo:
   - Inside that repo's worktree, ensure all changes are committed and push the feature branch: `git -C <worktree> push -u origin feat/REQ-xxx-short-description`
2. Set the requirement status to `complete` in its frontmatter (primary repo only).
3. **Detect the PR actor** — same probe used in Phase 8's local-bare fallback. If `origin` is a local bare path OR `gh` is unavailable/unauthenticated, **skip `gh pr create` for this repo** and write a synthetic marker URL `local-bare:<origin-path>#<branch>` to `repos[<id>].prUrl`. Phase 8 reads this marker and routes through the local hand-merge block. Do NOT halt here, do NOT prompt — the run continues straight to Phase 7 with a synthetic prUrl. End-of-phase log line: `<id>: local-bare origin — skipped gh pr create; will merge directly in Phase 8`.
4. Otherwise create a PR **in each touched repo** using `gh pr create` (invoke via `gh -R <owner/repo>` or by running `gh` from inside each worktree). In cross-repo mode, create the PR for the primary repo **last** so the primary PR body can link to all sibling PRs.
   - **Title (per repo)**: Short description referencing the REQ, tagged with the repo id when cross-repo (e.g., `feat(api): new endpoint [REQ-023]`).
   - **Body (per repo)**:
     ```
     ## Summary
     [2-3 bullet points describing what was built in THIS repo]

     ## Requirement
     REQ-xxx: [requirement title]
     Primary repo: <primary-repo-id>

     ## Related PRs (cross-repo)
     [Populated for siblings and also in the primary once its PR is created last.
      Omit entirely in single-repo mode.]
     - api: <url>
     - web: <url>

     ## Tasks Completed (this repo)
     - [x] TASK-001: [title]
     - [x] TASK-002: [title]

     ## Architecture Decisions
     [Key ADRs or "No architectural changes needed"]

     ## Test Coverage
     [Summary of tests added/modified in THIS repo]

     ## Reflection Notes
     [Key observations from the reflect phase — risks, assumptions, follow-ups]

     ## Merge Order
     [Only when cross-repo. List the mergeOrder from pipeline-state.json so
      reviewers know which PR merges first.]
     ```
5. After each PR is created (or the synthetic local-bare marker is written), persist `repos[<id>].prUrl` in `pipeline-state.json`.
6. After the last PR is created, go back and edit sibling PRs' bodies (`gh pr edit`) to add the cross-repo "Related PRs" section now that every URL is known. Skip this for any repo whose `prUrl` starts with `local-bare:` — there's no PR to edit.
7. Report all PR URLs to the user, grouped by repo and in `mergeOrder` sequence. Local-bare entries are reported as `<id>: local-bare (no PR — direct merge in Phase 8)`.

---

### Phase 7: PR Cleanup & CI

**Gate**: `currentPhase` must be `7`. After completion: append `7`, set `currentPhase=8`.

**Goal**: Lightweight sanity check on each PR — the full code review already happened in Phase 5. Do NOT re-run `/review`.

Do all the steps below **for every touched repo's PR**.

**Local-bare repos** (`prUrl` starts with `local-bare:`): no `gh pr diff` / `gh pr checks` to run. Substitute `git -C <repo-path> diff origin/<integrationBranch>...origin/<feat-branch>` for the diff scan and skip the CI-checks wait. The cleanup criteria below still apply — fix issues in the worktree and `git push` so Phase 8 picks up the latest tip.

1. Review the full PR diff using `gh pr diff <prUrl>` (use the URL stored in `repos[<id>].prUrl`).
2. Check for:
   - Stray debug logs, TODOs, or commented-out code
   - Files that shouldn't have been included (secrets, generated files, unrelated changes)
   - Commit message consistency and cleanliness
   - That the PR description accurately reflects the changes
   - Cross-repo consistency: if a sibling PR changes an API contract, verify this PR's corresponding consumer/producer code matches
3. If issues are found:
   - Fix inside the owning repo's worktree, commit with message: `fix(scope): PR cleanup [REQ-xxx]`
   - Push that worktree's branch: `git -C <worktree> push`
4. If CI checks are configured, verify each PR passes: `gh pr checks <prUrl>`. Wait for in-flight checks before moving on.

**End-of-phase log**: Emit one line per PR — "<repo-id>: clean, CI green" — followed by an aggregate "All N PRs ready for merge" or list any remaining concerns. Continue to Phase 8 immediately.

---

### Phase 8: Wrapup

**Gate**: `currentPhase` must be `8` and `7` must be in `completedPhases`. After completion: append `8`, set `"completed": true`.

**Goal**: Merge, deploy, capture knowledge, and close out the feature.

**Completion claim** (terminal state contract): the run's final report MUST lead with **exactly one** tag from `{merged, pr-ready, blocked, failed}`:

| Tag | Required preconditions |
|---|---|
| `merged` | Every touched repo has `repos[<id>].merged == true`. For hosted-remote repos, verifiable via `gh pr view --json state,mergedAt`. For local-bare repos, verifiable by checking that `origin/<integrationBranch>` contains the feat-branch tip (`git -C <repo-path> merge-base --is-ancestor origin/<feat> origin/<integration>`). **Local-bare repos MUST land here** — `pr-ready` is illegal for them. |
| `pr-ready` | **Hosted-remote-only.** All touched-repo PRs are `OPEN`, `MERGEABLE`, all required CI green. Used in cross-repo mode when the orchestrator owns merge sequencing, or in single-repo mode when the run is explicitly told not to merge. NEVER used for a repo whose `origin` is a local bare directory — that case must go through the local hand-merge fallback and emit `merged`. |
| `blocked` | Blocker requires human input. `pipeline-state.json.blockers` populated. |
| `failed` | Pipeline failed past automatic recovery. Failure details in `pipeline-state.json.notes`. |

A vague "Pipeline complete" claim without one of these tags is a protocol violation. When dispatched by `/sprint`, the orchestrator will reject untagged claims and treat them as `blocked`.

**Topology-driven merge actor**:
- **Single-repo REQ** (one touched repo): the pipeline owns the merge in this phase. Run `gh pr merge <prUrl> --squash --delete-branch` from the parent repo path (`repos[<id>].path`), NOT from the worktree. Then run the **wrapup-then-cleanup** block below. Terminal claim is `merged`.
- **Cross-repo REQ** (multiple touched repos): use the cross-repo merge sequencing block below. Terminal claim is `merged` after all repos land, or `pr-ready` if dispatched by an orchestrator that owns merge sequencing.

**Local-bare / no-`gh` fallback (run BEFORE the topology block above)**:

A repo whose `origin` is a local bare directory (path-based remote, no GitHub host) cannot use `gh pr merge`. Earlier runs hit this with KYC-REQ-001 and ended at `terminalState: "pr-ready"` indefinitely, blocking every dependent REQ. The pipeline must close the loop itself instead of waiting for a human hand-merge.

For each touched repo, decide actor at the top of Phase 8 by probing the remote and the `gh` CLI **once**:

```sh
REPO_PATH="${repos[<id>].path}"
PR_URL="${repos[<id>].prUrl}"
ORIGIN_URL=$(git -C "$REPO_PATH" remote get-url origin 2>/dev/null || true)

# Local-bare detection: origin resolves to a filesystem path (not http/git/ssh/gh URL)
# and that path exists. Includes file://, /abs/path, ./rel/path, and the prUrl marker
# 'local-bare:' written by Phase 6 when gh was unavailable.
case "$ORIGIN_URL" in
  http://*|https://*|git@*|ssh://*|git://*) IS_LOCAL_BARE=0 ;;
  file://*|/*|./*|../*) IS_LOCAL_BARE=1 ;;
  *) IS_LOCAL_BARE=0 ;;
esac
case "$PR_URL" in local-bare:*) IS_LOCAL_BARE=1 ;; esac

# gh availability: present, authenticated, and prUrl is a real https URL
GH_OK=0
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  case "$PR_URL" in https://github.com/*|https://*/pull/*) GH_OK=1 ;; esac
fi
```

Routing:

| `IS_LOCAL_BARE` | `GH_OK` | Actor |
|---|---|---|
| 0 | 1 | **Use `gh pr merge`** — proceed with the topology block above. |
| 1 | * | **Use the local hand-merge block below.** Skip the topology block for this repo. |
| 0 | 0 | **Halt as `pr-ready`** — `gh` should be present for a hosted remote but isn't. Surface a one-line note: `terminalState=pr-ready: gh CLI required for hosted remote <origin> but is unavailable / unauthenticated. Run \`gh auth login\` and re-run /proceed REQ-xxx --resume`. Do NOT attempt the local-bare path against a hosted remote — pushing past CI/branch-protection by hand is the wrong default. |

**Local hand-merge block** (runs only when `IS_LOCAL_BARE=1`). Per repo, in `mergeOrder`:

```sh
INTEGRATION="${integrationBranch:-main}"          # from pipeline-state.json
FEAT="${repos[<id>].branch}"                       # feat/REQ-xxx-...
REPO_PATH="${repos[<id>].path}"                    # main checkout, NOT the worktree

# Already-merged guard (recovering from an interrupted run)
if [ "$(jq -r ".repos[\"<id>\"].merged" pipeline-state.json)" = "true" ]; then
  continue
fi

# 1. Land the integration branch's tip locally before merging (no surprises).
git -C "$REPO_PATH" fetch origin "$INTEGRATION" "$FEAT"
git -C "$REPO_PATH" checkout "$INTEGRATION"
git -C "$REPO_PATH" reset --hard "origin/$INTEGRATION"

# 2. Mergeability probe — abort if the merge would conflict.
git -C "$REPO_PATH" merge-tree "origin/$INTEGRATION" "origin/$FEAT" \
  | grep -E '^(<<<<<<< |\+<<<<<<< )' >/dev/null && {
    echo "HALT: merge conflict between $FEAT and $INTEGRATION in <id>. Resolve manually."
    exit 1
}

# 3. Merge with --no-ff so the merge commit preserves the REQ boundary
#    (matches the existing 6e1f0a1-style merges hand-rolled by the orchestrator).
git -C "$REPO_PATH" merge --no-ff "origin/$FEAT" \
  -m "merge: <id> REQ-xxx <short-title>"

# 4. Push integration branch back to origin (works for local bare repos —
#    push to a filesystem path is just a pack copy).
git -C "$REPO_PATH" push origin "$INTEGRATION"

# 5. Delete the feature branch locally and on origin.
git -C "$REPO_PATH" push origin --delete "$FEAT" || true
git -C "$REPO_PATH" branch -D "$FEAT" || true

# 6. State write — same shape gh-merge would have produced.
jq ".repos[\"<id>\"].merged = true" pipeline-state.json > .tmp && mv .tmp pipeline-state.json
```

A merge conflict at step 2 is **legitimate halt #3** (same handling as the cross-repo halt below). Set `terminalState=blocked`, populate `blockers[]` with `{repo: <id>, reason: "merge conflict against <integrationBranch>"}`, and stop. Do NOT auto-resolve.

After the loop completes for all touched repos, fall through to **wrapup-then-cleanup**. The terminal claim is `merged` — never `pr-ready` — because this branch *did* land the merge. The pipeline-state's `terminalState` MUST be flipped to `merged` and `completed: true` written before the run exits, otherwise the dashboard's stall detector will keep flagging the REQ as in-flight forever.

**Cross-repo merge sequencing**:

1. Walk `mergeOrder` from `pipeline-state.json`. For each repo id in order:
   - Skip if `repos[<id>].merged == true` (already merged — recovering from an interrupted run).
   - Re-run the local-bare detection for THIS repo. The actor may differ per repo (e.g., a hosted `api` sibling and a local-bare `sfdc` primary). Use the local hand-merge block when `IS_LOCAL_BARE=1`; otherwise:
   - Merge that repo's PR (`gh pr merge <prUrl> --squash` or the project's configured merge strategy).
   - Wait for the merge to land, then set `repos[<id>].merged = true` in state.
   - If the next repo's PR was opened against `main` and depends on the just-merged changes being present, trigger a rebase/retarget before merging it. When siblings were developed in parallel worktrees against the same pre-REQ main, this is usually a no-op — but surface any auto-merge failure to the user as a conflict halt (legitimate halt #3).
2. Proceed to the **wrapup-then-cleanup** block below.

**Wrapup-then-cleanup** (single-repo and cross-repo both reach this block):

The order here is **load-bearing**: `/wrapup` writes ADLC artifacts (lessons, assumptions, status updates) into the primary repo's main checkout. `git worktree remove` cannot run before `/wrapup`. Earlier revisions reversed this and lost every captured lesson when the worktree was torn down.

1. **Run `/wrapup` with an explicit `--main-root`** so it doesn't have to re-derive `<ARTIFACT_ROOT>` from cwd:
   ```
   /wrapup REQ-xxx --main-root <repos[<primary-id>].path> [--touched-repos <id>,<id>,...]
   ```
   - `<primary-id>` is the entry in `repos` with `primary: true`.
   - `<repos[<primary-id>].path>` is the absolute path to the primary repo's **main checkout** (NOT its worktree under `.worktrees/REQ-xxx/`). This value was frozen by Phase 0 step 8 and is the same across all phases of the run.
   - In cross-repo mode also pass the comma-separated list of touched repo ids so `/wrapup` can emit the cross-repo ship summary and walk each sibling for deploy.
   - `/wrapup` will: update spec/task statuses, append assumptions/lessons, run any Salesforce gates (Step 3a/3b), generate the ship summary, deploy via `/canary`, and (Step 4b) commit the ADLC artifact changes onto `main` in the primary repo as a separate `chore(REQ-xxx): capture knowledge ...` commit.
2. **Verify `/wrapup` succeeded** before proceeding to cleanup. If it surfaced a Salesforce permset blocker or a deploy failure, STOP — do NOT remove the worktree. The user resolves the blocker and re-runs `/wrapup` (or `/canary` directly) before the pipeline can finish.
3. **Now remove the worktree in each touched repo**, using the absolute path from state:
   ```
   git -C <repo-path> worktree remove <repos[<id>].worktree>
   ```
   Do NOT use the relative `.worktrees/REQ-xxx` form here. Removal is safe at this point: `/wrapup` Step 4b already committed the captured knowledge to the main checkout, which is a separate working tree.
4. Update `pipeline-state.json` with `"completed": true`.
5. The pipeline is now complete.

**End-of-phase log**: Emit the ship summary from wrapup including per-repo merge confirmations and deployment status. Pipeline complete.
