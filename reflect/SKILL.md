---
name: reflect
description: Post-implementation self-review — catch issues before /review
argument-hint: Optional REQ-xxx ID or branch name to scope the reflection
---

# /reflect — Post-Implementation Reflection

You are performing a self-review of recently implemented code to catch issues before the formal `/review` step. This is a fast, honest assessment of your own work.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

- Current branch: !`git branch --show-current 2>/dev/null || echo "Not a git repo"`
- Recent changes: !`git diff main --stat 2>/dev/null || echo "No diff available"`

**Context files loaded on demand**: `.adlc/context/conventions.md` and `.adlc/context/architecture.md` are loaded by Step 1 below — **skip the Read if they are already in the current conversation** (e.g., when invoked from `/proceed`, which preloads them at Phase 0).

## Input

Scope: $ARGUMENTS

## Prerequisites

Before proceeding, verify that `.adlc/context/conventions.md` exists. If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` first to set up conventions."

## Instructions

### Step 1: Determine Scope
1. If given a REQ ID, find the associated branch and review its changes
2. If given a branch name, review all changes on that branch vs `main`
3. If no argument, review all changes on the current branch vs `main`
4. Get the full diff: `git diff main...HEAD`
5. **Context files**: if `.adlc/context/conventions.md` and `.adlc/context/architecture.md` are NOT already in your conversation context, Read them now. Otherwise skip — they're already loaded.

### Step 1.5: Run the source-only code audit gate

Before dispatching the reflector agent, run the deterministic Salesforce code audit (`tools/sf-code-audit/audit_source.py` via `partials/run-source-audit.sh`). This is fast, source-only (no org needed), and gates on `audit.fail_on` from `.adlc/config.yml` (default: any `CRITICAL` or `HIGH` finding fails the gate).

```bash
if [ -x .adlc/partials/run-source-audit.sh ]; then
  .adlc/partials/run-source-audit.sh
elif [ -n "${TOOLKIT_HOME:-}" ] && [ -x "$TOOLKIT_HOME/partials/run-source-audit.sh" ]; then
  sh "$TOOLKIT_HOME/partials/run-source-audit.sh"
else
  echo "[reflect] audit wrapper not found at .adlc/partials/run-source-audit.sh — re-run /init to install."
  exit 1
fi
```

Capture the exit code:
- **0** — gate passed. Continue to Step 2.
- **1** — gate failed. **Do not** dispatch the reflector agent. Read `.adlc/runtime/audit/source-audit.md`, surface the CRITICAL/HIGH findings to the user verbatim with file/line citations, and treat them as Critical-tier issues in Step 5 (Fix or Defer). After the user fixes them, re-run `/reflect` from Step 1.5.
- **2** — tool/config error. Surface the error to the user; do not silently skip the gate.

This ordering matters: the deterministic static-analysis gate runs before the LLM-based reflector so the cheap, definitive findings are reported first and the reflector then focuses on convention/design/test gaps that static analysis can't see. The gate is configured in `.adlc/config.yml` under `audit:` — set `fail_on: NONE` to make it advise-only, or `enabled: false` to disable entirely (not recommended).

### Step 2: Dispatch the `reflector` agent
Launch the **reflector** agent via the Agent tool. The agent owns the canonical self-review checklist (Correctness, Convention Compliance, Architecture, Testing, Completeness) and handles reading changed files and cross-referencing lessons learned. Keeping the checklist in the agent ensures a single source of truth that `/proceed` Phase 5 also uses.

Provide the agent with:
- The scope (REQ ID, branch name, or "current uncommitted changes")
- The full diff from Step 1
- `conventions.md` and `architecture.md` content (from Step 1)

Instruct it: "Read all changed files in full, grep `.adlc/knowledge/lessons/` for applicable lessons, run your checklist, and report findings + questions. Do not apply fixes."

The agent will return:
- **Issues Found** — grouped by severity (Critical / Major / Minor) with file/line, description, suggested fix
- **Clean Areas** — 1-2 sentences on what was checked and looked good
- **Questions for the User** — ambiguities, design tradeoffs, assumptions, deferred edge cases

### Step 3: Present the Agent's Report
Relay the agent's Issues Found and Clean Areas sections to the user verbatim. Do not re-run the checklist yourself — that would duplicate work and risk drift.

### Step 4: Surface Questions from the Agent
The reflector agent returns a "Questions for the User" block covering ambiguous requirements, design tradeoffs, assumptions made, deferred edge cases, and UX/behavioral uncertainties. Relay that block to the user as a numbered list. If the agent returned "No questions — implementation is unambiguous," state that explicitly.

Do not proceed past this step until the user has answered — their responses may change what needs to be fixed.

### Step 5: Fix or Defer
1. If Critical issues are found, fix them immediately
2. If Major issues are found, ask the user whether to fix now or note for `/review`
3. Minor issues can be listed for the user to decide
4. After fixes, re-run tests to verify nothing broke

### Step 6: Recommend Next Action
- If no issues or only minor ones: "Ready for `/review`"
- If fixes were applied: "Fixes applied. Re-run `/reflect` to verify, or proceed to `/review`"
- If blockers remain: "Address these issues before `/review`"
