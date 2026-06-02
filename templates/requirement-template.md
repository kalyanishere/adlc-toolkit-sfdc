---
id: XYZ-REQ-001       # `<project.shortname>-REQ-NNN` from .adlc/config.yml; allocated by /spec Step 2 via partials/id-counter.sh
title: "Feature Title"
status: draft
deployable: true
complexity: small   # trivial | small | medium | large — drives /proceed phase shape (REQ-C)
created: YYYY-MM-DD
updated: YYYY-MM-DD
component: ""       # narrow area, e.g., "API/auth", "iOS/SwiftUI", "adlc/spec"
domain: ""          # broad area, e.g., "auth", "payments", "ui"
stack: []           # tech layers touched, e.g., ["express", "firestore"]
concerns: []        # cross-cutting dimensions, e.g., ["security", "performance", "a11y"]
tags: []            # free-form keywords, e.g., ["password-reset", "tokens"]
---

<!--
  complexity tiers (REQ-C):
    trivial — single-file metadata change, no Apex, no architectural decisions
              (e.g., picklist value, layout edit, perm-set toggle).
              /proceed: skip validate gates, no architect fan-out, no implementer
              agent, reflect-only review, sandbox-only canary.
    small   — ≤3 files, no new pattern (e.g., 1 LWC + 1 Apex controller, single
              perm-set, 1 Flow). /proceed: inline architect, implementer per
              task, 2-agent review (reflect + quality), sandbox+staging canary.
    medium  — 4-10 files OR introduces a new pattern (new trigger handler,
              new Named Credential, new sObject). /proceed: full pipeline.
    large   — >10 files OR cross-domain (Data Cloud + Apex + Agentforce,
              multi-repo). /proceed: full pipeline + ADR capture.
-->


## Description

What the feature does and why.

## Frontend framework

_Pick one when the feature has a UI surface. Skills branch on this in Phase 4. The React paths require `salesforce.features.ui_bundles: true` in `.adlc/config.yml` (multi-framework UI Bundles Beta)._

- [ ] **LWC** (default) — record page, App Builder, Flow screen, or base-component-heavy work
- [ ] **React internal** (`ReactInternalApp`) — standalone SPA inside Lightning Experience for employees
- [ ] **React external** (`ReactExternalApp`) — standalone SPA served from an Experience Site / portal / public

## System Model

_Define the structured data model for this feature. Remove sections that don't apply._

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| [EntityName] | [field] | [string/number/boolean/timestamp] | [required, unique, max length, etc.] |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| [event_name] | [What causes it] | [Key data included] |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| [action_name] | [authenticated, owner, admin, etc.] |

## Business Rules

_Explicit, testable constraints governing this feature's behavior._

- [ ] BR-1: [Rule statement — e.g., "Only item owner can delete wardrobe items"]
- [ ] BR-2: [Rule statement]

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2

## External Dependencies

- None

## Assumptions

- None

## Open Questions

- [ ] Open question 1

## Out of Scope

- Items explicitly excluded
