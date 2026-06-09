# ADLC Toolkit — Salesforce edition

Skills, agents, templates, and quality gates for spec-driven development on **Salesforce** projects with [Claude Code](https://claude.com/claude-code). Wraps the ADLC orchestration around the [forcedotcom/afv-library](https://github.com/forcedotcom/afv-library) sf-skills set so reviewers and the implementer consume Salesforce-specific rubrics by file glob.

## What's Included

### Orchestration skills

| Skill | Description |
|-------|-------------|
| `/init` | Bootstrap `.adlc/` structure in a new SF repo |
| `/spec` | Write requirement specs from feature requests |
| `/architect` | Design architecture and break requirements into tasks |
| `/validate` | Validate any ADLC phase output before advancing |
| `/proceed` | End-to-end pipeline: validate → architect → implement → reflect → review → PR → wrapup |
| `/sprint` | Parallel pipeline orchestrator — multiple `/proceed` sessions across REQs (`--workflow` engine + legacy fallback) |
| `/reflect` | Post-implementation self-review walking salesforce-rules + sf-skill rubrics |
| `/review` | 6-agent panel (correctness, quality, architecture, tests, security, reflector) loading sf-skill rubrics by file glob |
| `/canary` | Salesforce sandbox → staging → prod promotion gate (`sf project deploy validate` + `sf agent test run` + Playwright smoke). **Prod is validate-only** — surfaces the validation id and instructs the user to run `sf project deploy quick` manually; the skill never deploys to prod itself. |
| `/wrapup` | Close out a feature — merge, Permissions.md gate, Agentforce deploy-order gate, knowledge capture, sf deploy |
| `/bugfix` | Streamlined bug fix workflow |
| `/status` | Show current state of all ADLC work |
| `/template-drift` | Detect drift between local `.adlc/templates/` and canonical toolkit templates (incl. sf-quality-checklist drift detection) |
| `/sf-router` | File-glob → sf-skill dispatch helper consumed by other skills |

### sf-skills (vendored)

Sixty Salesforce skills vendored from `forcedotcom/afv-library` (pinned commit recorded in [`skills/sf/VENDORED.md`](skills/sf/VENDORED.md)) covering Apex, LWC, Flow, SOQL, testing, debug, metadata, permissions, deploy, integration, Data Cloud, Agentforce, OmniStudio, Industries CME, B2B Commerce, UI bundles, and more. The complete catalog with phase mapping and the **file-glob → rubric dispatch table** lives in [`.adlc/context/sf-skills-catalog.md`](.adlc/context/sf-skills-catalog.md).

### Agents

Eleven specialized subagents (`agents/*.md`), models locked to Sonnet/Opus only — see [`MODEL_ASSIGNMENTS.md`](MODEL_ASSIGNMENTS.md):

- **Discovery (3, Sonnet)**: `architecture-mapper`, `feature-tracer`, `integration-explorer`
- **Build (1, Opus)**: `task-implementer`
- **Phase 5 panel (6)**: `correctness-reviewer` (Opus), `quality-reviewer` (Sonnet), `architecture-reviewer` (Sonnet), `test-auditor` (Sonnet), `security-auditor` (Opus), `reflector` (Opus)
- **Orchestrator (1, Opus)**: `pipeline-runner`

Each Phase 5 reviewer loads the relevant sf-skill rubric per touched file (sf-apex 150-pt, sf-lwc 165-pt, sf-flow 110-pt, sf-soql 100-pt, etc.) plus `partials/sf-quality-checklist.md` as the always-on baseline.

### Templates

- `requirement-template.md` — Requirement spec
- `task-template.md` — Technical task
- `bug-template.md` — Bug report
- `assumption-template.md` — Validated assumption
- `lesson-template.md` — Lesson learned
- `permissions-template.md` — Per-feature `Permissions.md` with assignment matrix + dependency mapping
- `config-template.yml` — `.adlc/config.yml` skeleton with Salesforce fields
- `claude-settings-template.json` — Per-project `.claude/settings.json` allowlist

### Presets

- [`presets/sfdc-core.yml`](presets/sfdc-core.yml) — Apex + LWC + Flow + SOQL + Permissions + Deploy baseline
- [`presets/sfdc-industries.yml`](presets/sfdc-industries.yml) — Core + Data Cloud + Agentforce + OmniStudio + CME + Vlocity

### Workflows

Deterministic Dynamic-Workflow scripts powering `/sprint --workflow`. See [`workflows/`](workflows/README.md).

### Tools

- [`tools/sf-lint/`](tools/sf-lint/README.md) — Salesforce-rules static checker (sharing keyword, AccessLevel, no `@future`, no `SeeAllData=true`, no SOQL/DML in loops, no hardcoded IDs/URLs, perm-set naming, `View/ModifyAllData` anti-patterns, ApexDoc presence)
- [`tools/lint-skills/`](tools/lint-skills/README.md) — SKILL.md hygiene + agent-model policy gate (Sonnet/Opus only) + sf-quality-checklist sourcing advisory
- [`tools/sf-preflight/`](tools/sf-preflight/README.md) — local pre-deploy gates that catch failures in seconds instead of paying 60-90s per `sf project deploy validate`. `permsets` (REQ-B): queries Tooling-API `FieldDefinition` and validates every `<fieldPermissions>` against required / formula / master-detail / auto-number / missing-from-org rules. `metadata` (REQ-F): workspace-internal cross-reference — perm-sets to Apex/apps/tabs/record-types, layouts to fields, FlexiPages to objects. Wired into `generating-permission-set` SKILL.md and `/canary` Step 2a.
- [`tools/sprint-dashboard/`](tools/sprint-dashboard/README.md) — zero-dep, single-server live dashboard that renders every registered project's REQs from `.adlc/specs/*/pipeline-state.json`. SSE-pushed updates (~1.5s), per-phase telemetry (Duration / Active / Last completion), project dropdown, manual refresh. Auto-launched by `/spec`, `/proceed`, `/sprint`, and `/init`; `/init` also opens it in Chrome and registers the project in `~/.adlc/dashboard-registry.json`.

### Quality gates

- [`partials/sf-quality-checklist.md`](partials/sf-quality-checklist.md) — machine-consumable companion to `.adlc/context/salesforce-rules.md`. Sourced by `task-implementer` (Phase 4) and the review panel (Phase 5). The single source of truth `.adlc/context/salesforce-rules.md` is the rules document; this partial is the sourced checklist.

## How it works

The toolkit is split into two layers:

1. **The toolkit repo** (this repo) — orchestration skills, agents, templates, the vendored sf-skills set, quality gates. Symlinked into `~/.claude/skills/` so every Claude Code session sees them.
2. **Per-project `.adlc/` directory** — lives in each Salesforce repo. Holds the project's specs, architecture, conventions, salesforce-rules, and a `config.yml` that declares the project's `app_prefix`, `api_version`, sf CLI org aliases, Industries footprint, and Agentforce variant. **All project-specific values live here**, never in the toolkit.

Skills read `.adlc/config.yml` at runtime for `salesforce.app_prefix` (permission-set naming), `salesforce.api_version` (Agentforce floor), `orgs.{sandbox,staging,prod}` (sf CLI aliases), `salesforce.industries` (which sf-skills are wired in), and `salesforce.agentforce_variant` (Employee | Service). Nothing is hardcoded in the skills.

## Setup

The toolkit uses a **symlink-based live install**: one canonical git clone on disk, exposed to Claude Code at `~/.claude/skills/` via an absolute-path symlink. There is no separate "installed" copy and no sync step — edits you commit to the clone are instantly visible to every Claude Code session on the machine.

### 1. Clone this repo

```bash
cd ~/code  # or wherever you keep repos
git clone https://github.com/<owner>/adlc-toolkit-sfdc.git
```

### 2. Symlink to Claude Code's skills and agents directories

```bash
[ -e ~/.claude/skills ] && mv ~/.claude/skills ~/.claude/skills.bak
[ -e ~/.claude/agents ] && mv ~/.claude/agents ~/.claude/agents.bak

TOOLKIT="$PWD/adlc-toolkit-sfdc"
ln -s "$TOOLKIT" "$HOME/.claude/skills"
ln -s "$TOOLKIT/agents" "$HOME/.claude/agents"
```

Verify:

```bash
readlink ~/.claude/skills   # → absolute path to your toolkit clone
readlink ~/.claude/agents   # → absolute path to .../adlc-toolkit-sfdc/agents
ls ~/.claude/skills/review/SKILL.md  # should resolve through the symlink
```

### 3. Initialize a Salesforce project

```bash
claude
> /init
```

This bootstraps `.adlc/context/`, `.adlc/specs/`, `.adlc/bugs/`, `.adlc/knowledge/`, and `.adlc/templates/`.

### 4. Configure for your scope

Pick a preset and copy it to `.adlc/config.yml`:

```bash
cp ~/.claude/skills/presets/sfdc-core.yml .adlc/config.yml         # most projects
# or
cp ~/.claude/skills/presets/sfdc-industries.yml .adlc/config.yml   # Data Cloud / Agentforce / OmniStudio / CME
$EDITOR .adlc/config.yml  # replace every <placeholder> — app_prefix, api_version, org aliases
```

Required values to fill in:
- `salesforce.app_prefix` — 3-8 char PascalCase identifier used in permission-set naming (`[AppPrefix]_[Component]_[AccessLevel]`)
- `salesforce.api_version` — ≥ 66.0 when Agentforce is in scope
- `orgs.{sandbox,staging,prod}` — sf CLI aliases (`sf org list` to check what's authenticated)
- `salesforce.industries` — trim to what's actually in scope (the file-glob router will skip rubrics for unused surfaces)
- `salesforce.agentforce_variant` — `Employee` or `Service` when Agentforce is in scope

## Workflow

```
/spec → /validate → /architect → /validate → implement → /reflect → /review → merge → /wrapup → /canary  ──▶  CI/CD pipeline promotes sandbox → staging → prod
```

`/canary` deploys to **sandbox only** (`orgs.sandbox` from `.adlc/config.yml`). Staging and production deploys are owned by the project's CI/CD pipeline (GitHub Actions, Gearset, Copado, etc.) — not by the ADLC pipeline. The ADLC handoff is "merged + sandbox-deployed + smoke-passed"; the team promotes from sandbox forward via their existing release process.

### Complexity-aware `/proceed` (REQ-C)

The requirement template carries a `complexity:` frontmatter field — `trivial | small | medium | large` — and `/proceed` scales the orchestration to match. Trivial perm-set / picklist / layout edits skip the validate gates and run a reflector-only Phase 5; small REQs add the quality reviewer; medium and large run the full 6-agent panel. Hard gates (worktree isolation, `pipeline-state.json`, local pre-flight, coverage policy, halt points) apply at every tier — only the fan-out changes. `/spec` Step 2.5 picks a default; the user can override.

### Diff-aware test level in `/canary` (REQ-D)

`/canary` Step 2 auto-picks `--test-level` from the diff. Metadata-only sandbox deploys run `NoTestRun`; sandbox+Apex runs `RunSpecifiedTests` against test classes derived from the changed-class file names. Saves typically 60-90% of validate wall time on metadata-only changes. (Staging and production deploys are CI-owned; their test-level policy lives in the project's pipeline config, not here.)

### React UI Bundles (Beta) — multi-framework

When `salesforce.features.ui_bundles: true` in `.adlc/config.yml`, the toolkit treats the multi-framework UI Bundles Beta as enabled in the target org. `generating-lwc-components` then offers a React path that scaffolds via `sf template generate ui-bundle -n ReactInternalApp|ReactExternalApp --template reactbasic`, requires `npm install` immediately after, and deploys via stock `sf project deploy start --source-dir uiBundles/<Name>` after `npm run build`. Internal vs external naming is captured in the requirement template's "Frontend framework" cue. When the flag is off (default), the React path is suppressed and skills stay LWC-only.

For bugs: `/bugfix` (report → analyze → fix → verify → ship)

For multi-REQ batches: `/sprint` (parallel `/proceed` runners — see "Sprint engines" below)

## Sprint engines (`legacy` vs `--workflow`)

`/sprint` has two engines behind one command. Both run REQs in parallel, but they drive the per-REQ pipeline very differently. The dispatcher in `sprint/SKILL.md` Step 0 picks one at runtime; default is `legacy`, opt-in is `--workflow`.

### Quick comparison

| | `legacy` (default) | `--workflow` |
|---|---|---|
| What runs the pipeline | One background `pipeline-runner` agent per REQ that literally executes `/proceed` Phases 0-8 | A Dynamic Workflows script (`workflows/adlc-sprint.workflow.js`) that dispatches per-phase agents itself |
| Subskills called | `/proceed` → `/validate`, `/architect`, `/wrapup`, `/canary` | `/wrapup` only — `/validate`, `/architect`, `/canary`, `/review` are inlined as paraphrased prompts |
| Resume after a halt | Re-run `/proceed REQ-xxx`; replays from last `currentPhase` in `pipeline-state.json` | `Workflow({resumeFromRunId, args:{answers}})` — surgical journal-replay; only the blocked REQ's halt-prone calls re-execute, every other call (and every other REQ) replays from cache with **zero** re-executed side effects |
| Per-REQ fan-out (Phase 2 explore trio, Phase 5 review panel) | Fans out only in `/proceed`'s main mode; subagent mode (used by `/sprint` background dispatch) serializes inside each runner | Always fans out at the script level (`parallel()`) regardless of where it's running |
| Cross-REQ shared-repo merge serialization | Best-effort, prose-driven | Pure-JS union-find post-pipeline barrier — disjoint REQs merge in parallel, shared-repo REQs serialize |
| Schema-validated agent IO | No — agent returns are free text | Yes — every leaf returns a JSON-schema-validated object |
| Tool availability | Always works | Plan-gated research preview; can be unavailable (see "Detecting Dynamic Workflows availability" below) |
| Dashboard observability | Phase strip + Active timer + per-phase telemetry update live as `pipeline-state.json` advances | Currently only Phase 0 (worktree init) and Phase 8 (terminal) update the state file — Phases 1-7 don't write `currentPhase`/`completedPhases`/`phaseHistory`/`currentPhaseStartedAt`, so the dashboard renders workflow REQs as stuck-on-Phase-0 until they merge |

### When each engine wins

**Use `legacy`** (or accept the default) when:
- You want the canonical phase contract — `legacy` calls real `/validate`, `/architect`, `/canary`, `/review` skills, so any improvement to those skills lands automatically.
- Your project depends on the Salesforce platform-validate gate (Phase 5 Step E) or the Phase 7 Step 7a deferred-validate reconcile — neither runs in `--workflow` today.
- You want live phase progress on the dashboard (per-phase Active timer, completedPhases, phaseHistory).
- Your REQs use the `complexity:` tier — `legacy` shrinks the review panel to 1 reviewer for `trivial`, 2 for `small`, 6 for `medium`/`large`. `--workflow` is currently always-6.
- Dynamic Workflows is unavailable in your session.

**Use `--workflow`** when:
- You hit a halt mid-sprint and want to resume by typing one answer instead of re-running `/proceed` and waiting for the journal to catch up. The surgical `args.answers[REQ-id]` resume is `--workflow`-only.
- You're running 5 REQs and want each REQ's internal explore trio + review panel to actually fan out in parallel (`legacy`'s background subagent mode serializes them inside each runner).
- You want script-enforced cross-REQ shared-repo merge serialization rather than trusting the orchestrator prose.
- You need schema-validated agent returns (rare — mostly matters when a downstream tool reads the output).

### Known divergences (audit, 2026-06)

Outcome-changing differences where the engines do not produce the same artifact:

1. **Salesforce platform-validate gate is missing in `--workflow`.** `/proceed` Phase 5 Step E runs `sf project deploy validate/start --dry-run` per touched repo (the project's ground-truth gate). The workflow script does not include this step, so SF projects ship without it. Phase 7 Step 7a's deferred-validate reconcile is also absent.
2. **`--workflow` does not invoke `/validate`, `/architect`, `/canary`, or `/review` as skills** — only paraphrased inline prompts. Improvements to those skills don't propagate to `--workflow` until the script body is also updated.
3. **No `complexity:` tier handling in `--workflow`** — always full explore trio + always full 6-agent review panel, even on `trivial`/`small` REQs.
4. **No ghost-REQ reconciler** at start of the workflow run. `/sprint` legacy runs `tools/reconcile-pipeline-state/reconcile.sh` first; `--workflow` does not.
5. **Phase 0-7 don't update phase telemetry.** Workflow REQs render as Phase 0 with no Active timer until they merge. (We fixed this earlier for spec/architect validation; the per-phase live updates inside a workflow run are the remaining gap.)
6. **No cross-repo task-routing in Phase 4.** Workflow's `implementPrompt` writes every task to the shared primary worktree; legacy routes each task to `repos[<task.repo>].worktree`.
7. **Phase 6 `local-bare:<origin>#<branch>` synthetic prUrl marker is not emitted by `--workflow`,** but its Phase 8 expects it for actor-probe — projects with no `gh` access on a hosted remote can fall through.
8. **Phase 4 is serial in `--workflow`,** even when tasks within a tier touch disjoint files. Legacy main-mode parallelizes within tier.
9. **Phase 7 fix-and-push is forbidden in `--workflow`** ("Do NOT modify code"). Legacy fixes-in-worktree on cleanup findings and pushes.
10. **`pipeline-runner.md` agent doc has drifted from `/proceed`** — it doesn't mention Phase 5 Step E (platform-validate) or Phase 7 Step 7a (deferred-validate reconcile). A `pipeline-runner` running in subagent mode silently skips those gates that `/proceed` requires.

The full audit (file:line citations) is in `audit/sprint-engines-divergence.md`. Treat any new divergence as a bug — fix toward whichever engine matches `/proceed`'s spec, since `/proceed` is the canonical phase definition.

### Detecting Dynamic Workflows availability

Dynamic Workflows is a research-preview, plan-gated capability — it can be absent on basic plans, in headless/cron Claude Code runs, or in some IDE integrations. `/sprint --workflow` falls back to `legacy` automatically when unavailable, but you can check ahead of time:

| Signal | What it tells you |
|---|---|
| **In a Claude Code session, ask:** `Can you call the Workflow tool? Just answer yes/no.` | Cheapest check. The model knows whether the tool is in its tool list for this session. |
| **In an existing transcript, grep for the tool name:** `grep -l '"name":"Workflow"' ~/.claude/projects/*/[session-id].jsonl` | If `Workflow` appears in any tool-use record from a prior session in this directory, it's available now too (same plan + same install). |
| **Run a sentinel `/sprint --workflow REQ-xxx`** — if the dispatcher logs `Workflow tool unavailable; falling back to legacy`, you know. | Burns one user prompt but is definitive. |
| **`claude --version` + plan name** | The current Claude Code release notes call out Dynamic Workflows availability per plan tier. If the version predates the feature, it's absent regardless of plan. |

If `Workflow` is unavailable, you don't need to do anything — `/sprint --workflow` degrades to `legacy` with an explicit notice. There is no separate "enable Dynamic Workflows" toggle to flip; availability is determined by the platform, not by project config.

## Project Structure

After `/init`, each Salesforce repo will have:

```
.adlc/
  config.yml              # app_prefix, api_version, org aliases, industries, agentforce_variant
  context/
    project-overview.md
    architecture.md
    conventions.md
    salesforce-rules.md   # the rules document — source of truth
    sf-skills-catalog.md  # phase mapping + file-glob → rubric dispatch
  specs/                  # REQ-xxx-* directories with requirement.md + tasks/
  bugs/                   # BUG-xxx-* reports
  knowledge/
    lessons/              # LESSON-xxx-* knowledge entries
    assumptions/          # ASSUME-xxx-* validated assumptions
  templates/              # local copies of toolkit templates
  partials/               # local copies of toolkit partials (incl. sf-quality-checklist.md)
  workflows/              # vendored Dynamic Workflow scripts
```

The toolkit repo contains the **process** (skills + templates). Each Salesforce repo contains the **artifacts** (specs, architecture, knowledge, Permissions.md per feature).

## Cross-repo support

Some features span multiple repos (e.g., a Salesforce package + an external integration repo + a documentation site). The toolkit supports cross-repo via the optional `repos:` block in `.adlc/config.yml`. See [`templates/config-template.yml`](templates/config-template.yml) for the full annotated shape.

The default for SF projects is single-repo (one DX project, `repos: { sfdc: { primary: true } }`).

## Salesforce-specific conventions

- **CLI**: always `sf` (v2). `sfdx` is deprecated.
- **Models**: only `sonnet` and `opus`. No `haiku`, no third-party models. See [`MODEL_ASSIGNMENTS.md`](MODEL_ASSIGNMENTS.md). Enforced by `tools/lint-skills/`.
- **Apex naming**: PascalCase classes, camelCase methods/variables, ALL_CAPS_SNAKE_CASE enums.
- **Permission set naming**: `[AppPrefix]_[Component]_[AccessLevel]` (`AccessLevel ∈ Read|Write|Full|Execute|Admin`). Enforced by `tools/sf-lint/`.
- **Sharing keyword**: every Apex class must declare `with sharing` / `without sharing` / `inherited sharing` explicitly. Enforced by sf-lint.
- **AccessLevel**: every SOQL/DML statement must declare an explicit `AccessLevel` (USER_MODE preferred). Enforced by sf-lint.
- **No `@future`**: use queueables with `System.Finalizer`. Enforced by sf-lint.
- **Permissions.md**: every feature touching metadata generates one (template at `templates/permissions-template.md`). Enforced by `/wrapup` Step 3a.
- **Agentforce deploy order**: fields → Apex → Flow → GenAi* → publish → activate. API ≥ 66.0. Enforced by `/wrapup` Step 3b.
- **Coverage policy (REQ-A)**: three-tier model in `.adlc/config.yml` `salesforce.coverage` — `org_floor` (75 platform min), `org_target` (project floor, default 80), `class_floor` (per-changed-class in brownfield mode, default 75), `mode: greenfield|brownfield`. Greenfield projects gate deploys on org-level coverage only; brownfield gates both org and per-changed-class. Skills MUST read from config; never hardcode 75/80. Enforced by `/canary` Step 5 and `agents/test-auditor.md`.
- **Local pre-flight before `validate` (REQ-B + REQ-F)**: `/canary` Step 2a runs `tools/sf-preflight/check.sh permsets` (org-aware FLS / required / formula / master-detail / missing-from-org gate) and `tools/sf-preflight/check.sh metadata` (workspace cross-reference) before paying for a server-side `sf project deploy validate`. Block findings refuse to call validate; the user fixes the metadata and re-runs `/canary`.

The full set is in [`.adlc/context/salesforce-rules.md`](.adlc/context/salesforce-rules.md), with the static-checkable subset in [`partials/sf-quality-checklist.md`](partials/sf-quality-checklist.md) and mechanized in [`tools/sf-lint/`](tools/sf-lint/README.md).

## Updating

Pull the latest toolkit to update all skills across all projects:

```bash
cd "$(readlink ~/.claude/skills)"
git pull
```

Since `~/.claude/skills` is a symlink, changes are picked up immediately.

To refresh the vendored sf-skills set against a newer upstream commit, see [`skills/sf/VENDORED.md`](skills/sf/VENDORED.md) for the procedure.

## Contributing

This is a Salesforce-tuned fork. Patches that add presets for additional Salesforce surface combinations, sharpen sf-skill dispatch logic, or extend the sf-lint static rule set are all welcome.
