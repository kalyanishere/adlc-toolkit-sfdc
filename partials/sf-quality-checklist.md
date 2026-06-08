# Salesforce quality checklist

This is the machine-consumable companion to `.adlc/context/salesforce-rules.md`. The implementer (Phase 4) and the review panel (Phase 5) source it. **The rules document is still the source of truth**; this file is the sourced checklist that points back to it.

## How skills load this

```sh
. .adlc/partials/sf-quality-checklist.md 2>/dev/null || . ~/.claude/skills/partials/sf-quality-checklist.md
```

(This file is plain markdown — sourcing it is a no-op in shell. The two-level fallback makes it discoverable from a consumer-project worktree OR the toolkit symlink. Skills `Read` it, then attach the relevant sections to the agent prompt.)

## Section reference

| Section | Where in salesforce-rules.md | Static-checkable? (sf-lint) |
|---|---|---|
| [CLI & metadata files](#cli--metadata-files) | `# General Salesforce Development Requirements`, `## Salesforce Platform Constraints` | partial |
| [Apex baseline](#apex-baseline) | `## Apex Triggers Requirements`, `## General Requirements` (Apex) | yes |
| [Governor limits & SOQL](#governor-limits--soql) | `## Governor Limits Compliance Requirements`, `## SOQL Optimization Requirements` | yes (no SOQL/DML in loops, LIMIT, no SELECT *) |
| [Security & access control](#security--access-control) | `## Security & Access Control Requirements` | yes (sharing keyword, AccessLevel, no @future) |
| [Permission sets](#permission-sets) | `## Permissions Requirements`, `## Mandatory Permission Documentation` | yes (naming format, anti-patterns) |
| [Code organization & docs](#code-organization--docs) | `## Code Organization & Structure Requirements`, `## Code Documentation Requirements` | partial (naming) |
| [Required patterns](#required-patterns) | `## Required Patterns` (Apex) | no — design guidance |
| [Testing](#testing) | `## Unit Testing Requirements`, `## Test Data Management Requirements` | yes (no SeeAllData=true, ≥75% coverage) |
| [LWC](#lwc) | `# Lightning Web Components (LWC) Requirements` | partial (handler naming, decorators) |
| [Integration & Platform Events](#integration--platform-events) | `## REST/SOAP Integration Requirements`, `## Platform Events Requirements` | yes (Named Credentials) |
| [Agentforce & Agent Script](#agentforce--agent-script) | `#Agentforce & Agent Script Standards` | yes (deploy order, API ≥ 66.0, @InvocableVariable wrappers) |
| [Prohibited practices](#prohibited-practices) | `## Prohibited Practices` | yes (entire section) |

The "Static-checkable?" column tells `tools/sf-lint/` which subset to mechanize. Anything `yes` or `partial` lives in the linter; design guidance (`no`) is review-only.

---

## CLI & metadata files

- Use `sf` v2 only — never `sfdx`.
- Every new SObject has a corresponding `<Object>.object-meta.xml`.
- Every new Apex class has a corresponding `<Class>.cls-meta.xml`.
- Every new trigger has a corresponding `<Trigger>.trigger-meta.xml`.
- API version: ≥ project floor declared in `.adlc/config.yml` `salesforce.api_version` (≥ 66.0 when Agentforce is in scope).
- Prefer `salesforcecli/mcp` MCP tools over raw `sf` invocations when available.

## Apex baseline

- **Sharing keyword** (`with sharing` / `without sharing`) explicit on every Apex class — no implicit defaults.
- **AccessLevel** explicit on every SOQL/DML — `WITH USER_MODE` for user-context queries, `Database.<dml>(records, AccessLevel.USER_MODE)` for DML.
- **No `@future`** anywhere. Use queueables with `System.Finalizer` instead.
- **One Trigger Per Object**, with logic delegated to a handler class. Static-boolean recursion guard only when truly necessary.
- **Bulkify everything** — never SOQL/DML inside loops; iterate over collections.
- **Database methods** for DML when partial-success / detailed errors matter (`Database.insert(records, false)` returns `Database.SaveResult[]`).
- **Return Early** pattern; avoid deep nesting.
- **ApexDoc** comments on classes and public methods (the *why*, not the *what*).
- **Enums** over string constants — ALL_CAPS_SNAKE_CASE values.
- **Invocable Apex** when callable from Flow: `@InvocableMethod` with `@InvocableVariable` wrapper classes; never bare `List<T>`.
- **Naming**: PascalCase classes, camelCase methods/variables, ALL_CAPS_SNAKE_CASE enums.

## Governor limits & SOQL

- **No SOQL in loops** (`[SELECT ...]` or `Database.query` inside a `for` body).
- **No DML in loops** (`insert/update/upsert/delete/undelete/merge` inside a `for` body).
- ≤ 100 SOQL queries / 150 DML statements per transaction.
- **No `SELECT *`** — list every field explicitly.
- **Indexed fields** in WHERE clauses when filtering.
- **`LIMIT` clauses** for unbounded inputs.
- **`WITH USER_MODE`** for user-context queries; **`WITH SYSTEM_MODE`** only when explicitly required (and justified in code comment).
- `Database.Stateful` only when the batch genuinely needs cross-execution state.

## Security & access control

- Database operations run in user mode (`AccessLevel.USER_MODE`).
- FLS check before reading/updating sensitive fields when sharing alone is insufficient.
- Sharing rules and org-wide defaults respected.
- `with sharing` keyword explicit (default for most classes).
- User permissions validated before mutations.
- User inputs sanitized — bind variables (`:variable`) in SOQL, never string concatenation.

## Permission sets

- **At least one permission set** per new feature — for Apex classes, custom objects/fields, LWC, Visualforce, custom tabs, Flow definitions, custom permissions.
- **One permission set per object per access level** (one for Read, separate one for Write/Full).
- **Separate permission sets** per Apex class group; per major feature.
- **≤ 10 different object permissions** per set.
- **Naming format**: `[AppPrefix]_[Component]_[AccessLevel]`
  - `AppPrefix`: 3–8 character PascalCase identifier from `.adlc/config.yml` `salesforce.app_prefix`
  - `Component`: PascalCase descriptive component name
  - `AccessLevel`: one of `Read`, `Write`, `Full`, `Execute`, `Admin`
  - Examples: `SalesApp_Opportunity_Read`, `OrderMgmt_Product_Write`, `IntegAPI_DataSync_Execute`
- **Label** human-readable; **Description** explains purpose, scope, intended persona.
- **License** appropriate user license type.

### Anti-patterns (always block)

- `View All Data` / `Modify All Data` granted in functional permission sets.
- **Any `<fieldPermissions>` block in a permission set** — framework policy is object-level access only (`viewAllFields=true` / `editAllFields=true` on `<objectPermissions>`). Per-field FLS is the #1 cause of deploy failures.
- `<objectPermissions>` missing `viewAllFields=true` (or missing `editAllFields=true` when `allowEdit=true`).
- **Read + Delete** combined on the same object in one set.
- Sensitive data bundled with general feature access (split into a dedicated set with its own assignment policy; never gate via per-field FLS).

### Permission set groups

Create when **any** of:
- Application has > 3 related permission sets
- Users need a combined bundle for their role
- Clear user persona/role exists

### Mandatory `Permissions.md`

Every feature touching metadata generates a `Permissions.md` (template at `templates/permissions-template.md`):
- Lists every new permission set with purpose
- **Dependency mapping** (which set unlocks which Apex/object/field/flow)
- **User role assignment matrix** (persona → set → environment)
- **Testing validation checklist** (anti-patterns confirmed clear)

## Code organization & docs

- PascalCase classes, camelCase methods/variables, ALL_CAPS_SNAKE_CASE enums.
- Descriptive, business-meaningful names.
- Newspaper rule: methods ordered as referenced (callers above callees). Alphabetize/arrange dependencies; separate instance vs static fields with blank lines.
- Less code is better; the second-best line of code is easy to read.
- Comments explain key design decisions; don't explain the obvious.
- ApexDoc on classes and public methods — **≤ 3 lines of prose**, signature/purpose only. Link the spec (`.adlc/specs/REQ-xxx-*/spec.md`) or architecture doc for deeper rationale rather than embedding it. No multi-paragraph headers, no walkthroughs, no usage tutorials inline.
- Inline comments only for non-obvious *why* (workaround, invariant, hidden constraint) — never for what the next line literally does.
- Up-to-date README files for each significant component (long-form prose lives here, not in code headers).

## Required patterns

- **Builder pattern** for complex object construction (multiple optional fields).
- **Factory pattern** for object creation when sub-types are involved.
- **Dependency Injection** for testability — services receive collaborators via constructor or interface.
- **MVC** in Lightning components — view/binding in LWC, business logic in Apex services.
- **Command pattern** for complex business operations.

## Testing

- **≥ 75% Apex code coverage** at the org level (Salesforce platform requirement); aim ≥ 80% per project policy.
- **Meaningful assertions** — no vacuous `Assert.areEqual(true, true)`.
- **`Test.startTest()` / `Test.stopTest()`** around the unit under test (fresh governor-limit pool).
- **`@TestSetup`** for shared fixtures (when ≥2 methods need them).
- **`System.runAs(<user>)`** for sharing/FLS/permission-context branches.
- **Mock callouts** with `Test.setMock(HttpCalloutMock.class, mock)` — never hit real endpoints.
- **No `SeeAllData=true`** — ever.
- **Bulk-trigger tests** — 200-record insert/update/delete that exercises the trigger path.
- **`Test.loadData()`** for large datasets; otherwise construct fixtures inline.
- **Test isolation** — no inter-test dependencies, no org-state coupling.

## LWC

- Reusable, single-purpose components.
- `@wire`/`@track`/`@api` decorators correctly applied.
- SLDS utility classes for spacing (`slds-m-*`, `slds-p-*`); CSS minimal.
- Lightning base components preferred over manual SLDS.
- `lightning-record-edit-form` for record creation/updates.
- `lightning-navigation` for navigation between components.
- `lightning__FlowScreen` target for components used inside Flow screens.
- Event handlers prefixed `handle…` (`handleClick`, `handleChange`).
- `if:true` / `if:false` for conditional rendering.
- `for:each` with unique `key` attribute for lists.
- JSDoc on public methods — **≤ 3 lines of prose**, signature/purpose only; link the spec/architecture doc for deeper context. No multi-paragraph descriptions.
- No `console.log` — use platform logger.
- Computed UI state via JavaScript getters (e.g., `get isButtonDisabled()`).
- Async/await for server calls; `refreshApex` for data refresh.
- CSS variables for themeable elements; CSS organized by component section.

## Integration & Platform Events

- **Named Credentials** for every callout. No hardcoded URLs/tokens. No bare `Http.send` to a literal URL.
- Timeout + retry mechanism on every callout.
- Appropriate HTTP status codes; structured error handling.
- **Bulk operations** for data synchronization — single-record sync only when bulk is impossible.
- Efficient JSON / XML serialization patterns (`JSON.deserialize` to typed wrappers, not Map<String, Object>).
- Integration activities logged for debugging (with PII/token redaction).
- **Platform Events** for loose coupling. Delivery mode chosen per commit semantics (`Publish Immediately` vs `Publish After Commit`). Subscriber error handling via `EventBus.TriggerContext`. Volume × governor limits considered.

## Agentforce & Agent Script

- **AgentforceEmployeeAgent** for internal-facing agents — **`default_agent_user` MUST be omitted**.
- **AgentforceServiceAgent** requires a dedicated **Einstein Agent User** + system permission set.
- **Agent Script `apex://ClassName`** targets work directly — `GenAiFunction` metadata is **NOT** required for Agent Script bundles (only needed for Agent Builder / GenAiPlannerBundle paths).
- Topic descriptions: **scenario-based, specific, non-overlapping**.
- **Business rules and ground truth in Flow or Apex** targets — never in free-form prompt prose.
- **No fabricated tracking, order, refund, or inventory data** in reasoning instructions.
- **Deploy order**: fields/metadata → Apex → Flow → GenAiPromptTemplate / GenAiFunction / GenAiPlugin → publish → `sf agent activate`.
- **`@InvocableVariable` wrapper classes** (with named fields) MUST be used. Bare `List<T>` parameters are incompatible with Agent Script actions.
- API version ≥ 66.0 for all Agentforce / AI metadata.

## Prohibited practices

These are always blocking — no exception, no rationale required.

- ❌ Hardcoded IDs (15- or 18-char Salesforce IDs in source) or hardcoded URLs.
- ❌ SOQL/DML inside loops.
- ❌ `System.debug()` in production code without log-level guard.
- ❌ Recursive triggers (no static-boolean guard when needed).
- ❌ Apex class without explicit `with sharing` / `without sharing` keyword.
- ❌ SOQL/DML without explicit `AccessLevel`.
- ❌ `@future` methods. Use queueables + `System.Finalizer`.
- ❌ `SeeAllData=true` in tests.
- ❌ `View All Data` / `Modify All Data` in functional permission sets.
- ❌ Read + Delete combined in the same permission set.
