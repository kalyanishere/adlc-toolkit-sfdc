---
name: proceed
description: End-to-end ADLC pipeline that takes a requirement from spec through to deployed. Takes a REQ number as argument and runs validate → fix → architect → fix → implement → verify (reflect + review) → create PR → wrapup (merge, deploy, knowledge capture). Use when the user says "proceed", "proceed with REQ-xxx", "run the pipeline", "take REQ-xxx to completion", "implement REQ-xxx end to end", or wants to advance a drafted requirement all the way through to deployment in one shot.
---

# Proceed — Full ADLC Pipeline

You are an autonomous ADLC orchestrator. Given a requirement number (REQ-xxx), you drive it from validated spec all the way to a pull request — validating at each gate, fixing issues automatically, and only pausing when you're stuck or need human input.

## Execution Mode

This skill supports two modes:

1. **Main conversation mode** (default): Dispatches formal agents (defined in `~/.claude/agents/`) for parallelism at Phase 4 (task implementation) and Phase 5 (verify). Use this mode when running `/proceed` directly.
2. **Subagent mode** (when running as a `pipeline-runner` agent inside `/sprint`): Execute ALL phases sequentially in-context. Do NOT dispatch sub-agents. At Phase 4, implement tasks one at a time. At Phase 5, run the reflector + reviewer checklists sequentially in your own context using the criteria from the agent definitions. Subagents cannot spawn other subagents.

You are in subagent mode if you were explicitly told so in your launch prompt.

## Autonomous Execution Contract

`/proceed` is an **autonomous orchestrator**. It is designed to run end-to-end without human input. The skill has exactly **three** legitimate halt points; every other instruction below is a log step, not a pause:

1. **Validation fails 3 times at any gate** (Phase 1 or Phase 3) — surface blockers.
2. **Reflector surfaces user-facing questions** (Phase 5, Step C item 4) — surface as a numbered list and wait.
3. **Merge conflicts during rebase** (Phase 8 / wrapup) — surface conflicts and wait.

For everything else — including every **End-of-phase log** block below, every agent dispatch, every commit, every PR creation, every CI wait — you **continue immediately** to the next step without asking the user. Prompt only for tool-level permissions on truly destructive operations (these are governed by `.claude/settings.json`, not this skill).

**Writing logs vs asking questions**: when the skill says "report X" or "log Y", emit a one-line status line to the conversation and continue. Do NOT phrase it as a question or wait for acknowledgment. A bad example: "Spec validated — shall I proceed to Phase 2?" A good example: "Spec validated. Moving to Phase 2."

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- SF quality checklist: !`cat .adlc/partials/sf-quality-checklist.md 2>/dev/null || cat ~/.claude/skills/partials/sf-quality-checklist.md 2>/dev/null || echo "No sf-quality-checklist found"`
- Sprint dashboard: !`sh ~/.claude/skills/tools/sprint-dashboard/launch.sh`

## Arguments

The user provides a requirement ID, e.g., `/proceed REQ-023` or `/proceed 23`.

- Normalize to `REQ-xxx` format (zero-pad to 3 digits if needed)
- Locate the spec at `.adlc/specs/REQ-xxx-*/requirement.md`
- If the spec doesn't exist, stop and tell the user to run `/spec` first

## Repository Configuration (single-repo vs cross-repo)

Some requirements touch one repo; others (e.g., a feature that simultaneously changes a mobile app, an API, and a web frontend) touch multiple repos. `/proceed` supports both.

**"Primary" is per-REQ, not a fixed role.** The primary repo for a given REQ is simply **the repo where you invoked `/proceed` from** — that repo's `.adlc/` holds the spec, tasks, and `pipeline-state.json` for this REQ. A different REQ can originate in a different repo; that REQ's primary is the other repo. Every repo that might host a REQ needs its own `.adlc/` structure (from `/init`) and its own `.adlc/config.yml` so it can act as primary when a REQ starts there.

**Single-repo mode** (the invoking repo's config has no siblings, or no config at all): existing behavior — one worktree, one PR, one merge. All phases run against the invoking repo. Used for work that's scoped to one repo.

**Cross-repo mode** (the invoking repo's config lists siblings): the invoking repo is primary for this REQ. Sibling repos are registered by id → path. `/proceed` creates a worktree in each touched repo, routes tasks by their `repo:` frontmatter field, opens one PR per repo, and merges in `merge_order`.

**Config schema** (`.adlc/config.yml`, present in every repo that can originate a REQ):

```yaml
repos:
  # Self — mark the current repo as primary. Path is implicit (it's this repo).
  # Each repo's config marks ITSELF as primary. The configs across repos end
  # up being mirror images of each other; that's expected and correct.
  web:
    primary: true
  # Siblings — other repos this one might coordinate with. Path is relative
  # to THIS repo's root, or absolute. Every sibling must be cloned locally.
  api:
    path: ../api
  mobile:
    path: ../mobile

# Merge order for Phase 8 when this repo is primary. If omitted, defaults to
# the order repos appear above. Only touched repos (those with tasks in the
# current REQ) are merged; untouched ones are skipped.
merge_order:
  - api
  - web
  - mobile
```

**Rules**:
- In each repo's own config, exactly one entry — that repo itself — has `primary: true`. Sibling entries describe other repos.
- Every repo that can originate a REQ needs `/init` run in it AND its own `.adlc/config.yml`. Repos that will only ever participate as siblings (never originate REQs) technically don't need a config, but it's cheap insurance — configure them anyway so any of them can host a REQ later.
- Task frontmatter must include a `repo:` field naming one of the invoking repo's configured repo ids. A task without `repo:` defaults to the invoking (primary-for-this-REQ) repo.
- "Touched repos" for a REQ = the set of distinct `repo:` values across its tasks.
- If the invoking repo's config has only itself (no siblings), or the file is absent, behave as single-repo.
- Sibling repo paths must exist and be git repositories. Fail fast in Step 0 if any are missing.

**Terminology used below**:
- **Primary repo** — for this REQ, the repo `/proceed` was invoked from. Hosts `.adlc/`, spec, state file. Always participates.
- **Touched repo** — any repo (primary or sibling) that has at least one task in this REQ.
- **Repo worktree** — `<repo-path>/.worktrees/REQ-xxx` for each touched repo, on branch `feat/REQ-xxx-short-description` (same branch name across repos).

## Complexity-aware phase shape (REQ-C)

Read `complexity:` from the REQ frontmatter (`.adlc/specs/REQ-xxx-*/requirement.md`). It's one of `trivial | small | medium | large`. If absent, default to `small`. The tier picks how much orchestration to spend — the *gates* below stay safe in every tier; only the *fan-out* changes.

| Phase | trivial | small | medium | large |
|---|---|---|---|---|
| Phase 1 (validate spec) | skip — trust author's frontmatter | inline single-pass check | full /validate | full /validate |
| Phase 2 (architect) | inline (no explore agents, no architecture.md) | inline (no explore agents) | full /architect (3-agent fan-out) | full /architect + ADR capture |
| Phase 3 (validate tasks) | skip | inline check | full /validate | full /validate |
| Phase 4 (implement) | direct in-context — no task-implementer dispatch | task-implementer per task | task-implementer per task | task-implementer per task |
| Phase 5 (verify) | reflector only | reflector + quality-reviewer (2 agents) | full 6-agent panel | full 6-agent panel + re-verify |
| Phase 5 re-verify | skip | skip | conditional (if Critical fixed) | conditional |
| Phase 6 (PR) | normal | normal | normal | normal |
| Phase 7 (CI) | normal | normal | normal | normal |
| Phase 8 (wrapup) | normal | normal | normal | normal |
| Canary ladder | sandbox-only | sandbox + staging | full ladder | full ladder |

**Hard rules that apply at every tier (do not skip):**
- Worktree isolation (Step 0) — always.
- `pipeline-state.json` writes — always.
- Local pre-flight gates (REQ-B perm-set FLS, REQ-F generalized metadata) — always when applicable metadata is in the diff.
- Coverage policy gate (REQ-A) — always; only the verbosity changes by tier.
- Three legitimate halt points in the Autonomous Execution Contract — always.

Record the resolved tier at the top of the run log: `Complexity: <tier> — phase shape: <summary>`. Persist it in `pipeline-state.json` as `complexity: "<tier>"` so a resumed run uses the same shape.

## The Pipeline

Execute these phases in order. Each phase has a validation gate — if validation fails, fix the issues and re-validate. Loop up to 3 times per gate; if still failing after 3 attempts, stop and present the remaining issues to the user.

## Pipeline State Tracking

**CRITICAL**: You MUST maintain a state file to track pipeline progress. This prevents phases from being skipped during long-running pipelines.

**State file location**: `.adlc/specs/REQ-xxx-*/pipeline-state.json`

**Schema rules — types are strict, follow them exactly**:

- `currentPhase`: **integer 0..8** (NOT a string like `"phase-3-validate-architecture"`). Use the descriptive name in `phaseHistory[*].name` if you want a human-readable label.
- `completedPhases`: **array of integers**. ALWAYS write it (never omit), even when empty. Append the integer phase number after each phase completes.
- `phaseHistory[*].phase`: **integer 0..8**, matching `currentPhase`'s type. NOT a string.
- `phaseHistory[*].name`: **string**, the human-readable phase title (e.g. `"Create Worktree + Preflight"`).
- `phaseHistory[*].startedAt` / `completedAt`: ISO-8601 UTC strings, sourced from `date -u +"%Y-%m-%dT%H:%M:%SZ"` (see Gate Protocol — Timestamps come from the OS).
- `completed`: **boolean**, true ONLY when Phase 8 (Wrapup) finishes.
- `startedAt` / `currentPhaseStartedAt`: ISO-8601 UTC strings; `currentPhaseStartedAt` is `null` once `completed` is `true`.

These types are what the sprint dashboard, slim-mode `jq` projection in `/sprint`, and Phase 5 reviewers all depend on. Writing strings where numbers are required, or omitting `completedPhases`, breaks the dashboard's phase strip and makes a live pipeline look stalled. The dashboard heals what it can but surfaces a `⚠ schema` pill — treat any such pill as a runner bug.

**Schema example**:
```json
{
  "req": "REQ-xxx",
  "branch": "feat/REQ-xxx-short-description",
  "complexity": "small",
  "startedAt": "2026-03-27T10:00:00Z",
  "completed": false,
  "currentPhase": 0,
  "currentPhaseStartedAt": "2026-03-27T10:00:00Z",
  "completedPhases": [],
  "phaseHistory": [
    { "phase": 0, "name": "Create Worktree", "startedAt": "2026-03-27T10:00:00Z", "completedAt": "2026-03-27T10:01:00Z" }
  ],
  "repos": {
    "web": {
      "primary": true,
      "path": "/absolute/path/to/web",
      "worktree": "/absolute/path/to/web/.worktrees/REQ-xxx",
      "branch": "feat/REQ-xxx-short-description",
      "touched": true,
      "prUrl": null,
      "merged": false,
      "snapshotBranch": null,
      "snapshotPR": null
    },
    "api": {
      "primary": false,
      "path": "/absolute/path/to/api",
      "worktree": "/absolute/path/to/api/.worktrees/REQ-xxx",
      "branch": "feat/REQ-xxx-short-description",
      "touched": true,
      "prUrl": null,
      "merged": false,
      "snapshotBranch": null,
      "snapshotPR": null
    }
  },
  "mergeOrder": ["api", "web"],
  "phase4": {
    "currentTask": null,
    "completedTasks": [],
    "failedTasks": []
  }
}
```

The `repos` block is the canonical registry for this pipeline run. Every cd/commit/push/PR/merge operation reads the target repo's `path` or `worktree` from here — never from cwd inference. `touched: true` means at least one task targets this repo; untouched repos skip Phases 4–8. `mergeOrder` is the list of touched repo ids in the order Phase 8 will merge them (primary is always a member).

**Single-repo mode**: `repos` contains exactly one entry with `primary: true, touched: true`, and `mergeOrder` is `[that-one-id]`. All phase logic still reads from `repos` — there is no separate code path.

The `phase4` block tracks task-level progress during implementation so that a mid-Phase-4 context compression can resume from the exact task in progress rather than restarting the phase. `currentTask` holds the TASK-xxx ID being worked on right now; `completedTasks` holds IDs of tasks whose status is `complete` and whose commit has landed; `failedTasks` holds IDs that hit unrecoverable errors and were surfaced to the user. Other phases do not need sub-state.

The `snapshotBranch` and `snapshotPR` fields on each `repos.<id>` entry are **deprecated as of REQ-380**. The skill no longer writes them; they remain in the schema for read-back compatibility with state files written between REQ-362 and REQ-380. A missing or null value is the expected state on all new runs. Snapshot promotion (the `staging → main` PR creation that previously ran in Phase 8a) is now handled out-of-band by a per-project workflow on staging-tip CI greenness; consult the project's CI configuration.

**Gate Protocol — follow exactly**:

**Timestamps come from the OS, never from the LLM.** Every `<now>` placeholder in this document — `startedAt`, `currentPhaseStartedAt`, every `phaseHistory[*].startedAt` and `completedAt` — MUST be the literal output of:

```bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
```

run via the Bash tool at the moment the value is needed. Do NOT type a timestamp in (no "today is 2026-06-06" reasoning, no "I'll use the current ISO-8601 time"). The LLM has no reliable clock and freelancing values poisons the dashboard's Active/Idle telemetry — fabricated `2026-06-06T00:00:00Z` values are how this gets caught. If the Bash command fails, halt the pipeline rather than guessing.

The same rule applies to subagent dispatches (pipeline-runner under /sprint): the agent's first action when reaching any timestamp write MUST be to run the Bash command above. State-file writes happen via Edit or Write — both of which require the value to be the exact captured Bash output, not a value the LLM types.

1. **Initialize** the state file at the start of Step 0 with `currentPhase: 0, currentPhaseStartedAt: <now>, completedPhases: [], completed: false, repos: {...resolved from config...}, mergeOrder: [...], phase4: { currentTask: null, completedTasks: [], failedTasks: [] }`
2. **Before starting any phase**: read `pipeline-state.json`. Verify `currentPhase` equals the phase you're about to start AND the previous phase is in `completedPhases`. If either check fails, **STOP** — you skipped a phase. Go back and complete it. **Telemetry**: if `currentPhaseStartedAt` is null/missing or if `currentPhase` was just advanced (i.e. you're entering a new phase), set `currentPhaseStartedAt` to the current ISO-8601 timestamp before doing any phase work. Resuming an interrupted phase MUST preserve the existing `currentPhaseStartedAt` (do NOT overwrite — that would erase already-accrued execution time on resume).
3. **After completing any phase**: append the phase number to `completedPhases`, append an entry to `phaseHistory` with `{phase, name, startedAt: <currentPhaseStartedAt>, completedAt: <now>}`, set `currentPhase` to the next phase number, and set `currentPhaseStartedAt` to the current timestamp (the next phase begins immediately). On the final phase (Phase 8), set `currentPhaseStartedAt` to `null` instead — the pipeline is done.
4. **Phase 4 task-level writes**: When starting a task, set `phase4.currentTask` to its TASK-xxx ID. When its commit lands (in the task's target-repo worktree), append the ID to `phase4.completedTasks` and clear `currentTask`. On unrecoverable failure surfaced to the user, append to `phase4.failedTasks` instead.
5. **Worktree paths are immutable post-Step-0**: once Step 0 records `repos[<id>].worktree`, every subsequent phase (1–8) MUST read the path from state and MUST NOT re-derive it from cwd, the REQ id, or any naming convention. This applies on the happy path, not just on resume. (Step 0 itself reads cwd exactly once — at item 2 of Step 0 — to initialize the registry, then freezes the path into state; the prohibition starts from the moment Step 0 completes.)
5b. **Resume from interruption**: If the state file already exists when you start, read it and resume from `currentPhase`. Trust `repos` as the source of truth for worktree paths. If `currentPhase` is 4 and `phase4.currentTask` is non-null, resume that specific task (re-read its file, use `repos[<task.repo>].worktree` for every git/file operation, re-check whether its commit already landed, continue or restart as appropriate) before moving to the next task in the dependency graph. Never replay tasks already in `completedTasks`.
6. **If context has been compressed**: re-read `pipeline-state.json` before doing anything and treat it as the source of truth for `currentPhase`, `repos`, and `phase4`. Do not rely on memory of which phase, task, or repo you're in.
7. **Per-repo writes during Phases 6–8**: when a PR is created, write its URL to `repos[id].prUrl`. When a PR merges, set `repos[id].merged = true`. These writes let a mid-Phase-8 interruption resume merges in order without double-merging.
8. **On completion**: After Phase 8 (Wrapup) finishes, set `"completed": true` in the state file.

Each phase below has a one-line **Gate** reminder. The full protocol above applies to every gate.

---

### Step 0: Preflight + Registry + Pre-Validation State File + Load Shared Context (ALWAYS FIRST)

**Before doing anything else**, resolve the repository set, write a *pre-worktree* state file so the sprint dashboard sees the pipeline immediately, and prime the shared context. **Worktree creation is deferred until after Phase 1 (Validate Spec)** so a failed validation does not leave a stray worktree behind. See "Step 1.5: Create Worktrees After Validation" below for the worktree creation step.

1. **Preflight** — verify all prerequisite files exist in the **primary** repo (stop with a clear message if any are missing):
   - `.adlc/context/project-overview.md` — run `/init` if missing
   - `.adlc/context/architecture.md` — run `/init` if missing
   - `.adlc/context/conventions.md` — run `/init` if missing
   - `.adlc/specs/REQ-xxx-*/requirement.md` — run `/spec` if missing
2. **Resolve repo registry**:
   - Read `.adlc/config.yml` if it exists. If absent or has no `repos` block, use single-repo mode: the registry is `{ <cwd-repo-id>: { primary: true, path: <cwd>, touched: true } }` where the repo id is the basename of the cwd.
   - In cross-repo mode: the primary entry's `path` is cwd. Resolve each sibling's `path` to an absolute path (relative paths are relative to the primary repo root). Verify each path exists and is a git repo (`git -C <path> rev-parse --git-dir`). If any sibling is missing, stop with a clear error listing the missing repos.
3. **Determine touched repos** (best-effort at Step 0; confirmed after Phase 2):
   - If tasks already exist under `.adlc/specs/REQ-xxx-*/tasks/`, read each task's `repo:` field to compute the touched set.
   - If tasks don't exist yet (fresh pipeline), assume every configured repo is potentially touched. Worktrees are NOT created here — that happens in Step 1.5 after validation passes. Post-Phase-2, untouched repos will be marked `touched: false`.
   - The primary is always touched (even if no primary tasks — it hosts the spec and state file).
4. **Determine the integration branch, then fetch it in each touched repo.** The base for feature branches is NOT always `main` (LESSON-036 — sprinted runners that hardcoded `main` in a staging-first repo paid a mid-pipeline rebase + PR-retarget every time). Detect the repo's branch model; **any one** signal is sufficient:
   - `.adlc/config.yml` declares a `gcp.staging_project` (or otherwise indicates a staging-first deploy), OR
   - a `.github/workflows/*` enforces a `verify-head-ref` / branch-protection head-ref check, OR
   - `CLAUDE.md` describes a "two-branch" / "staging-first" / "staging → main promotion" pipeline.

   If any signal is present, `<integration-branch>` is the project's integration branch (`staging` unless the project names another); otherwise `<integration-branch>` is `main`. **Always fetch before reasoning about any ref or spec presence** (never trust a stale local ref — LESSON-036):
   ```bash
   git -C <repo-path> fetch origin
   ```
   Do NOT `git checkout <integration-branch>` in `<repo-path>` — it may be checked out in another worktree and fail. Feature branches and the Phase 6 PR base MUST use `<integration-branch>`, never a hardcoded `main`. The worktree (Step 1.5) is created directly from `origin/<integration-branch>`.

5a. **Initialize `pipeline-state.json` in the primary repo's MAIN CHECKOUT** at `<primary-repo-path>/.adlc/specs/REQ-xxx-*/pipeline-state.json` with `currentPhase: 0, currentPhaseStartedAt: <now>, completedPhases: [], completed: false, startedAt: <now>, integrationBranch: <integration-branch>, repos: {...resolved registry, paths/branches set, worktree: null for each repo since worktrees do not yet exist...}, mergeOrder: [...from config.yml or declared order, filtered to touched repos...], phase4: { currentTask: null, completedTasks: [], failedTasks: [] }`. **Pre-worktree state file**: this initial write goes to the main checkout, NOT a worktree, because worktrees are created later (Step 1.5). The sprint dashboard's worktree-aware scan picks up this main-checkout file within ~1.5s, so Phase 0 and Phase 1 are visible the moment `/proceed` starts. Step 1.5 will move this file into the worktree once one exists.

   `integrationBranch` is the value resolved in step 4. `currentPhaseStartedAt` records when the in-flight phase began so the dashboard can report "Active" execution time accurately. If the file already exists at this path, read it and resume from `currentPhase` (and from `phase4.currentTask` if mid-Phase-4) — do NOT overwrite the existing `currentPhaseStartedAt` (preserving it keeps mid-phase telemetry honest across resume). On resume past Phase 1, the state file should already be in the worktree (Step 1.5 having moved it earlier) — read from there instead.

5b. **Load shared context ONCE from the primary main checkout** — use the Read tool to load these into conversation context so every subskill can reference them without re-reading. (At this point we are still in the primary repo's main checkout; cd into the worktree happens in Step 1.5.):
   - `.adlc/context/architecture.md`
   - `.adlc/context/conventions.md`
   - `.adlc/context/project-overview.md`
   - `.adlc/specs/REQ-xxx-*/requirement.md`
   - `.adlc/config.yml` (if present)
**Preflight verified** — when you invoke subskills in later phases, they may skip their own prerequisite checks (already validated here) AND they may skip re-reading `architecture.md` / `conventions.md` / `project-overview.md` (already in context). Treat the Step 0 loads as authoritative for the rest of the pipeline. Worktree creation is intentionally NOT part of Step 0 — it runs in Step 1.5 after Phase 1 passes.

**After completing Step 0**: Update `pipeline-state.json` — add `0` to `completedPhases`, add Step 0 to `phaseHistory`, set `currentPhase` to `1`.

---

### Phase 1: Validate the Requirement Spec
<!-- companion: proceed/phases-1-3-validation.md -->
**Gate**: `currentPhase` must be `1`. After completion: append `1`, set `currentPhase=2`.

Run `/validate` against the REQ spec. Validation reads `.adlc/specs/REQ-xxx-*/requirement.md` from the **primary main checkout** — at this point no worktree exists yet, and that's deliberate. APPROVED → mark `approved`, advance to Step 1.5. NEEDS REVISION → fix FAILs (in the main-checkout requirement.md) and re-validate (up to 3 loops); remaining blockers are legitimate halt #1. End-of-phase log: "Spec validated and approved." Full step list in companion.

If validation surfaces unrecoverable blockers, halt — the pipeline never created any worktree, so cleanup is a no-op. Failed validation does not leave artifacts behind.

---

### Step 1.5: Create Worktrees + Move State File Into Primary Worktree

Now that validation has passed, create the per-repo worktrees and migrate the pipeline-state file into the primary worktree. Subsequent phases (2–8) read and write the state file from the worktree, NEVER the main checkout.

1. **Parse the declared worktree path (primary repo only)** — scan the launch prompt for the dispatch-line contract. The format is normative in `REQ-263 architecture.md` ("The dispatch-line contract" section); do not change the regex or format here without updating that document.
   - Regex: `^WORKTREE PATH \(mandatory\): (.+)$` (entire line, capture group is the absolute path).
   - If multiple lines match the regex, use the **first** match and ignore the rest. (This makes parser behavior deterministic if a future change accidentally embeds free-text content that matches.)
   - If present, use the captured path **verbatim** as the primary repo's worktree path. Do not modify, normalize, or append to it. Compute `<primary-worktree-path>` = the captured value.
   - If absent (e.g., a direct `/proceed REQ-xxx` invocation by a user), fall back to deriving `<primary-worktree-path>` = `<primary-repo-path>/.worktrees/REQ-xxx` (where REQ-xxx is the concrete REQ id, not a literal placeholder). This preserves existing behavior for direct invocations.
   - Sibling repo worktree paths are always derived: for each sibling repo `s`, `<sibling-worktree-path[s]>` = `<sibling-repo-path[s]>/.worktrees/REQ-xxx` from `.adlc/config.yml` — the dispatch line declares only the primary path.

2. **Validate against `git worktree list` before adding** — for **each** touched repo (primary and every sibling), run:
   ```bash
   git -C <repo-path> worktree list --porcelain
   ```
   Parse the line-oriented output: blocks separated by blank lines. Each block contains `worktree <abs-path>`, `HEAD <sha>`, and either `branch <ref>` or `detached`. Locked or prunable worktrees may add extra lines (`locked [<reason>]`, `prunable <reason>`) — ignore those; the only fields that matter for collision detection are `worktree` and `branch`. The first block is always the repo's primary working tree (the repo root) — it will not match any `<repo-path>/.worktrees/REQ-xxx` target path, so it is harmlessly skipped. Continue scanning every subsequent block.

   Compute `<expected-branch-ref>` = `refs/heads/feat/REQ-xxx-<slug>` where `<slug>` is the same slug `/proceed` would derive for this REQ (the value that becomes `repos[<id>].branch` in state). For a fresh run, derive the slug from the REQ title per the project's branch-naming convention; for a resume, read it from `repos[<id>].branch`. Then for each per-repo target path (`<primary-worktree-path>` for primary, `<sibling-worktree-path[s]>` for each sibling), classify the registration state:
   - **No match** (target path not registered in any block): proceed to step 3 (`git worktree add` as normal).
   - **Match on `<expected-branch-ref>`** (same path, same branch): treat as resume per ADR-2 — record the path in state and **skip** the `git worktree add` for this repo. No halt, no re-add.
   - **Match on a different branch ref** (or a `detached` block at the target path): halt the pipeline immediately with a clear error naming the repo, the target path, the conflicting ref (or `detached HEAD`), and the cleanup commands the user must run. **Quote the substituted `<branch>` and `<path>` values with single quotes** in the surfaced commands so a user copy-paste cannot execute injected shell from a hostile branch name:
     ```
     Worktree collision in <repo-id>: '<path>' is already registered to '<other-branch>'
     (or detached HEAD), but REQ-xxx requires '<expected-branch-ref>'. Resolve with:

       git -C '<repo-path>' worktree remove '<path>'                # add --force if the worktree has uncommitted work you intend to discard
       git -C '<repo-path>' branch -D '<other-branch>'              # -D already forces deletion regardless of merge status; verify with `git log main..'<other-branch>'` first if you may have unmerged work to keep

     Then retry.
     ```
     This is a fail-loud halt and is a **precondition error** — it does **NOT** count toward the three legitimate halt points listed in the Autonomous Execution Contract. The three-halt quota begins counting only once the pipeline is past Step 1.5. The same error format applies whether the colliding repo is primary or sibling.

3. Create a worktree in each touched repo on the same branch name (skip any repo where step 2 classified the registration as a same-branch resume):
   ```bash
   git -C <repo-path> worktree add -b <branch-name> <worktree-path> origin/<integration-branch>
   ```
   - The new feature branch is cut from `origin/<integration-branch>` (the ref resolved in Step 0 item 4 — `staging` in two-branch repos, `main` otherwise), NOT from local `main`/`HEAD` (LESSON-036). The `-b` creates the branch; the explicit `origin/<integration-branch>` start-point makes the base deterministic regardless of what is checked out in the repo path.
   - `<worktree-path>` is the **absolute** path resolved in step 1 (`<primary-worktree-path>` for primary, `<sibling-worktree-path[s]>` for each sibling) — do **NOT** substitute a relative `.worktrees/REQ-xxx` here, even though the convention happens to produce an equivalent location. The whole point of the contract is that the orchestrator-declared absolute path is honored verbatim.
   - `<branch-name>` is `<expected-branch-ref>` from step 2 with the `refs/heads/` prefix stripped — i.e., literally `feat/REQ-xxx-<slug>`. Pass the bare branch name (not the full ref) to `git worktree add -b`. (On a same-branch resume, step 2 already skipped this add — the existing worktree/branch is reused as-is.)

   Record each repo's absolute `worktree` path and `branch` in the main-checkout state file's `repos` block. The recorded path is **immutable** for the rest of the run — Phases 2–8 read it from `repos[<id>].worktree`, never re-derive from cwd.

4. **Move the pipeline-state file into the primary worktree.** The pre-validation file at `<primary-repo-path>/.adlc/specs/REQ-xxx-*/pipeline-state.json` (written in Step 0 item 5a) becomes the live file at `<primary-worktree-path>/.adlc/specs/REQ-xxx-*/pipeline-state.json`. Use a copy + remove (NOT `mv`) and ensure both writes happen via the file system, not git, since the file is untracked at this point in both locations.
   ```bash
   mkdir -p "<primary-worktree-path>/.adlc/specs/REQ-xxx-*"
   cp "<primary-repo-path>/.adlc/specs/REQ-xxx-*/pipeline-state.json" \
      "<primary-worktree-path>/.adlc/specs/REQ-xxx-*/pipeline-state.json"
   rm "<primary-repo-path>/.adlc/specs/REQ-xxx-*/pipeline-state.json"
   ```
   The dashboard's worktree-aware scan finds the file under the worktree on its next ~1.5s poll; it never sees both at once. From this point on, every state-file read/write goes to the worktree path.

5. **Change your working directory to the primary repo's worktree.** Orchestration (state file reads/writes, spec edits, PR coordination) happens there from now on. Task implementation in Phase 4 will `cd` into the target repo's worktree per task.

6. **Worktree cleanup obligation** (Phase 8, not here): when the pipeline completes (all PRs merged), clean up every worktree using the absolute path recorded in state — read `repos[<id>].worktree` for each touched repo and pass that value to `git worktree remove`. Do NOT use the relative `.worktrees/REQ-xxx` form here — the contract requires the recorded absolute path:
   ```bash
   git -C <repo-path> worktree remove <repos[<id>].worktree>
   ```

After Step 1.5: `currentPhase` is still `1` (Phase 1 is already in `completedPhases`); Step 1.5 is part of the pipeline plumbing, not a numbered phase. Append a `phaseHistory` entry named `"Step 1.5: Create Worktrees"` for telemetry continuity, then advance to Phase 2.

---

### Phase 2: Architect & Break Into Tasks
<!-- companion: proceed/phases-1-3-validation.md -->
**Gate**: `currentPhase` must be `2`. After completion: append `2`, set `currentPhase=3`.

Invoke `/architect` to design the approach and emit task files (each tagged
with `repo:` in cross-repo mode). Reconcile `pipeline-state.json`: mark
touched/untouched repos, prune untouched-sibling worktrees, rebuild
`mergeOrder`, backfill missing `repo:` to primary. End-of-phase log:
one-paragraph architecture + task-graph + per-repo task counts.

---

### Phase 3: Validate Architecture & Tasks
<!-- companion: proceed/phases-1-3-validation.md -->
**Gate**: `currentPhase` must be `3`. After completion: append `3`, set `currentPhase=4`.

Re-invoke `/validate` (it auto-detects the architecture+tasks phase). Same
3-loop fix protocol as Phase 1; unresolved blockers are legitimate halt #1.
End-of-phase log: "Architecture and tasks validated."

---

### Phase 4: Implement
<!-- companion: proceed/phase-4-implementation.md -->
**Gate**: `currentPhase` must be `4`. After completion: append `4`, set `currentPhase=5`.

Execute the task graph across all touched-repo worktrees. Each task runs in
`repos[<task.repo>].worktree`. Track per-task progress in `phase4.currentTask`
/ `completedTasks` / `failedTasks` so a mid-phase compression resumes exactly.
Main mode dispatches `task-implementer` agents in dependency tiers (parallel
within a tier); subagent mode runs tasks sequentially in-context. End-of-phase
log: one line per tier with finished `TASK-xxx [repo] ✓` and any failures.

---

### Phase 5: Verify (Reflect + Review in Parallel)

**Gate**: `currentPhase` must be `5`. After completion: append `5`, set `currentPhase=6`.

**Goal**: Self-assess AND multi-agent review the implementation, then fix all findings in a single consolidated pass.

**Gather diffs per repo** (prerequisite): for each touched repo, compute the diff inside its worktree (`git -C <worktree> diff main...HEAD` plus the list of changed files). The reviewers receive per-repo diffs + file lists, plus the cross-repo architecture.md so they can reason about contracts spanning repos.

**Main conversation mode** — parallel agents:

**Step A — Single-gate parallel dispatch (complexity-aware, REQ-C)**. This whole step is ONE gate. The agent set scales with `pipeline-state.json`'s `complexity`:

| complexity | Agents dispatched per touched repo |
|---|---|
| `trivial` | reflector |
| `small` | reflector + quality-reviewer |
| `medium` | reflector + correctness-reviewer + quality-reviewer + architecture-reviewer + test-auditor + security-auditor (full 6) |
| `large` | full 6 (same as medium) |

Dispatch all selected agents in a **single assistant message**. In cross-repo mode, multiply by N touched repos. Do NOT report findings, do NOT pause, do NOT log progress between agent returns — wait until all have returned, then consolidate in Step B.

The six agents match the dimensions covered by `/review` (correctness, quality, architecture, test coverage, security) plus the reflector self-assessment. Each reviewer is responsible for producing its own candidate findings — there is no advisory pre-pass.

**Inline-context rule (REQ-E)**: every agent below receives the **content** of `conventions.md`, `architecture.md`, and (when relevant) `salesforce-rules.md` inlined into its prompt — not file paths. Step 0 already loaded these into your context; pass them through. Avoiding per-agent re-reads saves ~3-5s per agent per phase (≈ 1-2 min/run on the full 6-agent panel).

Each agent dispatch prompt should include a `## Project context (verbatim)` block with the markdown bodies, followed by the agent-specific instructions.

1. **reflector** agent — provide REQ-xxx, the repo id, the worktree path, changed files, diff, **inlined `conventions.md` + `architecture.md` content**. Tell it: "Report findings only. The parent pipeline will apply fixes."
2. **correctness-reviewer** agent — repo id, worktree path, changed files, diff, **inlined `conventions.md` content**. "Report findings only. Do not apply fixes."
3. **quality-reviewer** agent — same inputs. "Report findings only. Do not apply fixes."
4. **architecture-reviewer** agent — repo id, worktree path, changed files, diff, **inlined `architecture.md` content**, **plus a summary of the other touched repos' changes** (so it can flag cross-repo contract breaks). "Report findings only. Do not apply fixes."
5. **test-auditor** agent — repo id, worktree path, changed files, diff, **inlined `conventions.md` content + `.adlc/config.yml` `salesforce.coverage` block**. "Audit test coverage only for the diff under review. Apply the three-tier policy in REQ-A. Report findings only. Do not apply fixes."
6. **security-auditor** agent — repo id, worktree path, changed files, diff, **inlined `conventions.md` content + `salesforce-rules.md` content (Security & Permissions sections)**. "Audit security posture only for the diff under review. Report findings only. Do not apply fixes."

**Subagent mode** — sequential inline review:
For each touched repo, run the reflector checklist, then correctness, quality, architecture (with cross-repo context), test-auditor, and security-auditor checklists sequentially in your own context. Use the criteria from the agent definitions in `~/.claude/agents/`. Do NOT dispatch sub-agents.

**Step B — Consolidate**: When all agents return (or all checklists complete in subagent mode), dedupe overlapping findings **within each repo** and also flag cross-repo issues (e.g., API contract drift between an api repo and its consumer). Produce a single ranked list by severity, tagging each finding with the repo id it applies to.

**Step C — Fix in one pass**:
1. **Critical + must-fix Major** (bugs, security, convention violations, missing tests): fix immediately in the finding's target repo worktree, run that repo's test suite after each related cluster of fixes, commit inside that worktree with `fix(scope): address verify finding [REQ-xxx]`.
2. **Should-fix Minor** (code quality, naming): fix unless doing so would be a significant refactor — note those as follow-ups.
3. **Nit / observation**: fix trivial ones inline, skip the rest.
4. **User-facing questions from reflector**: if any, surface them to the user as a numbered list and wait for answers before continuing.

**Step D — Re-verify (conditional)**: Re-run ONLY the 5 reviewer agents (not reflector) if Critical or must-fix Major items were fixed — up to 1 confirmation loop. Skip if only minor fixes were applied. Scope re-verify to the (repo, dimension) pairs that had fixes: e.g., if correctness fixes landed only in the api repo, rerun correctness-reviewer for that repo only. In subagent mode, re-run the corresponding reviewer checklists inline.

**Step E — Platform validate (Salesforce ground-truth gate)**: Static review reasons about the code; the platform compiler is the only oracle that catches metadata-shape errors, Apex compile errors, missing fields, malformed FlexiPage XML, UI Bundle dist/ omissions, and feature-flag-gated metadata that exists in docs but not your org. Run a `sf project deploy validate` against the lowest-tier configured org **after** static fixes have been applied and **before** opening a PR. This step is mandatory whenever the project is a Salesforce project and at least one touched repo has Salesforce metadata in its diff — it is NOT gated by `complexity` (a `trivial` change can still ship broken metadata).

For each touched repo whose diff contains Salesforce metadata (any path under `force-app/`, or whatever `salesforce.workspace:` is set to in `.adlc/config.yml`), run inside that repo's worktree:

```sh
# Resolve the validation org. Order: salesforce.validate_org → orgs.sandbox → orgs.scratch.
ALIAS=$(awk '/^[[:space:]]*salesforce:/{f=1} f && /^[[:space:]]*validate_org:/{print $2; exit}' .adlc/config.yml | tr -d '"')
[ -z "$ALIAS" ] && ALIAS=$(awk '/^[[:space:]]*orgs:/{f=1} f && /^[[:space:]]*sandbox:/{print $2; exit}' .adlc/config.yml | tr -d '"')
[ -z "$ALIAS" ] && ALIAS=$(awk '/^[[:space:]]*orgs:/{f=1} f && /^[[:space:]]*scratch:/{print $2; exit}' .adlc/config.yml | tr -d '"')

# Resolve --test-level by reusing /canary Step 2b's diff-aware logic. Default to NoTestRun
# when the diff is metadata-only (saves 5-10 min per validate); RunSpecifiedTests when only
# a few Apex classes changed; RunLocalTests as a safe fallback.
#
# Metadata-only carve-out (per salesforce-rules.md "Unit Testing Requirements"): if the diff
# only touches custom objects/fields, perm sets, layouts, FlexiPages, Flows-without-Apex,
# static resources, etc. — i.e. NO `.cls`/`.trigger` files — a test class is NOT required.
# We run validate with --test-level NoTestRun and reviewers MUST NOT flag missing tests.
APEX_TOUCHED=$(git diff --name-only "origin/${integrationBranch:-main}...HEAD" | grep -E '\.(cls|trigger)$' | grep -vE '(Test|_Test)\.cls$' || true)
if [ -z "$APEX_TOUCHED" ]; then TEST_LEVEL="NoTestRun"; else TEST_LEVEL="RunLocalTests"; fi

WORKSPACE=$(awk '/^[[:space:]]*salesforce:/{f=1} f && /^[[:space:]]*workspace:/{print $2; exit}' .adlc/config.yml | tr -d '"')
WORKSPACE=${WORKSPACE:-force-app}

sf project deploy validate \
  --target-org "$ALIAS" \
  --source-dir "$WORKSPACE" \
  --test-level "$TEST_LEVEL" \
  --wait 5 \
  --json
```

**Wait cap = 5 minutes (hard cap, do not raise).** Each REQ in this pipeline is sized to be a small, isolated change set; a healthy validate against a sandbox should return in well under that. If the validate has not finished when `--wait 5` expires, the `sf` CLI returns a non-terminal "still running" response and the **pipeline must NOT block here** — capture the validation id, mark the gate as `running`, and continue to Phase 6. The validate keeps executing server-side and will be reconciled in Phase 7.

```sh
# Capture the JSON; --wait 5 will return either a terminal status OR a still-running response.
VALIDATE_JSON=$(sf project deploy validate \
  --target-org "$ALIAS" \
  --source-dir "$WORKSPACE" \
  --test-level "$TEST_LEVEL" \
  --wait 5 \
  --json 2>&1 || true)

VALIDATION_ID=$(echo "$VALIDATE_JSON" | jq -r '.result.id // empty')
STATUS=$(echo "$VALIDATE_JSON" | jq -r '.result.status // empty')

# If sf timed out the wait, status will be one of: Pending | InProgress | Queued.
# Treat those as "running" — DO NOT loop and DO NOT halt.
case "$STATUS" in
  Succeeded)             OUTCOME="passed" ;;
  Failed|Canceled)       OUTCOME="failed" ;;
  Pending|InProgress|Queued|"") OUTCOME="running" ;;
  *)                     OUTCOME="running" ;;
esac
```

**Outcome handling:**

1. **Clean validate** (`OUTCOME=passed`: status `Succeeded`, `checkOnly=true`, no component failures, no test failures): write `phase5.platformValidate[<repo-id>] = { status: "passed", validationId: <id>, alias: <alias>, testLevel: <level>, runAt: <ts> }` to `pipeline-state.json` and proceed.
2. **Validation failed** (`OUTCOME=failed`: compile errors, missing component, FLS error, malformed metadata, test failure): treat every failure entry as a **Critical finding** and loop back to Step C with the platform's error report inlined. Up to **2 retries** of the C → D → E cycle. Each retry MUST run all of Steps C → D → E in order — do not skip D between attempts because the platform errors only surfaced in E. After the second failed retry, the failure is legitimate halt #2 (same handling as reflector questions): stop, surface the validation id, the failing components, the test failures, and the verbatim platform error to the user.
3. **Validate still running after 5-min cap** (`OUTCOME=running`): write `phase5.platformValidate[<repo-id>] = { status: "running", validationId: <id>, alias: <alias>, testLevel: <level>, startedAt: <ts>, deadline: <ts+30m> }` to `pipeline-state.json`. Emit a one-line WARN: `WARN: platform validate did not return within 5m — id <id> still running on $ALIAS; pipeline continues. Phase 7 will reconcile.` Continue to Phase 6. **Do NOT loop, do NOT halt, do NOT raise --wait.** Phase 7 (PR Cleanup & CI) MUST poll `sf project deploy report --target-org "$ALIAS" --job-id "$VALIDATION_ID" --json` once before merge: if `Succeeded`, flip the gate to `passed`; if `Failed`, treat the failures as blockers on the PR and post them as a comment; if still `InProgress`, surface that on the PR and let CI carry the gate.
4. **No validation org configured** (`salesforce.validate_org`, `orgs.sandbox`, and `orgs.scratch` all absent): record `phase5.platformValidate[<repo-id>] = { status: "skipped", reason: "no validation org configured" }` in `pipeline-state.json`. Do NOT proceed silently — surface a one-line warning in the Phase 5 end-of-phase log: `WARN: platform validate skipped — configure salesforce.validate_org or orgs.sandbox in .adlc/config.yml to enable Salesforce ground-truth gate.` This is intentional (a hard fail would block local-only projects), but must NEVER be a silent skip.
5. **No Salesforce metadata in this repo's diff** (the touched paths are all docs/tests/non-SF code): mark `phase5.platformValidate[<repo-id>] = { status: "n/a", reason: "no SF metadata in diff" }` and proceed. This is the only legitimate quiet skip.
6. **`sf` CLI absent or unauthenticated**: surface a Critical finding immediately — this is a setup gap, not a code problem. Do NOT loop. `phase5.platformValidate[<repo-id>] = { status: "tooling-error", reason: "<error>" }`. The user fixes their environment and reruns `/proceed`.

**Why this gate exists**: every static reviewer (correctness, quality, architecture, test-auditor, security) reasons about source code in isolation. None of them can detect: an `.app-meta.xml` extension that should be `.uibundle-meta.xml`; a UI Bundle that ships without `dist/`; a permset referencing a field that exists only on a feature-flagged Edition; a FlexiPage with an invalid `template` ref; an Apex class compiled against a newer API version than the org supports; an OmniStudio component referencing a missing DataPack. The platform validate is the ground-truth oracle. With the 5-minute cap, a healthy small-REQ validate finishes inline; a slow run continues server-side and is reconciled in Phase 7 instead of blocking the agent.

**End-of-phase log**: Emit the combined verify summary across repos — per-repo findings, dedupe count, how many fixed, any deferred — followed by a per-repo `Platform validate: ✓ passed (id <validation-id>) | ⏳ running (id <validation-id>, deferred to Phase 7) | ⚠ skipped (no org) | ✗ failed (N components, M tests)` line. If reflector surfaced user-facing questions, halt here (legitimate halt #2). If platform validate failed twice, halt here (also legitimate halt #2). A `running` outcome is NOT a halt — it continues to Phase 6.

---

### Phase 6: Create Pull Request(s)
<!-- companion: proceed/phases-6-8-ship.md -->
**Gate**: `currentPhase` must be `6`. After completion: append `6`, set `currentPhase=7`.

Push each touched repo's feature branch and open one PR per repo via
`gh pr create --base <integrationBranch>` — read `integrationBranch` from
`pipeline-state.json` (set in Phase 0 step 4); do **NOT** let `gh` default the
base to the repo's default branch (`main`). Opening against `main` in a
two-branch repo triggers a `verify-head-ref` failure and forces a
rebase + retarget (LESSON-036). Cross-repo: create primary's PR last and
back-fill sibling bodies with the full URL list. Mark requirement `complete`
in primary frontmatter. Persist each PR URL to `repos[<id>].prUrl`. Report
URLs grouped by repo in `mergeOrder` sequence.

---

### Phase 7: PR Cleanup & CI
<!-- companion: proceed/phases-6-8-ship.md -->
**Gate**: `currentPhase` must be `7`. After completion: append `7`, set `currentPhase=8`.

Lightweight per-PR sanity check — review already ran in Phase 5, do NOT
re-run `/review`. For every PR: review diff, catch stray debug/TODO/secret
content, verify cross-repo contract consistency, push fixups in the owning
worktree if needed, wait for `gh pr checks` to go green. End-of-phase log:
one line per PR, then "All N PRs ready for merge".

**Step 7a — Reconcile deferred platform-validate (per repo with `phase5.platformValidate[<repo>].status == "running"`).** Phase 5's validate uses a 5-min wait cap; long-running validates carry over here. For each such repo:

```sh
VID=$(jq -r ".repos[\"$REPO\"].phase5.platformValidate.validationId" pipeline-state.json)
ALIAS=$(jq -r ".repos[\"$REPO\"].phase5.platformValidate.alias" pipeline-state.json)

REPORT=$(sf project deploy report --target-org "$ALIAS" --job-id "$VID" --json 2>&1 || true)
RSTATUS=$(echo "$REPORT" | jq -r '.result.status // empty')
```

Outcome handling:
- `Succeeded` → flip `phase5.platformValidate[<repo>].status` to `passed`. No PR action needed beyond the success line in the per-PR log.
- `Failed` / `Canceled` → treat as a blocker. Post the failing components + test failures as a PR comment, mark the PR as `blocked`, and halt this repo's promotion. Do NOT auto-loop back to Phase 5; the user decides whether to re-run `/proceed` or fix-forward.
- Still `InProgress` / `Pending` after a single check → leave the gate as `running`, post a PR comment with the validation id and the `sf project deploy report --job-id <id>` command, and let CI / the next manual check carry it. Do NOT poll in a loop; one read per pass.

This step replaces the Phase 5 "wait until validate finishes" behavior — it's the only place the pipeline reconciles a deferred validate. Skip the step entirely when no repo has a deferred validate.

---

### Phase 8: Wrapup
<!-- companion: proceed/phases-6-8-ship.md -->
**Gate**: `currentPhase` must be `8` and `7` must be in `completedPhases`. After completion: append `8`, set `"completed": true`.

Merge in `mergeOrder`, run `/wrapup` from the primary (deploys + knowledge
capture), tear down each touched-repo worktree via the absolute path in
state, set `completed: true`. Terminal claim MUST be tagged exactly one of
`{merged, pr-ready, blocked, failed}` — untagged claims are a protocol
violation `/sprint` rejects. Merge conflicts are legitimate halt #3.

**Local-bare / no-`gh` fallback**: when a touched repo's `origin` is a local
bare directory (or `gh` is unavailable / unauthenticated against a non-hosted
remote), the pipeline MUST hand-merge the feature branch into
`integrationBranch` itself rather than stopping at `pr-ready`. The full
detection probe and merge block live in
[phases-6-8-ship.md](phases-6-8-ship.md). Once the local merge lands,
`completed: true` and `terminalState: merged` MUST be written before exit —
a local-bare run is NEVER allowed to terminate as `pr-ready`. (KYC-REQ-001
hit this and stalled every dependent REQ until a human noticed; the
fallback closes the loop.) An `pr-ready` claim is reserved for hosted
remotes where an orchestrator (e.g. `/sprint`) explicitly owns merge
sequencing.

---

## Error Handling

- **Test failures during implementation**: Stop the current task, diagnose the failure, fix it inside the task's target-repo worktree, and re-run tests before continuing. If you can't fix it after 2 attempts, pause and ask the user.
- **Validation stuck after 3 loops**: Present the remaining FAIL items and ask the user how to proceed (fix manually, skip validation, or abort).
- **Missing context files**: If `.adlc/context/` files don't exist in the primary repo, stop and tell the user to run `/init` first. Do not proceed without context files.
- **Missing sibling repo**: If `.adlc/config.yml` references a sibling whose path doesn't exist or isn't a git repo, stop at Step 0 and list the missing repos. The user must clone or fix paths before retrying.
- **Task with unknown `repo:` value**: If a task frontmatter names a repo id not in the registry, stop Phase 4 and surface the mismatch — either the config or the task is wrong.
- **Merge conflicts**: If any feature branch has conflicts with its base branch — during Phase 7 rebase or Phase 8 merge — stop and ask the user how to resolve. In cross-repo mode, state which repo conflicted; earlier repos in `mergeOrder` may have already merged (see `repos[<id>].merged`), so the user can resume mid-sequence rather than re-doing completed merges.
- **Partial merge recovery**: If the pipeline is interrupted mid-Phase-8, resume by reading `pipeline-state.json` — the merge loop walks `mergeOrder` and skips any repo where `merged: true`.

## Prerequisites

Verified by Phase 0 Preflight — see Step 0 above.

## What This Skill Does NOT Do

- It does not create the initial spec — run `/spec` first
