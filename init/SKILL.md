---
name: init
description: Bootstrap .adlc/ structure in a new repo or subdirectory
argument-hint: Optional target directory (defaults to current directory)
---

# /init — Bootstrap ADLC Structure

You are setting up the `.adlc/` directory structure for spec-driven development.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Input

Target: $ARGUMENTS

## Instructions

### Step 1: Determine Target Directory
1. If given a path, use that as the target
2. If no argument, use the current working directory
3. Check if `.adlc/` already exists — if so, report what's already there and ask if the user wants to reinitialize or fill gaps

### Step 2: Gather Project Context
Ask the user for the following (skip any that are already known from existing files):
1. **Project name** — What is this project called?
2. **What it does** — One paragraph description
3. **Tech stack** — Languages, frameworks, databases, cloud providers
4. **Project scope** — What's in scope vs out of scope
5. **Key architectural patterns** — Layered? Microservices? Monolith?

If a `CLAUDE.md`, `README.md`, or `package.json` exists, extract this info automatically and confirm with the user instead of asking.

### Step 3: Create Directory Structure
```
.adlc/
  ETHOS.md               # Copy of ~/.claude/skills/ETHOS.md — ensures skills work inside git worktrees
  context/
    project-overview.md    # What the project does, tech stack, scope
    architecture.md        # System diagram, layers, key patterns, ADRs
    conventions.md         # File organization, naming, testing, git conventions
    taxonomy.md            # Retrieval tag vocabulary (component/domain/stack/concerns)
    sf-skills-catalog.md   # (SF projects only) Layer/glob → sf-skill dispatch table — required by /architect, task-implementer, Phase 5 reviewers
    salesforce-rules.md    # (SF projects only) Always-on rules baseline (sharing, AccessLevel, no @future, etc.)
  specs/
    .gitkeep
  bugs/
    .gitkeep
  knowledge/
    assumptions/
      .gitkeep
    lessons/
      .gitkeep
  templates/             # Copies of ~/.claude/skills/templates/*.md — ensures skills work inside git worktrees
    assumption-template.md
    bug-template.md
    lesson-template.md
    requirement-template.md
    task-template.md
  partials/              # Copies of ~/.claude/skills/partials/*.sh — shared shell snippets sourced by SKILL.md files
    ethos-include.sh
  workflows/             # Copies of ~/.claude/skills/workflows/ RUNTIME files only — Dynamic Workflow scripts used by the workflow engine
    adlc-sprint.workflow.js   # ONE self-contained file: meta first, schemas + pure helpers inlined behind // ==== BEGIN/END PURE ==== (runtime has no require)
    README.md            # NOTE: workflows/tests/ is intentionally NOT copied — those are toolkit-internal node:test files (CommonJS require) that break Jest in "type":"module" consumer repos (see Step 6)
```

**Why the local copies of ETHOS.md, templates, partials, and workflows?** Claude Code's sandbox blocks the `Read` tool from accessing paths outside the current working directory. When a skill runs inside a git worktree (e.g., `.claude/worktrees/<name>/`), `~/.claude/skills/ETHOS.md`, `~/.claude/skills/templates/*.md`, `~/.claude/skills/partials/*.sh`, and `~/.claude/skills/workflows/*` become unreadable by subagents and any tool that uses `Read` mid-skill. Keeping copies under `.adlc/` makes the toolkit work identically in main checkouts and worktrees.

### Step 4: Populate Context Files

**project-overview.md** — Based on user input or existing docs:
```markdown
# {Project Name} — Project Overview

## What It Does
{description}

## Tech Stack
{tech stack table or list}

## Project Scope
{in scope / out of scope}
```

**architecture.md** — Initial structure:
```markdown
# {Project Name} — Architecture

## System Diagram
{ASCII diagram of major components}

## Layers
{description of architectural layers}

## Key Patterns
{important patterns used in the codebase}

## ADRs
(Add architectural decision records here as decisions are made)
```

**conventions.md** — Based on project analysis:
```markdown
# {Project Name} — Conventions

## File Organization
{directory structure}

## Naming
{naming conventions per language}

## Testing
{test framework, conventions, coverage requirements}

## Error Handling
{error handling patterns}

## Git Conventions
{branch naming, commit messages, PR process}
```

### Step 5: Update .gitignore
Add the following entries to the project's `.gitignore` (create it if it doesn't exist):
```
# ADLC worktrees (used by /proceed for parallel session isolation)
.worktrees/

# Claude Code per-user permission overrides (team settings live in .claude/settings.json)
.claude/settings.local.json

# ADLC per-project ID counters and locks — transient state; rebuilt on demand
# from existing artifacts (see partials/id-counter.sh). Do not commit.
.adlc/.next-req
.adlc/.next-bug
.adlc/.next-lesson
.adlc/.next-req.lock.d/
.adlc/.next-bug.lock.d/
.adlc/.next-lesson.lock.d/
.adlc/.cache/

# Playwright session tokens & test artifacts. storageState.json holds a live
# Salesforce session cookie — checking it in is a credential leak (test-auditor
# flags as Critical). reports/playwright/ holds traces/videos/HTML reports
# regenerated on every run.
tests/e2e/storageState.json
reports/playwright/
playwright-report/
test-results/
```

### Step 6: Copy ETHOS.md and Templates Into the Project

Copy the canonical ETHOS.md and all templates from the toolkit into the project so skills keep working inside git worktrees (where Read is sandboxed to the worktree root).

```bash
# Verify source exists
if [ ! -f ~/.claude/skills/ETHOS.md ] || [ ! -d ~/.claude/skills/templates ] || [ ! -d ~/.claude/skills/partials ] || [ ! -d ~/.claude/skills/workflows ]; then
  echo "ERROR: Toolkit not found at ~/.claude/skills/. Ensure ~/.claude/skills is symlinked to the adlc-toolkit repo."
  exit 1
fi

# Copy ETHOS.md (overwrite — canonical is source of truth)
cp ~/.claude/skills/ETHOS.md .adlc/ETHOS.md

# Copy templates (overwrite — canonical is source of truth)
mkdir -p .adlc/templates
cp ~/.claude/skills/templates/*.md .adlc/templates/

# Copy partials (overwrite — canonical is source of truth). These are POSIX
# shell snippets sourced by SKILL.md files (e.g., ethos-include.sh).
mkdir -p .adlc/partials
cp ~/.claude/skills/partials/*.sh .adlc/partials/
chmod +x .adlc/partials/*.sh

# Copy workflows (overwrite — canonical is source of truth). These are the
# Dynamic Workflow scripts the workflow engine runs (e.g.,
# adlc-sprint.workflow.js — ONE self-contained file with schemas + pure helpers
# inlined, since the runtime has no require). Resolved via the two-level fallback
# (.adlc/workflows/... -> ~/.claude/skills/workflows/...) so the engine works
# inside git worktrees where Read is sandboxed to the worktree root.
#
# Copy ONLY the runtime files: the workflow script(s) and the top-level README.
# Do NOT copy workflows/tests/ — those are toolkit-internal `node:test` unit
# tests for the inlined PURE helpers (CommonJS `require('node:test')`). They have
# no purpose in a consumer repo, and shipping a `*.test.js` under .adlc/ is a
# trap: in any "type":"module" repo running Jest, the DEFAULT testMatch
# (**/?(*.)+(spec|test).[jt]s?(x)) discovers .adlc/workflows/tests/helpers.test.js,
# runs it as ESM, and fails it with "ReferenceError: require is not defined" —
# reddening `npm test` and any CI gate that runs it. The engine is ONE
# self-contained file (no require/import/fs), so globbing *.workflow.js captures
# everything the runtime ever resolves.
mkdir -p .adlc/workflows
cp ~/.claude/skills/workflows/*.workflow.js .adlc/workflows/
cp ~/.claude/skills/workflows/README.md .adlc/workflows/
# Idempotent cleanup: remove a stale tests/ dir left by an OLDER /init that did
# `cp -R` of the whole workflows tree. Heals already-initialized repos on re-run;
# safe no-op when absent. (Belt-and-suspenders to the explicit-file copy above.)
rm -rf .adlc/workflows/tests

# Clean up Finder-style duplicates if present. Matches:
#   - .md files: "requirement-template 2.md"
#   - non-.md files: "pipeline-state 2.json", ".next-bug 2"
#   - directories: "knowledge 2", "specs 2"
# The `-depth` flag processes directory contents before the directory itself,
# so `rm -rf` on a "* 2" dir doesn't fail due to prior deletions.
find .adlc -depth \( -name "* 2" -o -name "* 2.*" \) -exec rm -rf {} + 2>/dev/null

# Advisory (Jest repos): the copy above ships NO test files under .adlc/, so the
# default Jest testMatch stays green with no config change. Only a repo with a
# custom BROAD testMatch (e.g. "**/*.js") would pick up .adlc/ — those repos
# should add "<rootDir>/.adlc/" to testPathIgnorePatterns. Purely informational;
# this does not edit package.json or any jest config.
if grep -q '"jest"' package.json 2>/dev/null || find . -maxdepth 1 -name 'jest.config.*' 2>/dev/null | grep -q .; then
  echo "ADVISORY (Jest detected): .adlc/ contains no test files by design — default 'npm test' is unaffected. If you use a custom broad testMatch, add \"<rootDir>/.adlc/\" to testPathIgnorePatterns."
fi
```

If the user has previously made intentional customizations to their local `.adlc/ETHOS.md`, `.adlc/templates/*.md`, `.adlc/partials/*.sh`, or `.adlc/workflows/adlc-sprint.workflow.js`, confirm before overwriting. Use `/template-drift` to surface what differs (it also flags a stale `.adlc/workflows/tests/` left by an older `/init` — the Jest landmine fixed above). Typical drift (stale copies) should be overwritten silently.

### Step 7: Scaffold Retrieval Taxonomy

Copy the canonical taxonomy template to `.adlc/context/taxonomy.md` so authors of new REQs, bugs, and lessons have a reference vocabulary for retrieval tags.

**This step is idempotent — skip if the file already exists** (preserve any project-local customizations).

```bash
# Verify source exists
if [ ! -f ~/.claude/skills/templates/taxonomy-template.md ]; then
  echo "ERROR: Taxonomy template not found at ~/.claude/skills/templates/taxonomy-template.md. Ensure ~/.claude/skills is symlinked to the adlc-toolkit repo."
  exit 1
fi

# Ensure destination directory exists (safe if Step 3 already created it)
mkdir -p .adlc/context

# Idempotent copy: only copy if destination does not already exist
if [ ! -f .adlc/context/taxonomy.md ]; then
  cp ~/.claude/skills/templates/taxonomy-template.md .adlc/context/taxonomy.md
  echo "Created .adlc/context/taxonomy.md from canonical template."
else
  echo "Preserved existing .adlc/context/taxonomy.md (idempotent — not overwritten)."
fi
```

Advise the user: "Open `.adlc/context/taxonomy.md` and customize the example values for this codebase. Authors of new REQs, bugs, and lessons will reference this file when choosing tag values (`component`, `domain`, `stack`, `concerns`). The `tags` dimension stays free-form."

### Step 7.5: Scaffold Salesforce skills catalog & rules

Copy the canonical Salesforce skill dispatch table (`sf-skills-catalog.md`) and the rules baseline (`salesforce-rules.md`) into the consumer repo's `.adlc/context/`. These are required by:
- `/architect` Step 2.5 — to look up which orchestrator skills to load based on spec signals
- `task-implementer` agent — to look up rubrics from the **File-glob → rubric dispatch** table
- Phase 5 reviewer agents — same lookup, applied to the diff
- `/proceed` Phase 5 Step E — to know what counts as Salesforce metadata for the platform validate gate

Without these files in the consumer repo, the architect/implementer/reviewers fall back to first-principles reasoning, which is the failure mode that ships hand-rolled UI Bundle scaffolding instead of `sf template generate ui-bundle` output (and similar drift across every artifact family).

**This step is idempotent — both files are *templates*, not customization surfaces.** Overwrite existing copies silently to keep them in sync with the toolkit; if the user has hand-edited either, surface a `/template-drift` advisory.

```bash
# Verify sources exist
TOOLKIT_CTX="$HOME/.claude/skills/.adlc/context"
if [ ! -f "$TOOLKIT_CTX/sf-skills-catalog.md" ] || [ ! -f "$TOOLKIT_CTX/salesforce-rules.md" ]; then
  echo "ERROR: Salesforce context files not found at $TOOLKIT_CTX. Ensure ~/.claude/skills is symlinked to the adlc-toolkit repo."
  exit 1
fi

mkdir -p .adlc/context

# Catalog: overwrite — canonical, machine-consumed dispatch table
cp "$TOOLKIT_CTX/sf-skills-catalog.md" .adlc/context/sf-skills-catalog.md
echo "Synced .adlc/context/sf-skills-catalog.md from toolkit canonical."

# Rules: overwrite if missing or unchanged from a prior toolkit version. Skip
# overwrite if the file appears hand-customized (file size differs significantly
# AND first line still matches the canonical header) — surface a /template-drift
# advisory instead.
if [ ! -f .adlc/context/salesforce-rules.md ]; then
  cp "$TOOLKIT_CTX/salesforce-rules.md" .adlc/context/salesforce-rules.md
  echo "Created .adlc/context/salesforce-rules.md from toolkit canonical."
else
  if ! cmp -s "$TOOLKIT_CTX/salesforce-rules.md" .adlc/context/salesforce-rules.md; then
    echo "Preserved existing .adlc/context/salesforce-rules.md (differs from toolkit). Run /template-drift to review and sync."
  else
    echo "Preserved existing .adlc/context/salesforce-rules.md (already in sync)."
  fi
fi
```

Skip this step entirely for non-Salesforce projects (no `salesforce:` block in `.adlc/config.yml` and no `force-app/` directory). For Salesforce projects, this step is mandatory — the architect cannot reason about UI Bundles, OmniStudio, Data Cloud, or Agentforce scaffolding without the catalog.

### Step 8: Scaffold Claude Code Permissions Allowlist

Copy the canonical Claude Code settings template to `.claude/settings.json` so `/proceed` (and every other skill in this toolkit) can run end-to-end without prompting for permission on every routine `git`, `gh`, test, and agent-dispatch operation. This is the single biggest mitigation against per-phase gating in long-running pipelines.

**This step is idempotent — skip if the file already exists** (preserve any project-local customizations).

```bash
# Verify source exists
if [ ! -f ~/.claude/skills/templates/claude-settings-template.json ]; then
  echo "ERROR: Settings template not found at ~/.claude/skills/templates/claude-settings-template.json. Ensure ~/.claude/skills is symlinked to the adlc-toolkit repo."
  exit 1
fi

# Ensure destination directory exists
mkdir -p .claude

# Idempotent copy: only copy if destination does not already exist
if [ ! -f .claude/settings.json ]; then
  cp ~/.claude/skills/templates/claude-settings-template.json .claude/settings.json
  echo "Created .claude/settings.json from canonical template."
else
  echo "Preserved existing .claude/settings.json (idempotent — not overwritten)."
fi
```

The template pre-approves the routine `git`, `gh`, `npm`, Read/Write/Edit, and agent-dispatch operations the ADLC pipeline fires. Destructive operations (`rm -rf`, `git reset --hard`, `gh pr merge`, `./deploy.sh`, `terraform apply/destroy`, force-push to `main`) remain on the **ask** list so a human still confirms the one-way moves. Customize for project-specific commands (e.g., add `Bash(cd app && ./deploy.sh:*)` for iOS deploys) by editing `.claude/settings.json` directly.

Advise the user: "`.claude/settings.json` was scaffolded with a default allowlist. Commit this file — it is team-shared. Use `.claude/settings.local.json` (gitignored by Claude Code) for personal overrides."

### Step 9: Scaffold `.adlc/config.yml` and set `project.shortname`

`.adlc/config.yml` is **required for every project** because the ADLC ID allocator (`partials/id-counter.sh`) reads `project.shortname` to namespace REQ / BUG / LESSON ids as `<XYZ>-REQ-NNN`. Without a shortname, `/spec`, `/bugfix`, and `/wrapup` all hard-fail. So this step is no longer optional.

```bash
# Verify source exists
if [ ! -f ~/.claude/skills/templates/config-template.yml ]; then
  echo "ERROR: Config template not found at ~/.claude/skills/templates/config-template.yml."
  exit 1
fi

if [ ! -f .adlc/config.yml ]; then
  cp ~/.claude/skills/templates/config-template.yml .adlc/config.yml
  echo "Created .adlc/config.yml from template."
else
  echo "Preserved existing .adlc/config.yml."
fi
```

Then **resolve `project.shortname`**:

1. Ask the user: "Pick a 3-uppercase-letter shortname for this project (used in IDs like `XYZ-REQ-001`). Examples: `SFC` for Salesforce-Customer-360, `ORD` for Order-Management, `PRT` for Partner-Portal. Pick something unique across every repo on your machine — once specs exist, changing it requires a migration."
2. Validate against `^[A-Z]{3}$`. Reject anything else and re-prompt.
3. Write it under `project.shortname` in `.adlc/config.yml`. If a value already exists and matches the regex, preserve it; if it's the placeholder `XYZ`, prompt the user to set a real value.

```bash
# Verify the shortname field is set and valid
shortname=$(awk '
  /^project:/                  { in_project=1; next }
  in_project && /^[^[:space:]#]/ { in_project=0 }
  in_project && /^[[:space:]]+shortname:/ {
    sub(/^[[:space:]]+shortname:[[:space:]]*/, "")
    gsub(/["'\'']/, "")
    sub(/[[:space:]]*#.*$/, "")
    print
    exit
  }
' .adlc/config.yml)
case "$shortname" in
  [A-Z][A-Z][A-Z])
    if [ "$shortname" = "XYZ" ]; then
      echo "WARNING: project.shortname='XYZ' is the placeholder — replace with a real value before /spec."
    else
      echo "OK: project.shortname='$shortname'"
    fi
    ;;
  *)
    echo "ERROR: project.shortname is missing or invalid in .adlc/config.yml. Set it to 3 uppercase letters before running /spec, /bugfix, or /wrapup."
    ;;
esac
```

**Cross-repo (optional add-on)**. If the user says this repo will ever share features with other repos (admin app + its API + an iOS app, etc.), edit the `repos:` block in the same `.adlc/config.yml` to list siblings. The cross-repo conceptual model:

- "Primary" is per-REQ, not a fixed role. The current repo is primary for REQs that originate here. Siblings are other repos that might participate when a cross-repo REQ starts here.
- If you also originate REQs from one of those siblings, you'll run `/init` there too — each repo that hosts REQs gets its own `.adlc/`, its own `config.yml`, and its own `project.shortname`. Configs are symmetric mirrors of each other.

Advise the user:
- "Edit `.adlc/config.yml`. The entry for THIS repo should have `primary: true` and no `path` (path is implicit since it's this repo). Each sibling entry gets a `path:` (relative to this repo root, or absolute). Every sibling must already be cloned locally at that path."
- "If this is a single-repo project (REQs only ever originate here and never touch other repos), leave `repos:` with the single primary entry. ADLC skills fall back to single-repo behavior when no siblings are declared."
- "After editing, verify with `cat .adlc/config.yml` and make sure each sibling path resolves: `git -C <sibling-path> rev-parse --git-dir`."

### Step 10: Scaffold Playwright UI harness (LWC / FlexiPage / OmniStudio / UI-Bundle projects)

`/architect` Step 8 ("UI test obligation") requires every UI-bearing task to ship a paired Playwright spec when `.adlc/config.yml` declares `playwright_specs:`. The default `config-template.yml` and both presets (`sfdc-core.yml`, `sfdc-industries.yml`) seed `playwright_specs: "tests/e2e"`, so by default a new project will start asking for Playwright specs the first time `/architect` runs on a UI REQ.

Without a runner wired up, the implementer drops the spec into a project that has no `playwright.config.ts` and `agents/test-auditor.md` flags missing wiring as Major. This step scaffolds the runner so the *first* spec lands in a working harness.

**Skip this step entirely** when:
- `.adlc/config.yml` does not declare `playwright_specs:` (the user opted out), OR
- `stack.frontends` does not include `lwc` AND no `force-app/**/lwc/**` directory exists AND `industries:` does not include `omnistudio` or `agentforce` (no UI surface in scope).

**This step is idempotent** — every file copy is gated on `[ ! -f <dest> ]` so a re-run preserves customizations. If the user has hand-edited any harness file, surface a `/template-drift` advisory rather than overwriting.

```bash
# Verify sources exist
TOOLKIT_PW="$HOME/.claude/skills/templates/playwright"
if [ ! -d "$TOOLKIT_PW" ]; then
  echo "ERROR: Playwright harness template not found at $TOOLKIT_PW. Ensure ~/.claude/skills is symlinked to the adlc-toolkit repo."
  exit 1
fi

# Decide whether to scaffold. Read playwright_specs from .adlc/config.yml; bail when unset/empty.
pw_specs=$(awk '/^playwright_specs:/ { sub(/^playwright_specs:[[:space:]]*/, ""); gsub(/["'\'']/, ""); sub(/[[:space:]]*#.*$/, ""); print; exit }' .adlc/config.yml 2>/dev/null)
if [ -z "$pw_specs" ]; then
  echo "Skipped Playwright harness scaffold — playwright_specs is not declared in .adlc/config.yml."
else
  # 1. playwright.config.ts at repo root — only if absent (preserve customizations).
  if [ ! -f playwright.config.ts ]; then
    cp "$TOOLKIT_PW/playwright.config.ts" playwright.config.ts
    echo "Created playwright.config.ts from canonical template."
  else
    echo "Preserved existing playwright.config.ts."
  fi

  # 2. tests/e2e/global-setup.ts — only if absent.
  mkdir -p "$pw_specs"
  if [ ! -f "$pw_specs/global-setup.ts" ]; then
    cp "$TOOLKIT_PW/tests/e2e/global-setup.ts" "$pw_specs/global-setup.ts"
    echo "Created $pw_specs/global-setup.ts from canonical template."
  else
    echo "Preserved existing $pw_specs/global-setup.ts."
  fi

  # 3. example.spec.ts.example — implementer copies this when authoring the
  # first spec. Always present, no-op if already there.
  if [ ! -f "$pw_specs/example.spec.ts.example" ]; then
    cp "$TOOLKIT_PW/tests/e2e/example.spec.ts.example" "$pw_specs/example.spec.ts.example"
    echo "Created $pw_specs/example.spec.ts.example."
  fi

  # 4. tests/e2e/.gitignore — defense in depth on top of root .gitignore.
  if [ ! -f "$pw_specs/.gitignore" ]; then
    cp "$TOOLKIT_PW/tests/e2e/.gitignore" "$pw_specs/.gitignore"
  fi

  # 5. README.md inside the harness dir — orientation for the next dev.
  if [ ! -f "$pw_specs/README.md" ]; then
    cp "$TOOLKIT_PW/README.md" "$pw_specs/README.md"
  fi

  # 6. Wire Playwright into package.json — install the dev dep, install the
  # chromium browser binary, and add the "test:e2e": "playwright test" script.
  # This step is mandatory by default so the harness is immediately usable;
  # set ADLC_INIT_SKIP_PLAYWRIGHT_INSTALL=1 to opt out (e.g. offline init,
  # CI bootstrap that handles deps separately, pnpm/yarn projects that
  # manage installs out-of-band).
  if [ "${ADLC_INIT_SKIP_PLAYWRIGHT_INSTALL:-0}" = "1" ]; then
    echo "Skipped Playwright npm install (ADLC_INIT_SKIP_PLAYWRIGHT_INSTALL=1). Run manually:"
    echo "  npm install --save-dev @playwright/test"
    echo "  npx playwright install --with-deps chromium"
    echo "  and add \"test:e2e\": \"playwright test\" to package.json scripts."
  elif [ ! -f package.json ]; then
    echo "Skipped Playwright npm install — no package.json at repo root. Run /init from the repo root, or scaffold one first."
  else
    # Install @playwright/test as a dev dep when not already present. Detect
    # via package.json (devDeps OR deps) rather than running `npm ls` so an
    # uninstalled lockfile state still triggers a clean install.
    pw_already_dep=$(node -e '
      try {
        const p = JSON.parse(require("fs").readFileSync("package.json","utf8"));
        const has = (p.devDependencies && p.devDependencies["@playwright/test"]) ||
                    (p.dependencies && p.dependencies["@playwright/test"]);
        process.stdout.write(has ? "1" : "0");
      } catch (_) { process.stdout.write("0"); }
    ')
    if [ "$pw_already_dep" = "1" ]; then
      echo "@playwright/test already declared in package.json — skipping npm install."
    else
      echo "Installing @playwright/test (npm install --save-dev @playwright/test)..."
      if npm install --save-dev @playwright/test; then
        echo "  Done."
      else
        echo "WARNING: 'npm install --save-dev @playwright/test' failed. Re-run manually after fixing the cause (often offline/registry/permissions)."
      fi
    fi

    # Install the chromium browser binary used by the harness. Idempotent —
    # Playwright's installer no-ops when the matching version is already
    # present. --with-deps pulls OS-level shared libs (Linux); on macOS it's
    # a no-op for the deps part. Honor a separate skip flag so CI runners
    # that pre-bake browsers can opt out.
    if [ "${ADLC_INIT_SKIP_PLAYWRIGHT_BROWSERS:-0}" = "1" ]; then
      echo "Skipped 'npx playwright install --with-deps chromium' (ADLC_INIT_SKIP_PLAYWRIGHT_BROWSERS=1)."
    else
      echo "Installing Chromium for Playwright (npx playwright install --with-deps chromium)..."
      if npx --yes playwright install --with-deps chromium; then
        echo "  Done."
      else
        echo "WARNING: 'npx playwright install --with-deps chromium' failed. Re-run manually before the first /architect on a UI REQ."
      fi
    fi

    # Add the test:e2e script to package.json without touching anything else.
    # Use Node so we don't risk breaking JSON formatting or losing an existing
    # scripts entry.
    test_e2e_added=$(node -e '
      const fs = require("fs");
      const p = JSON.parse(fs.readFileSync("package.json","utf8"));
      p.scripts = p.scripts || {};
      if (p.scripts["test:e2e"]) { process.stdout.write("kept"); return; }
      p.scripts["test:e2e"] = "playwright test";
      fs.writeFileSync("package.json", JSON.stringify(p, null, 2) + "\n");
      process.stdout.write("added");
    ')
    if [ "$test_e2e_added" = "added" ]; then
      echo "Added \"test:e2e\": \"playwright test\" to package.json scripts."
    else
      echo "Preserved existing \"test:e2e\" script in package.json."
    fi
  fi
fi
```

After this step, Playwright is installed (`@playwright/test` + chromium browser binary) and `npm run test:e2e` is wired up. The next `/architect` run on a UI-bearing REQ lands its required `tests/e2e/<feature>.spec.ts` into an immediately-runnable harness — no manual `npm install` follow-up needed. Set `ADLC_INIT_SKIP_PLAYWRIGHT_INSTALL=1` to opt out of the npm install (e.g. offline init); set `ADLC_INIT_SKIP_PLAYWRIGHT_BROWSERS=1` to opt out of just the browser-binary download (e.g. CI runner with pre-baked browsers).

### Step 10.5: Register the project with the sprint dashboard & open it in Chrome

Tell the shared dashboard (running on this host, shared across every project) about this project so its REQs show up alongside everything else. Then launch / surface the dashboard URL in the user's default browser (Chrome preferred on macOS) so they can immediately see this project listed.

The launcher script is idempotent: it upserts the current `ADLC_ROOT` into `~/.adlc/dashboard-registry.json`, no-ops if the dashboard is already running, and never fails the parent skill on error. Setting `ADLC_DASHBOARD_OPEN=1` tells it to open the dashboard URL in the browser after registration.

```bash
# Resolve the launcher. Prefer the locally-copied .adlc/ path so this works
# inside git worktrees; fall back to the canonical toolkit location.
LAUNCHER=""
if [ -x .adlc/tools/sprint-dashboard/launch.sh ]; then
  LAUNCHER=".adlc/tools/sprint-dashboard/launch.sh"
elif [ -x "$HOME/.claude/skills/tools/sprint-dashboard/launch.sh" ]; then
  LAUNCHER="$HOME/.claude/skills/tools/sprint-dashboard/launch.sh"
fi

if [ -n "$LAUNCHER" ]; then
  ADLC_ROOT="$(pwd)" ADLC_DASHBOARD_OPEN=1 sh "$LAUNCHER" || true
else
  echo "[init] sprint-dashboard launcher not found — skipping dashboard registration."
fi
```

After this step, the user should see `<project-name>` listed at `http://127.0.0.1:5174` (default port; override with `ADLC_DASHBOARD_PORT`). The server picks up the new entry from the registry on its next ~1.5s poll, so even when the launcher reports "already running", the project shows up within seconds.

### Step 11: Summary
1. Display the created directory structure
2. Explain the ADLC workflow: `/spec` → `/validate` → `/architect` → `/validate` → implement → `/reflect` → `/review` → `/wrapup` (or use `/proceed` to run the full pipeline automatically)
3. If cross-repo config was scaffolded, remind the user that `/proceed` will create worktrees in every touched sibling and open one PR per repo
4. If the Playwright harness was scaffolded, confirm `npm run test:e2e` is wired (Step 10 installs `@playwright/test`, downloads chromium, and adds the script). If either install reported a WARNING, surface that line in the summary so the user can re-run it before the first `/architect` on a UI REQ.
5. Suggest adding ADLC skill references to the project's `CLAUDE.md` if one exists
