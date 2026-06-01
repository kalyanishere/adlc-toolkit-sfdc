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
