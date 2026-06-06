---
name: deploying-metadata
description: "Salesforce DevOps automation using sf CLI v2. TRIGGER when: user deploys metadata, creates/manages scratch orgs or sandboxes, sets up CI/CD pipelines, or troubleshoots deployment errors with sf project deploy. DO NOT TRIGGER when: writing Apex code (use generating-apex), building LWC components (use generating-lwc-components), creating metadata definitions (use generating-custom-object or generating-custom-field), or querying org data (use handling-sf-data)."
license: MIT
metadata:
  version: "1.1"
---

# deploying-metadata: Comprehensive Salesforce DevOps Automation

Use this skill when the user needs **deployment orchestration**: dry-run validation, targeted or manifest-based deploys, CI/CD workflow advice, scratch-org management, failure triage, or safe rollout sequencing for Salesforce metadata.

## When This Skill Owns the Task

Use `deploying-metadata` when the work involves:
- `sf project deploy start`, `quick`, `report`, or retrieval workflows
- release sequencing across objects, permission sets, Apex, and Flows
- CI/CD gates, test-level selection, or deployment reports
- troubleshooting deployment failures and dependency ordering

Delegate elsewhere when the user is:
- authoring Apex code → [generating-apex](../generating-apex/SKILL.md)
- authoring LWC components → [generating-lwc-components](../generating-lwc-components/SKILL.md)
- creating custom objects or fields → [generating-custom-object](../generating-custom-object/SKILL.md), [generating-custom-field](../generating-custom-field/SKILL.md)
- building Flows → [generating-flow](../generating-flow/SKILL.md)
- doing org data operations → [handling-sf-data](../handling-sf-data/SKILL.md)
- authoring or testing Agentforce agents → [developing-agentforce](../developing-agentforce/SKILL.md)

---

## Critical Operating Rules

- Use **`sf` CLI v2 only**.
- On non-source-tracking orgs, deploy/retrieve commands require an explicit scope such as `--source-dir`, `--metadata`, or `--manifest`.
- Prefer **`--dry-run` first** before real deploys.
- For Flows, deploy safely and activate only after validation.
- Keep test-data creation guidance delegated to **`handling-sf-data`** after metadata is validated or deployed.

### Default deployment order
| Phase | Metadata |
|---|---|
| 1 | Custom objects / fields (includes `*__mdt` type definitions) |
| 2 | Custom Metadata records (rows of `*__mdt` types) |
| 3 | Permission sets |
| 4 | Apex |
| 5 | Flows as Draft |
| 6 | Flow activation / post-verify |

This ordering prevents many dependency and FLS failures. Custom Metadata records (`CustomMetadata` type) **must deploy after** their type definition (`CustomObject` type, member ending in `__mdt`) — they are separate Metadata API types and belong in **separate `<types>` blocks** in `package.xml`.

---

### Custom Metadata Types — package.xml structure (Critical)

**Custom Metadata Types** ship as **two distinct Metadata API types** that must each have their own `<types>` block. Never nest the records inside the type definition's block.

| Concept | Metadata API type | Member format | File |
|---|---|---|---|
| **Type definition** ("table") | `CustomObject` | `Tier_Rule__mdt` (with `__mdt`) | `objects/Tier_Rule__mdt/Tier_Rule__mdt.object-meta.xml` |
| **Records** ("rows") | `CustomMetadata` | `Tier_Rule.Gold` (no `__mdt`) | `customMetadata/Tier_Rule.Gold.md-meta.xml` |

**✅ CORRECT** — separate `<types>` blocks:
```xml
<types>
    <members>Tier_Rule__mdt</members>
    <name>CustomObject</name>
</types>
<types>
    <members>Tier_Rule.Gold</members>
    <members>Tier_Rule.Silver</members>
    <name>CustomMetadata</name>
</types>
```

**❌ INCORRECT** — nesting records inside the CustomObject block (will not deploy the records):
```xml
<types>
    <members>Tier_Rule__mdt</members>
    <members>Tier_Rule.Gold</members>     <!-- WRONG: not a CustomObject member -->
    <name>CustomObject</name>
</types>
```

**❌ INCORRECT** — using `*__mdt` suffix in the CustomMetadata block:
```xml
<types>
    <members>Tier_Rule__mdt.Gold</members>  <!-- WRONG: drop the __mdt -->
    <name>CustomMetadata</name>
</types>
```

When generating `package.xml` for a deploy that includes Custom Metadata Types, always emit two blocks. See `assets/package.xml` for the canonical commented template.

---

## Required Context to Gather First

Ask for or infer:
- target org alias and environment type
- deployment scope: source-dir, metadata list, or manifest
- whether this is validate-only, deploy, quick deploy, retrieve, or CI/CD guidance
- required test level and rollback expectations
- whether special metadata types are involved (Flow, permission sets, agents, packages)

Preflight checks:
```bash
sf --version
sf org list
sf org display --target-org <alias> --json
test -f sfdx-project.json
```

---

## Recommended Workflow

### 1. Preflight
Confirm auth, repo shape, package directories, and target scope.

### 2. Validate first
```bash
sf project deploy start --dry-run --source-dir force-app --target-org <alias> --wait 30 --json
```
Use manifest- or metadata-scoped validation when the change set is targeted.

### 3. If validation succeeds, offer the next safe workflow
After a successful validation, guide the user to the correct next action:
1. deploy now
2. assign permission sets
3. create test data via [handling-sf-data](../handling-sf-data/SKILL.md)
4. run tests / smoke checks
5. orchestrate multiple post-deploy steps in order

### 4. Deploy the smallest correct scope
```bash
# source-dir deploy
sf project deploy start --source-dir force-app --target-org <alias> --wait 30 --json

# manifest deploy
sf project deploy start --manifest manifest/package.xml --target-org <alias> --test-level RunLocalTests --wait 30 --json

# manifest deploy with Spring '26 relevant-test selection
sf project deploy start --manifest manifest/package.xml --target-org <alias> --test-level RunRelevantTests --wait 30 --json

# quick deploy after successful validation
sf project deploy quick --job-id <validation-job-id> --target-org <alias> --json
```

### 5. Verify
```bash
sf project deploy report --job-id <job-id> --target-org <alias> --json
```
Then verify tests, Flow state, permission assignments, and smoke-test behavior.

### 6. Report clearly
Summarize what deployed, what failed, what was skipped, and what the next safe action is.

Output template: [references/deployment-report-template.md](references/deployment-report-template.md)

---

## High-Signal Failure Patterns

| Error / symptom | Likely cause | Default fix direction |
|---|---|---|
| `FIELD_CUSTOM_VALIDATION_EXCEPTION` | validation rule or bad test data | adjust data or rule timing |
| `INVALID_CROSS_REFERENCE_KEY` | missing dependency | include referenced metadata first |
| `CANNOT_INSERT_UPDATE_ACTIVATE_ENTITY` | trigger / Flow / validation side effect | inspect automation stack and failing logic |
| tests fail during deploy | broken code or fragile tests | run targeted tests, fix root cause, revalidate |
| field/object not found in permset | wrong order | deploy objects/fields before permission sets |
| Flow invalid / version conflict | dependency or activation problem | deploy as Draft, verify, then activate |
| Custom Metadata records not deployed (or `Cannot find CustomObject member 'Foo.Bar'`) | records nested inside the `CustomObject` `<types>` block, or `__mdt` left on the member name | split into a separate `<types><name>CustomMetadata</name></types>` block; member format is `<TypeApiName>.<RecordDeveloperName>` (no `__mdt`) |

Full workflows: [references/orchestration.md](references/orchestration.md), [references/trigger-deployment-safety.md](references/trigger-deployment-safety.md)

---

## CI/CD Guidance

Default pipeline shape:
1. authenticate
2. validate repo / org state
3. static analysis
4. dry-run deploy
5. tests + coverage gates
6. deploy
7. verify + notify

- When org policy and release risk allow it, consider `--test-level RunRelevantTests` for Apex-heavy deployments.
- Pair this with modern Apex test annotations such as `@IsTest(testFor=...)` and `@IsTest(isCritical=true)` — see [generating-apex](../generating-apex/SKILL.md) for authoring guidance.

Static analysis now uses **Code Analyzer v5** (`sf code-analyzer`), not retired `sf scanner`.

Deep reference: [references/deployment-workflows.md](references/deployment-workflows.md)

---

## Agentforce Deployment Note

Use this skill to orchestrate **deployment/publish sequencing** around agents, but use the agent-specific skill for authoring decisions:
- [developing-agentforce](../developing-agentforce/SKILL.md) for `.agent` authoring, Agent Builder, Prompt Builder, and metadata config

For full agent DevOps details, including `Agent:` pseudo metadata, publish/activate, and sync-between-orgs, see:
- [references/agent-deployment-guide.md](references/agent-deployment-guide.md)

---

## Cross-Skill Integration

| Need | Delegate to | Reason |
|---|---|---|
| custom object creation | [generating-custom-object](../generating-custom-object/SKILL.md) | define objects before deploy |
| custom field creation | [generating-custom-field](../generating-custom-field/SKILL.md) | define fields before deploy |
| Apex authoring / fixes | [generating-apex](../generating-apex/SKILL.md) | code authoring and repair |
| Flow creation / repair | [generating-flow](../generating-flow/SKILL.md) | Flow authoring and activation guidance |
| test data or seed records | [handling-sf-data](../handling-sf-data/SKILL.md) | describe-first data setup and cleanup |
| Agent authoring and publish readiness | [developing-agentforce](../developing-agentforce/SKILL.md) | agent-specific correctness |

---

## Reference Map

### Start here
- [references/orchestration.md](references/orchestration.md)
- [references/deployment-workflows.md](references/deployment-workflows.md)
- [references/deployment-report-template.md](references/deployment-report-template.md)

### Specialized deployment safety
- [references/trigger-deployment-safety.md](references/trigger-deployment-safety.md)
- [references/agent-deployment-guide.md](references/agent-deployment-guide.md)
- [references/deploy.sh](references/deploy.sh)

### Asset templates
- [assets/package.xml](assets/package.xml) — manifest template covering common metadata types
- [assets/destructiveChanges.xml](assets/destructiveChanges.xml) — template for removing metadata from target orgs

---

## Score Guide

| Score | Meaning |
|---|---|
| 90+ | strong deployment plan and execution guidance |
| 75–89 | good deploy guidance with minor review items |
| 60–74 | partial coverage of deployment risk |
| < 60 | insufficient confidence; tighten plan before rollout |

---

## Completion Format

```text
Deployment goal: <validate / deploy / retrieve / pipeline>
Target org: <alias>
Scope: <source-dir / metadata / manifest>
Result: <passed / failed / partial>
Key findings: <errors, ordering, tests, skipped items>
Next step: <safe follow-up action>
```
