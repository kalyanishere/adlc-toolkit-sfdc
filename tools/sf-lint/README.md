# tools/sf-lint — Salesforce-rules static checker

A small offline linter that catches the **static-checkable subset** of `partials/sf-quality-checklist.md` (which is the machine-readable companion to `.adlc/context/salesforce-rules.md`). It is NOT a general Apex linter, NOT a replacement for `sf scanner run`, and NOT a substitute for the Phase 5 review panel.

The agents (correctness-reviewer, quality-reviewer, security-auditor) own the semantic checks (newspaper rule, Builder pattern, sharing-vs-FLS judgment, ApexDoc completeness). This linter owns the rules that mechanize cleanly: presence of explicit keywords, anti-pattern strings, naming format, no-go literals.

## What it checks

1. **`sharing-keyword`** — Apex top-level class declared without `with sharing` / `without sharing` / `inherited sharing`.
2. **`access-level`** — SOQL or DML statement without explicit `WITH USER_MODE`/`WITH SYSTEM_MODE` (SOQL) or `AccessLevel.USER_MODE`/`SYSTEM_MODE` (DML). Test classes are exempt.
3. **`no-future`** — `@future` annotation anywhere (use queueables + `System.Finalizer` instead).
4. **`no-seealldata`** — `@IsTest(SeeAllData=true)` in tests.
5. **`soql-in-loop`** / **`dml-in-loop`** — SOQL `[SELECT ...]` or DML statement inside a `for`/`while` body.
6. **`hardcoded-id`** — 15- or 18-char Salesforce ID literal in source (common prefixes: 001, 003, 005, 006, 00G, etc.).
7. **`hardcoded-url`** — `https://*.salesforce.com` / `force.com` URL literal in source.
8. **`perm-set-naming`** — `.permissionset-meta.xml` file basename does not match `[AppPrefix]_[Component]_[AccessLevel]` (AppPrefix 3-8 PascalCase chars, AccessLevel ∈ Read|Write|Full|Execute|Admin).
9. **`perm-set-anti-pattern`** — `ViewAllData`/`ModifyAllData` enabled in any permission set.
10. **`apex-doc`** — public class or public method lacking an immediately-preceding `/** ... */` block. Reports at most one finding per file (the agent runs deeper review).

Each finding is one line: `<file>:<line>: <rule>: <message>` — the same shape as `tools/lint-skills` so /architect and /sprint can splice both lints into a single output.

## Usage

```sh
# From the repo root
python3 tools/sf-lint/check.py
# or
sh tools/sf-lint/check.sh
```

Both forms accept `--root <path>` to scan a specific subtree. Exit code is `0` on clean, otherwise `min(findings, 255)`.

## Where it runs in the ADLC pipeline

- **Phase 4 (build)**: `task-implementer` runs sf-lint over the touched files after writing them; any finding aborts the commit and triggers a fix.
- **Phase 5 (review)**: the `/proceed` Phase-5 step invokes sf-lint once across the entire change set; findings are merged into the review-panel output.
- **Pre-PR (/sprint)**: sf-lint is one of the must-pass gates before a PR is opened.
- **`/architect`**: optional — surfaces baseline static issues during architecture review so they don't surface as design rework later.

It is **not** wired into a git pre-commit hook by default. If you want pre-commit enforcement, add an entry to your project's `.husky/pre-commit` (or equivalent) calling `sh tools/sf-lint/check.sh`.

## Scope and skipped paths

- Scans `*.cls`, `*.trigger`, and `*.permissionset-meta.xml` files
- Skips: `.git/`, `.worktrees/`, `node_modules/`, and `skills/` (the vendored sf-skills set is content, not project code under review)
- Markdown documentation (`.md`) is never scanned

## What it does NOT do

- It does NOT parse Apex AST. Every check is regex/substring. False negatives are expected on heavily-formatted edge cases.
- It does NOT validate semantic correctness — bulkification logic, FLS rationale, governor-limit accounting, or whether a `with sharing` is actually appropriate for a given class. Those are the review panel's job.
- It does NOT replace `sf scanner run` (Salesforce Code Analyzer / sfca / graph engine). When the project has Code Analyzer configured, run both — they catch different things.
- It does NOT lint LWC, Flow, or OmniStudio metadata. Those are the rubric reviewers' territory (sf-skill catalog + agents).
- It does NOT enforce the deploy-order gate for Agentforce — that lives in `/wrapup` and `/sprint` (Batch 8).

## Constraints

- Python 3 stdlib only (`argparse`, `re`, `pathlib`, `sys`). No third-party packages. No network.
- POSIX `sh`-compatible wrapper. Tested on macOS and Linux.
- Read-only against the repo. No temp files, no logs, no cache.
