# Conventions — ADLC Toolkit (Salesforce edition)

## Code is markdown, not code

Every skill and agent is a markdown file. No TypeScript, no Python, no package.json at the toolkit level. Claude Code interprets the markdown at invocation time. This matters:

- **No build step**: edits take effect immediately via the symlink install
- **No test runner for skills**: "tests" are dogfooding — invoke the skill on a real REQ and see if it produces the expected artifacts
- **Linting is minimal**: markdown formatting, frontmatter validity, and bash syntax in `!`...`` macros (see `tools/lint-skills/`)

**Exceptions — `tools/` and `workflows/`:** the `tools/` directory may contain real executable code (e.g. `tools/lint-skills/` Python). Workflow scripts in `workflows/` are JS files run by Claude Code's Workflow primitive; they have their own node:test unit tests. Both are exempt from the markdown-only rule.

## Salesforce-specific conventions

- **CLI**: always use the modern `sf` CLI (v2). Never `sfdx` (deprecated).
- **MCP**: prefer `salesforcecli/mcp` MCP tools over Salesforce CLI commands when available.
- **Apex naming**: PascalCase for classes, camelCase for methods/variables, ALL_CAPS_SNAKE_CASE for enums.
- **Permission set naming**: `[AppPrefix]_[Component]_[AccessLevel]` (e.g., `SalesApp_Opportunity_Read`). AppPrefix is a 3–8 char project-scoped identifier declared in `.adlc/config.yml`.
- **Sharing keyword**: every Apex class must declare `with sharing` or `without sharing` explicitly.
- **AccessLevel**: every SOQL/DML statement must declare an explicit `AccessLevel` (USER_MODE preferred for user-context queries).
- **No `@future`**: use queueables with `System.Finalizer` instead.
- **No SeeAllData=true** in tests.
- **Named Credentials**: required for all callouts.
- **Coverage policy** (REQ-A): three-tier policy in `.adlc/config.yml` `salesforce.coverage` — `org_floor` (75 platform min), `org_target` (project floor, default 80), `class_floor` (per-changed-class in brownfield mode, default 75). Greenfield projects gate deploys on org-level coverage only; brownfield gates both org and per-changed-class. Meaningful assertions required regardless. Skills MUST read from config, never hardcode 75/80.
- **Frontend framework**: LWC is the default. The **multi-framework UI Bundles Beta** is opt-in via `salesforce.features.ui_bundles: true` in `.adlc/config.yml`. When the flag is on, skills assume the Beta is enabled in the target org and may scaffold React apps with `sf template generate ui-bundle -n <Name> --template reactbasic`. Bundle names follow the **internal/external** convention — `ReactInternalApp` for employee-/Lightning-Experience-facing surfaces, `ReactExternalApp` for portal-/Experience-Site-facing surfaces (or domain-prefixed variants like `OrdersInternalApp`). Immediately after scaffolding, run `cd uiBundles/<Name> && npm install`; before every deploy, run `npm run build` and then `sf project deploy start --source-dir uiBundles/<Name>` (no UI-bundle-specific deploy command exists).

The full set is in `.adlc/context/salesforce-rules.md`. Phase 4 (task-implementer) and Phase 5 (review panel) both source `partials/sf-quality-checklist.md`, which is generated from salesforce-rules.md and is the single source of truth.

## File and directory naming

- Skill directories: lowercase, single word or hyphenated (`spec`, `bugfix`, `template-drift`)
- Skill files: always `SKILL.md` (uppercase, singular) inside the skill directory
- Agent files: `agents/<agent-name>.md`, hyphenated lowercase
- Templates: `templates/<artifact>-template.md`
- IDs: `REQ-xxx` (zero-padded to 3 digits), `TASK-yyy`, `BUG-zzz`, `LESSON-nnn` — always uppercase prefix, always 3 digits minimum
- Slugs: lowercase kebab-case, ≤6 words, no dates, no bare numbers
- Salesforce metadata follows Salesforce-native naming (PascalCase API names for objects/fields, etc.) — those rules are owned by salesforce-rules.md, not this file.

## Frontmatter conventions

All artifact types use YAML frontmatter. Dates in ISO format (`YYYY-MM-DD`). Arrays use JSON inline syntax (`tags: [a, b, c]`). Status enum values are lowercase strings.

**Required vs optional** varies per template. Generally: `id`, `title`, `status`, `created` are required; everything else is optional. When adding new fields, prefer additive — do not rename existing fields without a migration plan.

## Ethos injection pattern

Every skill begins with:

```markdown
## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`
```

The partial itself emits the canonical fallback chain (consumer-project ETHOS.md first, then toolkit-root, then graceful "No ethos found" message). The two-level fallback at the call site (project `partials/` first, then global `~/.claude/skills/partials/`) ensures the macro still works in consumer projects that haven't re-run `/init` after the toolkit shipped the partial.

## Context loading pattern

Skills load context via `!bash` macros under a `## Context` section. Use the same fallback chain: prefer consumer-project `.adlc/...`, fall back to `~/.claude/skills/...`. Example:

```markdown
- Conventions: !`cat .adlc/context/conventions.md 2>/dev/null || echo "No conventions found"`
- Salesforce rules: !`cat .adlc/context/salesforce-rules.md 2>/dev/null || echo "No salesforce-rules found"`
```

Never hardcode paths; always allow the skill to degrade gracefully when a file is absent.

For shared multi-line snippets that would otherwise duplicate across many SKILL.md files, extract a POSIX shell partial under `partials/<name>.sh` and source it from each call site (see "Ethos injection pattern" above and the architecture.md "Partials" subsection).

## Prerequisites block

Every skill that depends on the `.adlc/` scaffold must have a `## Prerequisites` section that stops with a clear "run `/init` first" message if required files are missing. Do not silently produce broken output when context is absent.

## Bash in skills

- Keep bash minimal — prefer Claude's own tool calls (Read, Grep, Glob, Edit, Write) over shell
- Bash is fine for deterministic operations: counter increments, directory creation, git/gh/sf commands, file globbing
- **POSIX-only**: no GNU-specific flags. Use `grep -oE` (not `-oP`), use `mkdir` locks (not `flock`), use `sed 's/old/new/'` not `-i ''` on macOS directly — prefer `perl` for in-place edits or write a temp file
- Quote file paths with spaces: `"$path"`
- Avoid `cd` — prefer absolute paths so commands work from any working directory

**Fenced blocks do not share shell state across steps.** Each ```sh fenced block in a SKILL.md may be an independent shell invocation — shell functions and non-exported variables defined in one fenced block are NOT visible in another. Therefore a shared shell **function** MUST be sourced from a `partials/*.sh` at *each* call site, in the **same fenced block as the invocation**, and MUST NEVER be defined in one fenced block and invoked from another. This is enforced structurally by the `tools/lint-skills` `cross-fence-fn` check.

## Agent dispatch patterns

- **Parallel review**: dispatch the 6-member panel in a single message (`reflector`, `correctness-reviewer`, `quality-reviewer`, `architecture-reviewer`, `test-auditor`, `security-auditor`). Read-only mandate: every agent must be told "Report findings only. Do not apply fixes."
- **Parallel implementation**: `task-implementer` agents dispatched one per independent task. Group into dependency tiers.
- **Subagent mode**: when a skill runs inside a subagent (e.g., via `/sprint`'s `pipeline-runner`), do NOT dispatch further subagents. Execute sequentially in-context instead.
- **sf-skills**: consumed as **rubrics**, not as separate agents. Reviewers and the implementer load the relevant rubric file by file glob (e.g. `.cls` → sf-apex 150-pt rubric).

## Pipeline state

Skills that span multiple phases (`/proceed`) write a `pipeline-state.json` next to the REQ spec. This lets a long-running pipeline resume from interruption without replaying phases. Every phase update writes the state file atomically.

## Commits and branches

- Branch naming: `feat/REQ-xxx-short-description` for features, `fix/bug-xxx-short-description` for bugs
- Commit message format: `<type>(<scope>): <description> [TASK-xxx]` — types are `feat`, `fix`, `refactor`, `docs`, `test`, `chore`
- The TASK-xxx (or REQ-xxx) trailer is required for work tracked through the pipeline
- Co-author trailer is added by Claude Code automatically when committing on behalf of the user

## Models policy

- Only `sonnet` and `opus` are permitted in any agent's `model:` frontmatter. `haiku` and any third-party model are out of scope.
- Per-agent picks live in `MODEL_ASSIGNMENTS.md` at the repo root. Update both files in lockstep.

## What NOT to do

- **Don't create new skill directories casually**: each new skill is a commitment to maintain. Prefer extending an existing skill unless the new responsibility is genuinely orthogonal.
- **Don't bypass ethos**: the five principles (especially #4 Verify, Don't Trust and #5 Process Is Not Optional) exist because shortcuts silently fail.
- **Don't duplicate context loading logic**: if the same bash macro appears in three or more skills, extract it to `partials/<name>.sh` and source it from each call site.
- **Don't hardcode project-specific paths or values**: skills must work for any Salesforce consumer project. AppPrefix, API version, org alias, Agentforce variant — all read from `.adlc/config.yml`, never hardcoded.
- **Don't edit `templates/` without considering downstream**: consumer projects that ran `/init` got a copy of the templates. Template changes propagate via `/template-drift` detection, not auto-update.
- **Don't introduce a third-party model or delegation tool**: the toolkit explicitly excludes Kimi K2.5 / Moonshot AI / any non-Anthropic model. Reasoning stays on Sonnet/Opus.

## Testing changes

Because this is a symlink-install, there is no staging layer. To validate a skill change:

1. Commit the change in this repo
2. Open a Claude Code session in a Salesforce consumer project
3. Invoke the changed skill on a real or synthetic REQ
4. Verify the artifacts it produces match the intended behavior
5. Revert if it breaks

For workflow scripts: `node --test workflows/tests/*.test.js` from the toolkit root. For lint-skills: `pytest tools/lint-skills/tests/ -q`.
