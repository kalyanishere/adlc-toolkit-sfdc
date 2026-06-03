---
id: LESSON-024
title: "UI Bundles must be scaffolded via `sf template generate ui-bundle` — never hand-rolled, and the architect must load `building-ui-bundle-app` before producing tasks"
component: "adlc/architect"
domain: "salesforce"
stack: ["sf-cli", "ui-bundle", "react", "vite"]
concerns: ["correctness", "scaffolding", "deploy", "feature-flag-gated-metadata"]
tags: ["ui-bundle", "react-internal-app", "react-external-app", "uibundle-meta-xml", "sf-template-generate", "skill-orchestrator", "required-skills", "platform-validate-gate"]
req: REQ-toolkit
created: 2026-06-03
updated: 2026-06-03
---

## What Happened

A consumer project enabled `salesforce.features.ui_bundles: true` and asked
`/spec` + `/architect` + `/proceed` to deliver a React Internal App. Three
independent failure points combined to ship a deploy-failing artifact:

1. **`/architect` reasoned from `requirement.md` alone.** It produced a task
   that said "create `package.json`, `tsconfig.json`, `src/index.tsx`" — exactly
   the path the `building-ui-bundle-app` skill explicitly forbids. The
   architect never loaded that orchestrator skill (or `generating-ui-bundle-metadata`),
   even though the dispatch table in `.adlc/context/sf-skills-catalog.md`
   wires those skills to `salesforce.features.ui_bundles: true`.

2. **The task file had no `required_skills:` field** — so when
   `task-implementer` opened it, the agent had no protocol forcing it to
   load `building-ui-bundle-app` before scratching out `Edit`/`Write` calls.
   Hand-rolling proceeded uncorrected.

3. **Phase 5 verify is 100% read-only.** None of the six review agents
   ran `sf project deploy validate`. The `architecture-reviewer` even
   flagged "Beta-feature metadata shape uncertain — verify at deploy time" —
   and that "deploy time" never came inside the pipeline. In local-only
   runs, Phase 7 CI is skipped entirely with no replacement.

The deploy then surfaced a cluster of bugs that one `sf project deploy validate`
would have caught in 30-90 seconds: wrong `.app-meta.xml` extension (should
be `.uibundle-meta.xml`), missing `dist/` directory (Vite output never built),
malformed `ui-bundle.json`, IllegalArgumentException on a feature-flagged
metadata field, ORDER BY CASE that the sandbox API version rejected, FlexiPage
template name drift, plus the obvious `\'` escape bug.

## Lesson

**Three things must hold for any feature whose layer has a vendored sf-skill
orchestrator:**

1. **`/architect` Step 2.5 loads orchestrator skills based on signals** in
   `.adlc/config.yml` and the spec frontmatter — not from first-principles
   reasoning. For UI Bundles, the trigger is
   `salesforce.features.ui_bundles: true` AND a stack/body signal. The
   architect must invoke `building-ui-bundle-app` (and friends) via the
   Skill tool before producing any task.

2. **Every task that touches a UI Bundle MUST list the orchestrator skill(s)
   in `required_skills:`** — populated by `/architect` from the catalog
   dispatch. `task-implementer` is required by its agent definition to
   invoke each entry via the Skill tool BEFORE editing files. The orchestrator
   tells you the canonical scaffolding command (`sf template generate ui-bundle
   -n <Name> --template reactbasic`); the implementer is forbidden from
   hand-rolling around it.

3. **`/proceed` Phase 5 has a Step E platform validate gate** that runs
   `sf project deploy validate` against `salesforce.validate_org` /
   `orgs.sandbox` / `orgs.scratch` — a Critical-severity loop back to Step C
   on any failure. This is the second-line defense regardless of how the
   first line failed: every static reviewer reasons about source code in
   isolation, but the platform compiler is the only oracle that knows your
   org's installed feature-flagged metadata, the `.uibundle-meta.xml` shape,
   and what `dist/` must contain.

The lesson capture itself is necessary but not sufficient — `/architect`
and `task-implementer` don't read `.adlc/knowledge/lessons/`. Pair this
lesson with the protocol-level fixes above (architect Step 2.5,
`required_skills:` enforcement, Step E platform validate gate); the lesson
is then the audit trail explaining *why* those steps exist.

## Why It Matters

A hand-rolled UI Bundle wastes 1-2 review cycles before a human notices the
artifact shape is wrong. The dist/ omission alone burns a full sandbox
deploy round-trip (~10-15 min). The same failure mode applies to every
artifact family with a vendored skill: Agentforce agents, OmniStudio
components (OmniScript / FlexCard / IP / DataMapper), Industries CME EPC
DataPacks, B2B Commerce stores, Data Cloud DLO/DMO/segments. If
`/architect` reasons from `requirement.md` alone for any of these, the
implementer ships a plausible-looking artifact the platform will reject.

## Applies When

- Spec has `salesforce.features.ui_bundles: true` AND mentions React /
  ReactInternalApp / ReactExternalApp / "UI Bundle".
- Spec implies any artifact family with a vendored `skills/sf/<name>/`
  orchestrator (see the catalog at `.adlc/context/sf-skills-catalog.md`).
- `/architect` is producing tasks that touch `force-app/main/default/uiBundles/`,
  `force-app/main/default/agents/`, `force-app/main/default/omniProcesses/`,
  `force-app/main/default/genAi*/`, or any other family whose canonical
  scaffolding is a `sf template generate` / `sf agent` command rather than
  a hand-written tree.

## Related

- `/architect` Step 2.5 — the signal-to-orchestrator dispatch table.
- `agents/task-implementer.md` Process step 4 — the `required_skills`
  invocation precondition.
- `/proceed` Phase 5 Step E — the platform validate ground-truth gate.
- `.adlc/context/sf-skills-catalog.md` — the file-glob → rubric and
  layer → orchestrator mapping.
- `skills/sf/building-ui-bundle-app/SKILL.md` — the canonical scaffolding
  instructions this lesson defends.
