# Project Overview — ADLC Toolkit (Salesforce edition)

## What this project is

The ADLC Toolkit (Salesforce edition) is a library of **skills, agents, templates, and quality gates** that enable spec-driven development for Salesforce projects with Claude Code. It is the source of `/spec`, `/architect`, `/proceed`, `/review`, `/bugfix`, `/wrapup`, and other skills that consumer Salesforce projects use to run their own Agentic Development Life Cycle (ADLC) pipelines.

This is the Salesforce-tuned fork of the generic ADLC toolkit. It vendors the [forcedotcom/afv-library](https://github.com/forcedotcom/afv-library) sf-skills set (37 skills covering Apex, LWC, Flow, SOQL, testing, debug, metadata, permissions, deploy, integration, Data Cloud, Agentforce, OmniStudio, Industries) and rewires the ADLC review panel to consume those skills as rubrics, not as separate agents.

This repo is itself a consumer of the toolkit only in the narrow sense that its own feature work is tracked in `.adlc/specs/`. No `.adlc/knowledge/lessons/`, `.adlc/bugs/`, or `.adlc/templates/` directory inside this repo (those live in consumer projects after `/init`). The toolkit's canonical `templates/` directory at the repo root is what `/init` copies into consumer projects.

## Who uses it

- **Salesforce consumer projects** symlink this repo to `~/.claude/skills/` and `~/.claude/agents/`. Any improvement committed here is immediately visible to every Claude Code session on the machine — no publish step.
- **Toolkit maintainers** evolve the skills, add new ones, and fix bugs in the skill definitions themselves. REQs tracked here describe changes to the toolkit's own surface area: skill behavior, template schemas, agent prompts, quality-gate rules, documentation.

## Install model

Symlink-based live install. One canonical git clone on disk, symlinked at `~/.claude/skills/`. Edits to the clone are visible immediately. No separate installed copy, no sync step, no versioning at the install layer.

## Primary surface areas

| Surface | Files | Purpose |
|---|---|---|
| Skills | `<skill-name>/SKILL.md` | Markdown files invoked by Claude Code as slash commands |
| sf-skills | `skills/sf/<skill-name>/SKILL.md` | Vendored 37 Salesforce skills from forcedotcom/afv-library |
| Agents | `agents/<agent-name>.md` | 11 specialized subagent definitions (5 Opus / 6 Sonnet) |
| Templates | `templates/*.md` | Canonical templates for requirements, bugs, lessons, tasks, assumptions, permissions |
| Partials | `partials/*.{sh,md}` | Shared snippets sourced by SKILL.md files (ethos, sf-quality-checklist) |
| Workflows | `workflows/*.workflow.js` | Deterministic Dynamic Workflow scripts for orchestration |
| Tools | `tools/lint-skills/`, `tools/sf-lint/` | SKILL.md hygiene linter; SF-specific static rule check (build-time gate) |
| Presets | `presets/sfdc-*.yml` | Stack-shaped starter configs for `.adlc/config.yml` |
| Ethos | `ETHOS.md` | Five principles injected into every skill — the non-negotiable constitution |
| Models | `MODEL_ASSIGNMENTS.md` | Per-agent registry — Sonnet | Opus only |
| Docs | `README.md` | Install instructions and skill catalog |

## Relationship to consumer projects

`/init` is the bridge: when a Salesforce consumer project runs `/init`, it creates `.adlc/context/`, `.adlc/specs/`, `.adlc/bugs/`, `.adlc/knowledge/`, and `.adlc/templates/` in that project, copying from the toolkit's `templates/` directory. After `/init`, the consumer project uses skills that read from **its** `.adlc/` structure — not the toolkit's.

The consumer's `.adlc/config.yml` declares Salesforce-specific values: `app_prefix` (3–8 char PascalCase, used in permission set naming), `api_version` (66.0+ floor for Agentforce), `org_alias` (sf CLI default org), `package_directories`, `agentforce_variant` (Employee | Service when Agentforce is in scope), and `industries: [datacloud, agentforce, omnistudio, cme]` opt-in flags. Skills branch on those flags — the Agentforce deploy-order gate fires only when the project has declared Agentforce; the OmniStudio review path activates only when omnistudio is declared.

The toolkit's own `.adlc/` (containing only `specs/`, `context/`, `archive/kimi-era/`) is minimal by design. The toolkit doesn't track lessons or bugs for itself; that may change if the toolkit's internal work grows.

## Current scope

The toolkit started as the generic ADLC toolkit (REQ-258 onward) with a generic web/iOS/Cloud Run preset. As of the Salesforce-tuning rewrite (2026-06-01), the toolkit:

- Removed all Kimi K2.5 / Moonshot delegation infrastructure (archived under `.adlc/archive/kimi-era/`)
- Restricted models to Sonnet/Opus only (Haiku eliminated, no third-party models)
- Replaced the iOS+Firebase+CloudRun preset with `sfdc-core.yml` and `sfdc-industries.yml`
- Will vendor the 37 sf-skills set in a later batch
- Promotes `salesforce-rules.md` to an enforced quality gate at Phase 4 (build) and Phase 5 (review)

## Permitted models

Only `sonnet` and `opus` are permitted in any agent's `model:` frontmatter. The single registry mapping every agent to a model is `MODEL_ASSIGNMENTS.md` at the repo root. Haiku and any third-party model (Kimi K2.5 etc.) are out of scope by policy.

## REQ-numbering policy (cross-project global counter)

This repo shares a **global** REQ counter at `~/.claude/.global-next-req` with all consumer projects on the machine. Future REQ allocations from this toolkit MUST take the next slot above the global high-water, not above adlc-toolkit's local high-water. Existing toolkit specs keep their numbers — the policy applies to new allocations only.

Rationale: a single REQ id should resolve to one work item across every repo on the machine, so cross-repo references (links, lessons, branch names, PR titles) are unambiguous.
