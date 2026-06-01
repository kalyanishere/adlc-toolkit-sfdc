# Model assignments

Single registry of which model each agent runs on. Edit `agents/<name>.md` frontmatter to change a pick; mirror the change here so the registry stays auditable.

Only `sonnet` and `opus` are permitted. `haiku` and any third-party model (Kimi K2.5 etc.) are out of scope for this toolkit by policy.

| Agent | Model | Phase | Role |
|---|---|---|---|
| `architecture-mapper`  | sonnet | 1–2 (discovery) | Maps SF artifact graph touched by a proposed change (SObjects, Apex, Flows, LWC, perm sets, Named Credentials, Platform Events, Agentforce topics). |
| `feature-tracer`       | sonnet | 1–2 (discovery) | Finds analogous Apex/Flow/LWC/permission-set patterns in the project; reads `.adlc/knowledge/lessons/` and prior REQs. |
| `integration-explorer` | sonnet | 1–2 (discovery) | Catalogues Named Credentials, External Services, REST/SOAP callouts, Platform Events, CDC, Connected Apps that a change touches. |
| `task-implementer`     | opus   | 4 (build)       | Phase 4 worker. Loads `partials/sf-quality-checklist.md` + relevant sf-skill rubric per artifact type. Enforces salesforce-rules.md inline. |
| `pipeline-runner`      | opus   | orchestrator    | Runs the complete `/proceed` pipeline sequentially in subagent mode. |
| `correctness-reviewer` | opus   | 5 (review)      | Logic, race, security adversarial pass. SF flavor: trigger recursion, governor-limit blast radius, mixed DML, async finalizer correctness. |
| `quality-reviewer`     | sonnet | 5 (review)      | Convention + code quality. Loads sf-apex 150-pt / sf-lwc 165-pt / sf-flow 110-pt / sf-soql 100-pt rubrics by file glob. |
| `architecture-reviewer`| sonnet | 5 (review)      | Architectural compliance. SF flavor: One-Trigger-Per-Object, handler/service separation, IP/OmniScript composition, Data Cloud DLO/DMO layering. |
| `test-auditor`         | sonnet | 5 (review)      | Test coverage + assertion quality. Loads sf-testing 120-pt + sf-ai-agentforce-testing rubrics. |
| `security-auditor`     | opus   | 5 (review)      | FLS, USER_MODE, sharing keyword, no @future, Named Credentials, perm-set naming `[AppPrefix]_[Component]_[AccessLevel]`, OAuth/Connected App anti-patterns. |
| `reflector`            | opus   | 5 (self-review) | Walks salesforce-rules checklist + touched-artifact's sf-skill rubric end-to-end before formal review fans out. |

## Distribution

- **Opus (5):** task-implementer, pipeline-runner, correctness-reviewer, security-auditor, reflector
- **Sonnet (6):** architecture-mapper, feature-tracer, integration-explorer, architecture-reviewer, quality-reviewer, test-auditor

## How to change a pick

1. Edit `agents/<name>.md` and update the `model:` frontmatter line.
2. Update the row in the table above.
3. Run `python3 tools/lint-skills/check.py --root .` to confirm no agent has an unresolved `model:` (any string outside `sonnet`/`opus` is a project policy violation; the linter will be taught to enforce this in a later batch).
