# Sprint Engine Divergence Audit

Side-by-side comparison of the two `/sprint` engines, with file:line citations. Updated after the audit run on 2026-06-09. README references this file from the "Sprint engines" section.

**Engines audited:**
- **`legacy`** — `/sprint` Steps 1-6 in `sprint/SKILL.md`, dispatching one Agent-tool subagent per REQ; each subagent runs `agents/pipeline-runner.md` which executes `/proceed` (`proceed/SKILL.md`) end-to-end.
- **`workflow`** — `/sprint` Step 0 hands `args` to `workflows/adlc-sprint.workflow.js`; the workflow script is the orchestration engine and inlines per-phase agent prompts rather than calling subskills.

**Severity legend:** none / cosmetic / behavior-changing / outcome-changing.

---

## Phase: Entry / Engine Selection

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Engine entry | `sprint/SKILL.md:36-93` Step 0 falls through to Steps 1-6 | `sprint/SKILL.md:51-91` invokes `Workflow({scriptPath, args})` (`workflows/adlc-sprint.workflow.js:711`) | none | Same dispatcher selects either path |
| Halt mechanism | Background-runner agent updates `pipeline-state.json.blockers`; orchestrator polls slim `jq` projection (`sprint/SKILL.md:194-245`) | Returned `{state:'blocked', detail.questions[]}` value (`adlc-sprint.workflow.js:53-56,271-294`) | behavior-changing | Workflow uses returned values (no journal-side state); legacy uses on-disk state polling |
| Resume mechanism | User answers, orchestrator relaunches the same `pipeline-runner` agent against existing `pipeline-state.json` | `resumeFromRunId` + `args.answers[<id>]` threaded surgically into halt-prone prompts only (`adlc-sprint.workflow.js:776-787,910-944`) | behavior-changing | Workflow replays the journal cache for untouched calls; legacy re-executes from last completed phase |

---

## Phase: Preflight / Eligibility (before Phase 0)

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Ghost-REQ reconciler | Mandatory `sh .adlc/tools/reconcile-pipeline-state/reconcile.sh` (`sprint/SKILL.md:97-116`) | NOT invoked anywhere; only mentioned in cleanup commentary (`adlc-sprint.workflow.js:1765,1776`) | outcome-changing | Workflow can mis-classify already-merged ghost REQs as eligible; offset partly by the Preflight agent's "already merged" exclusion (`:984`) |
| Approved-status filter | Excludes non-approved unless explicitly listed; prefers approved over draft (`sprint/SKILL.md:118-119,156-158`) | Eligibility bar EXPLICITLY allows `draft` specs — Phase 1 gates instead (`adlc-sprint.workflow.js:980-987`) | behavior-changing | Workflow accepts more REQs into the run; intended difference per the prompt |
| `completed:true` exclusion | Explicit (`sprint/SKILL.md:121`) | Implied by "already fully merged on the integration branch" rule (`:984-985`) | none | Same outcome via different signals |
| Active-pipeline collision | Excluded if recent state advancement (`sprint/SKILL.md:122`) | Worktree-collision-with-different-branch listed as ineligibility blocker (`:986`) — no recency check on phase advancement | behavior-changing | Workflow's check is narrower (path collision only) |
| Worktree path collision (primary) | Pre-flight scans `git worktree list --porcelain`, surfaces fix recipe with single-quoted args (`sprint/SKILL.md:134-139`) | Delegated to Preflight agent prose; collision check is best-effort prose-instructed (`:986-987`) | behavior-changing | Legacy has deterministic shell logic; workflow trusts the agent to do it |
| Sibling-repo worktree collision | Deferred to `/proceed` Step 0 (`sprint/SKILL.md:139,322`) | Same intent; deferred to Phase 0 leaf prompt (`adlc-sprint.workflow.js:1001-1023`) | none | |
| Spec-presence check against `origin/<integrationBranch>` | Mandatory `git fetch origin` then check against integration branch (`sprint/SKILL.md:128-130`) | Preflight agent told to do it (`:989-992`) but no script-side enforcement | behavior-changing | Workflow trusts agent compliance |
| Context files (`project-overview.md` / `architecture.md` / `conventions.md`) check | Listed in Prerequisites (`sprint/SKILL.md:29-32`); enforced by `/proceed` Step 0 (`proceed/SKILL.md:238-242`) | Not checked anywhere in the workflow script | behavior-changing | Workflow's Phase-0 leaf could create a worktree without context files; agent prompt does not check |
| `complexity:` resolution | Read in `/proceed` Phase 2 onward, persisted in state (`proceed/SKILL.md:96-120`) | NOT read anywhere; no complexity-aware fan-out (`adlc-sprint.workflow.js`: zero references to `complexity`) | outcome-changing | Workflow always runs full 6-agent panel; legacy can shrink to 1-2 agents on `trivial`/`small` |
| Max concurrent REQs | 5 (`sprint/SKILL.md:155`) | 5 (`MAX_CONCURRENT_REQS = 5`, `adlc-sprint.workflow.js:597,730`) | none | Same cap; workflow applies AFTER eligibility (`:730`) |
| Pre-confirmation prompt | "Ask the user to confirm the sprint lineup" (`sprint/SKILL.md:160`) | No confirmation step; runs immediately | behavior-changing | |

---

## Phase 0 — Worktree + State Init

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Phase 0 actor | `pipeline-runner` agent runs `/proceed` Step 0 (`agents/pipeline-runner.md:83`; `proceed/SKILL.md:225-273`) | One default workflow subagent driven by `phase0Prompt(id)` (`adlc-sprint.workflow.js:796-823,1001-1023`) | behavior-changing | Workflow Phase 0 = one agent; legacy = full `/proceed` Step 0 with 8 sub-steps |
| State file location | Primary repo MAIN CHECKOUT — NEVER worktree (`agents/pipeline-runner.md:53-77`; `proceed/SKILL.md:339`) | Workflow records `repos[*].worktree` only (`:1015-1017`); doesn't enforce main-checkout location of state file in Phase 0 | outcome-changing | Workflow loses the "ghost REQ" guardrail; the "state lives in main" rule is in `wrapupCleanupPrompt` only (`:1780`) |
| Integration-branch resolution | Detect via config/workflow/CLAUDE.md signals; fetch first (`proceed/SKILL.md:250-259`) | Per-repo agent re-resolves; never hardcodes main (`:1008-1010`) | none | Same intent |
| Worktree base | `origin/<integration-branch>` (`proceed/SKILL.md:259,321`) | Same — `origin/<integrationBranch>` (`adlc-sprint.workflow.js:1011-1012`) | none | |
| Pre-validation state init | State file written BEFORE Phase 1 so dashboard sees pipeline immediately (`proceed/SKILL.md:225-227,261-263`) | No pre-Phase-1 state write; Phase 0 leaf only writes `repos[*].worktree` (no `currentPhase`, `startedAt`, `completedPhases`) | outcome-changing | Dashboard cannot see workflow REQs in Phases 0–7 unless agent voluntarily writes those fields |
| Worktree creation timing | Step 1.5 — AFTER Phase 1 passes (`proceed/SKILL.md:227,287-349`) | Step 0 — BEFORE Phase 1 (`adlc-sprint.workflow.js:Phase 0 → Phase 1`) | behavior-changing | Workflow leaves a stray worktree if Phase 1 validation fails |
| `WORKTREE PATH (mandatory):` dispatch contract | Mandatory line w/ regex parser (`sprint/SKILL.md:170-182`; `proceed/SKILL.md:291-296`) | Not used; workflow tells the Phase-0 agent to derive `<repoRoot>/.worktrees/<id>` (`:1011`) | behavior-changing | Cosmetic for default invocations, but external callers depending on the contract have no entry point |
| Idempotent reuse on resume | Same-branch match → skip `git worktree add` (`proceed/SKILL.md:300-306`) | Same intent — explicit "IDEMPOTENT" guidance (`:1012-1014`) | none | |

---

## Phase 1 — Validate Spec

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Validator | Calls `/validate` skill (`proceed/phases-1-3-validation.md:21`); subagent mode runs the checklist inline | Inline `phase1ValidatePrompt` saying "equivalent of /validate" (`adlc-sprint.workflow.js:1025-1035`) — NOT a `/validate` skill invocation | outcome-changing | Workflow does NOT invoke `/validate`; it inlines a paraphrase. Drift risk if `/validate` evolves |
| Loop count | 3 (`proceed/SKILL.md:124`) | 3 (`MAX_GATE_ITERATIONS=3`, `adlc-sprint.workflow.js:598,914`) | none | |
| Fix actor | Inline / `/proceed` orchestrator | `task-implementer` agent (`adlc-sprint.workflow.js:943`) | cosmetic | |
| Halt on 3× fail | Legitimate halt #1 (`proceed/SKILL.md:23`) | Returns `blocked(id, '<target>-validation', …)` (`adlc-sprint.workflow.js:930-934,948`) | none | |
| State updates after Phase 1 | `currentPhase=2`, append 1 (`proceed/SKILL.md:279`) | NOT written by workflow Phase 1 (no agent prompt requires it) | outcome-changing | Dashboard's phase strip does not advance |

---

## Phase 2 — Architect

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Explore trio fan-out | `/architect` (main mode) does 3-agent fan-out at `medium`/`large` (`proceed/SKILL.md:103`); subagent mode skips agents | `parallel(['feature-tracer','architecture-mapper','integration-explorer'])` (`adlc-sprint.workflow.js:838-849`) | none in main mode; behavior-changing vs subagent mode | Workflow ALWAYS runs the trio regardless of complexity |
| Architect actor | `/architect` skill | Inline `architectPrompt` to default workflow subagent — NOT `/architect` skill (`adlc-sprint.workflow.js:851-857,1058-1069`) | outcome-changing | Workflow inlines /architect equivalent; loses `/architect`'s ADR capture, conventions |
| Touched-repo reconciliation | Phase 2 reconciles `touched`, prunes worktrees, rebuilds `mergeOrder`, backfills `repo:` (`phases-1-3-validation.md:35-43`) | NOT done by workflow; only the architect's TASKS array is captured (`:858`) | outcome-changing | Workflow doesn't prune untouched siblings or rebuild `mergeOrder` per architect output |
| Architecture.md emission | `/architect` writes `architecture.md` (medium/large) | Workflow returns `TASKS` only; no architecture.md file emission contract | outcome-changing | |
| Trivial/small downshift | Skip explore, skip architecture.md (`proceed/SKILL.md:103`) | No tier — runs full trio always | behavior-changing | |

---

## Phase 3 — Validate Architecture

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Validator | `/validate` (`proceed/phases-1-3-validation.md:53`) | Inline `phase3ValidatePrompt` saying "equivalent of /validate" (`adlc-sprint.workflow.js:1071-1080`) | outcome-changing | Same drift risk as Phase 1 |
| Skip in trivial | Skipped at `trivial` (`proceed/SKILL.md:103`) | Not skipped | behavior-changing | |
| Loop / fix / halt | 3 loops, halt on fail | Same gate machinery as Phase 1 (shared `gate()` (`adlc-sprint.workflow.js:910-951`)) | none | |

---

## Phase 4 — Implement

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Parallel-within-tier | Main mode: `task-implementer` per task in parallel within tier (`phase-4-implementation.md:37-43`); subagent mode: serial | SERIAL only — explicit `for (const task of ordered)` with await (`adlc-sprint.workflow.js:1399-1456`) | outcome-changing | Workflow declares "the engine runs Phase-4 tasks serially" (`:1102,1402`); legacy main-mode parallelizes |
| Tier ordering | Dependency-graph tier walk (`phase-4-implementation.md:22-26`) | `orderByTier` pure JS — stable sort by `task.tier` (`:317-322,1409`) | cosmetic | Workflow keys on `tier` field; legacy walks dependency graph |
| Cross-repo task routing | Each task uses `repos[<task.repo>].worktree` (`phase-4-implementation.md:28`) | Workflow `implementPrompt` passes `task.repo` but writes to a single shared `worktree` (`:1097-1108`) | outcome-changing | Workflow appears to write all tasks into the primary worktree, not the per-task target repo's worktree |
| Resume idempotency | `phase4.completedTasks` skip on resume (`proceed/SKILL.md:216`) | `completedTasksPrompt` reads `phase4.completedTasks` and skips (`adlc-sprint.workflow.js:1420-1432`) | none | |
| Per-task state writes | Append to `phase4.completedTasks` after each commit (`proceed/SKILL.md:214`) | Same — `phase4StatePrompt` per task (`:1447-1452`) | none | |
| Failed-task list | `phase4.failedTasks` populated (`proceed/SKILL.md:194`) | NOT modeled in any workflow prompt (only the schema mentions removing from `failedTasks` (`:1116`)) | behavior-changing | |
| Test-suite run per task | Mandatory (`phase-4-implementation.md:31`) | Mandatory in prompt prose (`:1103-1104`) | none | |

---

## Phase 5 — Verify

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Review panel size | Complexity-aware: 1 (trivial), 2 (small), 6 (medium/large) (`proceed/SKILL.md:106,403-406`) | Always 6 (`PANEL_DIMENSIONS` (`adlc-sprint.workflow.js:88,498-507`)) | outcome-changing | Workflow doesn't downshift on `trivial`/`small` |
| Reviewer parallelism | Single message dispatches all 6 in parallel (main mode) (`proceed/SKILL.md:407`) | `parallel(PANEL.map(...))` per repo (`adlc-sprint.workflow.js:1509-1523`) | none | |
| Cross-repo manifest for architecture-reviewer | Part of architecture-reviewer prompt (`proceed/SKILL.md:418`) | Computed once via `manifestPrompt` then passed only to architecture-reviewer (`adlc-sprint.workflow.js:1491-1497,1180-1186`) | none | |
| Inline-context optimization (REQ-E) | Inline `conventions.md` + `architecture.md` + `salesforce-rules.md` content into each agent prompt (`proceed/SKILL.md:411-413`) | Workflow prompts pass paths/repo references but do NOT inline file content (`adlc-sprint.workflow.js:1158-1188`) | behavior-changing | Workflow loses ~3-5s per agent savings; agents must re-read files |
| Salesforce platform-validate gate (Step E) | Mandatory `sf project deploy validate/start --dry-run` per touched repo with metadata (`proceed/SKILL.md:435-528`) | NOT executed anywhere | outcome-changing | Workflow ships REQs without running the platform ground-truth gate |
| Reflector userFacing question halt | Surfaced as numbered list, halt #2 (`proceed/SKILL.md:23,431`) | `reflectorQuestions()` + return `blocked(id,'reflector-questions',{questions})` (`adlc-sprint.workflow.js:444-455,1533-1543`) | none | |
| Re-verify (Step D) | Conditional, ≤1 loop, only fixed (repo,dimension) pairs, reviewers-only (`proceed/SKILL.md:433`) | `fixedPairs()` + per-pair re-dispatch, ≤1 loop, no reflector (`adlc-sprint.workflow.js:457-474,1581-1620`) | none | |
| Salesforce sf-skills-catalog rubric scoring | Loaded by reflector / reviewers in subagent mode (`agents/pipeline-runner.md:96-145`) | Not referenced in any workflow prompt | behavior-changing | |
| Coverage policy gate (REQ-A) | Always runs (`proceed/SKILL.md:113-117`) | Inherits in `test-auditor` prompt prose only — no enforcement leaf | behavior-changing | |
| Resume-answer-propagation | n/a (legacy doesn't have a journal cache) | Special "applyResumeAnswer" path so a non-blocking reflector reply still reaches the artifact (`adlc-sprint.workflow.js:1551-1579`) | none in practice; workflow-only feature | |

---

## Phase 6 — Open PR(s)

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Push + `gh pr create` | Per-repo, `--base <integrationBranch>`, primary last for backfill (`phases-6-8-ship.md:23-43`) | One IO agent loops touched repos via `openPRsPrompt` (`adlc-sprint.workflow.js:1209-1233`) | none | |
| Local-bare PR fallback | Synthetic `local-bare:<origin>#<branch>` URL written to `prUrl` (`phases-6-8-ship.md:25`) | NOT modeled in `openPRsPrompt` — no synthetic-marker contract | outcome-changing | Workflow's Phase 8 actor probe expects the marker (`:1296-1298`) but Phase 6 never writes it |
| PR-body template (cross-repo Related-PRs backfill) | Detailed body template w/ Related-PRs / Tasks / Architecture / Tests / Reflection sections (`phases-6-8-ship.md:30-59`) | Generic "concise title/body summarizing the REQ" (`adlc-sprint.workflow.js:1226`) | behavior-changing | PR review experience differs |
| `prUrl` persistence | Per-repo write to `pipeline-state.json.repos[<id>].prUrl` (`proceed/SKILL.md:218`) | Returned in PRS schema; not enforced as a state-file write | behavior-changing | |
| Status `complete` write to spec frontmatter | Mandatory before opening PR (`phases-6-8-ship.md:24`) | NOT instructed | behavior-changing | |

---

## Phase 7 — PR Cleanup + CI

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Diff/sanity check | `gh pr diff`, scan for stray debug/TODO/secrets, cross-repo contract check (`phases-6-8-ship.md:76-83`) | Same intent in `cleanupAndWatchCIPrompt` (`adlc-sprint.workflow.js:1241-1262`) | none | |
| Fix-and-push if issues found | Yes — fix in worktree, push (`phases-6-8-ship.md:84-85`) | Prompt says "Do NOT modify code" (`:1259`) | outcome-changing | Workflow will not auto-fix Phase-7 findings |
| CI watch | `gh pr checks` blocking until green (`phases-6-8-ship.md:86`) | Same — `gh pr checks <url> --watch` (`:1256`) | none | |
| Step 7a — deferred platform-validate reconciliation | `sf project deploy report` to flip Phase-5 `running` → `passed`/`Failed` (`proceed/SKILL.md:558-573`) | NOT executed (Phase 5 platform-validate doesn't run in workflow) | outcome-changing | Both engines drift Salesforce gating; workflow has neither side |

---

## Phase 8 — Wrapup + Merge

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| Topology rule | Single-repo → self-merge, claim `merged`; cross-repo → stop at `pr-ready` (`agents/pipeline-runner.md:150-156`) | Same — `wrapupAndMerge` branches on `touched.length` (`adlc-sprint.workflow.js:1684-1736`) | none | |
| `gh`/local-bare actor probe | Per-repo probe (`agents/pipeline-runner.md:158-191`; `phases-6-8-ship.md:117-141`) | Same probe inlined into `mergePrompt`/`crossRepoMergePrompt` (`adlc-sprint.workflow.js:1281-1338,1987-2024`) | none | |
| `IS_LOCAL_BARE=0,GH_OK=0` outcome | Halt `blocked` (`agents/pipeline-runner.md:189`) | Halt blocked via mergeResult report (`:1329-1331`); Phase 6 SKILL ship companion says `pr-ready` here (`phases-6-8-ship.md:149`) | behavior-changing | Internal disagreement; workflow follows the agent doc |
| Cross-repo merge sequencing | Walks `mergeOrder` per `pipeline-state.json` (`phases-6-8-ship.md:196-204`); orchestrator may sequence | `sequenceCrossRepoMerges` + `groupCrossRepoReqs` union-find over shared touched repos (`adlc-sprint.workflow.js:1850-1892,535-577`) | behavior-changing | Workflow does cross-REQ shared-repo serialization in pure JS post-pipeline barrier; legacy `/sprint` Step 5 does it ad-hoc per-pipeline |
| `mergeOrder` per REQ | Configured in `.adlc/config.yml`, persisted in state (`proceed/SKILL.md:182-191`) | Not read by the workflow; the agent is told "in dependency order (mergeOrder if one is recorded)" (`adlc-sprint.workflow.js:1996`) | behavior-changing | Workflow defers to agent compliance |
| State finalization first | LOAD-BEARING: write terminal flags BEFORE `/wrapup` runs (`agents/pipeline-runner.md:243-269`) | Same intent; explicit "step 1 first" prompt language (`adlc-sprint.workflow.js:1758-1809,1942-1977`) | none | |
| `/wrapup` invocation | `/wrapup REQ-xxx --main-root <path> [--touched-repos ...]` (`agents/pipeline-runner.md:272-276`) | Same call signature in `wrapupCleanupPrompt` (`adlc-sprint.workflow.js:1794`) | none | |
| Worktree removal | Last; absolute path from state (`agents/pipeline-runner.md:280-286`) | Same — uses `repos[<id>].worktree` (`adlc-sprint.workflow.js:1801,1972`) | none | |
| Verify gate (`gh pr view`) | Orchestrator post-claim (`sprint/SKILL.md:213-219`) | Built-in: `verifyMergedPrompt` + `allMerged()` block before claim accepted (`adlc-sprint.workflow.js:1346-1387,513-516,1720-1735`) | behavior-changing | Workflow re-verification is in-engine and gates the terminal value |
| `merge-unverified` halt | Surface as blocker per orchestrator (`sprint/SKILL.md:215-219`) | Returns `blocked(id,'merge-unverified',…)` (`adlc-sprint.workflow.js:1731-1735,1931-1934`) | none | |
| `/canary` invocation | Inside `/wrapup` Step 2 (per `phases-6-8-ship.md:247`) | Inside `/wrapup` invoked by the cleanup leaf (`adlc-sprint.workflow.js:1794`) | none | Both delegate to /wrapup |

---

## Cross-cutting

| Aspect | legacy | --workflow | Severity | Note |
|---|---|---|---|---|
| `pipeline-state.json` schema | Strict (integer phases, mandatory `completedPhases`, `phaseHistory`, `currentPhaseStartedAt`, etc.) (`agents/pipeline-runner.md:40-51`; `proceed/SKILL.md:132-197`) | Per-phase agents are NOT instructed to update `currentPhase`/`completedPhases`/`phaseHistory`/`currentPhaseStartedAt` for Phases 1–7. Only Phase 0 writes `repos[*].worktree`; Phase 4 writes `phase4.completedTasks`; Phase 8 writes terminal flags + final phaseHistory entry (`adlc-sprint.workflow.js:1780-1810,1953-1977`) | outcome-changing | Workflow REQs will appear stuck on Phase 0 in the dashboard for the entire run, then jump to merged at the end. Dashboard's phase-strip + currentPhaseStartedAt + completedPhases telemetry are unpopulated |
| Timestamp source | `date -u +"%Y-%m-%dT%H:%M:%SZ"` via Bash, never typed (`agents/pipeline-runner.md:24-38`; `proceed/SKILL.md:201-209`) | Workflow runtime FORBIDS `Date.now`/`new Date` (`adlc-sprint.workflow.js:51-52`); agents told to use `date -u` shell-out for the Phase-8 phaseHistory entry only (`:1788`) | behavior-changing | Workflow has no timestamp ledger between Phase 0 and Phase 8 |
| Resume / halt semantics — 3× validation | Halts; user fixes manually, re-runs `/proceed` | Same halt; resume via `args.answers[<id>]` threaded into validate+fix prompts only (`adlc-sprint.workflow.js:910-944`); other REQs replay byte-identically from journal cache | behavior-changing | Workflow has surgical resume; legacy re-runs from last completed phase in state |
| Resume — reflector userFacing | Halts, user answers, orchestrator restarts the agent | Resume threads answer into Phase-5 fix prompt; `applyResumeAnswer` path forces the answer to land even if nothing blocks (`adlc-sprint.workflow.js:1541-1579`) | behavior-changing | |
| Resume — merge conflict | Halts, user resolves manually | Returns `blocked(id,'merge-conflict',…)` (`adlc-sprint.workflow.js:1709-1715,1912-1917`); resume re-runs the merge agent | none | |
| Mid-phase agent crash | Background `run_in_background:true` agent dies → state file is the recovery anchor; orchestrator re-launches from `currentPhase` (`sprint/SKILL.md:307`) | A failed `parallel()` thunk yields null and is filtered out (`adlc-sprint.workflow.js:849,1523`); a failed `pipeline()` item drops to null. No automatic retry inside the workflow | outcome-changing | A dropped reviewer in workflow Phase 5 = silent loss of one dimension; legacy retries the agent |
| Mid-pipeline (whole REQ) crash | New sprint relaunches `pipeline-runner` from the recorded `currentPhase` | Resume via `resumeFromRunId` replays the journal cache up to the failure point | behavior-changing | Different recovery surfaces |
| Concurrency caps | `MAX_CONCURRENT_REQS=5`; per-REQ implicit (`pipeline-runner` is one agent) | `MAX_CONCURRENT_REQS=5`; per-REQ Phase-2 trio = 3, Phase-5 panel = 6 per repo, plus runtime budget | none / cosmetic | Workflow has explicit fan-out caps; legacy runs at most 1 background agent per REQ but that agent dispatches sub-agents in main `/proceed` mode |
| Subskills called | `/proceed` (legacy `pipeline-runner` agent literally executes `/proceed`); `/proceed` calls `/validate`, `/architect`, `/wrapup`, `/canary` (`/canary` via `/wrapup`) | `/wrapup` only (`adlc-sprint.workflow.js:1794,1965`). `/validate`, `/architect`, `/canary`, `/review` are paraphrased inline; no skill invocation | outcome-changing | Workflow drifts from the canonical skill bodies |
| Dashboard observability | Phase strip via `completedPhases`; `currentPhaseStartedAt` populates Active time; `phaseHistory` for telemetry; slim `jq` projection (`sprint/SKILL.md:194-207`) | Phase 0–7 do not update these fields. Only Phase 8 (final) writes `currentPhase`, `completedPhases`, `phaseHistory`, `currentPhaseStartedAt:null`, `completed:true` | outcome-changing | Workflow REQs render as Phase 0 with no Active timer until they merge |
| Cross-REQ shared-repo serialization | `/sprint` Step 5 ad-hoc; "merge as each completes" with batch-mode fallback (`sprint/SKILL.md:247-272`) | Pure-JS union-find post-pipeline barrier (`groupCrossRepoReqs`); shared-repo REQs serial, disjoint REQs parallel (`adlc-sprint.workflow.js:1850-1892`) | behavior-changing | Workflow has stronger guarantees here |
| Schema-validated agent IO | None — agents return free text | Every leaf returns a JSON-schema-validated object (`adlc-sprint.workflow.js:117-252,607-688`) | behavior-changing | Workflow has tighter shape contracts |
| `/wrapup` call signature | `/wrapup REQ-xxx --main-root <path> [--touched-repos ...]` | Same | none | |
| Recovery tool (`reconcile-pipeline-state.sh`) | Run at `/sprint` Step 1 (`sprint/SKILL.md:97-116`) and `/proceed` Step 0a (`proceed/SKILL.md:229-236`) | Not invoked | outcome-changing | Workflow runs on top of un-reconciled state; ghost REQs persist |
| Reconciler on a runner death late-Phase-8 | Rescues by synthesizing state file from PR/merge evidence | Same reconciler exists but is not called by the workflow path; user must run it manually | behavior-changing | |

---

## `pipeline-runner` Agent Contract — Drift Check

The `pipeline-runner.md` agent file documents what it does ("Run /proceed phases 0-8") and tracks `/proceed`'s contract closely. Specific drift findings:

| Topic | `pipeline-runner.md` says | `/proceed` actually says | Drift |
|---|---|---|---|
| Phase numbering | 0–8 + Step 1.5 (`agents/pipeline-runner.md:79-92`) | 0–8 + Step 1.5 (`proceed/SKILL.md:225-349`) | none |
| Phase 5 review panel | "reflector + correctness/quality/architecture/test-auditor/security-auditor" — full 6 sequentially in subagent mode (`agents/pipeline-runner.md:94-145`) | Complexity-aware: 1/2/6/6 (`proceed/SKILL.md:106,403-406`). pipeline-runner doc omits the trivial-only / small-only shrink | minor drift — pipeline-runner always runs the full 6 in subagent mode, even for `trivial`/`small` |
| Phase 5 platform-validate (Step E) | NOT mentioned anywhere | Mandatory for SF projects with metadata in diff (`proceed/SKILL.md:435-528`) | drift — `pipeline-runner` will skip the Salesforce ground-truth gate even though `/proceed` requires it |
| Phase 7 Step 7a (deferred validate reconcile) | NOT mentioned | Mandatory when Phase 5 wrote `running` (`proceed/SKILL.md:558-573`) | drift |
| Pre-Phase-1 state file in main checkout | "Step 0 (preflight + state init) and Phase 1 (Validate Spec) run in the primary repo's MAIN CHECKOUT" (`agents/pipeline-runner.md:55`) | Same — pre-validation state init + main-checkout location (`proceed/SKILL.md:227,261-263,329-340`) | none |
| `WORKTREE PATH (mandatory):` parsing | Documented (`agents/pipeline-runner.md:55,73`) | Same regex `^WORKTREE PATH \(mandatory\): (.+)$` (`proceed/SKILL.md:292-294`) | none |
| Phase 1 fail = no worktree cleanup | "Phase 1 runs in main checkout — failed validation does not leave a stray worktree behind" (`agents/pipeline-runner.md:55`) | Same (`proceed/SKILL.md:283`) | none |
| Phase 8 single-repo merge ownership | `merged` (`agents/pipeline-runner.md:152`) | Same (`phases-6-8-ship.md:110`) | none |
| Local-bare halt for hosted-no-gh | `blocked` (`agents/pipeline-runner.md:189`) | `pr-ready` per ship companion (`phases-6-8-ship.md:149`) | drift — `pipeline-runner.md` and `phases-6-8-ship.md` disagree |
| Terminal claim contract | `{merged, pr-ready, blocked, failed}` (`agents/pipeline-runner.md:299-310`) | Same (`phases-6-8-ship.md:98-107`) | none |
| Schema strictness (integer `currentPhase`, mandatory `completedPhases`) | Documented (`agents/pipeline-runner.md:40-51`) | Same (`proceed/SKILL.md:132-142`) | none |

**Summary of pipeline-runner drift:** the agent definition does not document `/proceed` Phase 5 Step E (Salesforce platform-validate) or Phase 7 Step 7a (deferred-validate reconcile), so a `pipeline-runner` running in subagent mode will silently skip those gates that `/proceed` requires. The hosted-no-gh terminal-claim disagreement (`blocked` vs `pr-ready`) is a real two-doc contradiction.

---

## Cases where one engine genuinely cannot do what the other does

- **Workflow cannot:** invoke `/validate`, `/architect`, `/canary`, or `/review` as skills (the runtime forbids `import`/`require` and the only entrypoint is `agent()` leaves). It can only inline paraphrased prompts.
- **Workflow cannot:** read the filesystem or shell out from the script body (`adlc-sprint.workflow.js:36-50`). All FS/git work must be in `agent()` leaves.
- **Workflow cannot:** call `Date.now()` / `new Date()` — every timestamp must be a Bash shell-out from inside an agent.
- **Legacy cannot:** post-pipeline cross-REQ union-find serialization in pure deterministic JS (it's prose-instructed in `/sprint` Step 5, with batch-mode as the documented exception).
- **Legacy cannot:** schema-validate agent returns; agent outputs are free-text and the orchestrator parses prose.
- **Legacy cannot:** offer surgical journal-replay resume; on resume it re-executes side effects from the last completed phase.

---

## Highest-impact divergences (outcome-changing, single line each)

1. Workflow has no `complexity:` tier handling — always full 6-agent panel + always full explore trio. (`adlc-sprint.workflow.js:838-849,1481-1525`)
2. Workflow has no Salesforce platform-validate gate (Phase 5 Step E) and no Phase 7 Step 7a reconcile. (`proceed/SKILL.md:435-573` vs workflow: absent)
3. Workflow does not invoke `/validate`, `/architect`, `/canary`, or `/review` skills — they are inlined paraphrases only. (`adlc-sprint.workflow.js:1025-1093,1180-1188`)
4. Workflow's Phase 0–7 leaves do not update `currentPhase`/`completedPhases`/`phaseHistory`/`currentPhaseStartedAt`; only Phase 8 writes those. Dashboard phase strip/active-time telemetry will be flat across the run. (`adlc-sprint.workflow.js:1780-1810`)
5. Workflow does not run the `reconcile-pipeline-state` ghost-REQ reconciler at start. (`sprint/SKILL.md:97-116` vs workflow: absent)
6. Workflow's Phase 6 does not write the `local-bare:<origin>#<branch>` synthetic prUrl, but Phase 8 expects it for actor probing. (`phases-6-8-ship.md:25` vs `adlc-sprint.workflow.js:1209-1233,1296-1298`)
7. Workflow Phase 4 always serial; legacy main-mode parallel-within-tier. (`adlc-sprint.workflow.js:1399-1456` vs `phase-4-implementation.md:37-43`)
8. Workflow does not check `.adlc/context/` files exist as a precondition. (vs `proceed/SKILL.md:238-242`)
9. Workflow Phase 7 explicitly forbids fix-and-push; legacy fixes-in-worktree on cleanup findings. (`adlc-sprint.workflow.js:1259` vs `phases-6-8-ship.md:84-85`)
10. Workflow does not pass the architect's task `repo:` to the per-task worktree; `implementPrompt` reuses the shared primary worktree path. (`adlc-sprint.workflow.js:1097-1108` vs `phase-4-implementation.md:28`)
