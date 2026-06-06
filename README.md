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
/spec → /validate → /architect → /validate → implement → /reflect → /review → merge → /wrapup → /canary sandbox → /canary staging → /canary prod (validate-only) → manual sf deploy
```

`/canary` deploys to sandbox and staging itself, but **for prod it stops at validate**. It surfaces the validation id from `sf project deploy validate` and prints the exact `sf project deploy quick --target-org <prod-alias> --job-id <validation-id>` command for you to run yourself. The skill never executes a deploy command against the prod alias under any circumstances — Agentforce and Playwright smoke gates against prod are skipped for the same reason (no fresh deploy yet) and should be re-run after the manual deploy lands. Validations remain reusable for ~10 days.

### Complexity-aware `/proceed` (REQ-C)

The requirement template carries a `complexity:` frontmatter field — `trivial | small | medium | large` — and `/proceed` scales the orchestration to match. Trivial perm-set / picklist / layout edits skip the validate gates and run a reflector-only Phase 5; small REQs add the quality reviewer; medium and large run the full 6-agent panel. Hard gates (worktree isolation, `pipeline-state.json`, local pre-flight, coverage policy, halt points) apply at every tier — only the fan-out changes. `/spec` Step 2.5 picks a default; the user can override.

### Diff-aware test level in `/canary` (REQ-D)

`/canary` Step 2b auto-picks `--test-level` from the diff. Metadata-only sandbox deploys run `NoTestRun`; sandbox+Apex runs `RunSpecifiedTests` against the test classes derived from the changed-class file names; staging falls back to `RunLocalTests` (or to a configured smoke list via `salesforce.smoke_tests`); prod always runs `RunLocalTests`. Saves typically 60-90% of validate wall time on metadata-only changes.

### React UI Bundles (Beta) — multi-framework

When `salesforce.features.ui_bundles: true` in `.adlc/config.yml`, the toolkit treats the multi-framework UI Bundles Beta as enabled in the target org. `generating-lwc-components` then offers a React path that scaffolds via `sf template generate ui-bundle -n ReactInternalApp|ReactExternalApp --template reactbasic`, requires `npm install` immediately after, and deploys via stock `sf project deploy start --source-dir uiBundles/<Name>` after `npm run build`. Internal vs external naming is captured in the requirement template's "Frontend framework" cue. When the flag is off (default), the React path is suppressed and skills stay LWC-only.

For bugs: `/bugfix` (report → analyze → fix → verify → ship)

For multi-REQ batches: `/sprint` (parallel `/proceed` runners)

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
