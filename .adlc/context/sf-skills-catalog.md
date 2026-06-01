# sf-skills catalog

The 60 vendored Salesforce skills (forcedotcom/afv-library, pinned at `302d11cc6a76bc1d7639ee69b89c6944b7f3f8fa`, see `skills/sf/VENDORED.md`) grouped by ADLC phase, with a **file-glob → skill** dispatch table that the `task-implementer` and the Phase 5 review panel use at runtime.

The skills are **rubrics**, not separately-dispatched agents. Each Phase 5 reviewer (correctness / quality / architecture / test-coverage / security) and the Phase 4 implementer load the relevant rubric by file glob — see the dispatch table below. The catalog is the single source of truth for that mapping.

## Phase mapping

### Requirements (Phase 1) — grounding & estimation

| Skill | Use when |
|---|---|
| `fetching-salesforce-docs` | Need authoritative grounding from developer.salesforce.com / help.salesforce.com / lightningdesignsystem.com / architect & admin docs. |
| `applying-cms-brand` | Brand voice/tone/style is in scope (Experience Cloud, Marketing assets, Agentforce persona). |

### Design (Phase 2 — Architect) — modeling & metadata shape

| Skill | Use when |
|---|---|
| `generating-custom-object` | Designing/creating a new SObject (`.object-meta.xml`). |
| `generating-custom-field` | Adding fields (`.field-meta.xml`). |
| `generating-custom-application` | Adding a Lightning App. |
| `generating-custom-tab` | Adding a custom tab. |
| `generating-custom-lightning-type` | Custom Lightning data types. |
| `generating-validation-rule` | Validation rules (`.validationRule-meta.xml`). |
| `generating-flexipage` | Lightning page composition (`.flexipage-meta.xml`). |
| `generating-list-view` | List view config (`.listView-meta.xml`). |
| `generating-mermaid-diagrams` | Architecture/sequence/ERD diagrams (Mermaid). |
| `generating-visual-diagrams` | PNG/SVG mockups, wireframes. |
| `configuring-connected-apps` | OAuth flows, JWT bearer, External Client Apps (`.connectedApp-meta.xml` / `.eca-meta.xml`). |
| `building-sf-integrations` | Named Credentials, External Services, REST/SOAP callouts, Platform Events, CDC. |
| `modeling-omnistudio-epc-catalog` | Industries CME EPC product modeling (Product2, AttributeAssignment, ProductChildItem, EPC DataPacks). |
| `getting-datacloud-schema` | Inspecting Data Cloud DLO/DMO/relationship metadata before designing. |

### Build (Phase 4 — Implement) — code & metadata generation

| Skill | Use when |
|---|---|
| `generating-apex` | Apex classes (.cls), triggers (.trigger), service/selector/domain/batch/queueable/schedulable/invocable/REST resource. |
| `generating-flow` | Record-triggered, screen, autolaunched, scheduled, platform-event flows (`.flow-meta.xml`). |
| `generating-lwc-components` | LWC bundles (lwc/**: .js, .html, .css, .js-meta.xml). |
| `generating-lightning-app` | Lightning Application bundle. |
| `generating-permission-set` | Permission set generation (`.permissionset-meta.xml`). |
| `querying-soql` | SOQL/SOSL authoring, optimization, query-plan analysis, NL→query. |
| `handling-sf-data` | Record CRUD, bulk import/export, sf data CLI, Apex data factory patterns. |
| `developing-agentforce` | Agent Script (.agent), Builder metadata (GenAiPlugin, GenAiFunction, GenAiPromptTemplate). |
| `developing-datacloud-code-extension` | Data Cloud code extensions. |
| `connecting-datacloud` | Data Cloud Connect phase: connectors, source-object setup. |
| `preparing-datacloud` | Data Cloud Prepare: data streams, DLOs, transforms, Document AI. |
| `harmonizing-datacloud` | Data Cloud Harmonize: DMOs, mappings, identity resolution, data graphs. |
| `segmenting-datacloud` | Data Cloud Segment: audiences, calculated insights, segment SQL. |
| `orchestrating-datacloud` | Multi-step Data Cloud pipelines spanning connect → prepare → harmonize → segment → act → retrieve. |
| `building-omnistudio-omniscript` | OmniScript step-based guided experiences. |
| `building-omnistudio-flexcard` | OmniStudio FlexCard at-a-glance UI cards. |
| `building-omnistudio-integration-procedure` | OmniStudio Integration Procedure server-side orchestration. |
| `building-omnistudio-datamapper` | OmniStudio Data Mapper (formerly DataRaptor) Extract/Transform/Load/Turbo Extract. |
| `building-omnistudio-callable-apex` | Industries Common Core Apex callables (System.Callable). |
| `building-ui-bundle-app` | UI Bundle React/SPA scaffolding. |
| `building-ui-bundle-frontend` | UI Bundle frontend logic. |
| `generating-ui-bundle-features` | UI Bundle feature generation. |
| `generating-ui-bundle-metadata` | UI Bundle metadata. |
| `generating-ui-bundle-site` | UI Bundle Experience Site. |
| `implementing-ui-bundle-agentforce-conversation-client` | UI Bundle Agentforce conversation client wiring. |
| `implementing-ui-bundle-file-upload` | UI Bundle file upload patterns. |
| `using-ui-bundle-salesforce-data` | UI Bundle ↔ Salesforce data calls. |
| `creating-b2b-commerce-store` | B2B Commerce store creation. |
| `integrating-b2b-commerce-open-code-components` | B2B Commerce open-code components. |
| `searching-media` | CMS / managed content search & retrieval. |
| `uplifting-components-to-slds2` | Migrating existing LWC to SLDS 2 + dark mode + a11y. |

### Test (Phase 5 — Test-coverage reviewer) — verification

| Skill | Use when |
|---|---|
| `generating-apex-test` | Authoring Apex test classes (`*Test.cls` / `*_Test.cls`). |
| `running-apex-tests` | Executing tests, coverage analysis, structured fix-loop. |
| `testing-agentforce` | Multi-turn conversation validation, sf agent test specs, topic/action coverage. |

### Review (Phase 5 — quality / architecture / security) — analysis

| Skill | Use when |
|---|---|
| `running-code-analyzer` | Salesforce Code Analyzer (graph engine, sfca) — static analysis baseline. |
| `analyzing-omnistudio-dependencies` | OmniStudio cross-component dependency mapping, namespace detection, BFS impact analysis. |
| `debugging-apex-logs` | Debug log analysis: governor limits, stack traces, slow queries, heap/CPU pressure. |
| `observing-agentforce` | STDM parquet trace extraction & Polars analysis of Agentforce sessions. |

### Deploy (Phase 7–8 — Ship) — promotion & rollout

| Skill | Use when |
|---|---|
| `deploying-metadata` | sf project deploy validate / start, manifest-based deploys, scratch-org/sandbox management. |
| `deploying-omnistudio-datapacks` | Vlocity Build packDeploy/packExport/packGetDiffs for OmniStudio DataPacks. |
| `deploying-ui-bundle` | UI Bundle deployment. |
| `activating-datacloud` | Data Cloud Act: activations, activation targets, data actions. |
| `switching-org` | sf CLI org alias switching (sandbox ↔ staging ↔ prod). |

### Operate (Phase post-deploy) — runtime introspection

| Skill | Use when |
|---|---|
| `retrieving-datacloud` | Data Cloud SQL queries (sync/paginated/async), describe, vector and hybrid search. |

## File-glob → rubric dispatch

The `task-implementer` (Phase 4) and the Phase 5 review panel load the matching rubric whenever a file matching the glob is in the change set. Multiple matches: load each. The router skill at `skills/sf-router/SKILL.md` is the single authoritative implementation of this table.

| File-glob | Build-time rubric (task-implementer) | Review-time rubrics (Phase 5 reviewers) |
|---|---|---|
| `**/*.cls` (excluding `*Test.cls`) | generating-apex | generating-apex (quality), debugging-apex-logs (correctness), running-code-analyzer (architecture), generating-permission-set (security context) |
| `**/*Test.cls`, `**/*_Test.cls` | generating-apex-test | generating-apex-test (test-coverage), running-apex-tests (test-coverage) |
| `**/*.trigger` | generating-apex | generating-apex (quality + correctness), running-code-analyzer (architecture) |
| `**/lwc/**/*.{js,html,css,js-meta.xml}` | generating-lwc-components, uplifting-components-to-slds2 | generating-lwc-components (quality + architecture) |
| `**/*.flow-meta.xml` | generating-flow | generating-flow (quality + correctness) |
| `**/*.{soql,sosl}` or embedded SOQL strings | querying-soql | querying-soql (correctness + quality) |
| `**/*.object-meta.xml`, `**/*.field-meta.xml` | generating-custom-object, generating-custom-field | building-sf-integrations (architecture) |
| `**/*.permissionset-meta.xml`, `**/*.permissionsetgroup-meta.xml` | generating-permission-set | generating-permission-set (security) |
| `**/*.connectedApp-meta.xml`, `**/*.eca-meta.xml` | configuring-connected-apps | configuring-connected-apps (security) |
| `**/*.namedCredential-meta.xml`, `**/*.externalService-meta.xml` | building-sf-integrations | building-sf-integrations (architecture + security) |
| `**/*.agent`, `**/agentTests/**` | developing-agentforce, testing-agentforce | testing-agentforce (test-coverage), observing-agentforce (architecture) |
| `**/*.{genAiFunction,genAiPlugin,genAiPromptTemplate}-meta.xml` | developing-agentforce | developing-agentforce (architecture) |
| OmniStudio `.omniScript` / `.flexCard` / IP / DataMapper bundles | building-omnistudio-* (matching kind) | analyzing-omnistudio-dependencies (architecture), building-omnistudio-* (quality) |
| Industries CME EPC `Product2` / `AttributeAssignment` / EPC DataPack JSON | modeling-omnistudio-epc-catalog | modeling-omnistudio-epc-catalog (architecture) |
| Data Cloud DLO/DMO/data stream/segment metadata | preparing-/harmonizing-/segmenting-datacloud (matching phase) | orchestrating-datacloud (architecture) |
| `**/*.flexipage-meta.xml`, `**/*.listView-meta.xml`, `**/*.validationRule-meta.xml` | matching `generating-*` | generating-* (quality) |
| UI Bundle (`ui-bundle/**`, React/SPA scaffolding) | building-ui-bundle-* | building-ui-bundle-* (quality + architecture) |
| B2B Commerce store / OCC components | creating-b2b-commerce-store, integrating-b2b-commerce-open-code-components | matching skill (quality) |

When **no** glob matches a touched file, the reviewer falls back to the salesforce-rules.md baseline from `partials/sf-quality-checklist.md` (Batch 7 introduces that partial).

## Skills consumed at every Phase

These are reference / always-on skills that any phase may invoke regardless of the change set:

- `fetching-salesforce-docs` — any phase needing official-doc grounding
- `running-code-analyzer` — Phase 5 architecture reviewer always runs this when the project has SF Code Analyzer configured
- `switching-org` — invoked by `/canary` (sandbox→staging→prod) and `/wrapup` (deploy)

## How agents reference this catalog

Reviewer agent prompts include this stub:

```
Touched files in the change set:
  - <path1>
  - <path2>
  ...

Per .adlc/context/sf-skills-catalog.md, load the rubrics matching these globs:
  - <skill A> for <glob A>
  - <skill B> for <glob B>

Each rubric lives at skills/sf/<skill>/SKILL.md. Read it before evaluating findings.
```

That stub is built mechanically by the `skills/sf-router/SKILL.md` orchestrator at dispatch time so individual reviewer agents do not need to know the dispatch table — they only need to read the rubrics handed to them.
