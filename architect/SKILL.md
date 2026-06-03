---
name: architect
description: Design architecture and break requirement into tasks
argument-hint: REQ-xxx ID or requirement description
---

# /architect — Architecture & Task Breakdown

You are designing architecture and breaking a requirement into implementable tasks.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Task template: !`cat .adlc/templates/task-template.md 2>/dev/null || cat ~/.claude/skills/templates/task-template.md 2>/dev/null || echo "No task template found"`
- Active specs: !`grep -rl 'status: draft\|status: approved\|status: in-progress' .adlc/specs/*/requirement.md 2>/dev/null | head -20 || echo "No active specs"`

**Context files loaded on demand**: `.adlc/context/architecture.md` and `.adlc/context/conventions.md` are loaded by Step 1 below — **skip the Read if they are already in the current conversation** (e.g., when invoked from `/proceed`, which preloads them at Phase 0).

## Input

Requirement: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.adlc/context/architecture.md` and `.adlc/context/conventions.md` exist. If either is missing, stop and tell the user: "The `.adlc/` structure hasn't been fully initialized. Run `/init` first to set up the project context."

## Instructions

### Step 1: Locate and Read the Requirement
1. If given a REQ ID, read `.adlc/specs/REQ-xxx-*/requirement.md`
2. If given a description, search `.adlc/specs/` for the matching requirement
3. Verify the requirement status is `draft` or `approved` (not already `complete`)
4. **Context files**: if `.adlc/context/architecture.md` and `.adlc/context/conventions.md` are NOT already in your conversation context (e.g., this skill is being run standalone, not from `/proceed`), Read them now. Otherwise skip — they're already loaded.
5. Check `.adlc/knowledge/assumptions/` for prior decisions that may affect design
6. **Lessons — grep first, then read only matches**: use the Grep tool on `.adlc/knowledge/lessons/` with patterns like `component:.*<affected-area>` or `domain:.*<domain>` to identify matching files. Then Read ONLY those matched files. Do NOT read all lessons. Note applicable lessons in your architecture rationale so past mistakes aren't repeated and proven patterns are reused.

### Step 2: Explore the Codebase
1. Launch 3 formal exploration agents in parallel using the Agent tool. Each agent is defined in `~/.claude/agents/` with model selection (haiku for fast exploration) and read-only tool restrictions.

   - **feature-tracer** agent — provide the requirement description and key terms to search for similar existing implementations
   - **architecture-mapper** agent — provide the requirement and current architecture.md to map all files and layers that will be affected
   - **integration-explorer** agent — provide the affected areas to identify extension points, tests, and integration surfaces

2. Read the key files identified by agents

### Step 2.5: Load orchestrator sf-skills that shape the architecture

`/architect` cannot reason about Salesforce-specific scaffolding from first principles — every artifact family (UI Bundles, Agentforce agents, OmniStudio, Data Cloud, B2B Commerce) has a vendored skill at `skills/sf/<name>/SKILL.md` that defines the canonical scaffolding command, file shape, and metadata layout. If the architect ignores those skills and writes tasks like "create `package.json` and `src/index.tsx` by hand" when `building-ui-bundle-app` exists, the deploy will fail at the platform validate gate (`/proceed` Phase 5 Step E) — costing a full review cycle. Load orchestrator skills BEFORE producing any task.

1. **Read the spec frontmatter and `.adlc/config.yml`** — extract `salesforce.features`, `salesforce.industries`, the spec's `stack:` and `tags:`, and any keyword signals in the spec body (Description, External Dependencies, Acceptance Criteria).

2. **Match signals to orchestrator skills** using this dispatch table. A signal MUST trigger a load — first-principles reasoning about a layer when its skill exists is a protocol violation:

   | Signal | Orchestrator skill(s) to invoke via the Skill tool |
   |---|---|
   | `salesforce.features.ui_bundles: true` AND (spec stack includes `react`/`reactInternal`/`reactExternal`, OR spec body mentions "UI Bundle" / "ReactInternalApp" / "ReactExternalApp") | `building-ui-bundle-app`, `generating-ui-bundle-metadata`, `building-ui-bundle-frontend`, `deploying-ui-bundle` |
   | spec body mentions "Experience Site" / "portal" + UI Bundle | add `generating-ui-bundle-site` |
   | spec body mentions "Agentforce conversation client" / "embedded chat" | add `implementing-ui-bundle-agentforce-conversation-client` |
   | spec body mentions "file upload" + UI Bundle | add `implementing-ui-bundle-file-upload` |
   | spec body mentions "Salesforce data" / "@salesforce/data" + UI Bundle | add `using-ui-bundle-salesforce-data` |
   | `salesforce.industries: [agentforce]` OR spec mentions "Agentforce" / "agent topic" / "GenAi" | `developing-agentforce`, `testing-agentforce`, `observing-agentforce` |
   | Spec `stack` includes `lwc` AND a new component is in scope | `generating-lwc-components`; add `uplifting-components-to-slds2` if SLDS 2 / dark mode / a11y is in scope |
   | Spec mentions "OmniStudio" / "OmniScript" / "FlexCard" / "Integration Procedure" / "Data Mapper" / "DataRaptor" | `analyzing-omnistudio-dependencies` plus the matching `building-omnistudio-*` skill(s) |
   | Spec mentions "Data Cloud" / "DLO" / "DMO" / "calculated insight" / "segment" | `getting-datacloud-schema`; the matching `connecting-`/`preparing-`/`harmonizing-`/`segmenting-`/`activating-datacloud` skill per phase; add `orchestrating-datacloud` for multi-phase pipelines |
   | Spec mentions "Industries CME" / "EPC" / "Product2" catalog | `modeling-omnistudio-epc-catalog` |
   | Spec mentions "B2B Commerce" / "OCC" / "store" | `creating-b2b-commerce-store`, `integrating-b2b-commerce-open-code-components` |
   | Spec mentions "REST callout" / "external service" / "Named Credential" / "Platform Event" / "CDC" | `building-sf-integrations` |
   | Spec mentions a new Apex class, trigger, batch, queueable, REST resource | `generating-apex` (rubric — load only at task time via `required_skills`, not as an orchestrator) |

   Multiple matches → load all. Always cross-reference the catalog at `.adlc/context/sf-skills-catalog.md` (Phase mapping section) for any artifact type the spec implies; if a match is missing from the table above, prefer loading from the catalog over skipping.

3. **Invoke each matched orchestrator skill via the Skill tool** in this Step 2.5 — not at task time, not in Phase 4. The orchestrator's instructions tell you the canonical scaffolding command (e.g., for UI Bundles: `sf template generate ui-bundle -n <Name> --template reactbasic`), the file shape the platform expects (e.g., `<Name>.uibundle-meta.xml` + `dist/` + `ui-bundle.json`), and the deploy quirks. The architecture you produce in Step 3 and the tasks you produce in Step 4 MUST reflect those instructions verbatim.

4. **Record the loaded orchestrators** in the architecture rationale so the lineage is auditable: a one-line `Orchestrator skills loaded: <comma-separated list>` block at the top of `architecture.md` (when one is created), or in the architecture summary surfaced at Phase 6 when no architecture.md is needed.

5. **If no signal matches** any row in the table AND the catalog yields nothing, record `Orchestrator skills loaded: none — change is generic-Apex/LWC and uses only the per-file rubrics at task time.` Do NOT silently skip.

### Step 3: Design Architecture (if needed)
1. If the requirement involves new architectural decisions, create `.adlc/specs/REQ-xxx-*/architecture.md`
2. Document:
   - **Approach**: High-level design and rationale
   - **Data model changes**: New Firestore collections/fields, GCS metadata
   - **API changes**: New or modified endpoints
   - **Service layer**: New or modified services
   - **Key decisions**: ADRs with rationale (follow the style in `.adlc/context/architecture.md`)
3. Propose any additions to `.adlc/context/architecture.md` with rationale

### Step 4: Break Into Tasks
1. Create `.adlc/specs/REQ-xxx-*/tasks/` directory
2. Determine the next TASK ID by checking existing tasks across ALL specs (not just this one)
3. **Detect repository mode**: check whether `.adlc/config.yml` exists in the primary repo and declares a `repos:` block with more than one entry.
   - **Single-repo mode** (no config or single entry): set `repo:` on each task to the primary repo id (or omit — `/proceed` will backfill). Files listed under "Files to Create/Modify" all live in the primary repo.
   - **Cross-repo mode** (config has siblings): **every task MUST declare a `repo:` field** naming one of the ids under `repos:`. Group files by repo — a single task should not modify files in multiple repos. If a piece of work spans repos (e.g., an API contract change requires matching backend and frontend edits), split it into at least two tasks with an explicit dependency between them.
4. Create `TASK-xxx-description.md` for each task using the template from `.adlc/templates/task-template.md`
5. Each task must specify:
   - **Frontmatter**: id, title, status (`draft`), parent REQ, created/updated dates, dependencies, `required_skills` (see below), `repo:` (required in cross-repo mode)
   - **`required_skills:` (mandatory population)** — for each task, intersect the orchestrator skills loaded in Step 2.5 with the layer this task implements, AND walk the task's `Files to Create/Modify` list against `.adlc/context/sf-skills-catalog.md`'s **File-glob → rubric dispatch** table. Put the resulting union into the task's `required_skills:` frontmatter array. Examples:
     - A task that creates a UI Bundle scaffold MUST list `[building-ui-bundle-app, generating-ui-bundle-metadata]` so the implementer is forced to run `sf template generate ui-bundle` instead of hand-rolling files. Hand-rolling is a protocol violation that the platform validate gate will catch — but populating `required_skills` correctly prevents it from happening in the first place.
     - A task that builds the bundle's React panels lists `[building-ui-bundle-frontend, using-ui-bundle-salesforce-data]` (when SF data is consumed).
     - A task that creates a perm-set lists `[generating-permission-set]`.
     - A task that creates an Agentforce topic + Apex action lists `[developing-agentforce, generating-apex]`.
     - A task that touches only existing Apex with no orchestrator-driven scaffolding lists `[generating-apex]` (rubric only).
     - A pure-test task lists `[generating-apex-test, running-apex-tests]`.
   - **Description**: What this task accomplishes
   - **Files to Create/Modify**: Specific file paths with descriptions of changes — all paths must live in the task's target repo
   - **Acceptance Criteria**: Concrete, testable criteria
   - **Technical Notes**: Implementation details, patterns to follow, edge cases. When `required_skills` includes an orchestrator (e.g., `building-ui-bundle-app`), reference its canonical scaffolding command verbatim here so the implementer does not improvise. In cross-repo mode, call out any cross-repo contracts this task establishes or consumes.
   - **Dependencies**: Other tasks that must complete first — dependencies may cross repos (a frontend task can depend on a backend task)
6. Tasks must form a valid dependency graph (no cycles), even when spanning repos
7. Order tasks so foundational work comes first (data layer → service → routes → UI). In cross-repo mode, backend/API tasks typically precede their frontend consumers.
8. **UI test obligation** — for any task that touches a user-facing surface (`force-app/**/lwc/**`, FlexiPages, Lightning Apps, Experience Cloud sites, OmniScripts, Flow screens, custom tabs, or Agentforce conversation UI), the task MUST list a Playwright spec under `tests/e2e/<feature>.spec.ts` in **Files to Create/Modify** and include an acceptance criterion of the form "Playwright spec `tests/e2e/<feature>.spec.ts` passes against `orgs.sandbox`". LWC Jest unit tests remain required separately — Playwright covers cross-component flows (login → navigate → interact → assert), Jest covers the component in isolation. If `.adlc/config.yml` does not declare `playwright_specs:`, note in Technical Notes that Playwright wiring needs to be added before this task can run; otherwise reference the configured directory.

### Step 5: Update Requirement Status
1. Update the requirement's frontmatter status from `draft` to `approved`
2. Update the `updated` date

### Step 6: Present for Review
1. Display the architecture decisions (if any)
2. Display the task breakdown as a dependency graph
3. Summarize the implementation plan
4. Remind the user to run `/validate` before starting implementation

## Quality Checklist
- [ ] Architecture follows existing patterns (layered: routes → services → repositories)
- [ ] Tasks are small enough to implement in a single session
- [ ] Task dependencies form a valid DAG (no cycles), including cross-repo edges
- [ ] Every file to be modified is listed in at least one task
- [ ] Tests are included in task acceptance criteria
- [ ] Every UI-bearing task lists a Playwright spec in Files to Create/Modify and an acceptance criterion that runs it
- [ ] No task has more than 3 dependencies
- [ ] In cross-repo mode: every task has a `repo:` field naming a valid repo id from `.adlc/config.yml`, and all files in that task live in that repo
- [ ] Step 2.5 ran — orchestrator skills loaded and recorded; OR explicitly recorded as "none" with justification
- [ ] Every task that touches Salesforce metadata under `salesforce.workspace` (default `force-app/`) has a non-empty `required_skills:` array. Tasks that touch UI Bundles MUST include `building-ui-bundle-app` (scaffolding orchestrator) — hand-rolling React project files is a protocol violation
