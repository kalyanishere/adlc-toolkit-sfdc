---
name: init
description: Bootstrap .adlc/ structure in a new repo or subdirectory (auto-detects SFDC vs MuleSoft stack)
argument-hint: Optional target directory (defaults to current directory). Pass --stack=sfdc|mulesoft to force a stack.
---

# /init — Bootstrap ADLC Structure (Stack-Aware Dispatcher)

You are setting up the `.adlc/` directory structure for spec-driven development.

This is a **unified dispatcher** shared by both `adlc-toolkit-sfdc` and `adlc-toolkit-mulesoft`. The same file lives in both toolkits byte-identically. At runtime it auto-detects whether the target project is SFDC or MuleSoft, locates the correct toolkit on disk, and runs the matching scaffold logic.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || true`

## Input

Target: $ARGUMENTS

## Instructions

### Step 0: Detect Project Stack & Locate Toolkit

Before anything else, decide whether this project is **Salesforce (`sfdc`)** or **MuleSoft (`mulesoft`)**, then resolve the absolute path of the matching toolkit (`TOOLKIT_HOME`).

Detection rules (filesystem signals — first match wins):
- `force-app/` directory present, OR `sfdx-project.json` at repo root → `sfdc`
- `mule-artifact.json` present anywhere, OR `pom.xml` containing `mule-maven-plugin` → `mulesoft`
- Existing `.adlc/context/sf-skills-catalog.md` → `sfdc`
- Existing `.adlc/context/mule-skills-catalog.md` → `mulesoft`
- Existing `.adlc/config.yml` containing `salesforce:` block → `sfdc`
- Existing `.adlc/config.yml` containing `mulesoft:` block → `mulesoft`
- `--stack=sfdc` or `--stack=mulesoft` in `$ARGUMENTS` → use that
- Otherwise → ambiguous; ask the user via AskUserQuestion which stack they want

Toolkit lookup (after stack is known):
- Probe these paths in order; pick the first that contains `init/SKILL.md` AND `templates/config-template.yml` declaring the matching stack key:
  1. `~/.claude/skills` (canonical SFDC symlink slot)
  2. `~/.claude/skills-mulesoft` (canonical Mule symlink slot)
  3. Sibling directories of the currently-running toolkit (`adlc-toolkit-sfdc`, `adlc-toolkit-mulesoft` next to each other)
  4. Common workspace roots: `~/Downloads/Workspaces/*/adlc-toolkit-{sfdc,mulesoft}`, `~/workspaces/*/adlc-toolkit-{sfdc,mulesoft}`, `~/code/*/adlc-toolkit-{sfdc,mulesoft}`
- If found, persist `STACK` and `TOOLKIT_HOME` so every later bash block can source them.
- If not found, hard-fail with a clear "clone the missing toolkit" message.

```bash
# Detect stack and locate toolkit. Persists STACK + TOOLKIT_HOME to
# ~/.adlc/runtime/init-state.sh so every subsequent block in this skill can
# source it. Idempotent: re-running /init re-resolves and overwrites.

set -e
mkdir -p "$HOME/.adlc/runtime"

# 0a — Argument override (--stack=sfdc | --stack=mulesoft)
ARG_STACK=""
case "$*" in
  *--stack=sfdc*)      ARG_STACK="sfdc" ;;
  *--stack=mulesoft*)  ARG_STACK="mulesoft" ;;
esac

# 0b — Filesystem signals
DETECTED=""
if [ -n "$ARG_STACK" ]; then
  DETECTED="$ARG_STACK"
elif [ -d "force-app" ] || [ -f "sfdx-project.json" ]; then
  DETECTED="sfdc"
elif [ -f "mule-artifact.json" ] || (find . -maxdepth 3 -name mule-artifact.json 2>/dev/null | head -1 | grep -q .); then
  DETECTED="mulesoft"
elif [ -f "pom.xml" ] && grep -q "mule-maven-plugin" pom.xml 2>/dev/null; then
  DETECTED="mulesoft"
elif [ -f ".adlc/context/sf-skills-catalog.md" ]; then
  DETECTED="sfdc"
elif [ -f ".adlc/context/mule-skills-catalog.md" ]; then
  DETECTED="mulesoft"
elif [ -f ".adlc/config.yml" ] && grep -q '^salesforce:' .adlc/config.yml 2>/dev/null; then
  DETECTED="sfdc"
elif [ -f ".adlc/config.yml" ] && grep -q '^mulesoft:' .adlc/config.yml 2>/dev/null; then
  DETECTED="mulesoft"
fi

if [ -z "$DETECTED" ]; then
  # Will be resolved in 0c by asking the user via AskUserQuestion.
  DETECTED="ASK"
fi
echo "DETECTED_STACK=$DETECTED"
```

If `DETECTED_STACK=ASK`, **call AskUserQuestion** to ask the user:

> "No SFDC or MuleSoft signals found in this directory (`force-app/`, `mule-artifact.json`, etc.). Which stack should `/init` scaffold?"
> Options:
> - **Salesforce (sfdc)** — Apex / LWC / Flow / OmniStudio / Data Cloud / Agentforce
> - **MuleSoft (mulesoft)** — Mule 4 apps / Anypoint Platform / DataWeave

Capture the answer in shell variable `STACK` (`sfdc` or `mulesoft`).

```bash
# 0c — Locate matching toolkit. STACK must be set ('sfdc' or 'mulesoft') by now.
# (If 0b returned ASK, the AskUserQuestion answer is set above as $STACK.)

# Probe a list of candidate toolkit roots. Pick the first that:
#   1. has init/SKILL.md
#   2. has templates/config-template.yml declaring the matching stack key
locate_toolkit() {
  stack="$1"
  needle="^${stack}:"
  [ "$stack" = "sfdc" ] && needle="^salesforce:"

  # Build candidate list
  candidates=""
  if [ "$stack" = "sfdc" ]; then
    candidates="$HOME/.claude/skills $HOME/.claude/skills-sfdc"
  else
    candidates="$HOME/.claude/skills-mulesoft $HOME/.claude/skills-mule"
  fi
  # Workspace fallback globs. Some shells (zsh in default mode) abort on a glob
  # that matches nothing. We expand each parent root individually with `find`
  # so missing dirs are no-ops instead of fatal.
  for root in "$HOME/Downloads/Workspaces" "$HOME/workspaces" "$HOME/code" "$HOME/repos" "$HOME/src"; do
    [ -d "$root" ] || continue
    # One level deep — sibling project dirs that might contain a checked-out toolkit.
    for parent in $(find "$root" -mindepth 1 -maxdepth 1 -type d 2>/dev/null); do
      if [ "$stack" = "sfdc" ]; then
        candidates="$candidates $parent/adlc-toolkit-sfdc $parent/adlc-toolkit"
      else
        candidates="$candidates $parent/adlc-toolkit-mulesoft $parent/adlc-toolkit-mule"
      fi
    done
    # Also consider the root itself as a parent (e.g., toolkits cloned directly under ~/code/).
    if [ "$stack" = "sfdc" ]; then
      candidates="$candidates $root/adlc-toolkit-sfdc $root/adlc-toolkit"
    else
      candidates="$candidates $root/adlc-toolkit-mulesoft $root/adlc-toolkit-mule"
    fi
  done
  # Sibling of the running toolkit (resolve symlinks)
  for sym in "$HOME/.claude/skills" "$HOME/.claude/skills-mulesoft"; do
    [ -L "$sym" ] || continue
    real=$(readlink -f "$sym" 2>/dev/null || readlink "$sym")
    [ -z "$real" ] && continue
    parent=$(dirname "$real")
    if [ "$stack" = "sfdc" ]; then
      candidates="$candidates $parent/adlc-toolkit-sfdc"
    else
      candidates="$candidates $parent/adlc-toolkit-mulesoft"
    fi
  done

  for c in $candidates; do
    [ -f "$c/init/SKILL.md" ] || continue
    [ -f "$c/templates/config-template.yml" ] || continue
    if grep -q "$needle" "$c/templates/config-template.yml" 2>/dev/null; then
      # Resolve symlinks to absolute path so later blocks aren't surprised.
      printf '%s' "$(cd "$c" && pwd -P)"
      return 0
    fi
  done
  return 1
}

if ! TOOLKIT_HOME=$(locate_toolkit "$STACK"); then
  echo "ERROR: Could not find adlc-toolkit-$STACK on this machine."
  echo "Searched: ~/.claude/skills, ~/.claude/skills-mulesoft, common workspace roots."
  echo ""
  echo "To fix:"
  echo "  1. Clone the toolkit, e.g.:"
  echo "       git clone https://github.com/<org>/adlc-toolkit-$STACK ~/code/adlc-toolkit-$STACK"
  echo "  2. (Optional, recommended) Create the well-known symlink so /init finds it instantly:"
  if [ "$STACK" = "sfdc" ]; then
    echo "       ln -sfn ~/code/adlc-toolkit-sfdc ~/.claude/skills"
  else
    echo "       ln -sfn ~/code/adlc-toolkit-mulesoft ~/.claude/skills-mulesoft"
  fi
  echo "  3. Re-run /init."
  exit 1
fi

echo "STACK=$STACK"
echo "TOOLKIT_HOME=$TOOLKIT_HOME"

# Persist for every later bash block in this skill.
cat > "$HOME/.adlc/runtime/init-state.sh" <<EOF
# Auto-generated by /init Step 0. Sourced by every subsequent bash block.
# Re-run /init to refresh.
STACK="$STACK"
TOOLKIT_HOME="$TOOLKIT_HOME"
export STACK TOOLKIT_HOME
EOF
echo "Wrote ~/.adlc/runtime/init-state.sh"
```

For the rest of this skill, **every Bash block must start with** `. "$HOME/.adlc/runtime/init-state.sh"` so `$STACK` and `$TOOLKIT_HOME` are available.

### Step 1: Determine Target Directory
1. If given a path argument (other than `--stack=...`), use it as the target.
2. If no argument, use the current working directory.
3. Check if `.adlc/` already exists — if so, report what's already there and ask if the user wants to reinitialize or fill gaps.

### Step 1.5: Ensure the Target Directory is a Git Repo

The whole ADLC pipeline assumes a working git repo: `/proceed` Step 0 runs `git worktree add`, every phase commits, `/wrapup` opens PRs. Initializing `.adlc/` inside a non-git directory ships a project that cannot proceed past `/spec`. Treat git as a precondition: if the directory isn't a git repo, **`git init` it locally by default** — assume a remote will be wired in later.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

# Detect git status. We use `git rev-parse --git-dir` rather than `[ -d .git ]`
# because a worktree's .git is a file, not a directory, and a parent-tracked
# subdirectory shouldn't get its own re-init.
if git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Target is already inside a git repo — skipping git init."
else
  echo "No git repo detected at target. Initializing one locally..."
  default_branch=$(git config --global --get init.defaultBranch 2>/dev/null || true)
  default_branch=${default_branch:-main}
  git init -b "$default_branch"
  echo "Initialized git repo on branch '$default_branch'. A remote can be wired in later via:"
  echo "  git remote add origin <url>"
  echo "  git push -u origin $default_branch"
fi
```

### Step 1.6: Scaffold Claude Code Permissions Allowlist (FIRST — before everything else)

This is intentionally hoisted before every other Bash-using step. The permissions allowlist must be in place **before** the rest of `/init` runs `mkdir`, `cp`, `sed`, `awk`, `node`, etc. — otherwise every subsequent step interactively prompts for the permission its allowlist was supposed to grant.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

if [ ! -f "$TOOLKIT_HOME/templates/claude-settings-template.json" ]; then
  echo "ERROR: Settings template not found at $TOOLKIT_HOME/templates/claude-settings-template.json. Toolkit appears corrupted."
  exit 1
fi

mkdir -p .claude

if [ ! -f .claude/settings.json ]; then
  cp "$TOOLKIT_HOME/templates/claude-settings-template.json" .claude/settings.json
  echo "Created .claude/settings.json from canonical template (Step 1.6 — early scaffold)."
else
  echo "Preserved existing .claude/settings.json (idempotent — not overwritten)."
fi
```

The template pre-approves the routine `git`, `gh`, `npm`, Read/Write/Edit, and agent-dispatch operations the ADLC pipeline fires. Destructive operations (`rm -rf`, `git reset --hard`, `gh pr merge`, `./deploy.sh`, `terraform apply/destroy`, force-push to `main`) remain on the **ask** list so a human still confirms the one-way moves.

The template also wires two Claude Code hooks (`Stop` and `UserPromptSubmit`) that emit one JSONL event per turn boundary to `~/.adlc/runtime/user-wait.jsonl`. The sprint dashboard tails this log to compute per-REQ "user wait" idle time. Zero overhead when the dashboard isn't running.

**How this takes effect.** Claude Code auto-reloads `.claude/settings.json` on file change — no `/clear`, no restart, no in-session reload command needed.

**Per-developer mode override.** The template's `defaultMode` is `bypassPermissions` because `/sprint` and `/proceed` run unattended pipelines. Each developer can override per-project in `.claude/settings.local.json` (gitignored by Claude Code).

Tell the user: "`.claude/settings.json` was scaffolded with a default allowlist plus user-wait hooks. **Commit this file** — it is team-shared. Use `.claude/settings.local.json` (gitignored) for personal overrides like a stricter `defaultMode`."

### Step 1.7: Wire Project-Local Skill Symlinks (CRITICAL — makes all other slash commands stack-aware)

After `/init`, every other ADLC slash command (`/architect`, `/proceed`, `/spec`, `/sprint`, `/wrapup`, etc.) must resolve to the **same toolkit** the project was initialized with. Claude Code resolves slash commands by checking `<project>/.claude/skills/<name>/SKILL.md` *before* falling back to `~/.claude/skills/<name>/SKILL.md` — so a project-local symlink that points each skill to the chosen toolkit guarantees correct resolution regardless of what `~/.claude/skills` globally points to.

This step creates one symlink per top-level skill in `<project>/.claude/skills/`. It does **not** symlink the whole `.claude/skills/` directory (so installations like Mule's `mule-development` skill pack — which lives at `.claude/skills/mule-development/` — can co-exist).

```bash
. "$HOME/.adlc/runtime/init-state.sh"

mkdir -p .claude/skills

# Discover top-level skills in the toolkit (any subdir containing SKILL.md).
created=0
preserved=0
relinked=0
for skill_dir in "$TOOLKIT_HOME"/*/; do
  [ -f "$skill_dir/SKILL.md" ] || continue
  name=$(basename "$skill_dir")
  dest=".claude/skills/$name"

  if [ -L "$dest" ]; then
    # Already a symlink. If it points elsewhere, repoint to current TOOLKIT_HOME
    # (handles toolkit relocation between init runs).
    cur_target=$(readlink "$dest" 2>/dev/null || true)
    expected="$skill_dir"
    expected="${expected%/}"
    if [ "$cur_target" != "$expected" ]; then
      ln -sfn "$expected" "$dest"
      relinked=$((relinked + 1))
    else
      preserved=$((preserved + 1))
    fi
  elif [ -e "$dest" ]; then
    # A real directory or file lives there — DO NOT overwrite (could be a
    # locally-customized skill or, for Mule, the installed mule-development
    # skill pack). Surface and skip.
    echo "  WARN: .claude/skills/$name exists and is not a symlink — preserved as-is."
    preserved=$((preserved + 1))
  else
    ln -s "${skill_dir%/}" "$dest"
    created=$((created + 1))
  fi
done

echo "Project-local skill symlinks: created=$created  relinked=$relinked  preserved=$preserved"
echo "All ADLC slash commands in this project now resolve to: $TOOLKIT_HOME"
```

The user should add `.claude/skills/` to git so the team gets the same resolution. (The symlinks are stable across machines as long as the toolkit lives at the same absolute path; otherwise re-running `/init` fixes them. For checked-in stability, a future enhancement could replace symlinks with thin proxy SKILL.md files — out of scope for now.)

### Step 2: Gather Project Context
Ask the user for the following (skip any that are already known from existing files):
1. **Project name** — What is this project called?
2. **What it does** — One paragraph description
3. **Tech stack** — Languages, frameworks, databases, cloud providers
4. **Project scope** — What's in scope vs out of scope
5. **Key architectural patterns** — Layered? Microservices? Monolith?

If a `CLAUDE.md`, `README.md`, or `package.json` exists, extract this info automatically and confirm with the user instead of asking.

### Step 3: Create Directory Structure

The directory layout differs slightly between SFDC and MuleSoft (different catalog/rules filenames). Use the layout matching `$STACK`.

**Common to both stacks:**
```
.adlc/
  ETHOS.md
  context/
    project-overview.md
    architecture.md
    conventions.md
    taxonomy.md
  specs/
    .gitkeep
  bugs/
    .gitkeep
  knowledge/
    assumptions/
      .gitkeep
    lessons/
      .gitkeep
  templates/
  partials/
  workflows/
```

**SFDC-only additions** (`$STACK = sfdc`):
```
.adlc/context/
  sf-skills-catalog.md
  salesforce-rules.md
```

**MuleSoft-only additions** (`$STACK = mulesoft`):
```
.adlc/context/
  mule-skills-catalog.md
  mulesoft-rules.md
.adlc/partials/
  mule-quality-checklist.md
```

**Why the local copies of ETHOS.md, templates, partials, and workflows?** Claude Code's sandbox blocks the `Read` tool from accessing paths outside the current working directory. When a skill runs inside a git worktree (e.g., `.claude/worktrees/<name>/`), `$TOOLKIT_HOME/...` becomes unreadable by subagents. Keeping copies under `.adlc/` makes the toolkit work identically in main checkouts and worktrees.

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
.adlc/.next-req
.adlc/.next-bug
.adlc/.next-lesson
.adlc/.next-req.lock.d/
.adlc/.next-bug.lock.d/
.adlc/.next-lesson.lock.d/
.adlc/.cache/

# Playwright session tokens & test artifacts
tests/e2e/storageState.json
reports/playwright/
playwright-report/
test-results/

# sf-code-audit project-local venv (auto-created by /init Step 7.8) and runtime reports
.adlc/tools/sf-code-audit/.venv/
.adlc/tools/sf-code-audit/__pycache__/
.adlc/runtime/audit/
```

### Step 6: Copy ETHOS.md, Templates, Partials, and Workflows Into the Project

Copy the canonical ETHOS.md and all templates/partials/workflows from the toolkit into the project so skills keep working inside git worktrees (where Read is sandboxed to the worktree root).

```bash
. "$HOME/.adlc/runtime/init-state.sh"

# Verify sources exist
if [ ! -f "$TOOLKIT_HOME/ETHOS.md" ] || [ ! -d "$TOOLKIT_HOME/templates" ] || [ ! -d "$TOOLKIT_HOME/partials" ] || [ ! -d "$TOOLKIT_HOME/workflows" ]; then
  echo "ERROR: Toolkit at $TOOLKIT_HOME appears corrupted (missing ETHOS.md / templates / partials / workflows)."
  exit 1
fi

# Copy ETHOS.md (overwrite — canonical is source of truth)
cp "$TOOLKIT_HOME/ETHOS.md" .adlc/ETHOS.md

# Copy templates (overwrite — canonical is source of truth)
mkdir -p .adlc/templates
cp "$TOOLKIT_HOME/templates"/*.md .adlc/templates/

# Copy partials (overwrite — canonical is source of truth)
mkdir -p .adlc/partials
cp "$TOOLKIT_HOME/partials"/*.sh .adlc/partials/
chmod +x .adlc/partials/*.sh

# Copy workflows — RUNTIME files only. Do NOT copy workflows/tests/ — those
# are toolkit-internal node:test files (CommonJS require) that break Jest in
# "type":"module" consumer repos.
mkdir -p .adlc/workflows
cp "$TOOLKIT_HOME/workflows"/*.workflow.js .adlc/workflows/
cp "$TOOLKIT_HOME/workflows/README.md" .adlc/workflows/
rm -rf .adlc/workflows/tests

# Clean up Finder-style duplicates if present (".adlc/* 2.md", "knowledge 2/", etc.)
find .adlc -depth \( -name "* 2" -o -name "* 2.*" \) -exec rm -rf {} + 2>/dev/null

# Advisory (Jest repos)
if grep -q '"jest"' package.json 2>/dev/null || find . -maxdepth 1 -name 'jest.config.*' 2>/dev/null | grep -q .; then
  echo "ADVISORY (Jest detected): .adlc/ contains no test files by design — default 'npm test' is unaffected. If you use a custom broad testMatch, add \"<rootDir>/.adlc/\" to testPathIgnorePatterns."
fi
```

If the user has previously made intentional customizations to their local `.adlc/ETHOS.md`, `.adlc/templates/*.md`, `.adlc/partials/*.sh`, or `.adlc/workflows/adlc-sprint.workflow.js`, confirm before overwriting. Use `/template-drift` to surface what differs.

### Step 7: Scaffold Retrieval Taxonomy

Copy the canonical taxonomy template to `.adlc/context/taxonomy.md` so authors of new REQs, bugs, and lessons have a reference vocabulary for retrieval tags.

**This step is idempotent — skip if the file already exists** (preserve any project-local customizations).

```bash
. "$HOME/.adlc/runtime/init-state.sh"

if [ ! -f "$TOOLKIT_HOME/templates/taxonomy-template.md" ]; then
  echo "ERROR: Taxonomy template not found at $TOOLKIT_HOME/templates/taxonomy-template.md."
  exit 1
fi

mkdir -p .adlc/context

if [ ! -f .adlc/context/taxonomy.md ]; then
  cp "$TOOLKIT_HOME/templates/taxonomy-template.md" .adlc/context/taxonomy.md
  echo "Created .adlc/context/taxonomy.md from canonical template."
else
  echo "Preserved existing .adlc/context/taxonomy.md (idempotent — not overwritten)."
fi
```

Advise the user: "Open `.adlc/context/taxonomy.md` and customize the example values for this codebase. Authors of new REQs, bugs, and lessons will reference this file when choosing tag values (`component`, `domain`, `stack`, `concerns`)."

### Step 7.4: (SFDC only) Scaffold Salesforce Clouds + Industry Domains taxonomy

**Skip this step entirely if `$STACK != sfdc`.**

The toolkit ships two canonical taxonomy files used by reviewer agents and by `/spec` retrieval:

- `.adlc/context/sf-clouds.md` — vocabulary of Salesforce Clouds (Sales, Service, Platform, Experience, FSC, Health, Life Sciences, Comms, Media, E&U, Mfg, CG, Auto, PSS, Education, Nonprofit, Net Zero, Loyalty + cross-cloud layers OmniStudio / Data Cloud / Agentforce / MuleSoft / Slack / Heroku / Field Service / Payments). Each entry carries an India-specific contextual note (DPDP, GST, ABDM, ONDC, RBI, IRDAI, SEBI, TRAI, etc.).
- `.adlc/context/industry-domains.md` — vocabulary of business industry domains (BFSI, Healthcare, CME, Manufacturing, Auto, Consumer & Retail, Public Sector, Education, Nonprofit) plus cross-cutting concerns (kyc-aml, payments, compliance-data-privacy, tax-gst-india, field-execution, contact-center, digital-onboarding, revenue-billing, sustainability-esg, partner-distributor). India-specific anchors throughout.

This step (a) copies both files into the consumer repo, (b) prompts the user to pick the clouds and domains in scope, and (c) writes those selections into `.adlc/config.yml`.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

if [ "$STACK" = "sfdc" ]; then
  TOOLKIT_CTX="$TOOLKIT_HOME/.adlc/context"

  if [ ! -f "$TOOLKIT_CTX/sf-clouds.md" ] || [ ! -f "$TOOLKIT_CTX/industry-domains.md" ]; then
    echo "ERROR: Cloud/domain taxonomy files not found at $TOOLKIT_CTX. Toolkit appears corrupted."
    exit 1
  fi

  mkdir -p .adlc/context

  # Overwrite — canonical, machine-consumed dispatch tables.
  cp "$TOOLKIT_CTX/sf-clouds.md" .adlc/context/sf-clouds.md
  cp "$TOOLKIT_CTX/industry-domains.md" .adlc/context/industry-domains.md
  echo "Synced .adlc/context/sf-clouds.md and .adlc/context/industry-domains.md from toolkit canonical."
fi
```

Then **prompt the user** (skip this prompting if `$STACK != sfdc` or if `.adlc/config.yml` already has non-empty `salesforce.clouds:` AND non-empty `industry_domains:` — preserve user-customized values).

**Cloud selection (multi-select via AskUserQuestion).** Ask:

> "Which Salesforce Clouds will this project deploy metadata into or integrate with at runtime? Pick all that apply. The full vocabulary is in `.adlc/context/sf-clouds.md`."

Present the most common selections as quick options (Platform is always included automatically; do not present it):
- **Sales Cloud** — Lead/Opportunity/Account CRM, Forecasting, CPQ
- **Service Cloud** — Case/Entitlement/Knowledge/Omni-Channel/Field Service
- **Experience Cloud** — partner portals, customer self-service, dealer/distributor sites
- **Data Cloud** — DLO/DMO/Calculated Insights/Identity Resolution/Activations
- **Agentforce** — Topic/Action/Plan, Atlas Reasoning, Prompt Builder
- **OmniStudio** — OmniScript/FlexCard/DataRaptor/Integration Procedure
- **Marketing Cloud Engagement** — Journey Builder, Email/Mobile/AMPscript
- **Account Engagement (Pardot)** — B2B marketing automation
- **Commerce Cloud B2C** — SFRA/SCAPI/Composable Storefront
- **Commerce Cloud B2B** — native B2B storefront
- **Revenue Cloud** — CPQ + Billing + Subscription
- **Financial Services Cloud** — banking/wealth/insurance data model
- **Health Cloud** — patient/care plan/provider network
- **Life Sciences Cloud** — clinical trial / patient services / MSL
- **Communications Cloud (CME)** — telco EPC / order mgmt
- **Media Cloud** — broadcast/digital media patterns
- **Energy & Utilities Cloud** — discom/genco/transco data model
- **Manufacturing Cloud** — Sales Agreement / Run-Rate Forecast / Rebate
- **Consumer Goods Cloud** — Retail Execution / Visit Planner / TPM
- **Automotive Cloud** — OEM-Dealer-Customer 360 / VIN / Service
- **Public Sector Solutions** — LPI / Benefits / Grants / Constituent 360
- **Education Cloud** — Student 360 / Admissions / Advising
- **Nonprofit Cloud** — Donor / Gift / Program Mgmt
- **Net Zero Cloud** — Scope 1/2/3 emissions accounting
- **Field Service** — Service Appointment / Resource / Dispatch
- **Slack** — Slack Connect / Workflow Builder
- **MuleSoft (integration contract)** — RAML/OAS contracts on Anypoint
- **Other** — user types in a key from `.adlc/context/sf-clouds.md`

The user picks one or more. Always also include `platform` automatically. Map each user-picked label to its key in `.adlc/context/sf-clouds.md` (e.g., "Financial Services Cloud" → `financial-services-cloud`).

**Industry domain selection (multi-select via AskUserQuestion).** Ask:

> "Which business industry domains will this project serve? Pick all that apply. The full vocabulary is in `.adlc/context/industry-domains.md`."

Present grouped options. The user can pick across groups:

*BFSI:* `banking-retail`, `banking-corporate`, `banking-sme`, `wealth-management`, `capital-markets`, `insurance-life`, `insurance-general`, `insurance-reinsurance`, `payments`, `lending-digital`, `microfinance`, `account-aggregator`, `kyc-aml`

*Healthcare & Life Sciences:* `provider-hospital`, `provider-clinic`, `payer`, `medtech-devices`, `pharma-rx`, `pharma-generics`, `pharma-biotech`, `clinical-trials`

*CME:* `telco-consumer`, `telco-enterprise`, `telco-network-ops`, `media-broadcast`, `media-digital`, `energy-utilities-power`, `energy-utilities-water-gas`, `energy-renewables`, `oil-and-gas`

*Manufacturing & Auto:* `manufacturing-discrete`, `manufacturing-process`, `automotive-oem`, `automotive-aftermarket`, `automotive-mobility`, `industrial-machinery`

*Consumer & Retail:* `cpg-fmcg`, `cpg-durables`, `retail-fashion`, `retail-grocery`, `retail-pharmacy-omni`, `qsr-foodservice`, `travel-hospitality`, `loyalty-cobrand`, `e-commerce-marketplace`

*Public Sector & Education:* `government-central`, `government-state`, `government-municipal`, `government-defense`, `education-k12`, `education-higher`, `education-edtech`, `nonprofit-india`

*Cross-cutting:* `compliance-data-privacy`, `tax-gst-india`, `field-execution`, `contact-center`, `digital-onboarding`, `revenue-billing`, `sustainability-esg`, `partner-distributor`

The user picks one or more domain keys. If the user is unsure, default to no domains (`[]`) — they can edit `.adlc/config.yml` later.

**Persist the selections** into `.adlc/config.yml`:

```bash
. "$HOME/.adlc/runtime/init-state.sh"

if [ "$STACK" = "sfdc" ]; then
  # Picked values come from AskUserQuestion above. The skill body should set
  # these two shell vars before this block:
  #   CLOUDS="platform sales-cloud service-cloud experience-cloud"
  #   DOMAINS="banking-retail kyc-aml payments"
  CLOUDS="${CLOUDS:-platform}"
  DOMAINS="${DOMAINS:-}"

  # Convert space-separated lists to YAML inline-array form: "[a, b, c]"
  to_yaml_array() {
    list="$1"
    [ -z "$list" ] && { printf '[]'; return; }
    out=""
    for k in $list; do
      [ -z "$out" ] && out="$k" || out="$out, $k"
    done
    printf '[%s]' "$out"
  }

  CLOUDS_YAML=$(to_yaml_array "$CLOUDS")
  DOMAINS_YAML=$(to_yaml_array "$DOMAINS")

  # India-context auto-detect: any India-tier domain flips this on.
  INDIA_TRIGGER_KEYS=" banking-retail banking-corporate banking-sme wealth-management capital-markets insurance-life insurance-general insurance-reinsurance payments lending-digital microfinance account-aggregator kyc-aml provider-hospital provider-clinic payer medtech-devices pharma-rx pharma-generics pharma-biotech clinical-trials telco-consumer telco-enterprise telco-network-ops media-broadcast media-digital energy-utilities-power energy-utilities-water-gas energy-renewables oil-and-gas manufacturing-discrete manufacturing-process automotive-oem automotive-aftermarket automotive-mobility cpg-fmcg cpg-durables retail-fashion retail-grocery retail-pharmacy-omni qsr-foodservice e-commerce-marketplace government-central government-state government-municipal government-defense education-k12 education-higher education-edtech nonprofit-india tax-gst-india compliance-data-privacy "
  INDIA_FLAG="false"
  for d in $DOMAINS; do
    case "$INDIA_TRIGGER_KEYS" in
      *" $d "*) INDIA_FLAG="true"; break ;;
    esac
  done

  # Write under salesforce.clouds:, salesforce.india_context:, and top-level industry_domains:
  python3 - "$CLOUDS_YAML" "$DOMAINS_YAML" "$INDIA_FLAG" <<'PY'
import sys, re, pathlib
clouds_yaml, domains_yaml, india_flag = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path('.adlc/config.yml')
text = p.read_text()

def upsert_under_block(text, block, key, value):
    """Insert or replace `  key: value` inside the named top-level block."""
    pattern = re.compile(rf'(^{block}:\n(?:[ \t]+.*\n)*)', re.M)
    m = pattern.search(text)
    if not m:
        return text  # block missing — leave file alone
    body = m.group(1)
    line_re = re.compile(rf'^([ \t]+){re.escape(key)}:\s*.*$', re.M)
    if line_re.search(body):
        new_body = line_re.sub(lambda mm: f'{mm.group(1)}{key}: {value}', body)
    else:
        # Append before the block ends.
        indent = '  '
        # Detect indent from existing lines under the block.
        first_indent = re.search(r'^([ \t]+)\S', body[len(f"{block}:\n"):], re.M)
        if first_indent:
            indent = first_indent.group(1)
        new_body = body.rstrip() + f'\n{indent}{key}: {value}\n'
    return text.replace(body, new_body, 1)

def upsert_top_level(text, key, value):
    line_re = re.compile(rf'^{re.escape(key)}:\s*.*$', re.M)
    if line_re.search(text):
        return line_re.sub(f'{key}: {value}', text, count=1)
    return text.rstrip() + f'\n\n{key}: {value}\n'

text = upsert_under_block(text, 'salesforce', 'clouds', clouds_yaml)
text = upsert_under_block(text, 'salesforce', 'india_context', india_flag)
text = upsert_top_level(text, 'industry_domains', domains_yaml)

p.write_text(text)
print(f"Wrote salesforce.clouds={clouds_yaml}, salesforce.india_context={india_flag}, industry_domains={domains_yaml}")
PY
fi
```

Tell the user:
- Selected clouds and industry domains have been written to `.adlc/config.yml`.
- If `salesforce.india_context: true` was set, every reviewer agent will pull in DPDP/GST/ABDM/ONDC/RBI/IRDAI/SEBI/TRAI anchors when relevant.
- The selections are editable any time — open `.adlc/config.yml` and add/remove keys from the `clouds:` and `industry_domains:` lists.
- The full vocabulary lives in `.adlc/context/sf-clouds.md` and `.adlc/context/industry-domains.md`.

### Step 7.5: Scaffold stack-specific skills catalog & rules

Copy the canonical skills dispatch table and rules baseline into the consumer repo's `.adlc/context/`. Branches on `$STACK`.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

mkdir -p .adlc/context

if [ "$STACK" = "sfdc" ]; then
  TOOLKIT_CTX="$TOOLKIT_HOME/.adlc/context"
  if [ ! -f "$TOOLKIT_CTX/sf-skills-catalog.md" ] || [ ! -f "$TOOLKIT_CTX/salesforce-rules.md" ]; then
    echo "ERROR: Salesforce context files not found at $TOOLKIT_CTX. Toolkit appears corrupted."
    exit 1
  fi

  # Catalog: overwrite — canonical, machine-consumed dispatch table
  cp "$TOOLKIT_CTX/sf-skills-catalog.md" .adlc/context/sf-skills-catalog.md
  echo "Synced .adlc/context/sf-skills-catalog.md from toolkit canonical."

  # Rules: overwrite if missing or unchanged. If hand-customized, surface a /template-drift advisory.
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

elif [ "$STACK" = "mulesoft" ]; then
  TOOLKIT_CTX="$TOOLKIT_HOME/.adlc/context"
  TOOLKIT_PARTIALS="$TOOLKIT_HOME/partials"
  if [ ! -f "$TOOLKIT_CTX/mule-skills-catalog.md" ] || [ ! -f "$TOOLKIT_CTX/mulesoft-rules.md" ] || [ ! -f "$TOOLKIT_PARTIALS/mule-quality-checklist.md" ]; then
    echo "ERROR: MuleSoft context files not found at $TOOLKIT_CTX or $TOOLKIT_PARTIALS. Toolkit appears corrupted."
    exit 1
  fi

  mkdir -p .adlc/partials

  cp "$TOOLKIT_CTX/mule-skills-catalog.md" .adlc/context/mule-skills-catalog.md
  echo "Synced .adlc/context/mule-skills-catalog.md from toolkit canonical."

  if [ ! -f .adlc/context/mulesoft-rules.md ]; then
    cp "$TOOLKIT_CTX/mulesoft-rules.md" .adlc/context/mulesoft-rules.md
    echo "Created .adlc/context/mulesoft-rules.md from toolkit canonical."
  else
    if ! cmp -s "$TOOLKIT_CTX/mulesoft-rules.md" .adlc/context/mulesoft-rules.md; then
      echo "Preserved existing .adlc/context/mulesoft-rules.md (differs from toolkit). Run /template-drift to review and sync."
    else
      echo "Preserved existing .adlc/context/mulesoft-rules.md (already in sync)."
    fi
  fi

  cp "$TOOLKIT_PARTIALS/mule-quality-checklist.md" .adlc/partials/mule-quality-checklist.md
  echo "Synced .adlc/partials/mule-quality-checklist.md from toolkit canonical."
fi
```

Without these files in the consumer repo, the architect/implementer/reviewers fall back to first-principles reasoning, which is the failure mode that ships hand-rolled scaffolding instead of canonical generator output.

### Step 7.6: (MuleSoft only) Validate prerequisites & install official skill pack

**Skip this step entirely if `$STACK = sfdc`.**

The MuleSoft toolkit depends on Node 20+, JDK 17, Maven 3.8+, `anypoint-cli-v4`, two Anypoint connected apps (DX MCP + Platform MCP), and the official `mulesoft/mulesoft-dx/skills/mule-development` skill pack.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

if [ "$STACK" != "mulesoft" ]; then
  echo "Step 7.6 skipped — not a MuleSoft project."
else
  # 1. Node version check
  node_version=$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1 || echo 0)
  if [ "${node_version:-0}" -lt 20 ] 2>/dev/null; then
    echo "ERROR: Node.js 20+ required (found ${node_version:-none}). Install from https://nodejs.org/"
    exit 1
  fi

  # 2. Java version check
  if ! command -v java >/dev/null 2>&1; then
    echo "ERROR: Java not found. Install JDK 17 (LTS)."
    exit 1
  fi
  java_version=$(java -version 2>&1 | head -1 | sed -E 's/.*"([0-9]+).*/\1/')
  if [ "${java_version:-0}" -lt 17 ] 2>/dev/null; then
    echo "WARN: Java ${java_version:-unknown} detected — Mule 4.6+ runtime requires JDK 17 (LTS). Mule may fail to build."
  fi

  # 3. Maven check
  if ! command -v mvn >/dev/null 2>&1; then
    echo "ERROR: Maven 3.8+ required. Install via brew/apt/sdkman."
    exit 1
  fi

  # 4. anypoint-cli-v4 check
  if ! command -v anypoint-cli-v4 >/dev/null 2>&1; then
    echo "ERROR: anypoint-cli-v4 not found. Install: npm install -g @mulesoft/anypoint-cli-v4"
    echo "  Then authenticate: anypoint-cli-v4 conf client_id <ID>; anypoint-cli-v4 conf client_secret <SECRET>"
    exit 1
  fi

  # 5. Connected-app credentials check (env vars)
  missing_creds=""
  [ -z "${ANYPOINT_CLIENT_ID:-}" ] && missing_creds="${missing_creds}  - ANYPOINT_CLIENT_ID (DX MCP)\n"
  [ -z "${ANYPOINT_CLIENT_SECRET:-}" ] && missing_creds="${missing_creds}  - ANYPOINT_CLIENT_SECRET (DX MCP)\n"
  [ -z "${ANYPOINT_PLATFORM_CLIENT_ID:-}" ] && missing_creds="${missing_creds}  - ANYPOINT_PLATFORM_CLIENT_ID (Platform MCP)\n"
  [ -z "${ANYPOINT_PLATFORM_CLIENT_SECRET:-}" ] && missing_creds="${missing_creds}  - ANYPOINT_PLATFORM_CLIENT_SECRET (Platform MCP)\n"
  if [ -n "$missing_creds" ]; then
    echo "WARN: Missing connected-app credentials in environment:"
    printf "$missing_creds"
    echo "  Without these, the MCP servers wired in .mcp.json will fail to start."
    echo "  Two options:"
    echo "    1. Export them in your shell rc: export ANYPOINT_CLIENT_ID=..."
    echo "    2. Create a project-local .env (gitignored) and source before running Claude Code."
  fi

  # 6. Install the official MuleSoft skill pack
  if [ -d .claude/skills/mule-development ] || [ -d .agents/skills/mule-development ]; then
    echo "Official MuleSoft skill pack already installed — skipping."
  else
    echo "Installing official MuleSoft skill pack via npx skills add..."
    if npx -y skills add mulesoft/mulesoft-dx/skills/mule-development --target claude-code --scope project --method symlink; then
      echo "  Done."
    else
      echo "WARN: 'npx skills add mulesoft/mulesoft-dx/skills/mule-development' failed."
      echo "  Re-run manually after fixing the cause (commonly: anypoint-cli-v4 not authenticated, or anypoint-cli-dx-mule-plugin missing)."
    fi
  fi
fi
```

### Step 7.7: (MuleSoft only) Wire `.env.example` for connected-app credentials

**Skip this step entirely if `$STACK = sfdc`.**

The `templates/claude-settings-template.json` already includes the `mcpServers` block. Step 1.6 copied that to `.claude/settings.json`. This step generates a project-local `.env.example` so contributors know which env vars to populate, and confirms `.env` is gitignored.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

if [ "$STACK" = "mulesoft" ]; then
  if [ ! -f .env.example ]; then
    cat > .env.example <<'EOF'
# MuleSoft connected-app credentials. Copy this file to .env (gitignored)
# and fill in your Client ID / Secret values from Anypoint Platform.
#
# DX MCP — connected app acting on its own behalf (client credentials grant).
ANYPOINT_CLIENT_ID=
ANYPOINT_CLIENT_SECRET=
ANYPOINT_REGION=PROD_US

# Platform MCP — connected app acting on user's behalf (Authorization Code +
# Refresh Token grant).
ANYPOINT_PLATFORM_CLIENT_ID=
ANYPOINT_PLATFORM_CLIENT_SECRET=
EOF
    echo "Created .env.example documenting required MCP env vars."
  fi

  if [ -f .gitignore ] && ! grep -q '^\.env$' .gitignore; then
    echo ".env" >> .gitignore
    echo "Added '.env' to .gitignore."
  fi
fi
```

Document the connected-app setup steps in the project README so other developers can configure their machines (DX MCP + Platform MCP scopes — see toolkit README "Consumer prerequisites").

### Step 7.8: (SFDC only) Install the source-only Salesforce code audit gate

**Skip this step entirely if `$STACK != sfdc`.**

The toolkit ships a vendored copy of `salesforce-code-audit-tool v1.2.13` under `tools/sf-code-audit/`. This step copies the analyzer modules (Apex pattern matcher, LWC analyzer, grading engine) plus the source-only CLI (`audit_source.py`) into the consumer repo so the `/reflect` Phase 5a gate can fire **without an org** and inside any git worktree.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

if [ "$STACK" = "sfdc" ]; then
  TOOLKIT_AUDIT="$TOOLKIT_HOME/tools/sf-code-audit"
  TOOLKIT_PARTIAL="$TOOLKIT_HOME/partials/run-source-audit.sh"

  if [ ! -f "$TOOLKIT_AUDIT/audit_source.py" ] || [ ! -f "$TOOLKIT_PARTIAL" ]; then
    echo "ERROR: Audit tool not found at $TOOLKIT_AUDIT or $TOOLKIT_PARTIAL. Toolkit appears corrupted."
    exit 1
  fi

  mkdir -p .adlc/tools/sf-code-audit .adlc/partials .adlc/runtime/audit

  # Copy analyzer + grading + CLI modules (overwrite — canonical source-of-truth).
  cp "$TOOLKIT_AUDIT/audit_source.py" .adlc/tools/sf-code-audit/
  cp "$TOOLKIT_AUDIT/pattern_matcher.py" .adlc/tools/sf-code-audit/
  cp "$TOOLKIT_AUDIT/lwc_analyzer.py" .adlc/tools/sf-code-audit/
  cp "$TOOLKIT_AUDIT/grading_engine.py" .adlc/tools/sf-code-audit/
  cp "$TOOLKIT_AUDIT/tool_version.json" .adlc/tools/sf-code-audit/
  cp "$TOOLKIT_AUDIT/update_config.json" .adlc/tools/sf-code-audit/
  cp "$TOOLKIT_AUDIT/README.md" .adlc/tools/sf-code-audit/

  # Org-connected CLI is optional — copy it too so manual deep audits work.
  # These have heavier deps (simple-salesforce, pandas, openpyxl, reportlab)
  # which are NOT installed by default; pip install requirements.txt on demand.
  cp "$TOOLKIT_AUDIT/salesforce_audit.py" .adlc/tools/sf-code-audit/ 2>/dev/null || true
  cp "$TOOLKIT_AUDIT/sf_utils.py"        .adlc/tools/sf-code-audit/ 2>/dev/null || true
  cp "$TOOLKIT_AUDIT/report_generator.py" .adlc/tools/sf-code-audit/ 2>/dev/null || true
  cp "$TOOLKIT_AUDIT/run_audit.sh"        .adlc/tools/sf-code-audit/ 2>/dev/null || true
  cp "$TOOLKIT_AUDIT/requirements.txt"    .adlc/tools/sf-code-audit/ 2>/dev/null || true
  cp "$TOOLKIT_AUDIT/UPSTREAM-README.md"  .adlc/tools/sf-code-audit/ 2>/dev/null || true
  cp "$TOOLKIT_AUDIT/GRADING_SYSTEM_DETAILED.md"     .adlc/tools/sf-code-audit/ 2>/dev/null || true
  cp "$TOOLKIT_AUDIT/VIOLATION_CATEGORIES_CORRECTED.md" .adlc/tools/sf-code-audit/ 2>/dev/null || true
  [ -f .adlc/tools/sf-code-audit/run_audit.sh ] && chmod +x .adlc/tools/sf-code-audit/run_audit.sh

  # Pipeline wrapper.
  cp "$TOOLKIT_PARTIAL" .adlc/partials/run-source-audit.sh
  chmod +x .adlc/partials/run-source-audit.sh

  # Verify python3 is reachable. Source-only mode is stdlib-only, but we still
  # build a project-local venv so the org-connected CLI (salesforce_audit.py)
  # is also zero-friction the first time someone runs it. No pip pollution of
  # the system Python.
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found on PATH. The audit gate requires Python 3.8+."
    echo "  Install Python 3 from https://www.python.org/downloads/ and re-run /init."
    exit 1
  fi

  PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if [ "${PY_MAJOR:-0}" -lt 3 ] 2>/dev/null || { [ "${PY_MAJOR:-0}" = "3" ] && [ "${PY_MINOR:-0}" -lt 8 ] 2>/dev/null; }; then
    echo "ERROR: Python ${PY_VER} is below the 3.8 minimum required by the audit tool."
    echo "  Install Python 3.8+ from https://www.python.org/downloads/ and re-run /init."
    exit 1
  fi
  echo "Python found: $PY_VER"

  # Create the project-local venv and install all audit deps. The venv is
  # gitignored (Step 5 added the entry). Skippable via ADLC_INIT_SKIP_AUDIT_PIP=1
  # for offline / firewalled environments — the source-only gate still works
  # without these deps; only the org-connected CLI needs them.
  VENV_DIR=".adlc/tools/sf-code-audit/.venv"
  if [ "${ADLC_INIT_SKIP_AUDIT_PIP:-0}" = "1" ]; then
    echo "Skipped audit-tool venv setup (ADLC_INIT_SKIP_AUDIT_PIP=1)."
    echo "  Source-only /reflect gate still works (stdlib only)."
    echo "  Org-connected salesforce_audit.py needs deps:"
    echo "    python3 -m venv $VENV_DIR"
    echo "    $VENV_DIR/bin/python -m pip install -r .adlc/tools/sf-code-audit/requirements.txt"
  else
    if [ ! -d "$VENV_DIR" ]; then
      echo "Creating audit tool venv at $VENV_DIR (one-time)..."
      if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
        echo "WARN: 'python3 -m venv' failed (is the 'venv' module available?)."
        echo "  On Debian/Ubuntu: sudo apt install python3-venv"
        echo "  Source-only audit gate will still work via system python3."
      fi
    else
      echo "Audit tool venv already present at $VENV_DIR — reusing."
    fi

    if [ -x "$VENV_DIR/bin/python" ]; then
      echo "Installing audit tool dependencies into venv (one-time, no system pollution)..."
      # Quiet, but capture failures. The source-only gate only needs stdlib —
      # if pip install fails (offline, firewall, build error), surface a warning
      # but DO NOT fail /init. The wrapper falls back to system python3 and
      # source-only mode keeps working.
      if "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip 2>/dev/null \
         && "$VENV_DIR/bin/python" -m pip install --quiet -r .adlc/tools/sf-code-audit/requirements.txt; then
        echo "  Done. Org-connected salesforce_audit.py is ready (no manual pip needed)."
      else
        echo "WARN: pip install failed. The source-only audit gate still works (stdlib only)."
        echo "  To retry the org-connected CLI deps later (e.g., once you're on a network):"
        echo "    $VENV_DIR/bin/python -m pip install -r .adlc/tools/sf-code-audit/requirements.txt"
      fi
    fi
  fi

  echo "Installed source-only audit at .adlc/tools/sf-code-audit/ and wrapper at .adlc/partials/run-source-audit.sh"
fi
```

After this step, the consumer repo has:
- `.adlc/tools/sf-code-audit/audit_source.py` — source-only CLI (Apex + LWC, no org)
- `.adlc/tools/sf-code-audit/salesforce_audit.py` — full org-connected CLI (manual deep audits)
- `.adlc/partials/run-source-audit.sh` — wrapper that reads `.adlc/config.yml` `audit:` block and runs the gate
- `.adlc/runtime/audit/` — output directory for `source-audit.json` + `source-audit.md`

`/reflect` Phase 1.5 calls the wrapper and refuses to dispatch the LLM reviewer when the gate fails. The default policy (`audit.fail_on: "CRITICAL,HIGH"`) blocks the pipeline when any CRITICAL or HIGH finding lands in toolkit-generated code.

Tell the user: "The Salesforce code audit gate is wired into `/reflect`. It runs against changed files (diff scope) by default and blocks on `CRITICAL`/`HIGH` findings. Tune via `.adlc/config.yml` → `audit:` block. The `salesforce_audit.py` org-connected CLI is also installed for manual deep audits — `pip install -r .adlc/tools/sf-code-audit/requirements.txt` first."

### Step 8: Verify `.claude/settings.json` (Step 1.6 already created it)

```bash
. "$HOME/.adlc/runtime/init-state.sh"

if [ ! -f .claude/settings.json ]; then
  echo "WARN: .claude/settings.json missing — Step 1.6 should have created it. Re-running scaffold."
  mkdir -p .claude
  cp "$TOOLKIT_HOME/templates/claude-settings-template.json" .claude/settings.json
  echo "Created .claude/settings.json from canonical template (late fallback)."
else
  echo "Verified .claude/settings.json present (created in Step 1.6)."
fi
```

### Step 8.5: Backfill user-wait hooks into pre-existing settings

When `.claude/settings.json` already existed (Step 1.6 preserved it), it may pre-date the user-wait hooks added in this version of the template. Detect that case and merge in just the hook block — never overwrite the user's allowlist customizations.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

if [ -f .claude/settings.json ] && ! grep -q '"UserPromptSubmit"' .claude/settings.json; then
  echo "Backfilling user-wait hooks into existing .claude/settings.json..."
  node -e '
    const fs = require("fs");
    const file = ".claude/settings.json";
    const cur = JSON.parse(fs.readFileSync(file, "utf8"));
    cur.hooks = cur.hooks || {};
    const stopCmd = "mkdir -p ~/.adlc/runtime && printf \x27{\\\"ts\\\":\\\"%s\\\",\\\"kind\\\":\\\"stop\\\",\\\"session\\\":\\\"%s\\\",\\\"cwd\\\":\\\"%s\\\"}\\\\n\x27 \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" \"${CLAUDE_SESSION_ID:-unknown}\" \"${CLAUDE_PROJECT_DIR:-$PWD}\" >> ~/.adlc/runtime/user-wait.jsonl";
    const submitCmd = stopCmd.replace("\\\"kind\\\":\\\"stop\\\"", "\\\"kind\\\":\\\"submit\\\"");
    cur.hooks.Stop = cur.hooks.Stop || [];
    cur.hooks.UserPromptSubmit = cur.hooks.UserPromptSubmit || [];
    cur.hooks.Stop.push({matcher:"*", hooks:[{type:"command", command:stopCmd}]});
    cur.hooks.UserPromptSubmit.push({matcher:"*", hooks:[{type:"command", command:submitCmd}]});
    fs.writeFileSync(file, JSON.stringify(cur, null, 2) + "\n");
    console.log("OK: appended Stop + UserPromptSubmit hooks");
  '
fi
```

### Step 9: Scaffold `.adlc/config.yml` and resolve `project.shortname`

`.adlc/config.yml` is **required for every project** because the ADLC ID allocator reads `project.shortname` to namespace REQ / BUG / LESSON ids as `<XYZ>-REQ-NNN`.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

if [ ! -f "$TOOLKIT_HOME/templates/config-template.yml" ]; then
  echo "ERROR: Config template not found at $TOOLKIT_HOME/templates/config-template.yml."
  exit 1
fi

if [ ! -f .adlc/config.yml ]; then
  cp "$TOOLKIT_HOME/templates/config-template.yml" .adlc/config.yml
  echo "Created .adlc/config.yml from template."
else
  echo "Preserved existing .adlc/config.yml."
fi
```

Then **resolve `project.shortname`**:

1. Ask the user: "Pick a 3-uppercase-letter shortname for this project (used in IDs like `XYZ-REQ-001`). Pick something unique across every repo on your machine — once specs exist, changing it requires a migration."
   - SFDC examples: `SFC` (Salesforce-Customer-360), `ORD` (Order-Mgmt), `PRT` (Partner-Portal)
   - MuleSoft examples: `MUL` (MuleSoft-Integrations), `ORD` (Order-Process-API), `BNK` (Banking-Experience-API)
2. Validate against `^[A-Z]{3}$`. Reject anything else and re-prompt.
3. Write under `project.shortname` in `.adlc/config.yml`. If a value already exists and matches the regex, preserve it; if it's the placeholder `XYZ`, prompt for a real value.
4. **Auto-fill the dependent fields** (stack-specific):

```bash
. "$HOME/.adlc/runtime/init-state.sh"

PROJECT_DIR=$(basename "$(pwd)")
SHORTNAME="$shortname"   # set by the prior validation block

if [ "$STACK" = "sfdc" ]; then
  # salesforce.app_prefix — default to project.shortname.
  if grep -qE '^[[:space:]]*app_prefix:[[:space:]]*"XYZ"[[:space:]]*$' .adlc/config.yml; then
    sed -i.bak -E "s|^([[:space:]]*app_prefix:[[:space:]]*)\"XYZ\"|\1\"$SHORTNAME\"|" .adlc/config.yml && rm .adlc/config.yml.bak
    echo "Set salesforce.app_prefix='$SHORTNAME'"
  fi
  # salesforce.org_alias — default to basename of repo root.
  if grep -qE '^[[:space:]]*org_alias:[[:space:]]*"<repo-basename>"[[:space:]]*$' .adlc/config.yml; then
    sed -i.bak -E "s|^([[:space:]]*org_alias:[[:space:]]*)\"<repo-basename>\"|\1\"$PROJECT_DIR\"|" .adlc/config.yml && rm .adlc/config.yml.bak
    echo "Set salesforce.org_alias='$PROJECT_DIR'"
  fi
  # orgs.sandbox — same convention.
  if grep -qE '^[[:space:]]*sandbox:[[:space:]]*"<repo-basename>"[[:space:]]*$' .adlc/config.yml; then
    sed -i.bak -E "s|^([[:space:]]*sandbox:[[:space:]]*)\"<repo-basename>\"|\1\"$PROJECT_DIR\"|" .adlc/config.yml && rm .adlc/config.yml.bak
    echo "Set orgs.sandbox='$PROJECT_DIR'"
  fi

elif [ "$STACK" = "mulesoft" ]; then
  # mulesoft.app_prefix — default to project.shortname.
  if grep -qE '^[[:space:]]*app_prefix:[[:space:]]*"XYZ"[[:space:]]*$' .adlc/config.yml; then
    sed -i.bak -E "s|^([[:space:]]*app_prefix:[[:space:]]*)\"XYZ\"|\1\"$SHORTNAME\"|" .adlc/config.yml && rm .adlc/config.yml.bak
    echo "Set mulesoft.app_prefix='$SHORTNAME'"
  fi
  # orgs.sandbox — default to basename of repo root.
  if grep -qE '^[[:space:]]*sandbox:[[:space:]]*"<repo-basename>"[[:space:]]*$' .adlc/config.yml; then
    sed -i.bak -E "s|^([[:space:]]*sandbox:[[:space:]]*)\"<repo-basename>\"|\1\"$PROJECT_DIR\"|" .adlc/config.yml && rm .adlc/config.yml.bak
    echo "Set orgs.sandbox='$PROJECT_DIR'"
  fi
fi
```

For MuleSoft, the user must still **manually configure** values per their Anypoint org (no sensible auto-default):
- `mulesoft.anypoint_org_id`, `mulesoft.anypoint_environment`, `mulesoft.anypoint_region`, `mulesoft.api_layer`
- `mulesoft.governance.required_policies` (when `api_manager_enabled: true`)

Verify shortname:
```bash
. "$HOME/.adlc/runtime/init-state.sh"

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

**Cross-repo (optional add-on)**. If the user says this repo will share features with other repos, edit the `repos:` block in `.adlc/config.yml` to list siblings.

### Step 10: Scaffold Playwright UI harness (when applicable)

Required when `.adlc/config.yml` declares a non-empty `playwright_specs:`. SFDC default seeds `tests/e2e`; MuleSoft default is empty (most Mule projects are headless), so this typically only runs on SFDC or on Mule Experience APIs that render HTML.

**Skip this step entirely** when:
- `.adlc/config.yml` does not declare `playwright_specs:` or sets it to empty, OR
- For SFDC: `stack.frontends` does not include `lwc` AND no `force-app/**/lwc/**` directory exists AND `industries:` does not include `omnistudio` or `agentforce`.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

# Toolkits ship the Playwright harness under templates/playwright/. Both
# toolkits have an identical copy.
TOOLKIT_PW="$TOOLKIT_HOME/templates/playwright"
if [ ! -d "$TOOLKIT_PW" ]; then
  echo "ERROR: Playwright harness template not found at $TOOLKIT_PW. Toolkit appears corrupted."
  exit 1
fi

pw_specs=$(awk '/^playwright_specs:/ { sub(/^playwright_specs:[[:space:]]*/, ""); gsub(/["'\'']/, ""); sub(/[[:space:]]*#.*$/, ""); print; exit }' .adlc/config.yml 2>/dev/null)
if [ -z "$pw_specs" ]; then
  # Silent skip — most MuleSoft projects (and SFDC projects with playwright_specs
  # disabled) don't need the harness. Set ADLC_INIT_VERBOSE=1 for the audit line.
  [ "${ADLC_INIT_VERBOSE:-0}" = "1" ] && echo "Skipped Playwright harness scaffold — playwright_specs is not declared in .adlc/config.yml."
  :
else
  # 1. playwright.config.ts at repo root
  if [ ! -f playwright.config.ts ]; then
    cp "$TOOLKIT_PW/playwright.config.ts" playwright.config.ts
    echo "Created playwright.config.ts from canonical template."
  else
    echo "Preserved existing playwright.config.ts."
  fi

  # 2. tests/e2e/global-setup.ts
  mkdir -p "$pw_specs"
  if [ ! -f "$pw_specs/global-setup.ts" ]; then
    cp "$TOOLKIT_PW/tests/e2e/global-setup.ts" "$pw_specs/global-setup.ts"
    echo "Created $pw_specs/global-setup.ts from canonical template."
  else
    echo "Preserved existing $pw_specs/global-setup.ts."
  fi

  # 3. example.spec.ts.example
  if [ ! -f "$pw_specs/example.spec.ts.example" ]; then
    cp "$TOOLKIT_PW/tests/e2e/example.spec.ts.example" "$pw_specs/example.spec.ts.example"
    echo "Created $pw_specs/example.spec.ts.example."
  fi

  # 4. tests/e2e/.gitignore
  if [ ! -f "$pw_specs/.gitignore" ]; then
    cp "$TOOLKIT_PW/tests/e2e/.gitignore" "$pw_specs/.gitignore"
  fi

  # 5. README.md inside the harness dir
  if [ ! -f "$pw_specs/README.md" ]; then
    cp "$TOOLKIT_PW/README.md" "$pw_specs/README.md"
  fi

  # 6. Wire Playwright into package.json
  if [ "${ADLC_INIT_SKIP_PLAYWRIGHT_INSTALL:-0}" = "1" ]; then
    echo "Skipped Playwright npm install (ADLC_INIT_SKIP_PLAYWRIGHT_INSTALL=1). Run manually:"
    echo "  npm install --save-dev @playwright/test"
    echo "  npx playwright install --with-deps chromium"
    echo "  and add \"test:e2e\": \"playwright test\" to package.json scripts."
  elif [ ! -f package.json ]; then
    echo "Skipped Playwright npm install — no package.json at repo root."
  else
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
        echo "WARNING: 'npm install --save-dev @playwright/test' failed. Re-run manually."
      fi
    fi

    if [ "${ADLC_INIT_SKIP_PLAYWRIGHT_BROWSERS:-0}" = "1" ]; then
      echo "Skipped 'npx playwright install --with-deps chromium'."
    else
      echo "Installing Chromium for Playwright..."
      if npx --yes playwright install --with-deps chromium; then
        echo "  Done."
      else
        echo "WARNING: 'npx playwright install --with-deps chromium' failed. Re-run manually before the first /architect on a UI REQ."
      fi
    fi

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

### Step 10.5: Register the project with the sprint dashboard

Tell the shared dashboard about this project so its REQs show up alongside everything else. The launcher script is idempotent, no-ops if the dashboard is already running, and never fails the parent skill on error.

```bash
. "$HOME/.adlc/runtime/init-state.sh"

# Resolve the launcher. Prefer the locally-copied .adlc/ path so this works
# inside git worktrees; fall back to the toolkit location.
LAUNCHER=""
if [ -x .adlc/tools/sprint-dashboard/launch.sh ]; then
  LAUNCHER=".adlc/tools/sprint-dashboard/launch.sh"
elif [ -x "$TOOLKIT_HOME/tools/sprint-dashboard/launch.sh" ]; then
  LAUNCHER="$TOOLKIT_HOME/tools/sprint-dashboard/launch.sh"
fi

if [ -n "$LAUNCHER" ]; then
  ADLC_ROOT="$(pwd)" ADLC_DASHBOARD_OPEN=1 sh "$LAUNCHER" || true
else
  echo "[init] sprint-dashboard launcher not found — skipping dashboard registration."
fi
```

After this step, the user should see `<project-name>` listed at `http://127.0.0.1:5174` (default port; override with `ADLC_DASHBOARD_PORT`).

### Step 11: Summary

1. Display the created directory structure. If Step 1.5 ran `git init`, call that out and remind the user to wire in a remote (`git remote add origin <url>`).
2. Confirm `STACK` and `TOOLKIT_HOME` (echo from `~/.adlc/runtime/init-state.sh`) so the user knows which toolkit was used.
3. Confirm project-local skill symlinks were created — explain that `/architect`, `/proceed`, `/spec`, etc., now resolve to the matching toolkit regardless of `~/.claude/skills`.
4. **For SFDC projects:** confirm rules and catalog files are in place: `.adlc/context/sf-skills-catalog.md`, `.adlc/context/salesforce-rules.md`, `.adlc/context/sf-clouds.md`, `.adlc/context/industry-domains.md`. Echo back the user's selections: `salesforce.clouds: [...]`, `industry_domains: [...]`, `salesforce.india_context: <true|false>`. Confirm the source-only audit gate is installed at `.adlc/tools/sf-code-audit/` and `.adlc/partials/run-source-audit.sh`, and remind the user the `/reflect` skill will block on `CRITICAL`/`HIGH` findings (configurable in `.adlc/config.yml` → `audit:`).
5. **For MuleSoft projects:** confirm `.adlc/context/mule-skills-catalog.md`, `.adlc/context/mulesoft-rules.md`, `.adlc/partials/mule-quality-checklist.md`. Confirm the official MuleSoft skill pack is installed under `.claude/skills/mule-development`. Remind the user to populate `.env` from `.env.example` with the four connected-app credentials. Remind them to manually populate the remaining `.adlc/config.yml` MuleSoft fields: `anypoint_org_id`, `anypoint_environment`, `anypoint_region`, `api_layer`, and (when `governance.api_manager_enabled: true`) `governance.required_policies` + `governance.governance_ruleset`.
6. Explain the ADLC workflow: `/spec` → `/validate` → `/architect` → `/validate` → implement → `/reflect` → `/review` → `/wrapup` (or use `/proceed` to run the full pipeline automatically).
7. If cross-repo config was scaffolded, remind the user that `/proceed` will create worktrees in every touched sibling and open one PR per repo.
8. If the Playwright harness was scaffolded, confirm `npm run test:e2e` is wired (Step 10 installs `@playwright/test`, downloads chromium, and adds the script). If either install reported a WARNING, surface that line.
9. Suggest adding ADLC skill references to the project's `CLAUDE.md` if one exists.
